# Provisioning Elk OS on a VPS — the reliable full-stack path

This is the **recommended way to get a live Elk OS demo**: a small VPS
(~$6–12/mo) plus a domain — or no domain at all, using a free wildcard
`sslip.io` hostname. `provision/cloud-init.sh` takes a fresh Ubuntu box from
nothing to a running, TLS-terminated stack with the human↔agent loop closed.

Why a box and not "just Netlify"? The portal **fail-fasts without a reachable
Directus backend** — a front-end-only host won't even boot. The box runs the
whole stack (Postgres + Directus + RAG + portal) in one place, so the loop is
real. (Netlify can host *only the portal front-end* against a Directus you host
elsewhere — see [`../deploy/netlify/`](../deploy/netlify/).)

## What you need

- A VPS with **2 GB+ RAM** (4 GB if you ever build images on the box), Ubuntu
  22.04 or 24.04, root/sudo.
- A hostname that resolves to the box's IP. Either:
  - a real domain (point an `A` record for the apex **and** `app` + `cms` records
    at the IP), or
  - **no domain** — use `sslip.io`: if your IP is `1.2.3.4`, set
    `ELK_OS_DOMAIN=1.2.3.4.sslip.io`. `1.2.3.4.sslip.io`, `app.1.2.3.4.sslip.io`
    and `cms.1.2.3.4.sslip.io` all resolve automatically, so Caddy gets TLS for
    all three with zero DNS setup.
- Ports **80 and 443** open (Caddy needs them for Let's Encrypt + serving).

## Routing (what the box serves)

| URL | Serves |
|---|---|
| `https://${ELK_OS_DOMAIN}` | the static whitepaper landing ([`../site/`](../site/)) |
| `https://app.${ELK_OS_DOMAIN}` | the portal (the human surface) |
| `https://cms.${ELK_OS_DOMAIN}` | Directus — the `os_*` board |
| `https://cms.${ELK_OS_DOMAIN}/mcp` | the native Directus MCP endpoint (agents) |

Caddy provisions and renews TLS for all three hosts automatically.

## Run it

SSH to the box as root and:

```bash
export ELK_OS_DOMAIN=1.2.3.4.sslip.io          # your IP + .sslip.io, or your domain
export ELK_OS_ADMIN_EMAIL=you@example.com
export ELK_OS_PROFILE=generic                  # generic | analogelk
export ELK_OS_REPO=https://github.com/<owner>/elk-os.git

# Optional — add the portal surface using PUBLISHED images (see "The portal" below)
# export PORTAL_IMAGE=ghcr.io/<owner>/elk-os-portal:0.1.0
# export RAG_IMAGE=ghcr.io/<owner>/elk-os-rag-api:0.1.0

curl -fsSL https://raw.githubusercontent.com/<owner>/elk-os/main/provision/cloud-init.sh | bash
```

Or, if you copied the repo to the box already
(`ELK_OS_SOURCE_DIR=/root/elk-os`), run `bash provision/cloud-init.sh` from there.

As **cloud-init user-data** at instance creation, prepend the `export` lines
above to the script body and paste the whole thing into your provider's
user-data field.

The script: installs Docker, places elk-os at `/opt/elk-os`, writes `.env` for
the `box` target, pins the public origins, then runs
`up → migrate → seed → wire → doctor`. When it finishes, `doctor` should be
green and `https://cms.${ELK_OS_DOMAIN}/mcp` answers.

## The portal (honest caveat)

A fresh box **cannot build the portal image** — the portal is built from the
private `analog-elk-front-end` source plus a heavy Next build, neither of which
lives on a bare VPS. So:

- **Without `PORTAL_IMAGE`/`RAG_IMAGE`** (default): the script stands up
  Directus + the RAG engine + the `os_*` board + the wired Claude loop, and skips
  the portal. This already demonstrates the whole human↔agent loop — the portal
  is just the missing human GUI.
- **With `PORTAL_IMAGE`/`RAG_IMAGE`** pointing at **published** GHCR images (cut
  by [`publish-images.yml`](../.github/workflows/publish-images.yml) on a release
  tag): the box pulls them and serves the full stack, portal included, with no
  local build.

So the turnkey full-stack demo is: publish images once (needs a GitHub remote
and access to the front-end source), then provision boxes that pull them.

## Troubleshooting

```bash
cd /opt/elk-os
./bin/elk-os doctor          # green/red board with next-action hints
./bin/elk-os logs directus   # or: caddy, portal, elkos-rag-api
```

- **Directus health red / TLS pending:** Caddy needs DNS resolving to the box and
  ports 80/443 reachable before Let's Encrypt issues a cert. Confirm the `A`
  records (or that you used an `sslip.io` host) and the firewall.
- **`doctor` portal row red but you expected no portal:** that's expected when
  the portal was omitted — `ELK_OS_WITH_PORTAL=false` removes the row entirely;
  if it shows, `PORTAL_IMAGE` was set without a reachable image.

## Seeding demo content (a full, on-thesis portal)

A fresh box comes up with the pruned `os_*` schema and a small generic seed. Two
scripts turn that into a rich, coherent demo where every portal section is
populated and the Knowledge Base works. Both are **idempotent** — safe to re-run.

```bash
cd /opt/elk-os   # or ~/elk-os
export DIRECTUS_URL=https://cms.${ELK_OS_DOMAIN}
export DIRECTUS_ADMIN_TOKEN=...        # from .env (never print it)

# 1. Read-only public demo user (Employee role + read-only policy)
DEMO_EMAIL=demo@muster.dev python3 provision/demo-readonly-role.py

# 2. Restore the Knowledge Base (kb_spaces + kb_pages) that the schema prune
#    dropped, seed real Muster docs, and grant the demo policy READ on them.
python3 provision/re-add-kb.py

# 3. Seed the board + CRM/billing so nothing looks empty:
#    - PRIORITY A: a "Muster" project + the REAL os_tasks that built the demo
#      (provision/seed/muster-tasks.json — epic + phases P0–P7 + follow-ups,
#      hierarchy + statuses preserved), and removes the synthetic starter rows.
#    - PRIORITY B: a deal pipeline, a proposal, CRM activities, two invoices
#      (one paid + a payment) with line items, products, project updates,
#      and Muster releases. All synthetic, is_test_data=false so they render.
python3 provision/seed-demo.py
```

**Data files** (`provision/seed/`):

| File | Purpose |
|---|---|
| `kb-schema.json` | `kb_spaces` + `kb_pages` collection/field/relation snapshot (from the prod CMS) that `re-add-kb.py` applies. |
| `kb-pages.json` | The seeded Engineering space + KB pages (architecture, the human↔agent loop, gotchas, self-hosting, the whitepaper). |
| `muster-tasks.json` | The real Muster build tasks exported from the CMS, sanitized (prod-specific relations stripped, hierarchy + statuses kept). |

> **Reproducibility follow-up:** these three steps are run manually against the
> live box today. To make a fresh box come up demo-ready automatically, fold them
> into `cloud-init.sh` (after `elk-os up` + `migrate`/`seed`), gated behind a
> `ELK_OS_SEED_DEMO=true` env flag, and add `kb_spaces`/`kb_pages` back into the
> profile schema snapshot so `re-add-kb.py` becomes a no-op on new boxes.

## Cost

A 2 GB VPS (Hetzner CX22, DigitalOcean, Vultr, etc.) runs ~$6–12/mo. With an
`sslip.io` host there is **no domain cost** — a genuinely cheap live demo.
