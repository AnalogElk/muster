---
description: Run the Muster green/red acceptance board against your stack.
---

# Doctor

Run `${CLAUDE_PLUGIN_ROOT}/bin/elk-os doctor` and show the user the board
verbatim.

`doctor` exits non-zero on any red row. Report the exit code honestly: a red
board is the useful answer, not something to soften. For each red row, surface
the next-action hint the tool already prints rather than inventing your own.
