"""Configuration management for Analog Elk v3 engine.

Reads settings from environment variables and an optional .env file discovered
by walking up the directory tree up to 5 levels from the working directory.

Usage::

    from engine.config import get_settings

    cfg = get_settings()
    print(cfg.database_url)
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


def find_env_file() -> str:
    """Search up to 5 parent directories for a .env file.

    Returns:
        Absolute path string to the first .env found, or ``".env"`` as a
        no-op fallback (pydantic-settings will silently skip missing files).
    """
    search_dirs = [Path.cwd()] + list(Path.cwd().parents)[:5]
    for directory in search_dirs:
        candidate = directory / ".env"
        if candidate.exists():
            return str(candidate)
    return ".env"


class Settings(BaseSettings):
    """Centralised settings for the Analog Elk v3 RAG engine.

    Every field can be overridden via an environment variable that matches the
    field name (case-insensitive).  A ``.env`` file is also loaded
    automatically (see :func:`find_env_file`).
    """

    # -------------------------------------------------------------------------
    # General
    # -------------------------------------------------------------------------
    environment: str = Field(default="development", description="Deployment environment")
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Logging level")

    # -------------------------------------------------------------------------
    # PostgreSQL
    # -------------------------------------------------------------------------
    postgres_host: str = Field(default="localhost", description="PostgreSQL host")
    postgres_port: int = Field(default=5432, description="PostgreSQL port")
    postgres_db: str = Field(default="analog_elk", description="PostgreSQL database name")
    postgres_user: str = Field(default="analog_elk", description="PostgreSQL username")
    postgres_password: str = Field(..., description="PostgreSQL password (required, no default)")
    postgres_pool_min: int = Field(default=2, description="Minimum connection pool size")
    postgres_pool_max: int = Field(default=10, description="Maximum connection pool size")

    # -------------------------------------------------------------------------
    # Redis
    # -------------------------------------------------------------------------
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_db: int = Field(default=0, description="Redis database number")
    redis_password: Optional[str] = Field(
        default=None, description="Redis password (omit for no-auth Redis)"
    )

    # -------------------------------------------------------------------------
    # Qdrant
    # -------------------------------------------------------------------------
    qdrant_host: str = Field(default="localhost", description="Qdrant host")
    qdrant_port: int = Field(default=6333, description="Qdrant REST/gRPC port")
    qdrant_api_key: Optional[str] = Field(
        default=None, description="Qdrant API key (for Qdrant Cloud; omit for local)"
    )

    # -------------------------------------------------------------------------
    # Embeddings
    # -------------------------------------------------------------------------
    # Embeddings are generated locally (BAAI/bge-small-en-v1.5 via fastembed, in
    # engine/embeddings.py). No embedding API key is needed. The model name and
    # dimension live in embeddings.py (EMBEDDING_MODEL / EMBEDDING_DIMS).

    # -------------------------------------------------------------------------
    # RAG API security
    # -------------------------------------------------------------------------
    rag_api_key: Optional[str] = Field(
        default=None,
        description=(
            "API key for protecting write endpoints (/ingest, /ingest/batch). "
            "When set, requests must include 'X-API-Key' header. "
            "Leave empty to disable auth (local dev only)."
        ),
    )

    # -------------------------------------------------------------------------
    # RAG tuning
    # -------------------------------------------------------------------------
    rag_max_context_chars: int = Field(
        default=8000,
        description="Maximum characters of retrieved context to inject per query",
    )
    rag_max_documents: int = Field(
        default=5,
        description="Maximum number of documents to return per query",
    )
    rag_semantic_weight: float = Field(
        default=0.7,
        description="Score weight applied to Qdrant semantic search results",
    )
    rag_fts_weight: float = Field(
        default=0.3,
        description="Score weight applied to PostgreSQL full-text search results",
    )

    # -------------------------------------------------------------------------
    # Computed helpers
    # -------------------------------------------------------------------------
    @property
    def database_url(self) -> str:
        """Asyncpg-compatible PostgreSQL DSN."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        """redis.asyncio-compatible Redis URL."""
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    model_config = {
        "env_file": find_env_file(),
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    """Return the cached, application-wide :class:`Settings` instance."""
    return Settings()


# Alias for callers that use the v2 naming convention.
get_config = get_settings
