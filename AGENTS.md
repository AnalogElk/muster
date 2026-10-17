# AGENTS.md

Before doing anything else, read `~/Desktop/DevProd/AGENTS.md` and follow it. It holds the session rules for every repo under `~/Desktop/DevProd/`: secrets go to the clipboard and are never printed, work happens in your own worktree, run tests locally before pushing, and the CMS task and release rules. Codex only loads AGENTS.md files from this repo's root down, so it never reads that parent file unless this one points to it. If the file does not exist (you are not on the maintainer's machine), ignore this pointer.
