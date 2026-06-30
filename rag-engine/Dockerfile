# ---------------------------------------------------------------------------
# Analog Elk v3 — RAG API image
# Base: Python 3.11-slim  |  Port: 9100
# ---------------------------------------------------------------------------

FROM python:3.11-slim AS base

# Prevent .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ---------------------------------------------------------------------------
# Install OS-level dependencies
# ---------------------------------------------------------------------------
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        libgomp1 \
        wget \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Python dependencies (layer-cached unless requirements.txt changes)
# ---------------------------------------------------------------------------
COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# ---------------------------------------------------------------------------
# Pre-bake the local embedding model into the image so the container never
# downloads at runtime (works offline / on a headless box). Cache lives at a
# world-readable path because the runtime user is the unprivileged `elk`.
# ---------------------------------------------------------------------------
ENV FASTEMBED_CACHE_PATH=/opt/fastembed_cache
RUN mkdir -p /opt/fastembed_cache \
    && python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')" \
    && chmod -R a+rX /opt/fastembed_cache

# ---------------------------------------------------------------------------
# Application code
# ---------------------------------------------------------------------------
COPY . ./engine/

# Create a minimal package stub so that relative imports work
RUN touch /app/__init__.py

# ---------------------------------------------------------------------------
# Non-root user for security
# ---------------------------------------------------------------------------
RUN addgroup --system elk && adduser --system --ingroup elk elk
USER elk

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
EXPOSE 9100

# Use the module path so that `from .config import …` resolves correctly.
CMD ["uvicorn", "engine.rag_server:app", \
     "--host", "0.0.0.0", \
     "--port", "9100", \
     "--workers", "2", \
     "--log-level", "info"]
