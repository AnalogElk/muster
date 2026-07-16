# Muster Plugin and Site Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Muster repo into a real, installable Claude Code plugin, then rebuild musterr.dev to lead with why a developer would use it.

**Architecture:** The Muster repo root **is** the plugin root. `.claude-plugin/plugin.json` declares it; `commands/`, `skills/`, `hooks/`, and `.mcp.json` sit at repo root alongside the existing `bin/` and `compose/`. This is the load-bearing consequence: installing the plugin clones the whole repo, so `bin/elk-os` and `compose/` come with it and the control commands (`/muster:up`, `/muster:doctor`) work with no separate `git clone`. The client half (`/muster:connect`, `/muster:board`) needs no Docker at all and works against the hosted demo board immediately. Phase 2 rebuilds the site to claim exactly what Phase 1 makes true.

**Tech Stack:** Claude Code plugin format (`plugin.json`, `marketplace.json`, markdown commands, `SKILL.md`, `hooks.json`), Directus native MCP, bash (`bin/elk-os`), static HTML/CSS (`site/`), Python 3 stdlib (`site/build-paper.py`), Caddy on the demo box.

## Global Constraints

Every task's requirements implicitly include this section.

- **Voice: NO em dashes.** Anywhere. Flat, factual, no hype words. The honesty is the brand. Use a colon, a semicolon, or a new sentence.
- **Secrets (CLAUDE.md section 2, hardened 2026-07-15): a secret value must NEVER be printed.** Not to stdout, not into a tool result, not once to check. A `PreToolUse` hook actively denies retrieval commands. Route values to the clipboard (`pbcopy`) and print only a fingerprint. In this plan that means: the Directus token is declared as `userConfig` with `"sensitive": true` (Claude Code stores it in the macOS Keychain / `~/.claude/.credentials.json`) and referenced ONLY as `${user_config.directus_token}`. Never echo it, never commit it, never write it into a tracked file.
- **Plugin paths are NOT configurable.** Only `plugin.json` may live in `.claude-plugin/`. `commands/`, `skills/`, `hooks/`, `agents/`, `.mcp.json`, `scripts/`, `bin/` MUST be at plugin root.
- **Plugin commands are namespaced with a colon**, derived from `plugin.json`'s `name`: `/muster:connect`, NOT `/muster-connect`.
- **Conventional Commits are load-bearing** (release-please derives semver from them). `feat:` minor, `fix:`/`perf:` patch, `feat!:` major. Note `bump-patch-for-minor-pre-major: true` means pre-1.0 `feat:` bumps PATCH.
- **Releases are cut BY HAND.** The enterprise blocks Actions from creating PRs. Recipe is in `.github/workflows/release-please.yml`'s header. Do not "fix" the red X on main.
- **Verify before asserting.** Every claim on the site must be reachable. `claude plugin validate --strict` must pass before any copy references a command.
- **Deploy is scp, not merge.** The box's `~/elk-os/` is a synced tree, NOT a git checkout. Merging deploys nothing. `site/` changes must be scp'd to `ubuntu@18.237.179.39:~/elk-os/site/`.

---

# PHASE 1: The Plugin

### Task 1: Plugin manifest and marketplace, validating

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `.claude-plugin/marketplace.json`
- Test: `claude plugin validate . --strict`

**Interfaces:**
- Consumes: nothing.
- Produces: plugin name `muster` (which fixes the command namespace to `/muster:*`), and `userConfig` keys `directus_url` + `directus_token`, referenced by later tasks as `${user_config.directus_url}` / `${user_config.directus_token}` and by hook scripts as `CLAUDE_PLUGIN_OPTION_DIRECTUS_URL` / `CLAUDE_PLUGIN_OPTION_DIRECTUS_TOKEN`.

- [ ] **Step 1: Write the failing test**

There is no unit-test framework for a plugin manifest; `claude plugin validate` IS the test. Run it now to confirm it fails before the manifest exists:

```bash
cd /Users/michaelwalliser/Desktop/DevProd/elk-os/.claude/worktrees/whitepaper-audit
claude plugin validate . --strict
```

- [ ] **Step 2: Run it to verify it fails**

Expected: non-zero exit, complaining there is no `.claude-plugin/plugin.json` (wording may vary; the failure is the point).

- [ ] **Step 3: Write the manifest**

Create `.claude-plugin/plugin.json`. `sensitive: true` on the token is what satisfies the secrets constraint:

```json
{
  "name": "muster",
  "description": "A shared task board your Claude agents read and write over MCP. They claim work, do it, verify it, and close it. You watch the same rows.",
  "version": "0.1.3",
  "author": {
    "name": "Michael Walliser",
    "url": "https://walliser.me"
  },
  "homepage": "https://musterr.dev",
  "repository": "https://github.com/AnalogElk/muster",
  "license": "MIT",
  "keywords": ["task-board", "coordination", "directus", "mcp", "agents", "rag"],
  "userConfig": {
    "directus_url": {
      "type": "string",
      "title": "Board URL",
      "description": "Directus base URL of the board, e.g. https://cms.musterr.dev",
      "default": "https://cms.musterr.dev"
    },
    "directus_token": {
      "type": "string",
      "title": "Board API token",
      "description": "Directus static token. Stored in your OS keychain, never written to the repo.",
      "sensitive": true
    }
  }
}
```

- [ ] **Step 4: Write the marketplace catalog**

Ship this explicitly rather than relying on auto-discovery, so the marketplace name is deterministic and the install string is stable. Create `.claude-plugin/marketplace.json`:

```json
{
  "name": "muster",
  "description": "A shared task board your Claude agents read and write over MCP.",
  "owner": {
    "name": "AnalogElk",
    "url": "https://github.com/AnalogElk"
  },
  "plugins": [
    {
      "name": "muster",
      "source": "./",
      "description": "A shared task board your Claude agents read and write over MCP."
    }
  ]
}
```

> **Corrected 2026-07-15 against the real validator (Claude Code 2.1.211).** This
> plan originally carried a documentation-derived example that does **not**
> validate. Three things were wrong: there is no top-level `schema` field (the
> real one is `$schema`); `source` is a **bare string** (`"./"`), not a
> `{source, path}` object; and `--strict` promotes "no marketplace description"
> to an error, so the top-level `description` is required. The shape above is
> what actually passes. This is the plan's own Task 7 premise arriving early:
> documentation is not observation.

- [ ] **Step 5: Run the test to verify it passes**

```bash
claude plugin validate . --strict
```
Expected: PASS, exit 0.

If it rejects an unknown field in either file (for example `keywords`, `license`, or `owner`), remove ONLY the rejected field and re-run. Do not invent fields to satisfy it. Record what you removed in the commit body.

- [ ] **Step 6: Commit**

```bash
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "feat(plugin): declare Muster as an installable Claude Code plugin

The repo root is the plugin root, so installing the plugin clones bin/elk-os
and compose/ with it. That is what lets the control commands work without a
separate git clone.

The Directus token is declared as userConfig with sensitive: true, so Claude
Code stores it in the OS keychain and it is referenced only as
\${user_config.directus_token}. It is never printed and never committed."
```

---

### Task 2: The muster-protocol skill

**Files:**
- Create: `skills/muster-protocol/SKILL.md`
- Read for source material: `claude-os/profiles/generic/CLAUDE.md.tmpl`
- Test: `claude plugin validate . --strict`

**Interfaces:**
- Consumes: plugin name `muster` from Task 1.
- Produces: a skill invocable as `/muster:muster-protocol` and auto-invocable by Claude; defines the claim/work/verify/close protocol that `/muster:connect` (Task 3) and `/muster:board` (Task 4) reference.

- [ ] **Step 1: Read the existing constitution for source material**

```bash
cat claude-os/profiles/generic/CLAUDE.md.tmpl
```
This is the distilled ruleset `wire` renders today. The skill is its portable form. Do not invent new rules; carry across what is already there.

- [ ] **Step 2: Write the skill**

Create `skills/muster-protocol/SKILL.md`. Keep it short and imperative; a skill that is not read is not a rule.

```markdown
---
name: muster-protocol
description: Use when working against a Muster board (os_tasks in Directus) - the claim, work, verify, close protocol that keeps parallel agents off each other's toes and separates done from claimed-done.
---

# The Muster protocol

The task record, not this chat, is where work is represented. Chat is where you
think. The board is where the team agrees on what is done.

## The loop

1. **Claim before you work.** Read the row. Confirm it is unclaimed. Write your
   identity and an in-progress status. Then start.
2. **Work.** In your own worktree, off fresh trunk. Never edit a path another
   agent has claimed.
3. **Verify.** Prove the thing does what the row says. Run it, drive it, look at
   the output. "The tests pass" and "the system works" are different claims.
4. **Close with the receipt.** Record what you did, what you proved, and what is
   still open. A closing note with no evidence is not a close.

## The rules that make it hold

- **Check the board before you file.** A row you did not read is a row you will
  duplicate.
- **A blocked or pending note is a claim with an expiry.** Re-verify it live
  before you repeat it. Stale notes propagate into shipped artifacts.
- **Do not trust a green check.** A gate that skips reports success. Assert the
  artifact exists, not that the job exited 0.
- **Secrets are referenced, never printed.** If a value would render, route it
  somewhere else.
- **The row is not atomic.** Two agents can race it. Contention is controlled by
  disjoint dispatch and worktree isolation, not by the board existing.

## When this does not apply

Single-file fixes and anything that fits one window. The board is overhead you
should not pay for work that cannot outlive a session.
```

- [ ] **Step 3: Verify no em dashes**

```bash
grep -c '—' skills/muster-protocol/SKILL.md
```
Expected: `0`. If not, replace each with a colon, a semicolon, or a new sentence.

- [ ] **Step 4: Run the test to verify it passes**

```bash
claude plugin validate . --strict
```
Expected: PASS, exit 0, and the skill is recognized.

- [ ] **Step 5: Commit**

```bash
git add skills/muster-protocol/SKILL.md
git commit -m "feat(plugin): ship the board protocol as a skill

Ports the constitution wire renders today (claude-os/profiles/generic/
CLAUDE.md.tmpl) into a portable skill, so an agent that installs the plugin
gets the claim/work/verify/close discipline without a deployment."
```

---

### Task 3: /muster:connect, the no-Docker on-ramp

**Files:**
- Create: `commands/connect.md`
- Create: `.mcp.json`
- Test: `claude plugin validate . --strict`, then a live run against `https://cms.musterr.dev`

**Interfaces:**
- Consumes: `${user_config.directus_url}` and `${user_config.directus_token}` from Task 1; the protocol from Task 2.
- Produces: a working MCP connection named `muster-board`, which `/muster:board` (Task 4) queries.

- [ ] **Step 1: Write the MCP config**

Create `.mcp.json` at plugin root. Directus 11 ships a native MCP server at `/mcp`, so no custom server process is needed:

```json
{
  "mcpServers": {
    "muster-board": {
      "type": "http",
      "url": "${user_config.directus_url}/mcp",
      "headers": {
        "Authorization": "Bearer ${user_config.directus_token}"
      }
    }
  }
}
```

- [ ] **Step 2: Write the connect command**

Create `commands/connect.md`:

```markdown
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
```

- [ ] **Step 3: Validate**

```bash
claude plugin validate . --strict
```
Expected: PASS, exit 0.

- [ ] **Step 4: Test it live, loading the plugin from this directory**

```bash
claude --plugin-dir .
```
Then in that session run:
```
/muster:connect https://cms.musterr.dev
```
Expected: it reports a reachable board and reads back real `os_tasks` rows. The public demo board is read-only, which is fine; connect only reads.

If the MCP connection fails, check the `${user_config.*}` interpolation first: the token must be supplied through the plugin's config prompt, NOT typed into the chat.

- [ ] **Step 5: Commit**

```bash
git add commands/connect.md .mcp.json
git commit -m "feat(plugin): add /muster:connect, the no-Docker on-ramp

Points Claude at any Directus os_* board over the native MCP endpoint and
proves the loop by reading real rows back. Needs no Docker, so a developer can
install the plugin and have agents working a real board in under a minute.

The token is interpolated from userConfig (keychain-stored) and is never
printed or committed."
```

---

### Task 4: /muster:board

**Files:**
- Create: `commands/board.md`
- Test: `claude plugin validate . --strict`, then a live run

**Interfaces:**
- Consumes: the `muster-board` MCP connection from Task 3.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the command**

Create `commands/board.md`:

```markdown
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
```

- [ ] **Step 2: Validate**

```bash
claude plugin validate . --strict
```
Expected: PASS.

- [ ] **Step 3: Test it live**

```bash
claude --plugin-dir .
```
Then:
```
/muster:board
```
Expected: a grouped summary of the demo board's real rows.

- [ ] **Step 4: Commit**

```bash
git add commands/board.md
git commit -m "feat(plugin): add /muster:board to read board state"
```

---

### Task 5: SessionStart hook, board state on boot

**Files:**
- Create: `hooks/hooks.json`
- Create: `scripts/session-board-snapshot.sh`
- Read for source material: `claude-os/hooks/cms-task-snapshot.sh`
- Test: `claude plugin validate . --strict`, then a live session

**Interfaces:**
- Consumes: `CLAUDE_PLUGIN_OPTION_DIRECTUS_URL` / `CLAUDE_PLUGIN_OPTION_DIRECTUS_TOKEN` (Claude Code exposes `userConfig` to hook scripts as uppercased `CLAUDE_PLUGIN_OPTION_*`), and `${CLAUDE_PLUGIN_ROOT}`.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Read the existing hook for source material**

```bash
cat claude-os/hooks/cms-task-snapshot.sh
```

- [ ] **Step 2: Write the snapshot script**

Create `scripts/session-board-snapshot.sh`. It must fail quietly: a hook that breaks a session is worse than no hook.

```bash
#!/usr/bin/env bash
# SessionStart: print a one-line board snapshot. Never fails the session, never
# prints the token.
set -uo pipefail

URL="${CLAUDE_PLUGIN_OPTION_DIRECTUS_URL:-}"
TOKEN="${CLAUDE_PLUGIN_OPTION_DIRECTUS_TOKEN:-}"

if [ -z "$URL" ] || [ -z "$TOKEN" ]; then
  echo "Muster: no board configured. Run /muster:connect to point at one."
  exit 0
fi

resp=$(curl -sS -m 8 -H "Authorization: Bearer $TOKEN" \
  "$URL/items/os_tasks?filter[status][_in]=in_progress,in_review&aggregate[count]=id" 2>/dev/null) || {
  echo "Muster: board unreachable at $URL (this is a warning, not a failure)."
  exit 0
}

count=$(printf '%s' "$resp" | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin)["data"][0]
    print(d.get("count",{}).get("id") if isinstance(d.get("count"),dict) else d.get("count","?"))
except Exception:
    print("?")' 2>/dev/null || echo "?")

echo "Muster board: ${count} task(s) in progress or in review. /muster:board for detail."
exit 0
```

Make it executable:
```bash
chmod +x scripts/session-board-snapshot.sh
```

- [ ] **Step 3: Wire the hook**

Create `hooks/hooks.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}\"/scripts/session-board-snapshot.sh"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 4: Test the script standalone with no config (the fail-quiet path)**

```bash
env -u CLAUDE_PLUGIN_OPTION_DIRECTUS_URL -u CLAUDE_PLUGIN_OPTION_DIRECTUS_TOKEN \
  bash scripts/session-board-snapshot.sh; echo "exit=$?"
```
Expected: prints `Muster: no board configured...` and `exit=0`. It must never exit non-zero.

- [ ] **Step 5: Validate and test live**

```bash
claude plugin validate . --strict
claude --plugin-dir .
```
Expected: validate PASSes, and the new session prints the board snapshot line at start.

- [ ] **Step 6: Commit**

```bash
git add hooks/hooks.json scripts/session-board-snapshot.sh
git commit -m "feat(plugin): print a board snapshot at session start

Ports claude-os/hooks/cms-task-snapshot.sh into the plugin's SessionStart hook.
Fails quiet by design: an unreachable board warns and exits 0, because a hook
that breaks the session is worse than no hook. Reads the token from the
keychain-backed plugin option and never prints it."
```

---

### Task 6: /muster:up and /muster:doctor, the control half

**Files:**
- Create: `commands/up.md`
- Create: `commands/doctor.md`
- Test: `claude plugin validate . --strict`, then a live run

**Interfaces:**
- Consumes: `${CLAUDE_PLUGIN_ROOT}` and the repo's own `bin/elk-os` (present because the repo IS the plugin).
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the up command**

Create `commands/up.md`:

```markdown
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
```

- [ ] **Step 2: Write the doctor command**

Create `commands/doctor.md`:

```markdown
---
description: Run the Muster green/red acceptance board against your stack.
---

# Doctor

Run `${CLAUDE_PLUGIN_ROOT}/bin/elk-os doctor` and show the user the board
verbatim.

`doctor` exits non-zero on any red row. Report the exit code honestly: a red
board is the useful answer, not something to soften. For each red row, surface
the next-action hint the tool already prints rather than inventing your own.
```

- [ ] **Step 3: Validate**

```bash
claude plugin validate . --strict
```
Expected: PASS.

- [ ] **Step 4: Test doctor live against the repo (Docker not required for the command to dispatch)**

```bash
claude --plugin-dir .
```
Then:
```
/muster:doctor
```
Expected: it runs `bin/elk-os doctor` and reports the board. Red rows are an acceptable result here (no stack is up); the test is that the command dispatches and reports honestly.

- [ ] **Step 5: Commit**

```bash
git add commands/up.md commands/doctor.md
git commit -m "feat(plugin): add /muster:up and /muster:doctor, the control half

Because the repo is the plugin, bin/elk-os ships with the install, so these
drive the stack with no separate clone. doctor reports its exit code honestly:
a red board is the useful answer."
```

---

### Task 7: Verify the real install strings on a clean machine

**Files:**
- Create: `docs/plugin-install-verified.md`
- Test: an actual install from GitHub, not from a local path

**Interfaces:**
- Consumes: everything from Tasks 1 to 6, merged to `main` and pushed.
- Produces: **the verified install incantation**, which is the ONLY string Phase 2's hero may use.

**Why this task exists:** the docs say the sequence is `/plugin marketplace add AnalogElk/muster` then `/plugin install muster@muster`, but that is documentation, not observation. This string is the most load-bearing text on the homepage. Verify it empirically before writing it.

- [ ] **Step 1: Merge and push Phase 1 first**

The install pulls from GitHub, so it cannot verify unpushed work.

```bash
gh pr create --base main --title "feat(plugin): make Muster an installable Claude Code plugin" --body "..."
gh pr view <n> --json baseRefName   # confirm base is main per CLAUDE.md section 8
gh pr merge <n> --squash --delete-branch
```

- [ ] **Step 2: Verify from a clean plugin state**

In a scratch directory (NOT the repo, so nothing is picked up from disk):

```bash
cd $(mktemp -d)
claude
```
Then, in that session, run exactly:
```
/plugin marketplace add AnalogElk/muster
/plugin install muster@muster
```

- [ ] **Step 3: Record what actually worked**

Expected: both succeed and `/muster:connect` becomes available. **If the real strings differ from the above in any way, the real ones win.** Capture them verbatim.

Verify the plugin loaded:
```
/muster:connect https://cms.musterr.dev
```
Expected: reads real rows back from the demo board, with no Docker anywhere.

- [ ] **Step 4: Write the verified strings down**

Create `docs/plugin-install-verified.md`:

```markdown
# Verified install (do not paraphrase)

Verified on <DATE> against github.com/AnalogElk/muster from a clean state.
These exact strings are what the homepage hero must use.

    <PASTE THE EXACT COMMANDS THAT WORKED>

Then, with no Docker:

    /muster:connect https://cms.musterr.dev

Result observed: <PASTE what actually happened, including row count>
```

Replace every placeholder with observed output. If a step failed, record the
failure and fix the plugin before Phase 2. **Phase 2 is blocked until this file
contains commands that were actually run and actually worked.**

- [ ] **Step 5: Commit**

```bash
git add docs/plugin-install-verified.md
git commit -m "docs: record the empirically verified plugin install strings

The homepage hero is only allowed to use strings from this file. Documentation
said one thing; this is what was observed from a clean install."
```

---

# PHASE 2: The Site

### Task 8: Move the build log to /about

**Files:**
- Create: `site/about.html` (from the current `site/index.html`)
- Modify: `site/build-paper.py` (the back-link target)
- Test: local diff + link check

**Interfaces:**
- Consumes: nothing from Phase 1.
- Produces: `/about.html`, which Task 9's homepage links to for depth.

- [ ] **Step 1: Copy the current homepage to about**

Nothing is rewritten. It is the right content for the wrong slot.

```bash
cd /Users/michaelwalliser/Desktop/DevProd/elk-os/.claude/worktrees/whitepaper-audit
git checkout -b feat/site-product-homepage origin/main
cp site/index.html site/about.html
```

- [ ] **Step 2: Retitle it and add a way back**

In `site/about.html`, change the `<title>` to:
```html
<title>How Muster was built: a field report</title>
```
And update the meta description to:
```html
<meta name="description" content="Muster was built by a governed fleet of AI agents in about 2.5 hours, using the coordination apparatus it packages. This is the build log, the receipts, and the honest ledger of what that did and did not buy.">
```
Set the canonical:
```html
<link rel="canonical" href="https://musterr.dev/about.html">
```
In the topbar nav, change the brand link `href="#top"` so it still works, and add a link back to the product page as the FIRST nav item:
```html
<a href="/">Product</a>
```

- [ ] **Step 3: Add an orienting line under the hero**

The build log now needs to explain why a reader is here. Directly after the `hero__lede` paragraph in `about.html`, insert:

```html
<p class="hero__sub mono">This is the story of how Muster got built, by the thing it packages. If you want to know what Muster does for you, start on <a href="/">the product page</a>.</p>
```

- [ ] **Step 4: Point the paper's back-link at about**

In `site/build-paper.py`, the rendered paper links back to `index.html`. That link now means the build log, so retarget it:

```bash
grep -n 'back to the build log' site/build-paper.py
```
Change `href="index.html"` to `href="about.html"` on that line, keeping the label text.

Regenerate:
```bash
python3 site/build-paper.py
```
Expected: `wrote .../site/paper.html`.

- [ ] **Step 5: Verify no em dashes and that links resolve**

```bash
grep -c '—' site/about.html site/paper.html
```
Expected: `0` for both.

```bash
grep -o 'href="[^"]*"' site/about.html | sort -u | grep -v '^href="#' | grep -v 'http'
```
Expected: only `/`, `about.html`, `index.html`, `paper.html`, `privacy.html`, `styles.css`, `assets/...`. Confirm each target exists in `site/`.

- [ ] **Step 6: Commit**

```bash
git add site/about.html site/paper.html site/build-paper.py
git commit -m "feat(site): move the build log to /about

The build log is the right content in the wrong slot: it explains how Muster
was built to a reader who has not been told why they would use it. It becomes
the credibility artifact behind the product page rather than the opening pitch.
Content is unchanged; retitled, given a way back to the product, and the
paper's back-link now points at the build log where it belongs."
```

---

### Task 9: The new homepage

**Files:**
- Modify: `site/index.html` (replaced with the product page)
- Test: local render + link check + the no-overclaim check

**Interfaces:**
- Consumes: **the verified install strings from `docs/plugin-install-verified.md`** (Task 7). Do not write this page from the plan's guesses.
- Produces: the live homepage.

- [ ] **Step 1: Read the verified strings. Do not skip this.**

```bash
cat docs/plugin-install-verified.md
```
The hero uses these verbatim. If this file does not exist or still has
placeholders, STOP: Phase 1 is not done.

- [ ] **Step 2: Build the page on the existing design system**

Reuse `site/styles.css` and the existing band/doc structure from `about.html` so the visual language is unchanged. Keep the same `<head>` block (fonts, Matomo with the GPC guard, favicon), changing only title, description, canonical, and og tags:

```html
<title>Muster: a shared task board for your Claude agents</title>
<meta name="description" content="Your Claude agents forget everything between sessions and clobber each other in parallel. Muster gives them a shared task board they read and write over MCP, and one you can watch. Install the plugin, connect to a board, done.">
<link rel="canonical" href="https://musterr.dev/">
<meta property="og:title" content="Muster: a shared task board for your Claude agents">
<meta property="og:description" content="Agents that forget, collide, and mark things done that aren't. One board fixes the coordination half. Live demo inside.">
```

- [ ] **Step 3: Write the page content in this order**

Follow the spec's section 4b exactly. Copy rules: no em dashes, no hype words, every claim reachable.

1. **Hero: the pain.** Headline names the failure. Draft:
   - H1: `Your Claude agents forget everything.`
   - Lede: `Every session starts from zero. Two agents edit the same file and clobber each other. "What's actually done?" has no answer that outlives a context window.`
   - The turn: `Muster gives them a shared task board. They claim it, work it, verify it, close it. You watch the same rows.`
2. **Install**, using the verified strings from Step 1, and the connect line:
   `/muster:connect https://cms.musterr.dev`
   with the caption: `No Docker. That is the live demo board, and your agents can read it right now.`
3. **Proof.** The live board screenshot (`assets/muster-board.png`, already the real board) linked to `https://app.musterr.dev`, plus the read-only demo login.
4. **What it solves.** The universal bullets from spec section 2a, as a scannable list. Not all eight; pick the four that land hardest: forgetting, collisions, no durable answer to "what's done", and standards drift.
5. **The honest catch.** From spec section 2c, verbatim in spirit: it does not make the model smarter; it is overkill for anything that fits one window; there is a token premium; your own stack needs Docker, the demo does not.
6. **Depth.** Links to `/about.html` (how it was built) and `/paper.html` (the whitepaper).

- [ ] **Step 4: Verify no overclaiming**

Every command named on the page must exist:
```bash
for c in connect board up doctor; do
  grep -q "muster:$c" site/index.html && ([ -f "commands/$c.md" ] && echo "OK  /muster:$c" || echo "OVERCLAIM: /muster:$c on page, no command file")
done
```
Expected: only `OK` lines. Anything else must be removed from the page or built.

- [ ] **Step 5: Verify voice and links**

```bash
grep -c '—' site/index.html
```
Expected: `0`.

```bash
grep -o 'href="https://[^"]*"' site/index.html | sort -u
```
Then curl each and confirm 200 (or an intended redirect). Every external link on the page must resolve.

- [ ] **Step 6: Commit**

```bash
git add site/index.html
git commit -m "feat(site): rebuild the homepage to lead with why, not how

The old homepage explained how Muster was built to readers who had not been
told why they would use it. This one names the problem a Claude Code user
already has, shows the board, and gives the verified install line.

Install strings are taken verbatim from docs/plugin-install-verified.md, which
records what was actually run, not what the docs claimed. Every command named
on the page has a command file behind it."
```

---

### Task 10: Ship it and verify live

**Files:**
- Deploy: `site/index.html`, `site/about.html`, `site/paper.html` to the box
- Test: live HTTP checks against musterr.dev

**Interfaces:**
- Consumes: Tasks 8 and 9.
- Produces: the live site.

- [ ] **Step 1: Open the PR and confirm its base**

```bash
gh pr create --base main --title "feat(site): product homepage, build log moves to /about" --body "..."
gh pr view <n> --json baseRefName --jq .baseRefName
```
Expected: `main`. Per CLAUDE.md section 8, never merge without confirming the base.

- [ ] **Step 2: Merge**

```bash
gh pr merge <n> --squash --delete-branch
git fetch origin main && git log --oneline origin/main -1
```
Confirm the merge commit is on `origin/main`.

- [ ] **Step 3: Deploy (merging does NOT deploy)**

The box's `~/elk-os/` is a synced tree, not a git checkout:

```bash
scp -i ~/.ssh/elk-os-demo.pem \
  site/index.html site/about.html site/paper.html site/build-paper.py \
  ubuntu@18.237.179.39:~/elk-os/site/
```

If SSH times out, the cause is almost certainly the security group, not a dead
box: add your current IP to `sg-0b255de1b5677e320` port 22.

- [ ] **Step 4: Verify the deploy is byte-identical**

```bash
for f in index.html about.html paper.html; do
  L=$(shasum -a 256 site/$f | cut -d' ' -f1)
  R=$(curl -s https://musterr.dev/$f | shasum -a 256 | cut -d' ' -f1)
  [ "$L" = "$R" ] && echo "MATCH $f" || echo "MISMATCH $f"
done
```
Expected: `MATCH` for all three.

- [ ] **Step 5: Verify nothing regressed**

```bash
for u in https://musterr.dev/ https://musterr.dev/about.html https://musterr.dev/paper.html \
         https://musterr.dev/privacy.html https://app.musterr.dev/ https://cms.musterr.dev/server/health; do
  printf "%-45s %s\n" "$u" "$(curl -sS -o /dev/null -w '%{http_code}' "$u")"
done
```
Expected: `200` for the four site pages and cms health; `302` for `app.musterr.dev/` (it redirects to `/login`, per PR #18).

- [ ] **Step 6: Log it**

Per CLAUDE.md section 1, write the outcome to `os_tasks` (a completed row with `date_completed`, `pr_url`, `feature_url`), and per section 7 append a `releases` row describing what shipped. Muster releases are cut BY HAND: open `release-please--branches--main` as a PR, merge it, then `gh release create` at the merge SHA.

---

## Self-Review

**Spec coverage:**
- Spec 3a (plugin parts mapping): Tasks 1, 2, 3, 5. The `memory-seed/` mapping is intentionally dropped for now; it is not required for the client half to work and adding it would be scope the spec's success criteria do not test. Noted here so it is a decision, not an omission.
- Spec 3b (command surface): Tasks 3, 4, 6. **Command names corrected from the spec's `/muster-connect` to `/muster:connect`**: plugin commands are colon-namespaced from `plugin.json`'s name. The spec's hyphens were wrong.
- Spec 3c (no-Docker boundary): Task 3 Step 4 tests exactly this.
- Spec 3d (the gating unknown): Task 7, which blocks Task 9.
- Spec 4a (IA): Tasks 8 and 9.
- Spec 4b (homepage structure): Task 9 Step 3, in the spec's order.
- Spec 4c (voice): Global Constraints plus explicit `grep -c '—'` checks in Tasks 2, 8, 9.
- Spec 5 (sequencing): Phase 1 is merged and verified (Task 7) before Task 9 may write the hero.
- Spec 6 (success criteria): criterion 1 = Task 7 Step 3; criterion 2 = Task 7 Step 2; criteria 4 = Task 9 Step 4.
- Spec 7 (out of scope): honored. No portal rebrand, no GHCR work.

**Placeholder scan:** The only intentional placeholders are inside `docs/plugin-install-verified.md`'s template (Task 7 Step 4), which exists precisely to be filled with observed output, and the `--body "..."` of `gh pr create`. Task 9 Step 1 hard-blocks on that file being filled in.

**Type/name consistency:** plugin name `muster` (Task 1) fixes the namespace used in Tasks 3, 4, 6, 9. `userConfig` keys `directus_url`/`directus_token` are declared in Task 1 and consumed as `${user_config.*}` in Tasks 1 and 3, and as `CLAUDE_PLUGIN_OPTION_*` in Task 5. The MCP server name `muster-board` is declared in Task 3 and consumed in Tasks 3 and 4.

**Known risk, flagged rather than papered over:** `claude plugin validate --strict` may reject optional manifest fields (`keywords`, `license`, `homepage`, `repository`, `owner`) if the schema is narrower than the docs imply. Task 1 Step 5 handles this by removing only rejected fields and recording it, rather than guessing at the schema.
