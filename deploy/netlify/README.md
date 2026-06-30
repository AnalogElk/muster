# Elk OS portal on Netlify — front-end ONLY

> **Netlify hosts the portal front-end, not the Elk OS backend.** The portal
> needs a reachable Directus (the `os_*` board) or it **fail-fasts at boot**.
> Use this only when Directus already runs somewhere — the box
> ([`../../provision/`](../../provision/)), Render, Fly, Railway, or any host.

## What this is (and isn't)

- **Is:** a way to serve the Next.js portal UI on Netlify's edge/CDN, pointed at
  a Directus you host elsewhere.
- **Isn't:** a full Elk OS deploy. There is no Postgres, no Directus, no RAG, no
  native MCP server on Netlify. Those live on your backend host.

Because elk-os does not carry the portal source (it is vendored at build time
from `analog-elk-front-end`), **point Netlify at the portal's own repo** (your
fork of `analog-elk-front-end`), and copy [`./netlify.toml`](./netlify.toml) into
that repo's root.

## Steps

1. Stand up Directus somewhere reachable over HTTPS (e.g. the box in
   `provision/` → `https://cms.<your-domain>`). Note its URL.
2. In that Directus, create a **static token** on an admin (or suitably-scoped)
   user — this is the portal's `DIRECTUS_TOKEN`.
3. Connect your portal repo to Netlify. The committed `netlify.toml` declares the
   build + the required `@netlify/plugin-nextjs` plugin.
4. In **Netlify → Site settings → Environment variables**, set:

   | Variable | Value |
   |---|---|
   | `NEXT_PUBLIC_DIRECTUS_URL` | `https://cms.<your-host>` (browser-side) |
   | `DIRECTUS_URL` | `https://cms.<your-host>` (server-side) |
   | `DIRECTUS_TOKEN` | the static token from step 2 (secret) |
   | `NEXT_PUBLIC_SITE_URL` | `https://<your-site>.netlify.app` |

5. Deploy. If routes 404, confirm the Next plugin is active (it must be declared
   in `netlify.toml`; CLI/API-created sites do not auto-add it).

## Gotchas

- **No backend = no boot.** A Netlify deploy with `NEXT_PUBLIC_DIRECTUS_URL`
  pointing nowhere will not render the authed portal.
- **CORS:** your Directus must allow the Netlify origin — Elk OS ships
  `CORS_ENABLED=true` / `CORS_ORIGIN=true` (reflect), which covers this.
- **New env vars need a fresh publish** on Netlify to take effect.
