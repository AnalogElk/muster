---
description: Stand up your own Muster stack (Directus board, portal, RAG) with Docker. Wraps bin/elk-os.
---

# Stand up a Muster stack

This needs Docker running. It uses the `bin/elk-os` that shipped with this
plugin, so there is nothing to clone.

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
