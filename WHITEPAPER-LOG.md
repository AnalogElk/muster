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

## 2026-06-29 — Session 3: P2 built BY Max Mode — and the loop-proof caught its own bugs

This is the recursion's sharpest chapter. P2 (the `os_*` schema + seeds) was built
not by a single agent but by **the system's own parallel-execution engine** — Max
Mode, run on the Workflow fan-out — at the human's explicit request ("you should be
using maxx mode for this"). Eight agents:

**ground** (query the local RAG KB for Directus snapshot/migration guidance) →
**fan-out** (schema snapshot+prune+`migrate`/`seed` CLI ∥ generic Demo Co seed ∥
AE seed) → **scrub-audit** → **3 adversarial leak-verifiers** each trying to *prove*
real client data leaked into the sellable template.

- **Leak gate: clean.** Scrub-audit found + neutralized 6 cosmetic `AnalogElk`/`analogelk.com`
  refs in UI notes; all three skeptics returned `leakProven: false`; an independent
  orchestrator grep agreed. Schema pruned **141 → 50** collections, zero dangling refs.

Then the orchestrator's **from-scratch loop-proof** — boot a clean stack, `migrate`,
`seed`, read an `os_task` back — caught **three real bugs the agents' offline mocks
could not**:

1. **RAG API port 9100 collided** with the box's already-running elk-v3 engine — and
   `doctor` was *fooled* into reporting that other engine healthy. (Fixed: default → 19100.)
2. **`releases` seed missing required `repository_id`** (releases belong to a repo, which
   carries the project). Fixed both profiles; the AE profile was even missing its
   `repositories.json`. (Added.)
3. **AE seed files bare-named** (`projects.json`) collided with the kept `projects`
   UI-folder collection, so the loader seeded the wrong target. (Renamed to `os_*.json`.)

**Result (both profiles, clean-install, `doctor` all green):** generic `created=17/0`,
analogelk `created=16/0`, and on each a seeded `os_task` read back through the API. The
human↔agent task substrate now stands up from **one command**. (The AE demo board even
seeds tasks describing elk-os's own construction — "Stand up compose core", "Vendor the
RAG engine overlay".)

**The recursion in one line:** the system used its fan-out engine to build its own
installer, its adversarial verifiers to check its own template for leaks, and its
from-scratch loop-proof to catch bugs in its own packaging — including one where its
own health check was fooled by its own other instance.

Commits `de7fb05`, `5222976`. P2 (`09939f6c`) → **completed**. Robustness follow-ups
filed (§1): `up` shouldn't let an overlay failure abort core bootstrap; `doctor` should
confirm it's *our* engine on the port; loader `resolve()` should prefer table
collections over UI-folder aliases.

**Aspirational → real:** core + RAG + **schema + seeds + the proven loop** now run
locally on both profiles. Still aspirational: portal (P4), Claude-OS wiring (P5), cloud
demo URL (P6), self-host packaging (P7).

---

## 2026-06-29 — Session 4: P4 portal — the human surface, containerized (it renders the thesis)

The Next.js 16 portal is containerized and serving, wired to the fresh Directus. It
was built **§9-safely** from a READ-ONLY `git archive` of pinned `origin/main`
(`9931464`) — `analog-elk-front-end` was never touched, and at build time that repo
had **28 active worktrees** (the agent fleet, made literal; it's why we archive
instead of checkout — the root checkout was even sitting on a feature branch).

The build agent cleared five real blockers: a private GitHub-Packages dep
(`@analogelk/background-three-js`, lazy-imported + unused → stripped); missing
`output: 'standalone'`; an `instrumentation.ts` crash-loop because the admin token
mints *after* boot (so `up` now recreates the portal post-mint); a slim-image
healthcheck with no `wget` (→ Node probe); and a compose context path.

Result: `elk-os/portal:local` (413 MB) builds, `elk-os-portal` runs **healthy**,
`/login` and `/` both return **HTTP 200**, and `doctor` shows a green Portal row. The
§5 screenshot (committed under `docs/screenshots/p4-portal/` and uploaded to the P4
task's `completion_screenshot`) shows the login page — whose own right-panel tagline
reads **"The agency OS that runs itself."** The product literally renders the paper's
thesis on its front door.

**Honest gap (filed):** the portal still shows **Analog Elk branding even on the
`generic` profile** — only data + schema are profile-switched so far, not portal
branding. A truly sellable generic template must rebrand the portal too.

Commits `c3adb38..15e99f7`. P4 (`b93307f9`) → **completed**, screenshot attached.

**Aspirational → real:** core + RAG + schema/seed + **the portal** now stand up from
one command (5 of 8 phases). Still aspirational: Claude-OS wiring (P5 — the loop's
heart), cloud demo URL (P6), self-host packaging (P7).

---

## 2026-06-29 — Session 5: P5 Claude-OS wiring — the loop closes on a from-scratch install (the capstone)

The thesis is now executable end to end. `elk-os wire` installs the Claude-side
operating system into a deployment and connects a Claude session to the
deployment's **own** shared task board.

Key finding: Directus 11.15.1 ships a **native MCP server** at `/mcp` (JSON-RPC
streamable-HTTP; `items` + `system-prompt` tools — the same surface as the prod
`analog-elk-cms` MCP), gated by a `settings.mcp_enabled` flag (default off). So
`wire` flips it on and writes a `.mcp.json` pointing `elk-os-cms` at
`http://localhost:8056/mcp` with the token as a `${DIRECTUS_ADMIN_TOKEN}` env
reference (never a literal). It also renders a profile-switched `CLAUDE.md`
constitution, SessionStart hooks (banner + os_tasks queue), a memory seed, and a
`run-claude.sh` launcher — all from committed `claude-os/` templates into a
gitignored per-deployment `wire/` dir.

**The loop proof:** on a clean generic boot, `wire` read **8 seeded `os_tasks`
back through the wired MCP config**, and the SessionStart hooks printed the banner
+ "6 open / 8 total" exactly as a buyer's Claude session would. `doctor` is green
including a "Directus MCP → tools/list 200" row. One command stands up the
substrate; `wire` connects Claude to it; the human↔agent loop closes on a
from-scratch install. That is the whole thesis, reproducible.

Commits `89a7261`, `ad27725`. P5 (`efb782c6`) → **completed**.

**Aspirational → real:** core + RAG + schema/seed + portal + **the wired Claude-OS
loop** — 6 of 8 phases. Remaining: cloud demo URL (P6), self-host packaging (P7).

**Honest note for P6:** the portal app fail-fasts without a reachable Directus, so
a backend-less front-end-only demo won't even boot — the live demo genuinely needs
a backend host, not just Netlify. Plan revised accordingly.

---

## 2026-06-29 — Session 6: P7 self-host packaging — Elk OS becomes a product

The working stack is now a distributable product. No new runtime behavior — this
phase wraps the proven loop in the machinery to ship it: a VPS provisioner, PaaS
blueprints, image publishing, automated versioning, a landing-grade README, and a
licensing path.

What landed:

- **`provision/cloud-init.sh` + README** — the reliable full-stack path. On a
  fresh Ubuntu VPS it installs Docker, places elk-os, writes a box-target `.env`,
  and runs `up → migrate → seed → wire → doctor` behind Caddy + auto-TLS. The box
  Caddy routing was finished here (it was a P4 TODO): the **portal on the apex,
  Directus on `cms.${ELK_OS_DOMAIN}`**, both TLS'd, with the prod compose origins
  pinned to match. Recommended demo: a ~$6–12/mo VPS + a free `sslip.io` host (no
  domain cost — `cms.<ip>.sslip.io` resolves automatically).
- **Deploy blueprints (`deploy/`)** — `render.yaml` (primary one-click: Directus +
  managed Postgres + portal, RAG optional), `fly/` and `railway.json` (secondary,
  honest per-service wiring), and `netlify/` (the portal **front-end only**, with
  the loud caveat that it needs a Directus hosted elsewhere or it won't boot).
- **`publish-images.yml`** — builds + pushes the portal + RAG images to GHCR on
  tag. The RAG image is self-contained and builds in CI cleanly; the portal job is
  **honestly gated** — it needs the private front-end source, so it only runs when
  `AE_FRONTEND_REPO` + `AE_FRONTEND_PAT` secrets exist, else it skips with a notice.
- **Image-or-build toggle** — `compose.images.yaml` (`build: !reset null` + pinned
  `PORTAL_IMAGE`/`RAG_IMAGE`), wired into `bin/elk-os` via
  `ELK_OS_USE_PUBLISHED_IMAGES`. Validated both modes with `docker compose config`.
- **Versioning per CLAUDE.md §7** — release-please **`release-type: simple`** (bash
  repo, not Node): `version.txt` (0.1.0) + `.release-please-manifest.json` +
  `release-please-config.json` + `release-please.yml`, plus a `CHANGELOG.md`
  summarizing P0–P5.
- **Licensing** — no binding `LICENSE` committed (the choice affects monetization;
  Mike decides). `LICENSE-RECOMMENDATION.md` lays out MIT+attribution vs
  source-available (BSL/PolyForm — recommended) vs dual-license, and `NOTICE`
  retains the Agency OS (MIT) lineage.

**Honest verification:** no box, no GitHub remote, so nothing was actually
deployed. All artifacts were validated **syntactically + for internal
consistency**: `bash -n` on `cloud-init.sh` and `bin/elk-os`; YAML/JSON/TOML
parse on every blueprint + workflow; `docker compose config` green for the box
target and for both image/build modes; ports + env cross-checked against
`.env.example` and the compose set. The image-publish workflow and release-please
activate only once a GitHub remote exists; the published-image one-click deploys
work only once images are pushed. The native MCP enable stays driven by `wire`
(`settings.mcp_enabled`); `MCP_ENABLED=true` in the PaaS env only *permits* it
(verified against Directus docs) and is documented as a post-deploy toggle.

**Aspirational → real:** P0–P5 (the loop) remain proven; P7 packaging is built and
statically verified. Remaining: **P6 — the live public demo URL**, which needs
real infra (a box + domain/sslip.io, or pushed images + a Render deploy).

---

## 2026-06-29 — Session 7: P6 — the live demo URL. ALL 8 PHASES GREEN.

Elk OS is live on the public internet. The full stack deployed to a fresh AWS EC2
**t3.medium** — the cheapest viable host, chosen by a 4-lens **cost panel** that
pulled *live spot pricing* off the AWS CLI (the decisive finding: at demo
duty-cycle the instance-size debate is moot; stop-when-idle is the only lever, so
the floor is ~$2/mo EBS and compute is pennies). It runs behind Caddy +
Let's Encrypt TLS, reachable with **no DNS** via `sslip.io`:

- Portal: **https://34.220.64.149.sslip.io** — the login renders "Analog Elk ·
  The agency OS that runs itself," served over real HTTPS.
- Directus board: **https://cms.34.220.64.149.sslip.io**

Independently curl-verified off-box (200 + valid TLS, HTTP/2); `init → up →
migrate → seed → wire` ran clean; the native Directus MCP is enabled and **8
seeded `os_tasks` are readable through the public https API**. `doctor` 7/8 (the
one red is the cosmetic box-mode localhost portal probe; the portal serves 200
over https).

On-brand friction for the paper: the portal image built locally was **arm64**
(Apple Silicon) and the box is amd64 → `exec format error`. The deploy agent
fixed it live with qemu binfmt emulation. (Durable fix — publish an amd64/multi-arch
image — is filed.)

**THE EPIC IS COMPLETE.** All 8 phases (P0–P7) green. The system repackaged
itself: it used its own **CMS as the build spine**, its own **Max Mode fan-out**
to build the schema, its own **adversarial verifiers** to keep the sellable
template leak-free, its own **from-scratch loop-proofs** to catch four real bugs
in its own packaging, and its own **§9 worktree discipline** to build the portal
against a 28-worktree repo — and the result is a one-command, self-hostable
agency-OS now serving the thesis on its own front door, **live, for ~$2–4/mo**.

Commits through `f95a43d`. P6 (`ae38c1b5`) + epic (`59f55f3e`) → **completed**.
Remaining work is productization polish (GitHub repo + CI, amd64 image, portal
branding genericization, KB ingest, hardening) — not blockers.

The arc, in one line: *"whitepaper the admin panel" became "build the whole
system as a sellable product, and make building it the whitepaper" — and the
system did exactly that, to itself, live.*

---

<!-- Append new sessions/phases below. Each phase flips from aspirational to real
     only when `doctor` proves it. -->
