# Muster: Plugin Repositioning and Site Rebuild. Design Spec

**Status:** Approved (verbally) 2026-07-15 · **Owner:** Mike Walliser · **CMS:** project `0ef5827c-924d-4c2a-a769-d9d7c84097e1`

## 1. Why this exists

The current musterr.dev homepage is a whitepaper-as-landing-page. It is a strong
artifact and it answers the wrong question. It explains **how Muster was built**
("it built itself, in 2.5 hours") to a reader who has not yet been told **why
they would use it**. Mike's words: "I don't feel like this verbiage is very human
readable as to why someone should use this."

Two decisions follow, both made 2026-07-15:

1. **Muster becomes a real Claude Code plugin.** Not a marketing label on a
   Docker stack: an installable plugin with a manifest, commands, and a skill.
   The claim has to be true before the homepage makes it.
2. **The homepage is rebuilt for Claude Code developers.** Problem-first. The
   build-log narrative moves to `/about`, where it becomes credibility rather
   than the opening pitch.

## 2. The problems Muster solves

This section is the raw material for the homepage, and it is also the honest
answer to "I built this for my needs, so is it worth something to anyone else?"

### 2a. The universal problems (any serious Claude Code user has these)

- **Agents forget everything between sessions.** The rolling context window *is*
  the project memory, so the project's memory is as durable as a browser tab.
  Close it, and the next session re-reads files it already understood and
  re-litigates decisions it already made.
- **"What's actually done?" has no durable answer.** Status lives in a
  transcript, which is single-threaded, unaddressable, and gone at the context
  boundary. There is no stable handle for "the decision about the schema."
- **Parallel agents clobber each other.** Point two agents at one checkout and
  they silently overwrite each other's work. Parallelism without a shared place
  to coordinate is just faster chaos.
- **You re-explain your standards every session.** Commit format, branch rules,
  secret hygiene, what "done" means. A stateless model re-derives them, or
  drifts. Written rules loaded every session are what make it behave like a
  long-lived teammate.
- **Agents optimize toward "done", not done.** They mark work complete that
  isn't. Only a durable record plus an explicit verify step separates *done*
  from *claimed done*.
- **Work gets duplicated.** With no shared record, agent B redoes what agent A
  already did, or files the same issue twice.
- **Lessons don't accumulate.** Hard-won knowledge (the gotcha, the root cause,
  the trap) dies at the session boundary unless something outside the window
  catches it.
- **There is no audit trail for machine-written work.** What did the fleet
  change, when, and on whose instruction?

### 2b. The problems that are narrower (real, but not universal)

- **A human-watchable surface for non-technical stakeholders.** The portal
  matters most if someone who will never open a terminal needs to see progress.
  A solo dev may not care.
- **Client-facing delivery** (invoices, deals, proposals, releases as a client
  artifact). This is the agency layer. **It is genuinely Mike's need, not
  everyone's**, and the spec should stop pretending otherwise.

### 2c. What Muster does NOT solve (state this on the page)

- It does not make the model smarter. It is an operating system around the
  model, not a better model.
- It is overkill for a single-file fix or anything that fits one window. There
  is a real token premium on every run, paid whether or not the verifiers find
  anything.
- Your own stack needs Docker. The plugin against a hosted board does not.

### 2d. The strategic read (why the plugin framing is the right narrowing)

The **coordination core is universal**; the **agency layer is Mike's**. The
plugin framing ships exactly the universal part (a board your agents read and
write, a protocol, a constitution, memory) and leaves the agency stack as the
"and there's a whole system behind it" upsell. Scratching your own itch
generalizes precisely to the extent that the itch was coordination, and it was.

### 2e. Evidence these problems are real (from the 2026-07-15 session itself)

Not hypotheticals. Every one of these happened in a single working session, and
they are in the transcript and the board:

| What happened | The problem it demonstrates |
|---|---|
| Filed task `18b8ad89`, a duplicate of existing `a1bce112`, because the board was not checked first. Caught only by walking the board afterwards. | Duplicated work with no shared record (2a). The board is what caught it. |
| A stale note in the CMS v1.22.0 release row ("AEFE stuck at v1.21.0", true on 07-12, false by 07-13) propagated a **false claim into a public GitHub release**. | Knowledge rots; durable notes are snapshots, not facts (2a, lessons). |
| Six parallel auditors all probed `app.musterr.dev/login`; **none probed `/`**, the one URL every CTA points at. The bug shipped to Mike, not to the audit. | Disjoint dispatch without a shared checklist has blind spots. Fan-out is not coverage. |
| The audit worktree silently sat on a **stale local `main`** (8ec9572 vs origin 815e309); files looked unmodified that were not. | Shared checkouts drift under you (2a, collisions). |
| `publish-images` reported **green on all four release tags while never publishing the portal**, because a gate-skip exits 0. | Agents and CI both report success for the wrong reason; verification needs to assert the artifact. |
| `rag.analogelk.com` Caddy block was hand-added to a box, **never committed**, and silently wiped by a later repo sync. Prod semantic search went dark unnoticed. | Config outside the durable record has a half-life. |

The honest note: Muster's board would have prevented row 1 and row 4 and made
rows 2 and 6 discoverable. It would **not** have caught rows 3 and 5 on its own;
those need a verification discipline, which is a separate organ. Say so.

## 3. The plugin

### 3a. What it is

`claude-os/` already contains the plugin's parts. Today `wire` renders them into
a single deployment. The plugin makes them installable. The mapping:

| Today (`claude-os/`) | Becomes |
|---|---|
| `profiles/*/CLAUDE.md.tmpl` (the constitution) | `skills/muster-protocol/SKILL.md`: claim, work, verify, close |
| `mcp.json.tmpl` | `.mcp.json`, written by `/muster-connect`, token by env reference |
| `hooks/cms-task-snapshot.sh` | `hooks/hooks.json` SessionStart: board state on boot |
| `memory-seed/` | scaffolded by `/muster-connect` |

Prior art is in this monorepo: `analog-elk-v3` is a working Claude Code plugin
(`.claude-plugin/plugin.json` + `commands/` + `agents/` + `hooks/` + `skills/`).
Follow its structure.

### 3b. Command surface

| Command | Does | Needs Docker? |
|---|---|---|
| `/muster-connect <directus-url>` | The on-ramp. Writes `.mcp.json`, proves the loop by reading `os_tasks` back. | **No** |
| `/muster-board` | What is open, claimed, in review, done. | No |
| `/muster-up` | Stands up the stack (wraps `bin/elk-os up`). | Yes + repo |
| `/muster-doctor` | The green/red acceptance board. | Yes + repo |

### 3c. The boundary that makes this honest

**The client half works with zero Docker.** `/plugin install` followed by
`/muster-connect https://cms.musterr.dev` gives a developer working agents
against a real board in under a minute. That is what makes "install the plugin"
a real call to action rather than a label on a compose file. The control half
(`/muster-up`, `/muster-doctor`) is the growth path, not the entry fee.

### 3d. Open item that gates the hero copy

`analog-elk-v3` ships `plugin.json` but **no `marketplace.json`**, so the true
install incantation is unconfirmed. `/plugin install muster` may require
`/plugin marketplace add AnalogElk/muster` first. **This is the single most
load-bearing string on the homepage.** Verify against current Claude Code docs
during Phase 1 and let the hero use whatever is actually true, even if it is two
lines. Do not ship a one-liner that does not work.

## 4. The site

### 4a. Information architecture

```
/              product     NEW: problem-first, dev audience
/about         the story   today's build-log, retitled + trimmed intro, links to the paper
/paper.html    whitepaper  unchanged
/privacy.html  unchanged
```

### 4b. Homepage structure

1. **Pain.** Name the failure a Claude Code user recognizes instantly: agents
   forget, agents collide, nobody knows what is done.
2. **The fix, in one line.** Chat is where agents think; it is a terrible place
   to track work. Muster gives them a board they do not forget, and one you can
   watch.
3. **Proof.** The real board, one click, read-only. The live exhibit, not a
   mockup.
4. **Install.** The verified incantation (3d) plus `/muster-connect`.
5. **The honest catch.** Docker for your own stack; the demo needs nothing.
   What it does not solve (2c).
6. **Depth.** Links to `/about` and the whitepaper for the people who want the
   receipts.

### 4c. Voice

House rules hold: flat and factual, **no em dashes**, no hype words. The honesty
is the brand; a page that overclaims to Claude Code developers will be checked
within a minute and it will be checked by exactly the audience we want.

## 5. Sequencing

**Phase 1: the plugin.** Manifest, commands, skill, hooks, MCP wiring; verify
the install flow end to end against a clean environment.

**Phase 2: the site.** New homepage, `/about`, nav, deploy.

Order matters and is not negotiable: the hero *is* the install line, so the
commands must exist and be named before the copy can be true. Building the site
first means shipping a page that lies until Phase 1 lands.

## 6. Success criteria

- A developer with Claude Code and no Docker can install the plugin, connect to
  the demo board, and have an agent claim and close a real row.
- The homepage's install line works verbatim on a clean machine.
- The homepage names at least one problem that a Claude Code user recognizes as
  their own within the first screen.
- Nothing on the page overclaims. Every capability named is reachable.
- `/about` preserves the build-log narrative; `/paper.html` is unchanged.

## 7. Out of scope

- Rebranding the portal image's own marketing routes (CMS task `983cd69b`).
- Fixing GHCR package visibility (`e3b3fc2e`) or portal image publishing
  (`61988501`), though both weaken the self-host story and should be sequenced
  soon after.
- The agency layer (invoices, deals, proposals) as a pitch. It stays in the
  product, out of the homepage's first screen.
