"""Embedding service for Analog Elk v3.

Generates 384-dimensional vectors with a LOCAL embedding model
(``BAAI/bge-small-en-v1.5`` via fastembed, ONNX on CPU) and stores them in
Qdrant for semantic similarity search.

There is no external embedding API: no key, no quota, no rate limits. The model
runs in-process. This replaced the Google ``gemini-embedding-001`` layer on
2026-06-25 (free-tier 429s + headless-auth fragility made an external API the
wrong trade for a small, mostly-static corpus).

If the model cannot load (e.g. first-run download blocked), embedding calls
return ``None`` and the RAG service falls back to PostgreSQL full-text search.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

# Module-level lock guards the singleton against concurrent first-call races.
_SINGLETON_LOCK = asyncio.Lock()

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from .config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMS = 384
COLLECTION_NAME = "documents"

# Max characters fed to the model per call. bge-small handles ~512 tokens; the
# ingest path chunks long docs, and this is a guard so a huge page cannot blow
# memory. Embedding is symmetric (no bge query/passage instruction prefix) so the
# index and query paths stay identical through generate_embedding().
_MAX_EMBED_CHARS = 25_000

# Process-wide singleton for the loaded model (loading is expensive; the model is
# thread-safe for inference). Lazily constructed on first embed, off the event loop.
_MODEL: Optional[Any] = None
_MODEL_LOCK = asyncio.Lock()


async def _get_model() -> Optional[Any]:
    """Return the shared fastembed model, loading it once on first use."""
    global _MODEL
    if _MODEL is None:
        async with _MODEL_LOCK:
            if _MODEL is None:
                # Lazy import so merely importing this module does not require
                # fastembed (only the rag-api container actually embeds).
                from fastembed import TextEmbedding
                _MODEL = await asyncio.to_thread(TextEmbedding, EMBEDDING_MODEL)
                logger.info("Loaded local embedding model %s (%d dims)",
                            EMBEDDING_MODEL, EMBEDDING_DIMS)
    return _MODEL


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class EmbeddingService:
    """Manage document embeddings in Qdrant.

    Typical usage::

        svc = EmbeddingService()
        await svc.initialize()
        await svc.index_document(doc_id=1, title="Foo", content="Bar")
        results = await svc.semantic_search("my query")
        await svc.close()
    """

    def __init__(self) -> None:
        self._cfg = get_settings()
        self._qdrant: Optional[AsyncQdrantClient] = None
        self._initialized: bool = False
        self.dimension: int = EMBEDDING_DIMS

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Connect to Qdrant and ensure the ``documents`` collection exists."""
        if self._initialized:
            return

        qdrant_url = f"http://{self._cfg.qdrant_host}:{self._cfg.qdrant_port}"
        try:
            self._qdrant = AsyncQdrantClient(
                url=qdrant_url,
                api_key=self._cfg.qdrant_api_key or None,
            )

            collections = await self._qdrant.get_collections()
            existing = {c.name for c in collections.collections}

            if COLLECTION_NAME in existing:
                info = await self._qdrant.get_collection(COLLECTION_NAME)
                current_size = info.config.params.vectors.size
                if current_size != self.dimension:
                    logger.warning(
                        "Collection '%s' has %d dims, expected %d — recreating",
                        COLLECTION_NAME, current_size, self.dimension,
                    )
                    await self._qdrant.delete_collection(COLLECTION_NAME)
                    existing.discard(COLLECTION_NAME)

            if COLLECTION_NAME not in existing:
                await self._qdrant.create_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=self.dimension,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info("Created Qdrant collection '%s' (%d dims)", COLLECTION_NAME, self.dimension)

            self._initialized = True
            logger.info("EmbeddingService initialised (Qdrant @ %s)", qdrant_url)

        except Exception as exc:
            # Degraded mode: FTS-only fallback still works.
            logger.error("Qdrant unavailable — semantic search disabled: %s", exc)
            self._initialized = False

    async def close(self) -> None:
        """Release the Qdrant connection."""
        if self._qdrant:
            await self._qdrant.close()
            self._qdrant = None
            self._initialized = False

    # ------------------------------------------------------------------
    # Embedding generation
    # ------------------------------------------------------------------

    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate a 384-dim embedding vector for *text* with the local model.

        Args:
            text: Arbitrary text to embed. Truncated to
                  :data:`_MAX_EMBED_CHARS` characters first.

        Returns:
            A list of 384 floats, or ``None`` if the model is unavailable.
        """
        if not text or not text.strip():
            return None
        if len(text) > _MAX_EMBED_CHARS:
            text = text[:_MAX_EMBED_CHARS]

        try:
            model = await _get_model()
            if model is None:
                return None
            # fastembed returns a generator of numpy arrays; run it off the loop.
            vectors = await asyncio.to_thread(lambda: list(model.embed([text])))
            if not vectors:
                return None
            return vectors[0].tolist()
        except Exception as exc:
            logger.error("Local embedding failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    async def index_document(
        self,
        doc_id: int,
        title: str,
        content: str,
        source_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        domain: Optional[str] = None,
    ) -> bool:
        """Embed and upsert a single document into Qdrant.

        Args:
            doc_id:     PostgreSQL primary key (used as the Qdrant point ID).
            title:      Document title.
            content:    Full document text.
            source_url: Optional canonical URL stored in the payload.
            metadata:   Optional extra key/value pairs stored in the payload.
            domain:     Optional knowledge-domain tag stored in the payload so
                        semantic_search can filter by it.

        Returns:
            ``True`` on success, ``False`` otherwise.
        """
        if not self._initialized:
            await self.initialize()
        if not self._initialized:
            return False

        embedding = await self.generate_embedding(f"{title}\n\n{content}")
        if not embedding:
            return False

        try:
            payload: Dict[str, Any] = {
                "doc_id": doc_id,
                "title": title,
                # Store a truncated snippet — full content lives in PostgreSQL.
                "content": content[:2000],
                "source_url": source_url,
            }
            if domain:
                payload["domain"] = domain
            if metadata:
                payload.update(metadata)

            await self._qdrant.upsert(
                collection_name=COLLECTION_NAME,
                points=[PointStruct(id=doc_id, vector=embedding, payload=payload)],
            )
            logger.debug("Indexed doc %d in Qdrant", doc_id)
            return True

        except Exception as exc:
            logger.error("Failed to index doc %d: %s", doc_id, exc)
            return False

    async def bulk_index(
        self,
        documents: List[Dict[str, Any]],
        batch_size: int = 50,
    ) -> int:
        """Index many documents with rate-limited batching.

        Each *document* dict must contain ``doc_id``, ``title``, and
        ``content`` keys.  ``source_url`` and ``metadata`` are optional.

        Args:
            documents:  List of document dicts.
            batch_size: Documents to upsert per Qdrant call.

        Returns:
            Count of successfully indexed documents.
        """
        if not self._initialized:
            await self.initialize()
        if not self._initialized:
            return 0

        indexed = 0
        semaphore = asyncio.Semaphore(5)

        async def _embed_doc(doc: Dict[str, Any]) -> Optional[PointStruct]:
            async with semaphore:
                embedding = await self.generate_embedding(
                    f"{doc['title']}\n\n{doc['content']}"
                )
                # Honour Google's ~10 req/s free-tier rate limit.
                await asyncio.sleep(0.1)
                if embedding:
                    payload: Dict[str, Any] = {
                        "doc_id": doc["doc_id"],
                        "title": doc["title"],
                        "content": doc["content"][:2000],
                        "source_url": doc.get("source_url"),
                    }
                    if doc.get("domain"):
                        payload["domain"] = doc["domain"]
                    if doc.get("metadata"):
                        payload.update(doc["metadata"])
                    return PointStruct(id=doc["doc_id"], vector=embedding, payload=payload)
                return None

        for batch_start in range(0, len(documents), batch_size):
            batch = documents[batch_start : batch_start + batch_size]
            results = await asyncio.gather(*[_embed_doc(doc) for doc in batch])
            points: List[PointStruct] = [p for p in results if p is not None]

            if points:
                try:
                    await self._qdrant.upsert(
                        collection_name=COLLECTION_NAME, points=points
                    )
                    indexed += len(points)
                    logger.info(
                        "Bulk-indexed %d/%d documents", indexed, len(documents)
                    )
                except Exception as exc:
                    logger.error("Batch upsert failed: %s", exc)

        return indexed

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def semantic_search(
        self,
        query: str,
        limit: int = 5,
        score_threshold: float = 0.5,
        domain: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Find the *limit* most similar documents for *query*.

        Args:
            query:           Natural-language search string.
            limit:           Maximum results to return.
            score_threshold: Minimum cosine similarity (0–1) to include.
            domain:          Optional knowledge-domain filter applied as a
                             Qdrant payload condition.

        Returns:
            List of dicts with ``doc_id``, ``title``, ``content``,
            ``source_url``, and ``score`` keys.
        """
        if not self._initialized:
            await self.initialize()
        if not self._initialized:
            return []

        query_vec = await self.generate_embedding(query)
        if not query_vec:
            return []

        qdrant_filter: Optional[Filter] = None
        if domain:
            qdrant_filter = Filter(
                must=[
                    FieldCondition(key="domain", match=MatchValue(value=domain))
                ]
            )

        try:
            result = await self._qdrant.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vec,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
                query_filter=qdrant_filter,
            )
            docs = [
                {
                    "doc_id": p.payload.get("doc_id"),
                    "title": p.payload.get("title", ""),
                    "content": p.payload.get("content", ""),
                    "source_url": p.payload.get("source_url"),
                    "score": p.score,
                }
                for p in result.points
            ]
            logger.info(
                "Semantic search returned %d docs for: %.50s…", len(docs), query
            )
            return docs

        except Exception as exc:
            logger.error("Semantic search failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    async def get_collection_stats(self) -> Dict[str, Any]:
        """Return basic statistics for the Qdrant ``documents`` collection."""
        if not self._initialized:
            await self.initialize()
        if not self._initialized:
            return {"error": "Qdrant not initialised"}

        try:
            info = await self._qdrant.get_collection(COLLECTION_NAME)
            return {
                "points_count": info.points_count,
                "indexed_vectors_count": getattr(
                    info, "indexed_vectors_count", info.points_count
                ),
                "status": (
                    info.status.value
                    if hasattr(info.status, "value")
                    else str(info.status)
                ),
            }
        except Exception as exc:
            return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Singleton helper
# ---------------------------------------------------------------------------

_instance: Optional[EmbeddingService] = None


async def get_embedding_service() -> EmbeddingService:
    """Return the application-wide :class:`EmbeddingService` singleton.

    Guarded by an asyncio.Lock so concurrent first-callers don't each construct
    a separate service (which would create duplicate Qdrant clients).
    """
    global _instance
    if _instance is not None:
        return _instance
    async with _SINGLETON_LOCK:
        # Re-check under the lock — another coroutine may have initialized.
        if _instance is None:
            svc = EmbeddingService()
            await svc.initialize()
            _instance = svc
    return _instance
