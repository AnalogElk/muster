# Deploy blueprints

One-click(ish) configs for hosting Elk OS on a PaaS. None of these replace the
**box** path ([`../provision/`](../provision/)) — that remains the most reliable
full-stack demo. These help when you'd rather live on a managed platform.

| Path | Hosts | Turnkey? | Notes |
|---|---|---|---|
| [`render.yaml`](./render.yaml) | Directus + Postgres + portal (RAG optional) | **Most** | Primary. Multi-service + managed PG in one file. A few `sync: false` vars to fill post-deploy. |
| [`fly/`](./fly/) | Directus (+ separate PG, portal, RAG apps) | Partial | One app per `fly.toml`; wired by hand. |
| [`railway.json`](./railway.json) + [`railway.README.md`](./railway.README.md) | per-service; full stack via dashboard | Partial | Best cross-service variable refs (`${{Service.VAR}}`). |
| [`netlify/`](./netlify/) | portal **front-end only** | N/A | Needs a Directus hosted elsewhere; fail-fasts without one. |

## The shared constraints (read once)

1. **The portal is a published image.** No PaaS here can build the portal — it
   needs the private `analog-elk-front-end` source. Publish images first with
   [`../.github/workflows/publish-images.yml`](../.github/workflows/publish-images.yml)
   (on a release tag), make the GHCR package public (or add a registry cred), and
   reference `ghcr.io/<owner>/elk-os-portal:<tag>`.
2. **Directus is the official image** (`directus/directus:11.15.1`) — deploys
   anywhere with no build.
3. **The native MCP server** is *permitted* by `MCP_ENABLED=true` but must be
   *enabled* post-deploy: Settings → AI → Model Context Protocol, or
   `PATCH /settings {"mcp_enabled":true}` with an admin token. (On the box,
   `elk-os wire` does this for you.)
4. **The admin static token** the portal needs (`DIRECTUS_TOKEN`) is created on a
   Directus user *after* first boot — no env can mint it. (On the box, `elk-os up`
   mints it automatically.)

## Render — post-deploy wiring (the 4 `sync: false` values)

After Render's first deploy assigns URLs:

1. **`elk-os-directus` → `PUBLIC_URL`** = the Directus service URL
   (`https://elk-os-directus-XXXX.onrender.com`). Also set `ADMIN_EMAIL`.
2. Log into Directus (admin email + the generated `ADMIN_PASSWORD` from the
   dashboard). Enable MCP (Settings → AI → MCP). Create a **static token** on your
   admin user.
3. **`elk-os-portal`** → set `DIRECTUS_URL` + `NEXT_PUBLIC_DIRECTUS_URL` to the
   Directus URL from step 1, `NEXT_PUBLIC_SITE_URL` to the portal's own URL, and
   `DIRECTUS_TOKEN` to the token from step 2.
4. Redeploy the portal so the new env takes effect.

That's the honest cost of "one-click" across a platform with no env
interpolation: the topology and secrets are declarative; four cross-service
values are filled once.
