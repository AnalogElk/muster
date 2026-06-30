# Elk OS on Fly.io (secondary blueprint)

Fly deploys **one app per `fly.toml`** — there is no Render-style multi-service
blueprint. A full Elk OS on Fly is three pieces wired by hand. Render
([`../render.yaml`](../render.yaml)) is the more turnkey path; use Fly if you
already live there.

## 1. Managed Postgres

```bash
fly postgres create --name elk-os-db --region sea
```

## 2. Directus (this `fly.toml`)

```bash
cd deploy/fly
# edit fly.toml: set a unique `app` name + your `primary_region`
fly apps create elk-os-directus
fly postgres attach elk-os-db --app elk-os-directus   # injects DATABASE_URL

# Directus wants discrete DB_* vars, not a URL — set them from the attach output
# (or `fly postgres connect` to read them), plus the app secrets:
fly secrets set --app elk-os-directus \
  KEY="$(openssl rand -hex 32)" \
  SECRET="$(openssl rand -hex 32)" \
  DB_HOST=elk-os-db.flycast DB_PORT=5432 \
  DB_DATABASE=postgres DB_USER=postgres DB_PASSWORD='<from attach>' \
  DB_SSL=false \
  ADMIN_EMAIL='you@example.com' \
  ADMIN_PASSWORD="$(openssl rand -hex 24)" \
  PUBLIC_URL='https://elk-os-directus.fly.dev'

fly deploy
```

`DB_SSL=false` is correct over Fly's private `.flycast` network. The MCP server
is permitted by `MCP_ENABLED=true` in `fly.toml`; flip it on after boot in
**Settings → AI → Model Context Protocol**, or
`PATCH /settings {"mcp_enabled":true}` with an admin token.

## 3. Portal (a second app, PUBLISHED image)

Fly can't build the portal (private front-end source). Deploy a **published**
GHCR image as its own app:

```bash
fly apps create elk-os-portal
fly secrets set --app elk-os-portal \
  DIRECTUS_URL='https://elk-os-directus.fly.dev' \
  NEXT_PUBLIC_DIRECTUS_URL='https://elk-os-directus.fly.dev' \
  NEXT_PUBLIC_SITE_URL='https://elk-os-portal.fly.dev' \
  DIRECTUS_TOKEN='<static token from the Directus admin user>' \
  USE_STATIC_FALLBACK=true
fly deploy --image ghcr.io/<owner>/elk-os-portal:0.1.0 --app elk-os-portal
```

## Caveats

- The RAG engine (Qdrant + Redis + API) is three more Fly apps + a volume — out
  of scope for this secondary blueprint. Use the box (`provision/`) for the RAG
  surface.
- `auto_stop_machines` saves money but cold-starts add latency; the Directus app
  keeps `min_machines_running = 1` so the board + MCP stay live.
