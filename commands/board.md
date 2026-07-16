---
description: Show the current state of the Muster board: what is open, claimed, in review, and done.
---

# The board

Read `os_tasks` through the `muster-board` MCP connection and show the user
where the work stands.

If "$ARGUMENTS" is non-empty, treat it as a filter (a status, an assignee, or a
search term) and narrow to that.

Group by status and show, per row: the short id, the name, and who has it.
Lead with what needs attention (in progress, in review) rather than the full
list. If the board is empty, say so plainly rather than showing an empty table.

Do not modify anything. This command reads.
