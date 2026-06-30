"""FastAPI RAG server for Analog Elk v3.

Exposes the hybrid knowledge-base search and document ingestion pipeline on
port 9100.

Endpoints
---------
GET  /health         — Dependency health check
POST /query          — Hybrid semantic + FTS search
POST /ingest         — Ingest a single document
POST /ingest/batch   — Bulk ingest
GET  /stats          — Knowledge-base statistics

Run locally::

    uvicorn engine.rag_server:app --host 0.0.0.0 --port 9100 --reload

Or via Docker Compose::

    docker compose up rag-api
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import asyncpg
import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .embeddings import EmbeddingService, get_embedding_service
from .models import (
    BatchIngestRequest,
    BatchIngestResponse,
    HealthStatus,
    IngestRequest,
    IngestResponse,
    RAGQuery,
    RAGResponse,
    SourceReference,
    StatsResponse,
)
from .rag import RAGService

logger = logging.getLogger(__name__)
cfg = get_settings()

# ---------------------------------------------------------------------------
# Application state (shared across request handlers)
# ---------------------------------------------------------------------------

_db_pool: Optional[asyncpg.Pool] = None
_redis: Optional[aioredis.Redis] = None
_embed: Optional[EmbeddingService] = None
_rag: Optional[RAGService] = None

# ---------------------------------------------------------------------------
# Schema used to create the documents table on first boot
# ---------------------------------------------------------------------------

# NOTE: This must stay column-compatible with migrations/001_initial_schema.sql.
# The INSERTs in /ingest, the FTS filter in rag.py, and /stats all reference the
# `domain` column — omitting it here lets a fresh-volume boot create a
# domain-less table before migrations run, after which every ingest fails with
# `column "domain" does not exist`. Keep the two definitions in lock-step.
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    id          SERIAL PRIMARY KEY,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    source_url  TEXT,
    source_type TEXT NOT NULL DEFAULT 'custom',
    domain      TEXT,
    category    TEXT,
    tags        TEXT[],
    metadata    JSONB,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_fts
    ON documents
    USING GIN (to_tsvector('english', title || ' ' || content));

CREATE INDEX IF NOT EXISTS idx_documents_source_type
    ON documents (source_type);

CREATE INDEX IF NOT EXISTS idx_documents_domain
    ON documents (domain);

CREATE INDEX IF NOT EXISTS idx_documents_ingested_at
    ON documents (ingested_at DESC);
"""

# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise shared connections on startup; tear them down on shutdown."""
    global _db_pool, _redis, _embed, _rag

    logger.info("Starting Analog Elk v3 RAG server…")

    # PostgreSQL
    _db_pool = await asyncpg.create_pool(
        cfg.database_url,
        min_size=cfg.postgres_pool_min,
        max_size=cfg.postgres_pool_max,
    )
    async with _db_pool.acquire() as conn:
        await conn.execute(_CREATE_TABLE_SQL)
    logger.info("PostgreSQL ready")

    # Redis
    _redis = await aioredis.from_url(
        cfg.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    await _redis.ping()
    logger.info("Redis ready")

    # Qdrant / embeddings
    try:
        _embed = await get_embedding_service()
        logger.info("Qdrant / embedding service ready")
    except Exception as exc:
        logger.warning("Qdrant unavailable — FTS-only mode: %s", exc)
        _embed = None

    # RAG service (re-uses the connections above)
    _rag = RAGService(
        db_pool=_db_pool,
        redis_client=_redis,
        embedding_service=_embed,
    )
    await _rag.initialize()
    logger.info("RAG service ready — server listening on port 9100")

    yield

    # Shutdown
    logger.info("Shutting down RAG server…")
    if _rag:
        await _rag.close()
    if _redis:
        await _redis.aclose()
    if _db_pool:
        await _db_pool.close()
    logger.info("RAG server stopped")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Analog Elk v3 — RAG API",
    description=(
        "Hybrid semantic + full-text retrieval service. "
        "Query the knowledge base or ingest new content."
    ),
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def limit_request_body(request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 2_097_152:  # 2MB
        from starlette.responses import JSONResponse
        return JSONResponse(
            status_code=413,
            content={"detail": "Request body too large (max 2MB)"}
        )
    return await call_next(request)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_rag() -> RAGService:
    if _rag is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG service not initialised",
        )
    return _rag


def _require_db() -> asyncpg.Pool:
    if _db_pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not initialised",
        )
    return _db_pool


async def _verify_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """Verify the X-API-Key header for write endpoints.

    When ``RAG_API_KEY`` is not configured, all requests are allowed (local dev).
    """
    import hmac

    required_key = cfg.rag_api_key
    if not required_key:
        return  # Auth disabled — local dev mode
    if not x_api_key or not hmac.compare_digest(x_api_key, required_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header",
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get(
    "/health",
    response_model=HealthStatus,
    summary="Dependency health check",
)
async def health() -> HealthStatus:
    """Return the reachability status of PostgreSQL, Qdrant, and Redis."""
    postgres_ok = False
    qdrant_ok = False
    redis_ok = False
    doc_count = 0
    vector_count = 0

    # PostgreSQL
    if _db_pool:
        try:
            async with _db_pool.acquire() as conn:
                row = await conn.fetchrow("SELECT COUNT(*) AS n FROM documents")
                doc_count = row["n"] if row else 0
            postgres_ok = True
        except Exception as exc:
            logger.warning("PostgreSQL health check failed: %s", exc)

    # Redis
    if _redis:
        try:
            await _redis.ping()
            redis_ok = True
        except Exception as exc:
            logger.warning("Redis health check failed: %s", exc)

    # Qdrant
    if _embed:
        try:
            stats = await _embed.get_collection_stats()
            vector_count = stats.get("points_count", 0)
            qdrant_ok = "error" not in stats
        except Exception as exc:
            logger.warning("Qdrant health check failed: %s", exc)

    # Derive a vector-health signal so the exact symptom that hid the Gemini-auth
    # outage (docs present, vectors absent) can never report "ok" again.
    reason: Optional[str] = None
    if postgres_ok and doc_count > 0:
        if vector_count == 0:
            reason = "vectors_missing"
        elif vector_count < doc_count * 0.9:
            reason = "vectors_stale"
    if reason:
        logger.warning(
            "Vector health degraded (%s): %d docs but %d vectors. "
            "Semantic search is impaired — run `elk-engine reindex`.",
            reason, doc_count, vector_count,
        )

    # Core dependencies must be reachable AND vectors must be healthy.
    all_ok = postgres_ok and redis_ok and reason is None
    return HealthStatus(
        status="ok" if all_ok else "degraded",
        postgres=postgres_ok,
        qdrant=qdrant_ok,
        redis=redis_ok,
        doc_count=doc_count,
        vector_count=vector_count,
        reason=reason,
    )


@app.post(
    "/query",
    response_model=RAGResponse,
    summary="Hybrid knowledge-base search",
)
async def query(req: RAGQuery) -> RAGResponse:
    """Retrieve relevant context using hybrid semantic + full-text search.

    The response ``context`` field is formatted for direct injection into an
    LLM system prompt.
    """
    rag = _require_rag()
    try:
        result = await rag.get_context(
            query=req.query,
            session_id=req.session_id,
            max_chars=req.max_chars,
            max_docs=req.max_docs,
            domain=req.domain,
        )
    except Exception as exc:
        logger.exception("RAG query failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search failed — check server logs for details",
        ) from exc

    return RAGResponse(
        context=result["context"],
        sources=[SourceReference(**s) for s in result.get("sources", [])],
        cached=result.get("cached", False),
        found=result.get("found", 0),
    )


@app.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a single document",
)
async def ingest(
    req: IngestRequest, _auth: None = Depends(_verify_api_key)
) -> IngestResponse:
    """Store a document in PostgreSQL and index its vector in Qdrant."""
    db = _require_db()

    import json as _json

    try:
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO documents (title, content, source_url, source_type, domain, metadata)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                req.title,
                req.content,
                req.source_url,
                req.source_type,
                req.domain,
                _json.dumps(req.metadata) if req.metadata else None,
            )
        doc_id: int = row["id"]
    except Exception as exc:
        logger.exception("Failed to insert document")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database insert failed — check server logs for details",
        ) from exc

    # Index in Qdrant (best-effort — failure is non-fatal)
    indexed = False
    if _embed:
        indexed = await _embed.index_document(
            doc_id=doc_id,
            title=req.title,
            content=req.content,
            source_url=req.source_url,
            metadata=req.metadata,
            domain=req.domain,
        )

    return IngestResponse(doc_id=doc_id, indexed=indexed, title=req.title)


@app.post(
    "/ingest/batch",
    response_model=BatchIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bulk-ingest multiple documents",
)
async def ingest_batch(
    req: BatchIngestRequest, _auth: None = Depends(_verify_api_key)
) -> BatchIngestResponse:
    """Store and index multiple documents in one call."""
    db = _require_db()

    import json as _json

    ingested = 0
    errors: list[str] = []
    embed_docs: list[Dict[str, Any]] = []

    async with db.acquire() as conn:
        for doc in req.documents:
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO documents (title, content, source_url, source_type, domain, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING id
                    """,
                    doc.title,
                    doc.content,
                    doc.source_url,
                    doc.source_type,
                    doc.domain,
                    _json.dumps(doc.metadata) if doc.metadata else None,
                )
                doc_id: int = row["id"]
                ingested += 1
                embed_docs.append(
                    {
                        "doc_id": doc_id,
                        "title": doc.title,
                        "content": doc.content,
                        "source_url": doc.source_url,
                        "metadata": doc.metadata,
                        "domain": doc.domain,
                    }
                )
            except Exception as exc:
                errors.append(f"{doc.title!r}: {exc}")

    # Bulk-index in Qdrant
    indexed = 0
    if _embed and embed_docs:
        indexed = await _embed.bulk_index(embed_docs)

    return BatchIngestResponse(
        total=len(req.documents),
        ingested=ingested,
        indexed=indexed,
        errors=errors,
    )


@app.get(
    "/stats",
    response_model=StatsResponse,
    summary="Knowledge-base statistics",
)
async def stats() -> StatsResponse:
    """Return aggregate statistics: document count, vector count, and domains."""
    db = _require_db()

    doc_count = 0
    domains: list[str] = []
    last_indexed: Optional[datetime] = None
    vector_count = 0

    try:
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) AS n, MAX(ingested_at) AS last FROM documents"
            )
            if row:
                doc_count = row["n"] or 0
                last_indexed = row["last"]

            # Prefer the dedicated `domain` column; fall back to source_type for
            # legacy rows ingested before --domain plumbing existed.
            domain_rows = await conn.fetch(
                """
                SELECT DISTINCT COALESCE(domain, source_type) AS domain
                FROM documents
                WHERE COALESCE(domain, source_type) IS NOT NULL
                ORDER BY domain
                """
            )
            domains = [r["domain"] for r in domain_rows]
    except Exception as exc:
        logger.warning("Stats DB query failed: %s", exc)

    if _embed:
        try:
            vstats = await _embed.get_collection_stats()
            vector_count = vstats.get("points_count", 0)
        except Exception:
            pass

    return StatsResponse(
        doc_count=doc_count,
        vector_count=vector_count,
        domains=domains,
        last_indexed=last_indexed,
    )


# ---------------------------------------------------------------------------
# Entry point for direct execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(
        level=cfg.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    uvicorn.run(
        "engine.rag_server:app",
        host="0.0.0.0",
        port=9100,
        reload=cfg.debug,
        log_level=cfg.log_level.lower(),
    )
