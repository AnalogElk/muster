<h1 align="center">Muster</h1>

<p align="center">
  <strong>The operating system for agentic software teams, in one command.</strong><br>
  A human and a fleet of AI agents share one task substrate — Muster packages the
  whole loop so you can run it on a fresh box or a laptop.
</p>

<p align="center">
  <a href="https://34.220.64.149.sslip.io">Live demo &amp; whitepaper</a> ·
  <a href="https://app.34.220.64.149.sslip.io">Live portal</a>
  (read-only demo login <code>demo@muster.dev</code> / <code>muster-demo</code>)
</p>

> **Naming note:** the public product name is **Muster**; **Elk OS** is the
> project's working name and survives in the CLI (`bin/elk-os`), env vars
> (`ELK_OS_*`), and some internal docs. Renaming those is a tracked decision,
> not an accident — the two names refer to the same thing.

---

Most "AI for work" tools bolt a chatbot onto the side of your real system. Muster
inverts that: the **shared task board is the substrate**, and both the human and
the agents are first-class users of it. The row a human drags on a board is the
row an agent picks up over MCP — and writes back when it's done. Muster ships
that loop, wired and reproducible, as a self-hostable product.

```bash
git clone https://github.com/AnalogElk/muster.git && cd muster
./bin/elk-os init --profile generic   # generate secrets + .env
./bin/elk-os up                       # docker compose up the whole stack
./bin/elk-os doctor                   # green/red health board — the loop proof
```

Docker is the only hard dependency. Secrets are generated into a gitignored
`.env` and never printed.

## The four subsystems

One `elk-os up` stands up four wired pieces:

| Subsystem | What it is |
|---|---|
| **Claude-side OS** | A governance constitution (`CLAUDE.md`), an MCP bridge, SessionStart hooks, and persistent memory that turn Claude Code into a standing team member. Rendered per-deployment by `elk-os wire`. |
| **Directus + `os_*`** | The shared-state bus: tasks, sprints, projects, releases, repositories. Directus's **native MCP server** (`/mcp`) is the agent's door to the board. |
| **RAG knowledge engine** | A local "Claude is the LLM" knowledge base (Postgres + Qdrant + Redis + FastAPI). Embeddings are local — no external inference, no API key, no quota. |
| **The portal** | The human surface (admin + client), a Next.js app over the same `os_*` data. |

## The loop, concretely

```
        ┌─────────────────────────────────────────────────────┐
        │            Directus  +  the os_* board              │
        │     (tasks · sprints · projects · releases)         │
        └───────────────▲───────────────────────▲─────────────┘
       drags a card on  │                       │  reads/writes via the
        the portal      │                       │  native Directus MCP (/mcp)
                  ┌──────┴──────┐         ┌──────┴───────────┐
                  │    Human    │         │  Claude fleet    │
                  │  (portal)   │         │ (wired CLAUDE.md)│
                  └─────────────┘         └──────────────────┘
```

`elk-os wire` enables the native MCP server (`settings.mcp_enabled`), writes a
`.mcp.json` pointing Claude at *this* deployment's Directus, and proves the loop
by reading seeded `os_tasks` back through the same endpoint + token. `doctor`
then asserts every subsystem green — including a live `tools/list` against `/mcp`.

## Profiles

| Profile | Stands up |
|---|---|
| `generic` | A blank, unbranded agency-OS seeded with a synthetic "Demo Co" — make it your own. |
| `analogelk` | Analog Elk's own branding + demo data (the reference instance). |

```bash
./bin/elk-os init --profile analogelk
```

## The CLI

A resumable, idempotent phased installer (`.elk-os-state.json` records progress;
a re-run resumes at the first incomplete phase):

| Command | Does |
|---|---|
| `init` | Generate secrets + write `.env` from `.env.example`. |
| `up` | `docker compose up` the core (+ RAG + portal), then mint the admin static token. |
| `migrate` | Apply the pruned `os_*` schema snapshot (idempotent diff + apply). |
| `seed` | Load the profile's seed data (idempotent upsert). |
| `wire` | Render the Claude-side OS, enable the native MCP server, prove the loop. |
| `doctor` | Per-subsystem green/red board — the runtime acceptance test. |
| `down` | Stop the stack (`--volumes` to wipe data). |

## Deploy options (honest about what's local vs needs a host)

| Path | Hosts | Best for |
|---|---|---|
| **Box** ([`provision/`](./provision/)) | the **whole stack** behind Caddy + TLS | The recommended live demo: a ~$6–12/mo VPS + a domain (or a free `sslip.io` host). |
| **Render** ([`deploy/render.yaml`](./deploy/render.yaml)) | Directus + Postgres + portal | The most turnkey PaaS one-click. |
| **Fly / Railway** ([`deploy/`](./deploy/)) | per-service, wired by hand | If you already live there. |
| **Netlify** ([`deploy/netlify/`](./deploy/netlify/)) | the portal **front-end only** | Putting the UI on a CDN — **requires a Directus you host elsewhere**. |

**The honest caveat:** the portal **fail-fasts without a reachable Directus
backend** — a front-end-only host (Netlify) hosts the UI, *not* the backend. The
backend (Postgres + Directus + RAG + native MCP) needs a real host: the box is
the reliable full-stack path. And the portal image is published to GHCR (it can't
be built on a bare PaaS) — see [`provision/`](./provision/) and
[`deploy/README.md`](./deploy/README.md).

The live demo *is* the box path: [`site/`](./site/) is the whitepaper homepage
Caddy serves at the demo root, and [`provision/`](./provision/) includes the
scripts that make the public demo real — `seed-demo.py` (seed the actual Muster
build board), `re-add-kb.py` (restore + seed the knowledge base), and
`demo-readonly-role.py` (lock the `demo@muster.dev` login to read-only).

## What's regenerated post-clone (not shipped pre-rendered)

- **`portal/.build/`** — the portal's Docker build context is a *frozen archive*
  of a pinned `analog-elk-front-end` commit, reproduced on demand by
  `portal/prepare-context.sh`. Gitignored; never committed.
- **`wire/`** — the per-deployment Claude config is rendered by `elk-os wire` from
  the committed [`claude-os/`](./claude-os/) templates. It bakes absolute local
  paths and references the token by env name only. Gitignored; regenerate any
  time with `elk-os wire`.

## Versioning & releases

Versioning is automated via [release-please](https://github.com/googleapis/release-please)
(`release-type: simple` — Muster is a bash/compose repo, not a Node package). The
version of record lives in [`version.txt`](./version.txt); the narrative in
[`CHANGELOG.md`](./CHANGELOG.md). Every commit/PR title must be a valid
[Conventional Commit](https://www.conventionalcommits.org/) (`feat:` → minor,
`fix:`/`perf:` → patch, `feat!:` → major). On tag, service images publish to GHCR
([`publish-images.yml`](./.github/workflows/publish-images.yml)).

## Design & status

Full spec: [`docs/superpowers/specs/2026-06-29-elk-os-installer-design.md`](./docs/superpowers/specs/2026-06-29-elk-os-installer-design.md).
Per-phase real status (shipped vs aspirational) is tracked honestly in
[`WHITEPAPER-LOG.md`](./WHITEPAPER-LOG.md). The loop — core + RAG + schema/seed +
portal + the wired Claude-OS — is proven on a from-scratch install, and the live
public demo is up: [the whitepaper homepage](https://34.220.64.149.sslip.io) with
[the portal](https://app.34.220.64.149.sslip.io) one link away.

## License

Not yet finalized — Muster's `os_*` schema derives from
[directus-labs/agency-os](https://github.com/directus-labs/agency-os) (MIT, see
[`NOTICE`](./NOTICE)). The license choice affects monetization, so the options and
a recommendation are laid out in
[`LICENSE-RECOMMENDATION.md`](./LICENSE-RECOMMENDATION.md) for a deliberate
decision rather than a default.
