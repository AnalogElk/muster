# rag-engine — provenance

This directory is a **vendored copy** of the Analog Elk v3 local RAG knowledge
engine. It is checked in so that `elk-os` is self-contained: a customer install
must never depend on a sibling `../analog-elk-v3` checkout existing on the box.

## Source

- **Repo:** `analog-elk-v3` (private, AnalogElk)
- **Path:** `engine/` (Python app) + `migrations/` (SQL schema + runner)
- **Commit:** `02a38e5e79763813b505b9f7891a7e6a4ff8b17a`
  — _feat(engine): replace Gemini embedding API with local fastembed (#5)_
- **Vendored:** 2026-06-29 (P3 — RAG engine integration)

## What was copied

| File / dir | Role |
|---|---|
| `Dockerfile` | Builds the RAG API image (Python 3.11-slim, port 9100). Pre-bakes the embedding model at build time so the container never downloads at runtime. |
| `rag_server.py` | FastAPI app. `/health`, `/query`, `/ingest`, `/ingest/batch`, `/stats`. |
| `rag.py` | Hybrid semantic + full-text retrieval service. |
| `embeddings.py` | Local `BAAI/bge-small-en-v1.5` embeddings via fastembed (ONNX/CPU, 384-dim). **No external inference API, no key, no quota.** |
| `config.py` | pydantic-settings config; reads env vars (`POSTGRES_*`, `REDIS_*`, `QDRANT_*`). |
| `models.py` | Pydantic request/response models, incl. `HealthStatus` with the vector-health `reason` signal. |
| `requirements.txt` | Pinned Python deps. |
| `migrations/` | SQL schema (`001`–`003`) + `migrate.sh`. The server also self-creates the `documents` table on first boot, so these are reference/optional for the RAG API. |

## What was intentionally NOT copied

- The engine's own `docker-compose.yml` — replaced by `compose/compose.rag.yaml`
  (namespaced services, isolated ports, wired to the elk-os `.env`).
- `engine/.env` / `engine/.env.example` — elk-os drives all config through its
  root `.env` (`./bin/elk-os init`); the rag-api container reads env vars, not a file.
- `__pycache__/` and compiled artifacts (see `.dockerignore`).

## The vector-health signal (do not lose this)

`rag_server.py::health()` distinguishes **down** from **degraded**:

- `status: "ok"` — dependencies reachable; vectors consistent with docs
  (a fresh KB with **zero docs** also reports `ok`).
- `status: "degraded"`, `reason: "vectors_missing"` — docs exist but no vectors
  (the exact symptom that once hid a silent embedding-auth outage).
- `status: "degraded"`, `reason: "vectors_stale"` — vectors lag docs by >10%.

`./bin/elk-os doctor` preserves this: `degraded` is a **yellow WARN**, not a hard
fail; only an unreachable API is red.

## Forward-looking (P7)

P7 (self-host packaging) may replace this local build with a **published Docker
image** (`build:` → `image:`). When that happens, keep this `PROVENANCE.md` as the
record of what the image was cut from, and keep `compose/compose.rag.yaml` able to
fall back to a local build for development.
