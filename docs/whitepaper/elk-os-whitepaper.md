# Elk OS: The Task Record Is the Coordination Substrate

### How a governed fleet of AI agents built, and publicly shipped, the product that packages its own governance, in roughly 2.5 hours on a $3-a-month box

**A field report by Mike Walliser · 2026-06-29**

*Working name: "Elk OS." It began as an internal tool for my agency, Analog Elk; Analog Elk is now the case study, not the headline. This is an operating system for agentic software teams.*

*Live: [the portal](https://34.220.64.149.sslip.io) · [the build's own task board](https://cms.34.220.64.149.sslip.io). Note on the links: the demo runs on a `sslip.io` host with a certificate your browser will warn about before letting you through. That warning is the cost of a $3 box, not a security claim. Treat the TLS as "reachable," not "trusted."*

---

## Abstract

On the evening of June 29, 2026, an empty git repository became a live, internet-reachable, self-hostable software product. The arc from scaffold to public demo took about 2.5 hours of wall-clock (17:56 to 20:23 Pacific), spanned 8 phases, 27 commits, and 90 files, and was executed by a governed fleet of roughly 30 Claude subagent invocations that consumed over 2 million tokens. The result runs on a single AWS instance for about $2 to $4 per month, and you can open it right now.

That an agent fleet can emit 90 files quickly is not the interesting part. Volume is unfalsifiable and ages badly. The interesting part is the apparatus that let a long, multi-session, ship-grade build hold together without a human reviewing every diff, and the fact that the system used that apparatus on itself. Elk OS used its own task board as the build's spine, its own parallel fan-out to construct one of its own subsystems, and its own adversarial verifiers to keep its own sellable template clean.

This paper makes one architectural claim and defends exactly it:

> **The task record, not the chat transcript, is the coordination substrate between a human and a fleet of AI agents.**

Two honesty notes up front, because the rest of the paper depends on them. First, the contribution here is not new primitives. Claude Code already ships subagents, a session-loaded `CLAUDE.md`, and worktree support. The contribution is **assembling existing primitives into a coordination architecture anchored on a durable task board**, and reporting what that buys. Second, this is **n=1**: one build, by the tool's author, of the tool itself, the single most favorable possible case. Read it as an existence proof and a reasoned playbook, not a controlled study. I did not run the control, and I will say so again where it matters.

---

## 1. The problem: a bigger context window did not solve coordination

The baseline I am comparing against is not a strawman product. It is a **workflow**: a single agent, one rolling context window, working a session at a time, with no shared task store, no cross-session memory, no parallel fan-out, no adversarial verification, and no enforced collision discipline. Call it the ungoverned single-agent workflow. It is genuinely excellent for a large class of work. It is also structurally weak at a different class, and the weakness is a coordination weakness, not an intelligence weakness:

- The rolling window *is* the project memory, so the project's memory is as durable as a browser tab.
- A build that spans days re-reads files it already understood and re-litigates decisions it already made.
- One agent is one perspective on one timeline. You cannot attack a problem from several angles at once.
- The builder audits its own work in its own context, sharing every blind spot it is trying to find.
- "Don't commit secrets" lives in a human's head, so eventually it doesn't.
- Point two agents at the same checkout and they silently clobber each other.

The field spent 2025 and 2026 treating the context window as the bottleneck and celebrating million-token windows accordingly. A 1M-token window is still one window, one timeline, one agent. Scaling the window made the single-threaded ceiling more visible, not less. Once subagent fan-out went mainstream and you *could* spawn thirty agents, the unsolved problem stopped being "can they work?" and became "how do they agree on what is done, and stay out of each other's way?" Parallelism without a shared place to coordinate is just faster chaos.

The bottleneck in agentic development is shared, durable, addressable coordination state. The fix is not a bigger window or a cleverer prompt. It is an operating system around the model.

---

## 2. The thesis: the task record is the coordination substrate

Chat is where agents think. It is a poor place to coordinate. A transcript is single-threaded, ephemeral, and unaddressable: there is no stable handle to "the decision about the schema." You cannot run a multi-agent, multi-session build on it, for the same reason you cannot run payroll on a hallway conversation.

Replace chat-as-substrate with a durable, addressable **task record**, a shared board every agent reads, claims, updates, and closes, and the properties invert:

| Property | Task record | Chat transcript |
|---|---|---|
| Addressable | stable ID | a scroll position |
| Durable | survives any session | dies at the context boundary |
| Shared | every agent sees the same row | private to one window |
| Stateful | claim → work → verify → close | undifferentiated text |
| Auditable | the board is the ledger | reconstruct from prose |

A precise claim is worth more than a sweeping one, so let me separate three things the draft of this paper kept collapsing. There is not one atom; there are three substrates with three jobs:

- The **task record** is the *coordination* substrate: claimable units of work.
- **Memory files** are the *knowledge* substrate: lessons not derivable from code or git.
- The **append-only log** is the *narrative* substrate: what happened, in order.

The argument of this paper is about the first one. The other two are necessary support, and I will name them as such rather than folding them into a single slogan.

### 2a. The hard part: what makes "claim" safe?

A CTO's first question is the right one. If the board is the coordination substrate, what stops two parallel agents from grabbing the same row? This is the load-bearing engineering question, and I will answer it honestly rather than wave at it.

Elk OS does **not** rely on the Directus row being magically atomic. It isn't. A row has `assigned_to` and `status`, and the protocol is a compare-and-set: read the row, confirm it is unclaimed, write your identity and an in-progress status, then proceed. But Directus does not give you a true row lock by default, and I have observed the failure this implies: my own working memory carries the note *"version collisions happen across parallel sessions, re-check before bumping."* Two agents *can* race a row and produce a lost update.

In this build, contention was controlled one level up, by **disjoint dispatch**. The orchestrator (me, plus the top-level Claude session) handed each fan-out agent a non-overlapping slice of work, and physical isolation came from worktrees, not from the board. So the precise, defensible claim is this: the task record is where work is *represented, persisted, and audited* across the fleet; staying off each other's toes came from disjoint dispatch and worktree isolation, not from the board solving contention by existing. If you scale past human-arbitrated dispatch, you need real claim semantics (optimistic concurrency with a version check, or a queue in front of the board). I have not built that, and I am not going to pretend the row gives it to you for free.

---

## 3. The apparatus: five organs of an agent operating system

Elk OS is a coordination architecture with named organs. Read it as a transferable mental model; you can build all five on any vendor's stack.

**The spine: the shared task bus.** A Directus 11 instance over Postgres 15, exposing an `os_*` schema (`os_tasks`, `os_sprints`, `os_projects`, `releases`, `repositories`, `organizations`, `contacts`). The human watches it in the portal; the agent fleet reads and writes it over Directus's **native MCP server** at `/mcp`, not custom glue, gated by a single `mcp_enabled` setting. The credential is always an environment reference (`Bearer ${DIRECTUS_ADMIN_TOKEN}`), never a literal, so the real token lives only in a gitignored `.env`.

**The memory: durable cross-session knowledge.** On-disk memory files with a one-line index. Lessons that are not derivable from code or git survive the session boundary here.

**The narrative: an append-only log.** A running build log that records what happened, in order, separate from both state and lessons.

**The muscle: ROI-governed fan-out.** Not "spawn eight agents." A scout surveys the work, an ROI governor decides what is worth parallelizing, and only then do agents spawn with disjoint roles (ground → build → audit → verify) so they decorrelate instead of duplicating.

**The immune system: adversarial verification and loop-proofs.** Independent verifier agents whose mandate is to disprove the builder's claim, plus from-scratch loop-proofs that re-run the one-command install from an empty volume and check the contract holds.

**The constitution: governance as plain-English code.** A numbered, versioned ruleset (`CLAUDE.md` §1 to §10) loaded into every session as non-optional context: secrets are env-only, one trunk equals production, semver is automated, never edit a contested worktree path, and a literal "definition of done" ceremony. The rules are imperative and testable. This is what makes a stateless model behave like a long-lived teammate.

The whole thing stands up with one command. `bin/elk-os` is a resumable, idempotent phase machine (`init → up → migrate → seed → wire → doctor`) whose only hard dependency is Docker. The `doctor` subcommand is the credibility instrument: a green/red board that checks every subsystem from an empty start and exits nonzero on red. It is a from-scratch acceptance test, not a smoke check.

A note on alternatives, because "task board vs raw chat" is a soft target nobody serious argues for. The real competitors to a task board are: git itself (branches and PRs as the unit of work), markdown plan files in the repo (which my own spec-flow kit uses), and framework-managed handoff state (LangGraph, CrewAI, AutoGen). A board earns its place over markdown-plan-files for one reason: it is a **queryable, concurrently-writable, human-watchable** store with a stable ID per unit. Plan files in git serialize fine for one agent but invite merge conflicts the moment several agents update status at once, and they are not watchable in real time by a non-technical stakeholder. A board over a database gives you the query surface and the live human read-side that flat files do not. That is the honest reason to reach for one, and it is a smaller, more defensible claim than "tickets are novel."

---

## 4. The recursion: the system built the thing that ships the system

Every capability Elk OS ships was used to build Elk OS:

| The capability the product ships | …is the capability that built it |
|---|---|
| Directus `os_*` task bus | The build's spine *was* the `os_tasks` board: 8 logged sessions, phase state, and the shipped-vs-aspirational ledger lived in the CMS |
| ROI-governed parallel fan-out | Phase 2 (schema + seed) was built by an 8-agent workflow: ground → fan-out → scrub-audit → 3 leak-verifiers |
| Adversarial verification | Three leak-verifiers scrubbed the generic template clean of its own origin |
| From-scratch loop-proofs | The packaging's own bugs were caught by re-deriving the system from zero |
| Cross-session memory | 7+ sessions held with no context loss across the CMS, on-disk memory, and the log |

I want to be careful about what this proves. Self-use shows the apparatus is **coherent and usable**: it can carry its own non-trivial build. It does *not* prove the apparatus was *necessary* (a simpler path could exist) or *net-positive in dollars* (that is §7's job, and the answer is qualified). This is dogfooding, which is real evidence of fitness and a poor substitute for a controlled comparison. I am downgrading my own earlier phrasing on purpose.

---

## 5. The evidence: what got caught, and by which organ

The fleet caught roughly **7 functional bugs and 6 brand-leak references before shipping**, none caught by a human running the software. That is the headline. But the honest version splits these into two buckets, because conflating them inflates the multi-agent claim.

### Bucket A: clean-room / loop-proof catches (a single disciplined agent could run these too)

These were caught by **from-scratch reproduction and live deploy**, techniques that do not require parallelism or adversarial diversity. I am attributing them to *discipline*, not to *the fleet*, because a single agent that re-derives from zero would also find them. They are still real, and they are still bugs the ungoverned default ships, because the ungoverned default rarely re-runs from an empty volume.

**The instructive one, walked end to end so you can see a receipt rather than take my word.** The RAG service claimed port `:9100`. A naive health check reported "healthy." It was lying: a *different*, already-running engine was answering on that port, and the check was passing for the wrong reason. The trail is on the board: a task row was opened for the RAG bring-up, a loop-proof run in a clean environment (where the impostor process was not present to flatter the check) flipped it red, the closing note recorded the root cause as a co-located listener, and the fix commit pinned the port and hardened the check to assert identity, not just a 200. "Tests pass" and "the system works" are different claims, and an agent watching its own rolling context sees green and moves on. The thing that caught it was not a smarter agent. It was a from-zero environment.

Also in this bucket: a genuine RAG port collision in the compose topology; a `set -e`/`pipefail` bug in `doctor` that would have silently swallowed failures, the exact opposite of a doctor's job; a compose path where turning RAG *off* aborted the whole stack; and an **arm64-vs-amd64 portal-image mismatch** that is invisible in code review and unit tests and only surfaces when real bytes hit a real machine. That last one was diagnosed and fixed live on the box during deploy. A from-scratch agent without a live-deploy loop produces a repo that "should work." This loop produced a box that does.

### Bucket B: fleet-dependent catches (need parallel and/or adversarial agents)

These are the ones that genuinely required more than one decorrelated perspective.

The **six leak-scrubs** are the clearest. Elk OS ships two profiles, `generic` and `analogelk`, and the commercial premise is that `generic` contains zero trace of its origin. A scrub-audit plus three adversarial leak-verifiers found and cleaned 6 real "AnalogElk" / analogelk.com references before they could ship in the sellable template. I will undercut my own rhetoric here, because honesty is the brand: these six are *string-checkable*, which means a deterministic grep or linter would also catch them. So they are strong evidence that an automated provenance gate beats good intentions, and **weak** evidence for *fan-out specifically*. The fan-out's marginal value over a linter shows up only on the paraphrased, non-literal leaks, and those were fewer and softer.

The **seam bugs** are the more honest case for the fleet: a required `releases.repository_id` foreign key missing from the pruned schema snapshot, and AE seed files bare-named and colliding with a kept UI-folder collection. These are integration and packaging bugs that live between subsystems, where a single agent optimizing the file in front of it has no vantage point. Parallel explorers attacking the seams found them.

### The governance facts

- **0 secret leaks.** DB and admin tokens were always env-referenced, never echoed, never committed, and this was grep-verified, not assumed.
- **0 collisions while building the portal from a shared repo carrying 28 active git worktrees.** I want to be precise about *how*: I did not demonstrate collision-handling under load. I **avoided the contention by construction**, building the portal read-only from a pinned archive snapshot rather than from the live contested checkout, per the written §9 rule. That is good discipline and a real result, but it is "sidestepped the race," not "won it."
- **An honest shipped-vs-aspirational ledger,** maintained throughout, the antidote to agentic over-claiming.

### On the fleet's true size

"30+ subagents" deserves a breakdown so the number does not read as inflated. The accounted core is the 8-agent schema workflow and the 5-agent live-pricing cost panel. The remainder were explorers, builders, and verifiers spread across the other phases, several of them single-shot. Not all of them produced kept work: some fan-outs returned partial or discarded output that was retried or dropped, and that wasted production is part of the token cost in §7. I did not instrument a precise discard rate, which is itself a measurement gap I would close on a real product run.

---

## 6. The comparison, stated fairly

The ungoverned single-agent workflow is faster to start, cheaper per token, and the correct choice for a large class of work. The apparatus is a specialization, not a general upgrade.

| Capability | Ungoverned single-agent workflow | Elk OS apparatus |
|---|---|---|
| Cross-session state | one rolling window | durable `os_*` board + disk memory + log |
| Memory | none in practice | memory files + local RAG recall |
| Human↔agent surface | chat transcript | the same Directus rows, watched in the portal |
| Agent↔state transport | ad-hoc tools | Directus native `/mcp` |
| Parallelism | serial by default | ROI-governed fan-out |
| Self-verification | self-checks, shared blind spots | adversarial verifiers + loop-proofs |
| Governance | re-derived per session, drifts | written constitution, loaded every session |
| Secret hygiene | manual | env-only refs, grep-verified |
| Concurrency safety | same checkout, silent clobbers | worktree isolation + §9 discipline |

Every row is an architecture difference. But re-read §5 before you read this table as a clean win: the Bucket A bugs are available to any disciplined single agent that adopts clean-room reproduction, and the strongest leak catches are linter-catchable. The genuinely fleet-dependent value is narrower than the table's nine rows imply. The right summary: the apparatus is the operating system you wrap around the agent, and its incremental value is real but concentrated in persistence (multi-session builds) and seam-level adversarial verification, not spread evenly across every row.

---

## 7. The economics, with the costs firewalled

There are three different costs in this project and the slogans tend to blur them. Keep them apart:

1. **Demo hosting:** ~$2 to $4 per month. This is the AWS box. It is what "cheap" refers to, and it has nothing to do with the cost of *building* the system.
2. **Build model-spend:** the one-time cost of the 2.5-hour build. Over 2M subagent tokens. In dollars this is small in absolute terms but one to two orders of magnitude above the hosting figure.
3. **Ongoing fleet-operating cost:** what it would cost to run this apparatus on your *next* project, which is dominated by token spend and by the human time to govern it.

Now the verdict, stated against my own interest: **the apparatus did not primarily buy speed.**

**Wall-clock: real but secondary, and I will not fake the math.** Parallel fan-out helped, but a large share of the build (scaffold, compose wiring, live-box debugging, packaging) was inherently serial. An honest estimate is that fan-out bought something in the range of 1.5× to 2× on overall wall-clock, with the 8-agent schema phase collapsing far more *on that phase alone*. I am labeling that a rough estimate, not a measurement. I do **not** have a measured parallel fraction, and the precise Amdahl figure an earlier draft of this paper carried was invented. I am removing it rather than dress up a guess as arithmetic.

**Correctness: where most of the value lives.** ~7 functional bugs + 6 leaks = ~13 defects caught, **0 known-shipped as of writing** (I can count catches; I cannot enumerate misses, so "0 shipped" is survivorship and I will not claim it as a hard zero). Why would a linear run ship some of these? Because the single pass that *wrote* the `analogelk.com` reference is the same pass asked to *find* it, error-correlated, so it ships it. The verification layer's job is error decorrelation. With the caveat from §5: my verifiers are the *same base model* with different prompts and temperatures, which is weak decorrelation. They share training-failure modes. The decorrelation is real for surface and seam errors and thin for anything where the base model is confidently and uniformly wrong.

**Durability: the "possible at all" win.** The build consumed over 2M subagent tokens across 7+ sessions. A single window cannot physically hold that; it compacts, forgets, re-reads, re-litigates. By externalizing state into the board, disk memory, and the log, the apparatus turned an impossible-for-one-window task into a resumable one. This is the cleanest win, because it is categorical: a linear run does not finish this build cleanly, it stalls at the context boundary.

**The cost, plainly.** The apparatus spent over 2M tokens, dominated by coordination rather than production: the same artifact read and re-reasoned several times, plus the discarded fan-out output from §5. There is a genuine token premium on every run, including runs where the verifiers find nothing. You are buying insurance, and you pay the premium whether or not you file a claim.

**The caveat I will defend rather than hide.** I did not run the control. I did not build Elk OS twice and measure the delta. "The ungoverned default would have shipped these" is a reasoned argument from the logged catches, not a measured A/B. The bugs and the catches are in the board's history; the counterfactual is inference. I would rather state that than imply a rigor I did not perform.

---

## 8. Limitations: when not to reach for this

**When it is overkill.** A single-file fix, a sub-100-LOC change, a throwaway prototype, anything that fits one window: the ungoverned default is faster and far cheaper, and the memory/board layer is pure overhead. Elk OS itself ships a `/quick` lane for exactly this. If a human reviews every diff, paying several agents to re-derive that judgment is redundant. If the work is genuinely novel and not verifiable, open-ended design with no ground truth, adversarial verifiers add little; they excel only at checkable properties.

**The apparatus's own failure modes.** Correlated blind spots survive fan-out, as §7 conceded. Verification is only as good as what it was built to check; a verifier that greps `AnalogElk` misses a paraphrase, a base64'd token, or a brand reference baked into an image asset. I can log the catches and cannot enumerate the misses. Several caught bugs (the `doctor` pipefail bug, the compose RAG-off abort) were *in the governance machinery itself*: more moving parts, more places to break. And the task-spine as single source of truth is also a single point of coupling, which leads to the next gap.

**The spine is shared mutable state, and I have no graceful-degradation story.** If the board goes down mid-build, the fleet loses its coordination substrate, and I have not built a recovery path beyond "the orchestrator notices and restarts." Two agents *can* race a row (§2a). The board is sold as the solution to coordination while having a coordination problem of its own. On a $3 single-box demo the board is also a literal SPOF, and the live exhibit can 404 if the box hiccups.

**The public-demo posture, stated so you do not assume the worst.** The headline exhibit is a publicly reachable Directus instance. The board is exposed for *reading* the receipt; the admin token that can write it is env-only and not in the client. The honest risk acceptance is mine: this is a disposable demo with seed data, not production, and standing it up at a guessable URL with these specific exposures was a blast-radius judgment I made deliberately. If you self-host past a demo, lock the public read surface and never expose the admin instance.

**What still needs a human, non-negotiably.** This is the part I most want a hiring manager to read, so I am putting it in the body rather than a footnote. The reframe, "this is a product, Analog Elk is just the case study," was a product call no agent made. The shipped-vs-aspirational ledger exists because a human insisted on honesty and defined what counts as shipped; agents optimize toward "done" and only a human reliably separates done from claimed-done. The arm64/amd64 fix happened live on metal with a human diagnosing. Bounding the fan-out, deciding "this is enough verification," is human ROI governance; the machine will fan out forever. These judgment calls are the leadership content of this build, not a caveat to it.

The break-even rule: the apparatus pays off when the work is **multi-session** (won't fit one window) AND **ships to others** (correctness and leaks matter) AND **can't be continuously human-reviewed**. This build was all three. Miss any one and the ungoverned default is the right tool.

---

## 9. Generalization: build a coordination substrate for your own fleet

One loud caveat first, because every confound in this paper points the same way: this is **one anecdote, self-built, on the most favorable possible case**. The playbook below is reasoned extrapolation, untested elsewhere. Treat it as a hypothesis to falsify on your own work, not a proven method.

With that stated, the five organs are transferable, and none of it is vendor magic:

1. **Pick a durable store.** Any ticket system or database with an API. Make the task row the unit of work, the thing agents operate *on*. Prefer it over markdown-plan-files once more than one agent updates status concurrently (§3).
2. **Give every agent the protocol:** claim → work → verify → close, and build *real* claim semantics if you scale past human-arbitrated dispatch (§2a). Do not assume the row is atomic.
3. **Add an adversarial verify pass** for anything with a hard correctness or commercial boundary: secrets, PII, licensing, branding. Decorrelate the verifiers as much as you can, and know that same-model verifiers share blind spots.
4. **Write the constitution down** as numbered, testable rules loaded into every session.
5. **Enforce worktree isolation.** Every agent in its own branch off fresh trunk; the orchestration root read-only. Cheap to enforce; a clobbered branch is expensive.
6. **Validate by clean-room reproduction**, in CI, on the *target* architecture, because a health check that is green for the wrong reason ships broken systems.

Separate **state** (the task bus) from **lessons** (memory files) from **narrative** (the log), each with its own write cadence. Three substrates with three jobs beat one overloaded window. The principle should outlive these particular tools.

---

## 10. Run it yourself, and watch the spine

The apparatus is open and self-hostable. The one-command flow is the whole pitch, and the `doctor` board at the end is the credibility instrument:

```
bin/elk-os init      # scaffold + env
bin/elk-os up        # compose core (Directus, Postgres, RAG, portal)
bin/elk-os migrate   # apply os_* schema
bin/elk-os seed      # profile data (generic | analogelk)
bin/elk-os wire      # enable native MCP, mint env-referenced token
bin/elk-os doctor    # green/red from-scratch acceptance board
```

The repository ships `bin/elk-os`, the `CLAUDE.md` §1 to §10 constitution (the single most reusable artifact in this package, and the one I would copy first), the two profiles, and the compose topology. The repo link lives on the demo homepage alongside this paper.

An empty repository became a live, self-hostable product in about 2.5 hours, governed end to end by its own task board, hosted for a few dollars a month, and you can poke the real thing now. The [portal](https://34.220.64.149.sslip.io) is the human read-side of the loop. The [Directus board](https://cms.34.220.64.149.sslip.io) is the spine itself: open it and you are looking at the actual coordination substrate of *this build*, the same `os_tasks` rows the fleet claimed, worked, and closed to bring the system into existence.

The model is stateless; the organization around it does not have to be. That is the whole argument. The next generation of dev tools will not compete on model quality, which commoditizes. They will compete on the operating system around the model, and the task record is its coordination substrate. Make the ticket the unit of work, and the chat becomes disposable.

It built the thing that ships itself. Go watch the spine.

---

*Mike Walliser is a creative technologist and AI-systems builder. The homepage you are reading is itself the deliverable: a static field report that survives the live system being down, with the running system one link away. Elk OS is the headline; Analog Elk is the first install.*