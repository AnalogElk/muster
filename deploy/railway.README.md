# Elk OS on Railway (secondary blueprint)

Railway's `railway.json` configures **one service** (build + deploy), not a full
multi-service topology — that is assembled in the Railway dashboard/template. So,
like Fly, a full Elk OS on Railway is wired per-service. Render
([`./render.yaml`](./render.yaml)) remains the turnkey path.

## What `railway.json` here covers

[`./railway.json`](./railway.json) is a ready service config for the **RAG API**
— the one Elk OS service Railway can build straight from this repo
(`rag-engine/Dockerfile` is self-contained). Point a Railway service's config
path at it, or drop it at the repo root.

## Assembling the full stack (dashboard)

1. **Postgres** — add the Railway Postgres plugin. It exposes `PGHOST`, `PGPORT`,
   `PGDATABASE`, `PGUSER`, `PGPASSWORD`.
2. **Directus** — new service from the Docker image `directus/directus:11.15.1`.
   Set variables: `DB_CLIENT=pg`, `DB_HOST=${{Postgres.PGHOST}}`,
   `DB_PORT=${{Postgres.PGPORT}}`, `DB_DATABASE=${{Postgres.PGDATABASE}}`,
   `DB_USER=${{Postgres.PGUSER}}`, `DB_PASSWORD=${{Postgres.PGPASSWORD}}`,
   `KEY`/`SECRET` (random), `ADMIN_EMAIL`, `ADMIN_PASSWORD`,
   `WEBSOCKETS_ENABLED=true`, `CORS_ENABLED=true`, `CORS_ORIGIN=true`,
   `MCP_ENABLED=true`, `PUBLIC_URL=${{RAILWAY_PUBLIC_DOMAIN}}` (prefix `https://`).
   Railway DOES support `${{Service.VAR}}` reference variables — a real advantage
   over Render/Fly for cross-service wiring.
3. **Portal** — new service from a **published** GHCR image
   (`ghcr.io/<owner>/elk-os-portal:0.1.0`; Railway can't build it from the private
   front-end source). Set `DIRECTUS_URL` + `NEXT_PUBLIC_DIRECTUS_URL` to the
   Directus public URL, `DIRECTUS_TOKEN` to a static admin token,
   `USE_STATIC_FALLBACK=true`.
4. **RAG (optional)** — this `railway.json` service, plus a Qdrant service
   (`qdrant/qdrant:v1.13.2` + a volume) and a Redis plugin.

## Caveat

After Directus boots, enable the native MCP server in **Settings → AI → Model
Context Protocol** (or `PATCH /settings {"mcp_enabled":true}`). `MCP_ENABLED=true`
only permits it.
