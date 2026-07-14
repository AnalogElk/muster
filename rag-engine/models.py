"""Pydantic models for the Analog Elk v3 RAG engine.

All models are serialisation-safe (no circular references) and use strict
typing so that FastAPI can auto-generate accurate OpenAPI docs.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Knowledge-base document
# ---------------------------------------------------------------------------


class Document(BaseModel):
    """A document stored in the knowledge base."""

    id: int = Field(..., description="Primary key from PostgreSQL")
    title: str = Field(..., description="Document title")
    content: str = Field(..., description="Full text content")
    source_url: Optional[str] = Field(default=None, description="Canonical source URL")
    ingested_at: datetime = Field(..., description="UTC timestamp of initial ingestion")


# ---------------------------------------------------------------------------
# RAG query / response
# ---------------------------------------------------------------------------


class RAGQuery(BaseModel):
    """Parameters for a hybrid knowledge-base search."""

    query: str = Field(..., min_length=1, description="Natural-language search query")
    session_id: Optional[str] = Field(
        default=None,
        description="Optional session identifier for per-session caching",
    )
    max_chars: int = Field(
        default=8000,
        ge=100,
        le=50_000,
        description="Maximum characters of context to return",
    )
    max_docs: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of documents to retrieve",
    )
    domain: Optional[str] = Field(
        default=None,
        description=(
            "Restrict results to a single knowledge domain "
            "(e.g. 'schema-org', 'directus', 'nextjs', 'netlify', 'react', "
            "'a-list-apart', 'google-seo', 'custom'). Omit for cross-domain search."
        ),
    )


class SourceReference(BaseModel):
    """Lightweight reference to a document used in a RAG response."""

    title: str
    source_url: Optional[str] = None
    relevance: float = Field(default=0.0, ge=0.0, le=1.0)


class RAGResponse(BaseModel):
    """Result of a hybrid knowledge-base search."""

    context: str = Field(description="Concatenated document excerpts ready for prompt injection")
    sources: List[SourceReference] = Field(default_factory=list)
    cached: bool = Field(default=False, description="True when the result was served from Redis cache")
    found: int = Field(default=0, description="Number of documents matched before context truncation")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthStatus(BaseModel):
    """Aggregated health state of all engine dependencies."""

    status: str = Field(description="'ok' when all dependencies are reachable, 'degraded' otherwise")
    postgres: bool = Field(description="PostgreSQL reachability")
    qdrant: bool = Field(description="Qdrant reachability")
    redis: bool = Field(description="Redis reachability")
    doc_count: int = Field(default=0, description="Total documents in PostgreSQL")
    vector_count: int = Field(default=0, description="Total vectors indexed in Qdrant")
    reason: Optional[str] = Field(
        default=None,
        description=(
            "Why the engine is degraded, when applicable: "
            "'vectors_missing' (docs exist but no vectors — semantic search is "
            "down, falling back to full-text), 'vectors_stale' (vectors lag docs "
            "by >10% — reindex recommended), or a dependency name. None when healthy."
        ),
    )


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


class IngestRequest(BaseModel):
    """Payload for ingesting a single document into the knowledge base."""

    title: str = Field(..., min_length=1, description="Document title")
    content: str = Field(..., min_length=1, max_length=500_000, description="Full text to index (max 500KB)")
    source_url: Optional[str] = Field(default=None, description="Canonical URL of the source page")
    source_type: str = Field(
        default="custom",
        description="Provenance tag for the row (e.g. 'url', 'file', 'manual').",
    )
    domain: Optional[str] = Field(
        default=None,
        description=(
            "Knowledge domain key matching manifest.yaml "
            "(e.g. 'schema-org', 'directus', 'nextjs', 'custom'). "
            "Used by /query --domain filtering."
        ),
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Arbitrary additional metadata stored in Qdrant payload"
    )


class IngestResponse(BaseModel):
    """Result returned after a successful ingestion."""

    doc_id: int = Field(description="Newly created PostgreSQL row ID")
    indexed: bool = Field(description="True when the vector was also stored in Qdrant")
    title: str


class BatchIngestRequest(BaseModel):
    """Payload for bulk-ingesting multiple documents."""

    documents: List[IngestRequest] = Field(..., min_length=1, max_length=100)


class BatchIngestResponse(BaseModel):
    """Summary of a bulk ingestion operation."""

    total: int = Field(description="Number of documents submitted")
    ingested: int = Field(description="Number of PostgreSQL rows created")
    indexed: int = Field(description="Number of Qdrant vectors created")
    errors: List[str] = Field(default_factory=list, description="Per-document error messages (if any)")


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class StatsResponse(BaseModel):
    """Aggregate statistics for the knowledge base."""

    doc_count: int
    vector_count: int
    domains: List[str] = Field(default_factory=list, description="Distinct source_type values")
    last_indexed: Optional[datetime] = Field(
        default=None, description="UTC timestamp of the most-recently ingested document"
    )


# ---------------------------------------------------------------------------
# Delete / reconcile
# ---------------------------------------------------------------------------


class DeleteRequest(BaseModel):
    """Remove documents from the knowledge base.

    Provide ``source_urls`` (exact matches) and/or ``domain`` (all documents in
    that knowledge domain). At least one must be given so a bare ``{}`` cannot
    accidentally purge the whole corpus. This is how a KB page that was
    unpublished or deleted upstream is forgotten by the engine — without it the
    append-only store keeps serving stale/gated text forever.
    """

    source_urls: Optional[List[str]] = Field(
        default=None,
        description="Exact source_url values to delete (each may match multiple rows).",
    )
    domain: Optional[str] = Field(
        default=None,
        description="Delete every document in this knowledge domain (purge for reconcile).",
    )

    @model_validator(mode="after")
    def _at_least_one_selector(self) -> "DeleteRequest":
        if not self.source_urls and not self.domain:
            raise ValueError("Provide source_urls and/or domain — refusing to delete everything.")
        return self


class DeleteResponse(BaseModel):
    """Result of a delete/reconcile operation."""

    deleted: int = Field(description="Number of PostgreSQL rows removed")
    vectors_deleted: int = Field(description="Number of Qdrant vectors removed")
    vectors_pending: int = Field(
        default=0,
        description=(
            "Vectors that could NOT be confirmed deleted (Qdrant down or FTS-only "
            "mode). The rows are gone and /query drops orphaned vectors, so content "
            "is already unqueryable, but a reconcile should retry to reclaim disk. "
            ">0 means the operation was not fully clean."
        ),
    )
