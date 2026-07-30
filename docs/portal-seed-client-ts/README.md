# Portal seed-*.ts shared client + golden harness (reference copy)

The TS twin of the Python `provision/seed-full/_client` work: a shared Directus
client for the portal seed scripts (`seed-acme-invoices.ts`, `seed-help-articles.ts`,
`seed-kb.ts`), with a fetch-stub golden harness proving each port is
byte-identical.

## ⚠️ Where this lives

These scripts belong to **analog-elk-front-end**. In this repo they are vendored
under `portal/.build/`, which is **gitignored and regenerated on demand** by
`portal/prepare-context.sh`. The files here are a **committed reference copy**;
the live work was applied and validated inside `portal/.build/scripts/` and is
throwaway until upstreamed. To upstream, copy `directus-seed-client.ts` +
`seed-golden/*` into the analog-elk-front-end repo and apply the same 3 ports.

## Contents

- `directus-seed-client.ts` — shared client: `resolveDirectusEnv()`, `makeApi()`
  (seed-acme's `.data`-unwrapping helper), `directusFetch()` (seed-help/seed-kb's
  raw helper). Bodies are verbatim-preserved from the originals.
- `harness.mts` — deterministic fetch stub: records the request sequence, answers
  from a synthetic Directus responder (same policy as the Python harness), and
  freezes `Date` / `Math.random` / `crypto.randomUUID`. Golden format mirrors the
  Python one (JSONL of `{seq, method, url, headers(canonical, bearer-masked),
  body_b64, body_sha256}`).
- `run-seed.mts` — preload/runner: installs the stub + fixed fake env
  (`DIRECTUS_TOKEN=SEED_TEST_TOKEN`), sets `argv[1]` so `endsWith`-guarded scripts
  run their `main()`, dumps JSONL on exit.
- `seed-sequences.test.ts` — vitest gate: runs each script under the harness and
  asserts byte-identical to its golden.
- `goldens/*.jsonl` — locked baselines (acme 18, help 45, kb 25 requests).

## Run (inside portal/.build)

```bash
cd portal/.build
# regenerate a golden from current code
GOLDEN_OUT=scripts/seed-golden/goldens/seed-acme-invoices.jsonl \
  ./node_modules/.bin/tsx scripts/seed-golden/run-seed.mts "$PWD/scripts/seed-acme-invoices.ts"
# gate all three
./node_modules/.bin/vitest run scripts/seed-golden/seed-sequences.test.ts
```

## Status

All 3 ports validated: **seed-acme-invoices** proven byte-identical pre/post;
**seed-help-articles** + **seed-kb** behavior-preserved by construction (their
`directusFetch` is a verbatim move into the shared client, call sites unchanged)
and confirmed by the deterministic goldens plus the 39 pre-existing pure-function
unit tests still passing.
