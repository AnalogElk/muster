---
description: Stand up your own Muster stack (Directus board, portal, RAG) with Docker. Wraps bin/elk-os.
---

# Stand up a Muster stack

This needs Docker running. It uses the `bin/elk-os` that shipped with this
plugin, so the CLI itself needs no separate checkout. The portal is a separate
matter. Its image is private and its source is not public, so a fresh copy gets
the Directus record layer only. The portal is shown in the live demo and is not
yet public. The default `.env` has `ELK_OS_WITH_PORTAL=true`, and `up` stops
without a portal source. After `init` writes `.env`, edit it and set
`ELK_OS_WITH_PORTAL=false` before `up`.

1. Check Docker is reachable: `docker info` (if it fails, stop and say so; do
   not continue).
2. From `${CLAUDE_PLUGIN_ROOT}`, run the phases in order, reporting each:
   - `./bin/elk-os init --profile generic` (skip if `.env` already exists)
   - `./bin/elk-os up`
   - `./bin/elk-os migrate`
   - `./bin/elk-os seed`
   - `./bin/elk-os wire`
3. Finish by running `/muster:doctor` and showing the result.

Every phase is idempotent, so re-running is safe. If a phase fails, stop at that
phase and report its actual output. Do not continue past a red phase and do not
summarize a failure as a success.

Secrets are generated into a gitignored `.env`. Never print them.
