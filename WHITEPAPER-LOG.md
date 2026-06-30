# Whitepaper Log — "The system repackaged itself"

A running, timestamped record of Elk OS being built **by the very system it
packages**. This is the primary-source log for the companion whitepaper. Every
entry: what happened, which part of the system did it, what's real vs.
aspirational. Append-only; correct earlier claims with a dated follow-up rather
than editing them away (truthfulness ledger, constitution §10).

CMS: project [`0ef5827c`](https://cms.analogelk.com/admin/content/os_projects/0ef5827c-924d-4c2a-a769-d9d7c84097e1)
· epic `59f55f3e` · phases P0–P7.

---

## The thesis this project proves

The interesting claim of the Analog Elk system is not the admin panel — it's the
**loop**: a human and an autonomous agent fleet coordinating through one task
record (`os_tasks`), under a written constitution, grounded by a local RAG KB,
remembering across sessions on disk. Elk OS is the loop, packaged. Building it
is the loop's final exam: **the system used its own CMS, agents, and governance
to produce the thing that ships the system.**

---

## 2026-06-29 — Session 0: scope → design → CMS spine → scaffold

**Decisions reached (with the human, one fork at a time):**
- Subject shifted from "whitepaper the admin panel" → "whitepaper the whole
  system" → "build the whole system as a sellable installer, and make THAT the
  test case."
- Install scope: **full agency-OS** (all 4 subsystems).
- Branding: **both profiles** (`generic` | `analogelk`).
- Architecture: **Approach A** — Docker Compose core + resumable phased CLI.
- Distribution: **self-host / one-click product**; one live `generic` instance
  is the demo URL.

**The system acting on itself (evidence for the paper):**
- Three `Explore` subagents mapped the live system (elk-v3, the portal, the
  DevProd umbrella) in parallel — the fleet reading itself.
- The **CMS became the spine before any code**: an `os_projects` row + an epic
  `os_task` + 8 phase tasks (P0–P7) with points, priorities, and acceptance
  criteria were created via the Directus MCP bridge — the same board a human
  steers. Agents will pick these up.
- **Prior art reused, not duplicated:** `~/Desktop/DevProd/{setup,apply,cleanup}-agencyos-test.sh`
  already prototyped isolated docker-compose + fresh Directus + `directus-template-cli`.
  Elk OS extends that pattern (and automates the manual token-mint step).

**Real state after Session 0:** P0 scaffold only — repo structure, `.env`
contract, README, this log, and the design spec, committed. Nothing is runnable
yet. Everything below P0 is aspirational until a `doctor`-green entry says
otherwise.

**Logged to:** CMS project `0ef5827c`; epic `59f55f3e`; tasks P0 `28f0cb13` …
P7 `6367902d`; repo `elk-os` (this commit).

---

## 2026-06-29 — Session 1: P0 + P1 are real and green (the first `doctor` pass)

A single background agent built the runnable half of P0 and P1 and **genuinely
booted the stack** — Postgres + Directus came up, the admin static token was
minted non-interactively, and `elk-os doctor` reported all five checks green and
exited 0:

```
● Docker daemon      OK   reachable
● .env               OK   present
● Postgres container OK   running, healthy
● Directus health    OK   http://localhost:8056 → status ok
● Admin API token    OK   minted, authenticates (hidden)
```

On-brand detail for the paper: the agent hit a **real** port collision (5432 and
5433 were already taken by other Docker Postgres instances on the box) and fixed
it by isolating elk-os Postgres to 15432 — exactly the friction a fabricated
"green" never surfaces. Down→`doctor` honestly went red + exit 1.

Commits `82f23d0..267cbe3`. P0 (`28f0cb13`) and P1 (`592489c2`) → **completed**
in CMS, verified on disk by the orchestrator (commits, executable CLI, all
subcommands, no `.env` committed).

**Aspirational → real:** the compose core + CLI now exist and run locally.
Still aspirational: schema/seed (P2), RAG engine (P3), portal (P4), Claude-OS
wiring + the proven human↔agent loop (P5), cloud demo URL (P6).

**New follow-up filed (not floating, §1):** CI clean-room `doctor` release gate.

**Logged to:** CMS tasks `28f0cb13`, `592489c2` (completed) + new CI-gate task;
this log; repo `main`.

---

## 2026-06-29 — Session 2: P3 RAG engine is real and green

The third subsystem — the **local RAG knowledge engine** — is now vendored,
wired, and **genuinely booted**. The Analog Elk v3 engine (FastAPI + Qdrant +
Redis + Postgres, local `bge-small` embeddings, **no external inference**) was
copied into `rag-engine/` at source commit `02a38e5e`, made self-contained
(`PROVENANCE.md` records the lineage and the P7 published-image path), and added
as an **additive, namespaced, port-isolated** compose overlay
(`compose/compose.rag*.yaml`). The core Postgres/Directus services were not
touched.

`./bin/elk-os up` built the RAG image (Python + fastembed, model baked at build
time, ~695 MB) and brought all four RAG containers up **healthy**. The new
`doctor` row reports the engine honestly:

```
● RAG API health   OK   http://localhost:9101 → status ok (0 docs, 0 vectors)
```

A fresh, never-ingested KB legitimately reports `status: ok` (0 docs / 0
vectors) — ingestion is a separate concern (P-later). The engine's
**degraded-vs-down** signal is preserved: `doctor` renders `degraded`
(vectors missing/stale) as a non-blocking **yellow WARN**, and only an
unreachable API as red. Full board went green, exit 0; `down --volumes` tore the
overlay down cleanly.

On-brand friction for the paper: the box was already running Mike's live
analog-elk-v3 engine on `:9100`, and the first `doctor` pass exposed a **real
`set -e`/`pipefail` bug** (a `null` `reason` field made a no-match `grep` kill
the script before the RAG row printed) — both fixed, not papered over. RAG was
verified on `:9101` to leave the live engine untouched; the shipped default
stays `:9100`.

Inclusion choice: a single env switch **`ELK_OS_WITH_RAG` (default on)**, read
from `.env`, so up/down/logs always address the same service set without a flag
to remember (mirrors the existing `ELK_OS_TARGET` pattern).

Commit `4f5f5ad`. P3 (`044eb35a`) acceptance — reachable RAG `/health` with the
vector-health signal surfaced in `doctor` — **met**.

**Aspirational → real:** core + CLI + **RAG engine** now run locally. Still
aspirational: schema/seed end-to-end (P2), portal (P4), Claude-OS wiring + the
proven human↔agent loop (P5), cloud demo URL (P6), self-host packaging /
published images (P7).

**What P4/P5 will need from here:** the portal (P4) reaches the RAG API over the
`elkos-rag` network by service name (`elkos-rag-api:9100`) — no host port needed
in prod; the `.mcp.json`/`CLAUDE.md` wiring (P5) should point KB queries at
`http://localhost:${RAG_API_PORT:-9100}/query`. A KB **ingestion** step (manifest
load) is still owed before the KB answers substantively — until then `/health` is
green but `/query` returns nothing.

**Logged to:** CMS task `044eb35a` (orchestrator updates status); this log; repo
`main`.

---

<!-- Append new sessions/phases below. Each phase flips from aspirational to real
     only when `doctor` proves it. -->
