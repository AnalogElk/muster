# Elk OS — Design Spec

**Status:** Approved (verbally) 2026-06-29 · **Owner:** Mike Walliser · **CMS:** project `0ef5827c-924d-4c2a-a769-d9d7c84097e1`, epic `59f55f3e-29b4-47a8-ab2a-4957ca855eeb`

## 1. What we're building

`elk-os` is a one-command, self-hostable repackaging of the entire Analog Elk
system. On a fresh box or laptop it stands up four subsystems, wired together
and reachable behind Caddy/TLS:

1. **Claude-side OS** — the `CLAUDE.md` constitution, `.mcp.json`, hooks, memory
   seed, skills/commands.
2. **Directus + `os_*` schema** — the shared-state bus (tasks, sprints,
   projects, releases, …) that a human and the agent fleet both read and write.
3. **RAG knowledge engine** — local Postgres + Qdrant + Redis + RAG API
   ("Claude is the LLM"; no external inference).
4. **The Next.js portal** — the human observability surface (admin + client).

It is distributed as a **self-host / one-click product**: the repo + a deploy
blueprint (Render/Railway/Fly) + published Docker images. A single live
`generic`-profile instance is the public **demo URL** and doubles as the
showroom.

> This project is also the **system's own final test case** — Analog Elk using
> its CMS, agents, constitution, and worktree discipline to build the thing that
> ships itself. That recursion is the centerpiece of the companion whitepaper;
> see `WHITEPAPER-LOG.md`.

## 2. Locked decisions

| Decision | Choice | Why |
|---|---|---|
| Install scope | **Full agency-OS** (all 4 subsystems) | The sellable "clone an agency in one command" product |
| Branding | **Both, via `--profile generic\|analogelk`** | One repo = Mike's reproducer **and** the generic template |
| Architecture | **Approach A** — Docker Compose core + thin resumable phased CLI | Docker is the only hard dep; system-vs-box cleanly separated |
| Distribution | **Self-host / one-click** (repo + blueprint + images) | Fastest path to revenue, near-zero ops for us |
| Relationship to source repos | **Integration layer** — pull portal + RAG engine as published **images**, not submodules | Customers `up` and pull; no 4-repo clone-and-build |
| Tenancy | **Single-tenant per deployment** | One agency-OS instance per box/profile |
| External SaaS | **Graceful degradation** (Stripe/Matomo/Resend configured later) | An installer can't do human KYC; stack still comes up green |

## 3. Architecture

```
elk-os/                      # integration layer (this repo = the product)
├─ bin/elk-os                # resumable phased CLI
├─ compose/                  # compose.yaml + dev/prod overrides
├─ caddy/Caddyfile.tmpl      # reverse proxy + auto-TLS
├─ profiles/{generic,analogelk}/   # brand tokens · env defaults · seed · CLAUDE.md
├─ directus/{schema,seed,bootstrap}/
├─ claude-os/               # CLAUDE.md · .mcp.json.tmpl · hooks · memory-seed · skills · commands
├─ provision/              # optional remote: cloud-init + render/railway/fly
├─ deploy/                 # Deploy buttons + CI image publish
└─ docs/ · .env.example · WHITEPAPER-LOG.md · README.md
```

**The CLI is the spine.** Phases are ordered, idempotent, and resumable via a
`.elk-os-state.json` marker (pattern borrowed from elk-v3's `tools/new_site/`):

```
elk-os init     # pick --profile, generate secrets, write .env from .env.example
        up       # docker compose up the core
        migrate  # apply os_* schema snapshot to the fresh Directus
        seed     # load profile seed (generic Demo Co / AE)
        wire     # write CLAUDE.md + .mcp.json (→ fresh Directus) + hooks + memory seed
        doctor   # health-check every subsystem; print a green/red board
        down     # stop the stack
```

Same artifact runs on a laptop (`ELK_OS_TARGET=local`, localhost ports) and a
box (`ELK_OS_TARGET=box`, Caddy + `ELK_OS_DOMAIN` + auto-TLS). The optional
`provision/` layer stands up a bare Linux host and just runs `init && up` — so
"the system" never depends on "the box."

## 4. Install-time data flow (the wiring)

Secrets/URLs flow forward through the phases; secrets are generated where
possible and **never echoed to stdout** (constitution §2):

1. `init` → generate `POSTGRES_PASSWORD`, `DIRECTUS_KEY/SECRET`, admin password;
   write `.env`; copy the chosen profile's defaults.
2. `up` → Postgres + Directus boot.
3. bootstrap → create admin user, **mint a static `DIRECTUS_ADMIN_TOKEN`
   non-interactively** (the agencyos-test prototype required a manual UI click —
   we automate it), write it back to `.env`.
4. `migrate` → apply the `os_*` schema snapshot. `seed` → profile seed.
5. RAG engine boots (own DBs); KB manifest ingest (Claude-free).
6. portal gets `DIRECTUS_URL` + token + profile `USE_STATIC_FALLBACK`.
7. `wire` → render `.mcp.json` (Directus URL + token from env), drop `CLAUDE.md`,
   hooks, memory seed into the deployment.
8. `doctor` → assert: Directus `/server/health` ok, RAG `/health` ok (incl.
   vector-health signal), portal HTTP 200, MCP reachable, a seeded `os_task`
   readable — **proving the human↔agent loop closes**.

## 5. Error handling & resumability

- Each phase is **idempotent** (schema apply is declarative; seed checks for
  existing rows; token mint checks for an existing token).
- `.elk-os-state.json` records completed phases; a re-run resumes at the first
  incomplete one.
- `doctor` is the gate and the diagnostic: red rows name the failing subsystem
  and the next action (mirrors elk-v3's `/health` `reason` signal).
- No silent caps: if a phase skips work (e.g. SaaS unconfigured), it says so.

## 6. Testing — the "green install" contract

- `doctor` is the runtime acceptance test.
- **CI clean-room:** GitHub Actions brings the whole compose up on the `generic`
  profile from zero, runs `doctor`, and asserts green (Directus health + RAG
  health + portal 200 + MCP + a seeded task). This is the release gate.
- Per-phase unit tests for the CLI (`init` writes a correct `.env`; schema apply
  and seed are idempotent).
- A "fresh box" e2e: cloud-init on a throwaway VM → `up` → `doctor` green.

## 7. Phase plan (each phase = one CMS task = one implementation plan)

P0 scaffold · P1 compose core · P2 schema+seed · P3 RAG engine · P4 portal image
· P5 Claude-OS wiring · P6 cloud demo URL · P7 self-host packaging. We build
**P0–P1 first**; the rest are sequenced behind them.

## 8. Open questions (resolve as we reach them)

- **`dod_checklist` JSON shape** — confirm the portal's parser before populating
  (currently DoD lives in `acceptance_criteria` markdown).
- **Schema scrub depth (P2)** — exact PII/secret strip for the generic profile.
- **Repo / product name** — `elk-os` is provisional; a neutral brandable name
  may be better for selling.
- **Postgres: bundled vs managed** — default bundled container; allow a managed
  URL via env.

## 9. Honesty ledger (shipped vs aspirational)

This spec describes the **target**. As of scaffold, only P0 exists. The
whitepaper must keep this distinction; `WHITEPAPER-LOG.md` tracks real state per
phase. Known prose/code drifts to correct as we vendor from source: release-please
not yet on the portal's `main`; the activity feed is computed, not event-sourced.
