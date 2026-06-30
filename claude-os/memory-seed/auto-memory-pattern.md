# The auto-memory pattern

Claude is stateless across sessions. This `.claude/memory/` directory is how an
Elk OS deployment keeps hard-won context between sessions — the durable
counterpart to the live `os_tasks` board in Directus.

## The split
- **`os_tasks` (Directus)** — the *shared, structured* substrate. Both the human
  (via the portal) and the agent fleet (via the MCP server) read and write it.
  Anything that is a unit of work lives here, not in a memory file.
- **`.claude/memory/` (this dir)** — the *agent's private notebook*. Durable
  lessons, gotchas, and orientation facts that are not work items and would
  otherwise be re-derived every session.

## When to write a memory
Write or update a memory file when a session learns something **non-obvious and
not derivable from code or git history**:
- a root cause and the fix that actually worked,
- a measurement trap or a counter-intuitive default,
- a load-bearing fact about how this deployment is wired.

Do **not** write a memory for: a unit of work (→ `os_tasks`), something obvious
from the code, or a question for the human.

## The discipline
1. Write the lesson in a topic file in this directory (e.g. `stack.md`).
2. Add a **one-line** pointer to `MEMORY.md` under the right heading
   (keep it under ~200 chars; the index is scanned, not read in full).
3. Use **absolute dates** (YYYY-MM-DD), never "yesterday" / "last week".

## Closing a piece of work
When a meaningful task ships, close the loop in BOTH places:
- mark the `os_tasks` row done (status, completion notes) — the human sees it in
  the portal;
- if a durable lesson came out of it, record it here and index it in `MEMORY.md`.

That two-place close is what makes the human <-> agent loop legible from either side.
