# Changelog

All notable changes to Muster (working name: Elk OS, see the
naming note in [`README.md`](./README.md)) are documented here. This file is maintained
automatically by [release-please](https://github.com/googleapis/release-please)
(`release-type: simple`) from [Conventional Commit](https://www.conventionalcommits.org/)
history; do not edit released sections by hand. The version of record lives in
[`version.txt`](./version.txt).

## [0.1.2](https://github.com/AnalogElk/muster/compare/v0.1.1...v0.1.2) (2026-07-02)


### Added

* **site:** copy sweep + musterr.dev cutover ([#6](https://github.com/AnalogElk/muster/issues/6)) ([efe4d3c](https://github.com/AnalogElk/muster/commit/efe4d3c4eea283340379721ea2871a84336865fa))

## [0.1.1](https://github.com/AnalogElk/muster/compare/v0.1.0...v0.1.1) (2026-07-02)


### Fixed

* self-optimize refine pass (correctness, security, docs, copy) ([#3](https://github.com/AnalogElk/muster/issues/3)) ([ca2c46f](https://github.com/AnalogElk/muster/commit/ca2c46f3f66dac2cd88ae758a92e1d858038d776))

## 0.1.0 (2026-06-30): the first packaged cut

The initial self-host packaging of Elk OS. Phases P0–P5 stood up the whole loop;
P7 wraps it as a distributable product. One `./bin/elk-os up` brings up four
wired subsystems on a laptop or a box, and `./bin/elk-os wire` connects a Claude
Code session to the deployment's own shared task board.

### Added

- **P0: scaffold.** Repo skeleton, the resumable phased CLI contract
  (`init · up · migrate · seed · wire · doctor · down`), and the honesty-ledger
  whitepaper log.
- **P1: compose core.** Postgres 15 + Directus 11.15.1, wired together, with a
  non-interactive admin static-token bootstrap. `init` generates secrets into a
  gitignored `.env`; `doctor` is the green/red runtime acceptance board.
  Dev target binds localhost ports; box target fronts Directus with Caddy + TLS.
- **P2: schema + seed.** A pruned, PII-scrubbed `os_*` schema snapshot applied
  via the Directus schema diff/apply API (idempotent, version-skew tolerant), and
  per-profile seed data (`generic` "Demo Co" / `analogelk`) loaded through an
  idempotent natural-key upsert.
- **P3: RAG knowledge engine.** A local "Claude is the LLM" knowledge base
  (Postgres + Qdrant + Redis + FastAPI) as an additive overlay. Embeddings are
  local (BAAI/bge-small-en-v1.5 via fastembed, ONNX/CPU): no external inference,
  no API key, no quota. `doctor` surfaces the engine's degraded-vs-down signal.
- **P4: portal image.** The Next.js 16 portal (built from a pinned, self-host
  patched `analog-elk-front-end` commit) as a containerized overlay wired to the
  in-network Directus. Marketing content reads committed JSON via
  `USE_STATIC_FALLBACK` so the fresh stack needs no marketing collections.
- **P5: Claude-side OS wiring.** `wire` renders a per-deployment Claude config
  (`CLAUDE.md` constitution, `.mcp.json` for Directus's native MCP server, hooks,
  memory seed, launcher), enables the native MCP server
  (`settings.mcp_enabled`), and proves the loop by reading seeded `os_tasks` back
  through the wired endpoint + token.
- **P7: self-host packaging.** A one-shot VPS provisioner (`provision/`), PaaS
  deploy blueprints (Render / Fly / Railway / Netlify under `deploy/`), a GHCR
  image-publish workflow, automated semantic versioning (release-please,
  `release-type: simple`), a landing-grade README, and a licensing recommendation
  with agency-os attribution (`NOTICE`).

### Notes

- Secrets live only in `.env` (gitignored) and are never printed.
- Docker is the only hard runtime dependency for the box/local install;
  `migrate`/`seed` additionally use stdlib `python3`.
- The schema derives from
  [directus-labs/agency-os](https://github.com/directus-labs/agency-os) (MIT);
  see [`NOTICE`](./NOTICE).
