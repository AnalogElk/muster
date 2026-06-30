"""RAG (Retrieval-Augmented Generation) service for Analog Elk v3.

Hybrid search strategy
----------------------
1. **Semantic search** — Qdrant finds conceptually related documents.
2. **Full-text search** — PostgreSQL ``ts_rank`` finds keyword matches.
3. Results are merged, deduplicated by URL/title, and ranked with a
   configurable weighted score.
4. The ranked context is cached in Redis for 1 hour to avoid repeat embedding
   calls on identical queries.

Typical usage::

    svc = RAGService()
    await svc.initialize()
    result = await svc.get_context("Schema.org Article markup")
    print(result["context"])   # inject into an LLM system prompt
    await svc.close()
"""

import asyncio
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

import asyncpg
import redis.asyncio as aioredis

# Module-level lock guards the singleton against concurrent first-call races.
_SINGLETON_LOCK = asyncio.Lock()

from .config import get_settings
from .embeddings import EmbeddingService, get_embedding_service

logger = logging.getLogger(__name__)


class RAGService:
    """Hybrid semantic + full-text retrieval service.

    All public methods are async-safe and can be awaited concurrently.
    """

    # Redis key namespace
    _CACHE_PREFIX = "rag_context:"
    _CACHE_TTL = 3_600  # seconds — 1 hour

    def __init__(
        self,
        db_pool: Optional[asyncpg.Pool] = None,
        redis_client: Optional[aioredis.Redis] = None,
        embedding_service: Optional[EmbeddingService] = None,
    ) -> None:
        self._cfg = get_settings()
        self._db_pool = db_pool
        self._redis = redis_client
        self._embed = embedding_service
        self._initialized = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Connect to PostgreSQL, Redis, and Qdrant if not already connected."""
        if self._initialized:
            return

        if self._redis is None:
            self._redis = await aioredis.from_url(
                self._cfg.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info("RAGService connected to Redis")

        if self._db_pool is None:
            self._db_pool = await asyncpg.create_pool(
                self._cfg.database_url,
                min_size=self._cfg.postgres_pool_min,
                max_size=self._cfg.postgres_pool_max,
            )
            logger.info("RAGService connected to PostgreSQL")

        if self._embed is None:
            try:
                self._embed = await get_embedding_service()
                stats = await self._embed.get_collection_stats()
                logger.info(
                    "RAGService connected to Qdrant (%d vectors)",
                    stats.get("points_count", 0),
                )
            except Exception as exc:
                logger.warning("Qdrant unavailable — FTS-only mode: %s", exc)
                self._embed = None

        self._initialized = True

    async def close(self) -> None:
        """Gracefully close all connections."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None
        if self._db_pool:
            await self._db_pool.close()
            self._db_pool = None
        if self._embed:
            await self._embed.close()
            self._embed = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_context(
        self,
        query: str,
        session_id: Optional[str] = None,
        max_chars: Optional[int] = None,
        max_docs: Optional[int] = None,
        domain: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieve and format relevant context for *query*.

        Args:
            query:      Natural-language search string.
            session_id: Optional session tag used for cache-key scoping.
            max_chars:  Override for :attr:`Settings.rag_max_context_chars`.
            max_docs:   Override for :attr:`Settings.rag_max_documents`.
            domain:     Optional knowledge domain filter (e.g. 'schema-org').

        Returns:
            Dict with keys ``context`` (str), ``sources`` (list),
            ``cached`` (bool), and ``found`` (int).
        """
        await self.initialize()

        effective_max_chars = max_chars or self._cfg.rag_max_context_chars
        effective_max_docs = max_docs or self._cfg.rag_max_documents

        # --- Cache check (domain participates in cache key) ---
        cache_key = self._cache_key(query, session_id, domain)
        if self._redis:
            cached_raw = await self._redis.get(cache_key)
            if cached_raw:
                logger.debug("RAG cache hit: %.50s…", query)
                result = json.loads(cached_raw)
                result["cached"] = True
                return result

        # --- Hybrid retrieval ---
        documents = await self._hybrid_search(query, effective_max_docs, domain=domain)
        if not documents:
            return {"context": "", "sources": [], "cached": False, "found": 0}

        # --- Build context string ---
        context_parts: List[str] = []
        sources: List[Dict[str, Any]] = []
        total_chars = 0

        for doc in documents:
            content = doc["content"]
            remaining = effective_max_chars - total_chars
            if remaining <= 0:
                break
            if len(content) > remaining:
                if remaining < 200:
                    break
                content = content[:remaining] + "…"

            context_parts.append(f"### {doc['title']}\n{content}")
            sources.append(
                {
                    "title": doc["title"],
                    "source_url": doc.get("source_url"),
                    "relevance": round(doc.get("relevance", 0.0), 4),
                }
            )
            total_chars += len(content)

        result: Dict[str, Any] = {
            "context": "\n\n".join(context_parts),
            "sources": sources,
            "cached": False,
            "found": len(documents),
        }

        # --- Populate cache ---
        if self._redis:
            try:
                await self._redis.setex(
                    cache_key, self._CACHE_TTL, json.dumps(result)
                )
            except Exception as exc:
                logger.warning("Failed to write RAG cache: %s", exc)

        logger.info(
            "RAG retrieved %d docs (%d chars) for: %.50s…",
            len(sources),
            total_chars,
            query,
        )
        return result

    # ------------------------------------------------------------------
    # Internal search helpers
    # ------------------------------------------------------------------

    async def _hybrid_search(
        self, query: str, limit: int, domain: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Combine semantic and full-text search results.

        Deduplicates by ``source_url`` (falling back to ``title``), computes
        a weighted combined score, and returns the top *limit* documents sorted
        by descending relevance.

        When ``domain`` is provided, results are restricted to that knowledge
        domain via a Postgres ``WHERE domain = $X`` filter and an equivalent
        Qdrant payload filter.
        """
        merged: Dict[str, Dict[str, Any]] = {}
        sem_weight = self._cfg.rag_semantic_weight
        fts_weight = self._cfg.rag_fts_weight

        # 1 — Semantic search (Qdrant)
        if self._embed:
            try:
                sem_docs = await self._embed.semantic_search(
                    query=query,
                    limit=limit * 2,
                    score_threshold=0.4,
                    domain=domain,
                )
                for doc in sem_docs:
                    key = doc.get("source_url") or doc.get("title") or ""
                    if key and key not in merged:
                        merged[key] = {
                            "title": doc["title"],
                            "content": doc["content"],
                            "source_url": doc.get("source_url"),
                            "semantic_score": doc["score"],
                            "fts_score": 0.0,
                        }
                logger.debug("Semantic search: %d docs", len(sem_docs))
            except Exception as exc:
                logger.warning("Semantic search error (FTS only): %s", exc)

        # 2 — Full-text search (PostgreSQL)
        fts_docs = await self._fts_search(query, limit * 2, domain=domain)
        for doc in fts_docs:
            key = doc.get("source_url") or doc.get("title") or ""
            if not key:
                continue
            if key in merged:
                merged[key]["fts_score"] = doc["relevance"]
                # Use full content from PostgreSQL (Qdrant stores a snippet).
                merged[key]["content"] = doc["content"]
            else:
                merged[key] = {
                    "title": doc["title"],
                    "content": doc["content"],
                    "source_url": doc.get("source_url"),
                    "semantic_score": 0.0,
                    "fts_score": doc["relevance"],
                }

        # 3 — Compute combined score
        for doc in merged.values():
            sem = min(float(doc.get("semantic_score", 0.0)), 1.0)
            fts = min(float(doc.get("fts_score", 0.0)), 1.0)
            doc["relevance"] = sem_weight * sem + fts_weight * fts

        ranked = sorted(
            merged.values(), key=lambda d: d["relevance"], reverse=True
        )[:limit]

        # Log which search strategies contributed results
        has_sem = any(d.get("semantic_score", 0) > 0 for d in ranked)
        has_fts = any(d.get("fts_score", 0) > 0 for d in ranked)
        strategy = "+".join(
            s for s, flag in [("semantic", has_sem), ("fts", has_fts)] if flag
        ) or "none"
        logger.info(
            "Hybrid search [%s]: %d results for '%.50s…'",
            strategy,
            len(ranked),
            query,
        )
        return ranked

    async def _fts_search(
        self, query: str, limit: int, domain: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Full-text search using PostgreSQL ``plainto_tsquery``.

        Falls back to a simple ``ILIKE`` search if the FTS query returns no
        results (handles very short or stop-word-only queries).

        When ``domain`` is provided, restricts results to that knowledge domain
        via the indexed ``documents.domain`` column.
        """
        if self._db_pool is None:
            logger.warning("FTS search skipped — database pool not initialised")
            return []

        async with self._db_pool.acquire() as conn:
            if domain:
                rows = await conn.fetch(
                    """
                    SELECT
                        id,
                        title,
                        content,
                        source_url,
                        ts_rank_cd(
                            to_tsvector('english', title || ' ' || content),
                            plainto_tsquery('english', $1),
                            32
                        ) AS relevance
                    FROM documents
                    WHERE
                        domain = $3
                        AND to_tsvector('english', title || ' ' || content)
                            @@ plainto_tsquery('english', $1)
                    ORDER BY relevance DESC
                    LIMIT $2
                    """,
                    query,
                    limit,
                    domain,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT
                        id,
                        title,
                        content,
                        source_url,
                        ts_rank_cd(
                            to_tsvector('english', title || ' ' || content),
                            plainto_tsquery('english', $1),
                            32
                        ) AS relevance
                    FROM documents
                    WHERE
                        to_tsvector('english', title || ' ' || content)
                        @@ plainto_tsquery('english', $1)
                    ORDER BY relevance DESC
                    LIMIT $2
                    """,
                    query,
                    limit,
                )

            if not rows:
                # Fallback: ILIKE on the first keyword
                first_word = query.split()[0] if query.split() else query
                escaped = first_word.lower().replace("%", "\\%").replace("_", "\\_")
                if domain:
                    rows = await conn.fetch(
                        """
                        SELECT id, title, content, source_url, 0.5::float AS relevance
                        FROM documents
                        WHERE domain = $3
                          AND LOWER(title || ' ' || content) LIKE $1
                        ORDER BY ingested_at DESC
                        LIMIT $2
                        """,
                        f"%{escaped}%",
                        limit,
                        domain,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT id, title, content, source_url, 0.5::float AS relevance
                        FROM documents
                        WHERE LOWER(title || ' ' || content) LIKE $1
                        ORDER BY ingested_at DESC
                        LIMIT $2
                        """,
                        f"%{escaped}%",
                        limit,
                    )

        return [
            {
                "id": row["id"],
                "title": row["title"],
                "content": row["content"],
                "source_url": row["source_url"],
                "relevance": float(row["relevance"]) if row["relevance"] is not None else 0.0,
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _cache_key(
        self, query: str, session_id: Optional[str], domain: Optional[str] = None
    ) -> str:
        """Derive a short, deterministic Redis key.

        Includes *domain* so cross-domain and domain-scoped queries don't share
        cache entries.
        """
        raw = f"{query}:{session_id or 'global'}:{domain or '_all'}"
        digest = hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()[:12]
        return f"{self._CACHE_PREFIX}{digest}"

    def format_context_prompt(
        self,
        context: str,
        sources: List[Dict[str, Any]],
    ) -> str:
        """Wrap retrieved context in a prompt-ready block.

        Args:
            context: The concatenated document excerpts.
            sources: List of source references (title + source_url).

        Returns:
            A Markdown-formatted string suitable for injection into a system
            prompt, or an empty string when *context* is empty.
        """
        if not context:
            return ""

        source_lines = "\n".join(
            f"- {s['title']}" + (f" ({s['source_url']})" if s.get("source_url") else "")
            for s in sources[:5]
        )
        return (
            "\n## Project Context (Knowledge Base)\n\n"
            "The following content was retrieved from the project knowledge base.\n"
            "Use it to align your response with project conventions and architecture.\n\n"
            f"{context}\n\n"
            f"**Sources**:\n{source_lines}\n\n---\n"
        )


# ---------------------------------------------------------------------------
# Singleton helper
# ---------------------------------------------------------------------------

_instance: Optional[RAGService] = None


async def get_rag_service() -> RAGService:
    """Return the application-wide :class:`RAGService` singleton.

    Guarded by an asyncio.Lock so concurrent first-callers don't each build a
    separate service (which would open duplicate PG pools + Qdrant clients).
    """
    global _instance
    if _instance is not None:
        return _instance
    async with _SINGLETON_LOCK:
        # Re-check under the lock — another coroutine may have initialized.
        if _instance is None:
            svc = RAGService()
            await svc.initialize()
            _instance = svc
    return _instance
