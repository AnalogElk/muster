# Muster seed scripts → golden-locked shared Directus client

- **Date:** 2026-07-27
- **Status:** Approved (design), pre-implementation
- **Branch / worktree:** `chore/muster-seed-shared-client` in `.claude/worktrees/muster-seed-client` (off `origin/main` @ 83ecf5b)
- **Repo:** `github.com/AnalogElk/muster` (this repo *is* the Muster demo tenant)

## Problem

The Muster demo tenant (`cms.musterr.dev`) is populated by a large, accreted
pile of Python provisioning scripts under `provision/` and `provision/seed-full/`
(~52 `.py`). Every script re-implements the same three concerns, and they have
**drifted** apart:

- **env-loading** — `load_env()["DIRECTUS_ADMIN_TOKEN"]` in most, `ENV[...]` in
  `seed-D5`/`seed-F3`, read inline in `seed-F1` (47 scripts define their own
  `load_env`).
- **request** — `def req(...)` in ~33 scripts vs `def request(...)` in ~6, with
  divergent signatures, timeouts (45/60/120s), retry counts, and error modes
  (some swallow HTTP errors and return a tuple, some raise).
- **upsert** — a `def upsert(coll, filters, payload)` in ~10 scripts; inlined in
  the rest.

`BASE` is sometimes hard-coded `"https://cms.musterr.dev"`, sometimes
`os.environ.get("DIRECTUS_URL", "https://cms.musterr.dev").rstrip("/")`.

We want a single shared client — but we must not change behavior while doing it.
The scripts are the historical record of how the demo was built; a subtle change
in request ordering or JSON serialization could silently corrupt a future
re-seed.

## Goal

Extract the duplicated env-loading / request / upsert logic into **one
configurable shared client module per language**, porting each script to it,
and **prove behavior is unchanged** by pinning each script's exact HTTP request
sequence as a golden test against a stubbed transport. A port is accepted only
when its recorded request sequence is **byte-identical** to the pre-port golden.

## Scope

**In (Python, ~49):** every `provision/*.py` + `provision/seed-full/*.py` that
performs HTTP to Directus — the `seed-D1..D6` / `seed-F1..F4` seeders, the
`gapfix-*`, `run2-*`, `probe-*`, `insights-seed`, plus `seed-demo.py`,
`re-add-kb.py`, `demo-readonly-role.py`. Read-only probe scripts are included;
their GET-only sequences get locked too.

**In (TypeScript, 3):** `portal/.build/scripts/seed-{acme-invoices,help-articles,kb}.ts`.

**Out (explicit):**
- 4 `.js` scripts (`gapfix4-shots.js`, `fixed-client-shots.js`,
  `gapfix-shots-thc.js`, `render-logo-pngs.js`) — Playwright/canvas
  screenshot & PNG-render tools, not Directus seeders.
- 3 no-HTTP `.py` (`env-wire-run2.py`, `set-portal-image.py`,
  `set-portal-image-csp2.py`) — no request sequence to lock, nothing to port.
- **Non-HTTP side effects** (file writes, shell-outs) are outside the request-
  sequence golden. That logic is preserved untouched, not locked.

## Mechanism (identical shape in both languages)

Run each **real, unmodified** script as a subprocess under a harness that:

1. **Stubs the transport** with a recorder + deterministic synthetic responder.
   - Python: monkeypatch `urllib.request.urlopen` / the opener.
   - TS: an `--import` preload replacing global `fetch`.
   - The responder returns Directus-shaped canned replies keyed by
     `(method, path)`: `GET` list → `{"data": []}` or a seeded row; `POST` →
     `{"data": {"id": <counter>, ...echo}}`; `PATCH` → echo; `/auth/login` →
     canned. Per-script fixture overrides where a script needs a specific shape
     to proceed. **No network, ever.**
2. **Freezes non-determinism** — `time` / `datetime` / `uuid` / `random` (Py)
   and `Date` / `Date.now` / `Math.random` / `crypto.randomUUID` (TS) pinned to
   fixed values; `sleep` → no-op.
3. **Injects a FAKE token** (`DIRECTUS_ADMIN_TOKEN=SEED_TEST_TOKEN`) via a temp
   `$HOME`/env, so goldens carry a dummy `Bearer`, never the real secret
   (DevProd §2).
4. **Records the request sequence** to a JSONL golden — per request:
   `{seq, method, absolute_url, headers(canonical), body_bytes, body_sha256}`.

Python scripts run via `runpy.run_path(script, run_name="__main__")` because 40
of 55 have no `if __name__` guard (they execute at import). TS scripts run as
`tsx script.ts` subprocesses (all three auto-run `main()`).

### Definition of "byte-identical"

Same **ordered sequence** of `(method, absolute URL, canonical headers, exact
body bytes)`. Header comparison is canonical (sorted map; `Authorization`
normalized to the fake `Bearer`); raw order recorded for reference. **Body-byte
fidelity is the load-bearing part** — the shared client's `json.dumps` must
match each script's original serialization exactly (default separators, no
`sort_keys`, same key order). The golden diff catches any drift.

## Shared client (one configurable module per language)

`provision/seed-full/_client/directus_client.py` and a TS twin. Because the
current helpers diverge, the client exposes a small **explicit config surface** —
`base`, `token`, `timeout`, `retries`, `error_mode` (raise vs return-tuple),
plus `upsert(coll, filters, payload)`. Each ported script instantiates it to
reproduce its old behavior exactly.

**We preserve current behavior byte-for-byte — even where it is inconsistent or
buggy.** Any genuine fix is filed as a separate follow-up (`os_tasks`), never
smuggled into a port.

## Workflow (safety net first)

1. Build harness + responder + determinism shims.
2. **Generate & commit goldens for ALL in-scope scripts from the _current_
   code.** This is the net; nothing is refactored yet.
3. Extract `directus_client.py`; unit-test it in isolation.
4. **Port one script at a time:** rewrite to the shared client → re-run harness →
   accept **only if** its golden is byte-identical → atomic commit per script.
   Reject → fix or revert.
5. Repeat 3–4 for the TS twin. `portal/.build` must first be regenerated into
   the worktree via `portal/prepare-context.sh` (it is gitignored and absent in
   a fresh worktree).
6. CLOSE TASK ceremony (os_tasks, KB, memory, release, token-ledger sync).

The port phase (step 4, ~49 independent scripts) is a natural Workflow fan-out:
each agent ports one script and must pass its golden. The foundation (1–3) is
built sequentially first.

## Isolation

Dedicated worktree off fresh `origin/main`, created after a §9 collision check
(clean — no active Muster worktree touches `provision/` or the seed `.ts`). All
work lands on `chore/muster-seed-shared-client`.

## Approaches considered

- **A — subprocess characterization + synthetic responder (CHOSEN).** Runs the
  real, unmodified script for the baseline; deterministic; no network; no
  secrets; stdlib-only (Py) / vitest (TS). Cost: building the responder to carry
  each messy script far enough to exercise its helpers.
- **B — VCR/cassette replay.** Rejected: recording real responses would mutate
  the live `musterr.dev` demo and requires the real admin token (secret-handling
  risk); server timestamps are non-deterministic.
- **C — refactor-then-eyeball.** Rejected: no proof of byte-identity, which is
  the entire point.

## Risks / caveats

- **Responder-to-completion is the real labor.** Where a script can't be driven
  to completion, its golden locks the exercised prefix — still a valid
  byte-identical bar for that script's port.
- **`portal/.build` is throwaway.** Gitignored and regenerated by
  `prepare-context.sh`; the TS half is a prototype here unless later upstreamed
  to `analog-elk-front-end` (explicitly Mike's call).
- **JSON serialization drift** is the most likely source of a failed port; the
  shared client must replicate each call site's serialization precisely.

## Success criteria

- Every in-scope script has a committed golden request sequence.
- One shared client module per language; each ported script uses it.
- Re-running the harness after each port yields a byte-identical golden.
- Full local test run green before any push (DevProd §11).
