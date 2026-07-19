---
description: Point Claude at a Muster board (Directus os_tasks) and prove the loop by reading real rows back.
---

# Connect to a Muster board

The user's board URL is "$ARGUMENTS" (may be empty; if so, use the configured
`directus_url`, defaulting to https://cms.musterr.dev).

Do this in order:

1. Confirm the board answers at all:
   `curl -sS -o /dev/null -w '%{http_code}' <url>/server/health`
   A 200 means the board is reachable. Anything else: stop and report it
   plainly, do not continue.

2. Prove the loop. Read real rows back through the configured MCP connection
   (`muster-board`): fetch a few `os_tasks` rows with their `name` and `status`.

3. Report what you found: how many rows, and a one-line summary of the board's
   state. If the read returned nothing, say so; an empty board and a broken
   connection are different problems and must not be reported the same way.

4. Tell the user what they can do next: `/muster:board` to see the board, and
   `/muster:up` if they want their own stack instead of this one.

Never print the token. If a step would render it, do not run that step.
