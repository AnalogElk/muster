# Elk OS

> **An entire agency operating system, in one command.**
> A human and a fleet of AI agents share one task substrate — Elk OS packages
> the whole loop so you can run it on a fresh box or laptop.

> ⚠️ **Work in progress.** Scaffolding stage (P0). Not yet runnable end-to-end.
> Track real per-phase status in [`WHITEPAPER-LOG.md`](./WHITEPAPER-LOG.md).

## What you get

One `elk-os up` stands up four wired subsystems:

- **Claude-side OS** — a governance constitution, MCP bridge, hooks, and
  persistent memory that turn Claude Code into a standing team member.
- **Directus + `os_*`** — the shared-state bus: tasks, sprints, projects,
  releases. The row a human drags on a board is the row an agent picks up.
- **RAG knowledge engine** — a local "Claude is the LLM" knowledge base
  (Postgres + Qdrant + Redis), no external inference.
- **The portal** — the human surface (admin + client), behind Caddy/TLS.

## Quick start (target)

```bash
git clone <repo> elk-os && cd elk-os
./bin/elk-os init --profile generic   # generate secrets + .env
./bin/elk-os up                       # docker compose up the stack
./bin/elk-os doctor                   # green/red health board
```

Requires **Docker** (the only hard dependency).

## Profiles

| Profile | Stands up |
|---|---|
| `generic` | A blank, unbranded agency-OS seeded with a synthetic "Demo Co" — make it your own |
| `analogelk` | Analog Elk's own branding + demo data (the reference instance) |

## Design

Full spec: [`docs/superpowers/specs/2026-06-29-elk-os-installer-design.md`](./docs/superpowers/specs/2026-06-29-elk-os-installer-design.md).
Architecture: one Docker Compose core + a resumable phased CLI
(`init · up · migrate · seed · wire · doctor · down`). Distributed as a
self-host product (repo + deploy blueprint + published images).

## License

TBD (set at P7).
