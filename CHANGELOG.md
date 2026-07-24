# Changelog

All notable changes to Muster (working name: Elk OS, see the
naming note in [`README.md`](./README.md)) are documented here. This file is maintained
automatically by [release-please](https://github.com/googleapis/release-please)
(`release-type: simple`) from [Conventional Commit](https://www.conventionalcommits.org/)
history; do not edit released sections by hand. The version of record lives in
[`version.txt`](./version.txt).

## [0.1.6](https://github.com/AnalogElk/muster/compare/v0.1.5...v0.1.6) (2026-07-24)


### Added

* **analytics:** first-party interaction heatmap beacon ([#26](https://github.com/AnalogElk/muster/issues/26)) ([6fe0686](https://github.com/AnalogElk/muster/commit/6fe0686d472ae4b29461a34859d8debee3d1a9d6))
* **portal:** rebrand-check gate, image smoke test + portal sync design docs ([#22](https://github.com/AnalogElk/muster/issues/22)) ([bb3f649](https://github.com/AnalogElk/muster/commit/bb3f6498855f001ade5e8b7336c6e65bcb1a49eb))


### Fixed

* **security:** security headers on all Caddy sites ([#27](https://github.com/AnalogElk/muster/issues/27)) ([83ecf5b](https://github.com/AnalogElk/muster/commit/83ecf5bc59371578b8590d2749b49998a67f6e80))

## [0.1.5](https://github.com/AnalogElk/muster/compare/v0.1.4...v0.1.5) (2026-07-17)


### Added

* **demo:** full demo population: CSP fix pack, mock integrations, seed toolkit, daily refresh ([#23](https://github.com/AnalogElk/muster/issues/23)) ([68d9c8f](https://github.com/AnalogElk/muster/commit/68d9c8f73df7ab95e60bdfb3a520f6b15e1cf4d6))

## [0.1.4](https://github.com/AnalogElk/muster/compare/v0.1.3...v0.1.4) (2026-07-16)


### Added

* **plugin:** make Muster an installable Claude Code plugin ([#19](https://github.com/AnalogElk/muster/issues/19)) ([340d721](https://github.com/AnalogElk/muster/commit/340d72101a668de41be20fd6e508bcdeb434640f))
* **site:** product homepage, build log moves to /about ([#20](https://github.com/AnalogElk/muster/issues/20)) ([b7eb613](https://github.com/AnalogElk/muster/commit/b7eb61354f2ed8e11acc6dbd7b94810a9282a4b4))


### Fixed

* **caddy:** send app.* root to /login, not the portal image's marketing page ([#18](https://github.com/AnalogElk/muster/issues/18)) ([815e309](https://github.com/AnalogElk/muster/commit/815e30911e1691a1d579be0ce656110840b4ae4a))

## [0.1.3](https://github.com/AnalogElk/muster/compare/v0.1.2...v0.1.3) (2026-07-15)


### Added

* add cookieless Matomo analytics to musterr.dev site ([#9](https://github.com/AnalogElk/muster/issues/9)) ([8eb203b](https://github.com/AnalogElk/muster/commit/8eb203bb47b2fe364121e9512edb4d014751b2de))
* docs currency audit, assistant key passthrough, live-board exhibits ([#15](https://github.com/AnalogElk/muster/issues/15)) ([847d4a0](https://github.com/AnalogElk/muster/commit/847d4a09fb6e1dc20f412ca9f33809abc05c2d83))
* intelligent-layer port (part 1) — hardened engine + portal↔RAG bridge ([#12](https://github.com/AnalogElk/muster/issues/12)) ([53fe661](https://github.com/AnalogElk/muster/commit/53fe661ffec57032a2387ddf48a8f6bcfb9b29c4))
* skip analytics entirely for Global Privacy Control browsers ([#11](https://github.com/AnalogElk/muster/issues/11)) ([8ec9572](https://github.com/AnalogElk/muster/commit/8ec95728f33dec9b67bc7176c1bfbfca99faeccd))
* switch to cookie'd analytics with a privacy page ([#10](https://github.com/AnalogElk/muster/issues/10)) ([7d6a604](https://github.com/AnalogElk/muster/commit/7d6a604c8d58d2d1a41f480a7272ebe409db35ab))

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
