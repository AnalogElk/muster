# FINAL IDENTITY + HOMEPAGE SPEC — the agent-built agency OS

*This is the decisive, buildable brief. It resolves the four-lens draft against three critique passes (credibility/thesis, identity-sharpness, completeness). Every contested decision is closed here and carried consistently through every section. The product noun is set; the visual identity is decoupled from it; the demo seam is fixed; the perf budget is made real.*

---

## 0. Name decision — RESOLVED, and decoupled from everything downstream

The draft's `Cairn` is rejected. It repeats the exact failure it was chosen to avoid: **Cairn → Cairo** (cairographics.org, one of the most-used 2D libs; plus StarkWare's red-hot ZK language `Cairo` in this precise crowd), it sits in trademark/namespace walls (Cairn Energy, the Cairn wellness startup, `cairn` not greenfield on npm), it smells of exhausted nature-SaaS, and gating publish on a USPTO check contradicts the 2.5-hour velocity ethos. `Quorum` is worse (ConsenSys GoQuorum). Both finalists fail the dev-namespace test they were commissioned to pass.

### The name is `Muster`.

A muster is two things at once, and both map 1:1 to the two real differentiators:

1. **Muster the fleet** — assemble and coordinate a force on command (the governed fan-out / scheduler).
2. **The muster roll** — the durable register every member reports to (the `os_tasks` board as coordination spine + the durable cross-session record).

It is infra-toned (operational, not wellness), recursion-friendly ("the system mustered itself"), clean of the ELK/Cairo/Helm/Bedrock stack-collision landmines, fully decoupled from Analog Elk, and it does not need a sentence to land — people know the word. It gives the whitepaper one ownable noun ("a Muster-style task bus") and pairs natively with the mark and the Ledger Rail below.

- **Category line (name-agnostic, does the explaining):** **"The operating system for agentic software teams."** Lead with **agent**, never **agency**. "Agency OS" is killed: to a dev-tools CTO it pattern-matches to vertical SaaS for marketing shops and re-tethers to the origin we are demoting. Agency is the origin story, never the category. The agency/agentic pun is dead.
- **Tagline (primary):** **"Muster the agents. Keep the receipts."**
- **Tagline (name-agnostic backup, used wherever the noun is uncertain):** **"Every step is verified before it ships."**

### Clearance protocol (DO NOT gate launch on this)

Same-day check only — npm `muster`, `muster.dev` / `muster.sh`, GitHub org `muster-os` / `getmuster`. There is a dormant `muster` JS state lib; treat it as a yellow flag, not a blocker (no CTO will pattern-match to it the way they do ELK/Cairo). Decision rule for any candidate: reject if it (a) phonetically/visually collides with a known dev tool/lib/lang, (b) lacks a same-day-clearable npm + `.dev` + GitHub-org, or (c) actively misleads about category.

- **If a handle is taken:** ship coined fallback **`Mustr`** (deliberate vowel-drop stylization, Resend/Flickr-style; near-certainly greenfield), same mark, same copy.
- **Absolute last resort:** ship as `Elk OS` via the `{{PRODUCT}}` swap — but only with the §0-mandated reframe (this is the one piece the companion whitepaper MUST adopt; see §7).

**Token discipline:** every string below uses `{{PRODUCT}}`. Swapping one token reskins the whole page. **The mark is name-agnostic by construction** (see §5) — there is no "revert to the Antler-DAG" anymore. A name change never breaks the thesis-carrying visual.

---

## 1. Positioning

**One-sentence positioning:**
> **{{PRODUCT}} is a self-hostable operating system for agentic software teams: a coordination architecture — a shared task bus, durable cross-session memory, governed parallel fan-out, and an adversarial verification layer — assembled around a task board so AI agents can build, verify, and ship real production systems. It proved itself by building and shipping itself in about 2.5 hours.**

**Nav/meta length:** *"The governance layer that lets AI agents ship production software — and shipped itself."*

**Audience, in priority order:** (1) CTOs/eng leaders deciding whether agentic AI ships production, not demos; (2) the agentic-AI/dev-tools community, who care about the mechanism; (3) hiring managers (secondary, never the headline) — the page is the credential, read as a system, not a CV.

**The honest contribution (do not overclaim primitives).** Do NOT say "primitives Claude Code lacks." Subagents/Task, `CLAUDE.md`, and worktrees all ship in the base tool — this audience uses them daily and will catch a strawman, which taints everything else. The contribution is **architecture, not primitives: assembling existing capabilities into a coordination system around a durable task board, with governance and adversarial verification layered on top.** The comparison target is therefore named **"an ungoverned single-agent workflow,"** never "out-of-box Claude Code."

**The three proof points — lead with these everywhere:**
1. **It built itself, end to end, in ~2.5 hours.** Empty repo to a live, HTTPS, internet-reachable demo. 8 phases, 27 commits, 90 files, 30+ subagents, 2M+ tokens. Orchestrated, not vibe-coded.
2. **Its own machinery caught real defects before a human saw them** — and we split them honestly into catches any disciplined single agent could reach (loop-proofs, clean-room reproduction, live deploy) versus catches that genuinely needed the parallel/adversarial fleet (the multi-tenant brand-leak scrub, the seam bugs). Honest attribution is the credibility move.
3. **It held 7+ sessions of context with zero loss and zero leaks.** A Directus task board as the spine, on-disk memory, an append-only log. 0 secret leaks (grep-verified). Built the portal alongside a repo with 28 active worktrees without a single collision — by snapshotting out of the contention, not by handling it (state this honestly).

**The retention payload — promote it to near-headline:** **"Governance is the product."** This is the most ownable, most CTO-resonant line in the package and it *is* the thesis (the value is not the prompt, it is the architecture that lets agents ship). Pair it with the attention hook: *"The software that built itself — and shipped."*

**Frame as mechanism + measured specifics, not adjectives.** The community respects reproducible numbers (a live URL they can hit, exact token counts, $2–4/mo) over claims. Position it as the missing OS layer: agents are the CPU; {{PRODUCT}} is the scheduler, memory, and filesystem that make them production-grade. Avoid "framework."

**The thing to keep visible:** the honest "shipped vs aspirational" ledger and the limitations (n=1, self-built, author-run, same-base-model verifiers = weak decorrelation). These are trust assets. Lead with rigor, not magic.

**Thought-leadership mechanics (no résumé smell):** the system is the protagonist; Mike is the architect in the margins. One byline, one short "why I built this" note, no skills list — but the page's own craft is the portfolio (see §5 colophon and §11).

---

## 2. Core build decision

A **standalone static single-page document** (`index.html` + one CSS file + inline SVG, no framework, no build step) that **IS the report.** It deploys as its own artifact at the apex/root — **NOT** a route inside the Next.js portal — so it loads fast, survives the portal being down, prints to a real PDF, and reads like a document, not an app. Portal + board become inner links / live exhibits.

**Perf envelope (corrected — the draft's `<50KB` was impossible with variable Fraunces):**
- HTML + CSS + inline SVG: **≤ 50KB** over the wire.
- Fonts: **3 faces, static weights, subset to the actual Latin glyphs used, ≤ 90KB total**, loaded `async` with `font-display: swap`. No variable axes shipped. System-font fallback renders text instantly, so **LCP < 1s does not depend on the webfonts.**
- Total first view target: **≤ 140KB**, stated honestly. A sharp front-end reviewer is part of the audience; an impossible budget undercuts the "we sweat the details" brand more than an honest one.

**Resilience (the page is the durable artifact; live links are bonus proof):**
- Hero, metric strip, every proof table, and all exhibit buttons render and work even if every live exhibit is 404s.
- Deployed separately from the portal so a portal redeploy can't break the homepage.
- **Live-board fallback (the board is a SPOF on a $3 box):** every live-exhibit button ships with a sibling **"archived snapshot"** link to a static read-only export (screenshot + short screen recording of the board, committed to the static deploy). A lightweight health-ping may swap the primary link to the snapshot on failure; if no JS, both links are always present. The headline proof must degrade gracefully, never dead-end.
- `@media print` stylesheet; OG card = a rendered image of the metric strip (this page will be shared on X/LinkedIn).

---

## 3. Homepage spec — section by section, with final copy

Long-scroll numbered document. Every section anchored for deep-linking. Sections render on warm `--paper`; "see it live" interludes flip to full-bleed dark `--console` so scrolling physically alternates **document ↔ terminal**.

### Hero (`#top`)

```
MUSTER
The operating system for agentic software teams — that built itself.

A self-hostable agency OS (Claude-side governance + a Directus shared-task bus +
local RAG + a Next.js portal) went from empty repo to a live, public, HTTPS demo
in about 2.5 hours — built by a fleet of ~30 AI subagents that used the system's
own task board as their spine, caught their own bugs, and scrubbed their own
shipping artifacts.

This page is the build log. The links are the live system.

[ Read the log ↓ ]   [ Open the live portal ↗ ]   [ See the build board ↗ ]   [ GitHub ↗ ]

────────────────────────────────────────────────────────────────
~2.5 hrs   empty repo → live HTTPS demo
30+ agents · 2M+ tokens · 6 parallel fan-outs
27 commits · 90 files · 8 phases
~7 functional bugs + 6 branding leaks — caught by machines, not humans
0 secret leaks · 0 collisions across 28 live worktrees
$2–4/mo to run
────────────────────────────────────────────────────────────────
```

**"This page is the build log. The links are the live system."** is the page's sharpest line — keep the structure verbatim, but the noun is **build log / field report**, never "whitepaper." (One critic loved the original "whitepaper" phrasing; another correctly flagged that the word "whitepaper" signals vendor-marketing PDF, the opposite of dev cred. The grittier noun wins on-page; "whitepaper" survives only as the structural genre, never as UI copy.)

The **metric strip** is the load-bearing hero element: a horizontal band of ground-truth numbers as plain mono text (no JS counters required), the thing a skimming CTO screenshots. Must render fully with CSS disabled. One self-drawing mark (the Build-Trail, §5). No stock illustration, no carousel.

**Headline A/B (only this product can say #1):** 1) *"The software that built itself — and shipped."* (hook) 2) *"Governance is the product."* (payload — use both, hook above the fold, payload as the §2 lead). 3) *"An operating system for agents that ship."*

### §1 — Abstract (`#abstract`)
150-word TL;DR for the CTO who won't scroll. Plain prose, no links. State the system, the ~2.5-hour self-build, the three proof points, the $2–4/mo live demo, and the thesis ("the value is the architecture, not the prompt"). Firewall the costs in one clause: hosting (~$3/mo) is not build model-spend is not ongoing fleet-operating cost.

### §2 — Governance is the product: the system built itself (`#thesis`)
The recursion, stated once, plainly: the system that ships the system used its own task board as the spine, its own governed fan-out to build a subsystem (the schema), its own adversarial verifiers to keep its own sellable template clean, and its own loop-proofs to catch bugs in its own packaging. **Call it dogfooding, not "the strongest possible evidence"** — self-use proves the apparatus is coherent and usable, not necessary or net-positive. Surfaces the live board link ("the spine, still browsable, read-only"). This is where Analog Elk gets its one origin clause: *"{{PRODUCT}} began as the internal OS of one agency, Analog Elk. That lineage is now just the first profile (`analogelk`) shipped alongside a generic one."*

### §3 — What {{PRODUCT}} is (`#what`)
The **four planes** as a labeled inline-SVG figure (the page's one architecture diagram — referenced explicitly in the prose, per the completeness critique): **Governance** (Claude-side constitution / §-rules) · **Task bus** (Directus `os_*` shared board) · **Memory + RAG** (local engine) · **Portal** (Next.js). One line each. State the precise claim here: the **task record is the coordination atom** (claimable work units); **memory files are the knowledge substrate**; **the append-only log is the narrative substrate.** Three substrates, three cadences — do NOT collapse back to "the task record is THE atom." Note the `generic | analogelk` profiles — the architecture detail that makes "it's a product, not an internal tool" true at the code level.

### §4 — One receipt, end to end (`#receipt`) — NEW, the single highest-leverage section
The completeness critique is right: a paper about receipts that shows zero receipts is "trust me," not "look." Walk **one** defect all the way through, with real artifacts shown inline as a small figure:

> the RAG `:9100` false-green health check → **the board row** (task id) → **the verifier's claim** (the co-located engine that fooled the check) → **the closing note** → **the fix commit** (hash).

This converts "the receipts are public" from a claim into one demonstrated artifact. It also seeds the §"try it" clone path. Every other proof section can stay summary because this one is concrete.

### §5 — The build, in 8 phases (`#build`)
Timeline P0 scaffold → P7 packaging, 17:56 → 20:23 PT (2026-06-29), with commit/token counts per phase, rendered as the **Build-Trail** (a line of stacked-step markers). Deep-links into the board. Phases: P0 scaffold · P1 compose core · P2 schema+seed · P3 RAG · P4 portal · P5 Claude-OS wiring · P6 live demo · P7 packaging.

### §6 — The agent fleet (`#fleet`)
30+ subagent invocations, 6 fan-outs, >2M tokens. Spotlight the two named set-pieces: the **8-agent schema build (546k tokens** — ground → fan-out → scrub-audit → 3 adversarial leak-verifiers) and the **5-agent live-AWS-pricing cost panel (256k).** **Account for the rest in one sentence** (parallel explorers/builders/verifiers across P0–P7) so "30+" doesn't read as inflated, and **state the discarded-work denominator** honestly (retries/garbage subagents are part of the real token cost).

### §7 — Bugs the machines caught (`#bugs`) — PROOF SECTION, table with HONEST attribution
Add the attribution column the credibility critique demands — concede openly which catches a single disciplined agent could also reach:

| Defect / risk | What caught it | Needed the fleet? |
|---|---|---|
| RAG `:9100` port collision | from-scratch loop-proof | No — any disciplined agent |
| Health check fooled by a co-located engine | clean-room reproduction | No — single-agent reachable |
| Missing `releases.repository_id` FK | loop-proof | No |
| `set -e` / `pipefail` bug in `doctor` | loop-proof | No |
| arm64-vs-amd64 portal-image mismatch (fixed live on the box) | live deploy | No |
| Compose RAG-off abort | loop-proof | No |
| AE seed files bare-named, colliding with a kept UI-folder collection | scrub-audit | Partly (seam) |
| **6 real `AnalogElk` / analogelk.com references** in the sellable template | scrub-audit + 3 adversarial leak-verifiers | **Yes — multi-tenant policing** |

Caption: *"About 7 functional bugs and 6 branding leaks, none caught by a human. Most functional catches are loop-proof wins a single disciplined agent could reach; the genuinely fleet-dependent win is the system policing its own multi-tenancy before it shipped a sellable generic template. We note honestly that the brand leaks are string-checkable — a grep/linter catches those too; the fleet's value is the seam and semantic cases."* Reframe the scrub as a **capability, not a confession.**

### §8 — Governance & safety (`#governance`) — PROOF SECTION
0 secret leaks (DB + admin tokens always env-referenced, never echoed or committed; grep-verified). On the 28 worktrees, state it precisely: *"we avoided the contested checkout entirely by building read-only from a frozen snapshot — 0 collisions by not participating in the contention, not by handling it."* The shipped-vs-aspirational ledger rendered as a literal two-column mono ledger (the honesty is the design feature). Defects shipped: **"0 known-shipped as of writing"** — not a hard "0" (undiscovered defects are uncounted by definition).

### §9 — Durability across sessions (`#durability`)
7+ sessions held with no context loss across (a) the board [coordination spine], (b) on-disk memory files [knowledge], (c) the append-only log [narrative]. **One honest paragraph on the spine's own coordination problem:** the board is shared mutable state and a single point of coupling. Address claim atomicity directly — what makes a claim exclusive across parallel agents (`assigned_to` + status compare-and-set / optimistic locking), what happens on a race (the build observed version collisions; re-check before write), and recovery if the board is down mid-build. Selling the board as the solution to coordination while it has its own coordination problem is the first thing a CTO probes.

### §10 — vs. an ungoverned single-agent workflow (`#vs`) — PROOF SECTION, table
Baseline **relabeled** (no strawman):

| Ungoverned single-agent workflow | {{PRODUCT}} |
|---|---|
| one rolling context window | durable task board + on-disk memory + append-only log (7+ sessions, no loss) |
| serial work, no coordination substrate | 30+ subagents across 6 fan-outs around a shared board |
| trusts its own output | loop-proofs + adversarial verifiers, with honest attribution of which catches needed the fleet |
| ad-hoc, no written rules | a written §1–§10 constitution loaded every session |

Add one honest line of **prior-art positioning**: *"The real alternatives aren't a chat transcript — they're git branches/PRs, markdown plan-files in a repo (this kit uses those too), and framework state (LangGraph/CrewAI/Swarm). {{PRODUCT}}'s bet is a queryable, multi-writer, cross-session task board as the durable coordination atom — and we use files alongside it, not instead."* Without this, the win looks rigged.

### §11 — Run it yourself (`#try`) — full-bleed `--console` band, the conversion band
The exhibits gathered: **GitHub repo + the literal one-command install snippet (first-class, copyable)**, the live portal, the build board (+ archived snapshot fallback). The most persuasive single artifact lives here: an **asciinema / SVG-term recording of `bin/{{product}} init → … → doctor → green board`** — watching it stand up from zero, no cert warning required, degrades gracefully because it's a recording. Plus a link to the literal `CLAUDE.md §1–§10` constitution (the most reusable artifact in the package).

### §12 — Author & judgment calls (`#author`)
Mike Walliser, creative-technologist / AI-leadership pivot. Short. One "why I built this" paragraph. **Surface the human-only decisions here, not as a limitations afterthought** (they are the leadership signal for the hiring-manager audience): the product reframe (internal tool → sellable product), insisting on the honesty ledger, ROI-bounding the fan-out, the live arm64 diagnosis. *"Here is what no agent decided."* Note explicitly that **Mike designed this page and the system architecture** — the page's craft is the portfolio piece. Links out (resume/contact). No accomplishments list.

### Footer
`{{PRODUCT}} · built by agents · origin & case study: Analog Elk` · `Design & system architecture: Mike Walliser` · links repeated · `Download PDF / Print`.

> **Structural spine:** §2, §4, §7, §8, §10 are the proof. §4 (one walked receipt) and §11 (clone path + doctor recording) are the two highest-leverage additions over the draft — they convert "trust me" into "look." Render proof as tables/ledgers, not prose.

---

## 4. Inner-link / IA map

**Sticky top bar** (after hero scrolls past): `MUSTER` wordmark (left) · jump-links `Thesis · Receipt · Build · Proof · Run it` (center) · two **persistent** buttons `Live portal ↗` and `GitHub ↗` (right). A thin **Phase Ticker** progress strip shows P0–P7 as Build-Trail nodes, fills as you scroll, clicks to jump, marked up as `<nav>` (doubles as TOC).

**The exhibits (the only outbound destinations that matter), all `target="_blank"`:**
1. **Live portal** — `https://34.220.64.149.sslip.io` — labeled *"the running product."* **Demo runs the `generic` profile by default** so the product noun is consistent across the paper↔demo seam (see below). Caption: *"sslip.io demo box — see TLS note."*
2. **Build board** — `https://cms.34.220.64.149.sslip.io` — labeled *"the actual task spine the agents used to build this."* The headline exhibit. Caption: *"public, read-only — you can browse the receipts, you can't write to them."* Sibling **"archived snapshot ↗"** fallback link always present.
3. **GitHub repo** — source + the one-command install. First-class, not buried.
4. **The report itself** — `Download PDF` / `Print` via `@media print`.

In-page jumps smooth-scroll; live exhibits open in a new tab. The Build-Trail mark's **top (ember) step hyperlinks to the live board** — the recursion close.

**FIX — the demo seam (the draft's single worst contradiction):** clicking "the running product" must NOT dump a CTO into Analog Elk's internal tool. Resolve one of two ways, in priority order:
- **(preferred) Boot the public demo on the `generic` profile.** This keeps the noun consistent end-to-end AND proves the `generic` profile actually works (currently an unverified claim). The `analogelk` profile becomes a visible, optional **"view the Analog Elk case-study profile ↗"** toggle/banner — turning the origin into a demonstrated feature.
- **(fallback)** if only the `analogelk` profile is deployable in time, ship a persistent in-portal banner: `viewing: analogelk profile — this is the case study; switch to generic ↗`, so the seam reads as a feature demonstration, not a branding leak.

**TLS:** prefer a real cert — Caddy + Let's Encrypt is already in the stack; a guessable sslip.io interstitial hands the audience a security warning at the moment of maximum trust. If a real cert can't be issued in time, pre-empt it in copy on **both** the page and the link caption: *"sslip.io demo cert — your browser will warn once; it's a $3/mo demo box."*

**De-emphasizing Analog Elk (concrete rules — this part of the draft worked, keep it exactly):**
- `<title>`: `{{PRODUCT}} — the operating system for agentic software teams`. Wordmark: `{{PRODUCT}}`. Do not reuse the Analog Elk marketing logo or skin.
- "Analog Elk" allowed in **exactly two places:** the origin clause in §2 and the footer origin/case-study line. Everywhere else: "the system / {{PRODUCT}} / the product."

---

## 5. Visual / design direction

**The two memorable, build-derived ideas:**

1. **The Build-Trail mark (NAME-AGNOSTIC).** Logo, favicon, and section divider in one line-art system: **stacked steps**, each step = one verified unit (a commit / an agent / a session) accreting upward; the **top step glows ember = the live system** and links to the board. This visualizes the durability-and-incremental-memory thesis directly under **any** name — there is no Antler fallback and no Cairn dependency. The draft's fatal coupling (revert the mark if the name changes) is eliminated: durability-stacking is the mark, period. Must read at 16px (favicon = three steps + one ember). **Self-draws once on load** via `stroke-dashoffset` (~1.4s ease-out), reading as the build assembling itself; final state shown instantly under `prefers-reduced-motion`.
2. **The Ledger Rail.** A persistent **monospace right margin** (desktop ≥1100px; collapses to a sticky top strip on mobile) running the real build telemetry alongside the prose as you scroll: `17:56 PT`, `P2 · 8 agents · 546k tok`, `27 commits`, `0 leaks`, `28 worktrees · 0 collisions`, commit hashes. As you read a section, the rail highlights the phase it describes — the task-board-as-spine made into the page's actual furniture. This is the signature layout move and the screenshot magnet. Numbers count up once on scroll-into-view (one-shot, reduced-motion safe).

**Layout:** single editorial column, ~66ch measure, set slightly left of center to give the Ledger Rail room (intentional, distinctive asymmetry). 8pt grid, generous vertical rhythm — whitespace is the authority signal. **Paper-vs-Machine bands:** report sections on `--paper`; live interludes (§11, board screenshots, the doctor recording) flip to full-bleed `--console`.

**Typography** (editorial field-report, not dev-tool landing; mono is a brand pillar because the content is literally a build log) — **specified for the real perf budget (static weights, subset, 3 faces):**
- **Display — Fraunces, STATIC weights 400 + 600 only** (no variable axes shipped), high optical size, tight leading 1.05–1.1. Subset to Latin + the actual headline glyphs.
- **Body — Hanken Grotesk** (humanist grotesque, deliberately NOT Inter), 18px over 62–66ch. *(IBM Plex Sans if a more overt engineering signal is wanted.)*
- **Mono — Commit Mono** (or Geist/IBM Plex Mono): timestamps, token counts, hashes, agent IDs, the Ledger Rail, live chips, all metrics. **Rule the reader learns in the first scroll: if a number is a ground-truth build metric, it is set in mono.**

```
display    3.05rem / 1.06   Fraunces 600
h2         1.95rem / 1.15   Fraunces 600
h3         1.40rem / 1.20   Hanken 600
body       1.125rem / 1.65  Hanken 400   (measure 62–66ch)
small/meta 0.84rem / 1.40   Commit Mono 400, +0.02em
```
System-font stack renders all text instantly; the three subset woff2 swap in async. LCP never waits on a webfont.

**Color & mood — field-journal / specimen-ledger, not black-neon-AI.** Warm bone paper for the document; deep pine for authority; **one ember accent reserved exclusively for *live*** — anything ember is clickable into the running system.

```
--paper      oklch(0.972 0.008 85)   #F4EFE4   page base (warm bone)
--ink        oklch(0.235 0.010 60)   #221F1A   text
--pine       oklch(0.380 0.055 155)  #25402F   primary / headline accent / mark stroke
--bone-rule  oklch(0.860 0.018 80)   #DDD4C2   hairlines, dividers, ghost strokes
--ember      oklch(0.685 0.170 48)   #DE7330   LIVE links, top step, "system is running" — RESERVED
--console    oklch(0.175 0.012 160)  #14201B   dark bg for live-system bands
--console-fg oklch(0.940 0.010 90)   #ECE7DC
```

**Ember discipline:** semantic, never decorative — it marks only the seam between *paper* (the writing) and *machine* (the live demo). That single reserved color does the brand work.

**Signature components:** the self-drawing Build-Trail mark; the Ledger Rail (mono, right-aligned, hairline-separated, count-up-once); the **live-console chip** — inline link `[ ▸ live ]` in ember on a subtle inset showing the bare host `34.220.64.149.sslip.io`, unmistakable from prose links; **metric callouts** as big mono numbers on pine cards (one per band, not a stat-wall); the **bug-ledger / shipped-vs-aspirational** as honest two-column mono ledgers; the **archived-snapshot** sibling link styled as a muted twin of each live chip.

**Motion — restraint is the brand.** Total moving parts: **two** one-shot animations (mark draw, metric count-up) plus the passive scroll-linked rail highlight. No parallax, no loops, no gradient shimmer, no scroll-jacking. Everything honors `prefers-reduced-motion`.

**Anti-generic guardrails:** no purple/indigo gradients, no glassmorphism, no glowing orbs/neurons/"AI brain," no neon dark-mode-by-default, no Inter as body, no 3D blobs/particles, no emoji in UI. **And trim the AI-slop in copy:** no slogan used more than once ("price of a sandwich," "make the ticket the unit of work," "here are the receipts" — one appearance max each), no self-narration of impressiveness, and **thin the em-dashes hard** (high em-dash density is an LLM tell, doubly ironic given the board purges them — favor periods and commas).

**Implementation:** pure static HTML + one CSS file + inline SVGs; self-hosted subset woff2 (`font-display: swap`). Tokens as CSS custom properties (OKLCH with hex fallback) so the same palette can later seed the live portal's theme. A11y: real semantic headings, Phase Ticker as `<nav>` TOC, all body text WCAG AA on both paper and console, ember focus-visible rings, all motion guarded. Every ember chip targets a real endpoint; the mark's top step → the board.

---

## 6. One-line brief for the builder

> A warm-paper engineering **build log** that IS the homepage — Fraunces (static) over Commit Mono, deep-pine ink with a single reserved ember "live" accent — spined by a monospace **Ledger Rail** of the real build metrics and marked by a **name-agnostic Build-Trail** (stacked verified steps, top step ember/live) that draws itself once, alternating paper-document and dark-console bands, with five proof sections (governance-is-the-product / **one walked receipt** / bugs-machines-caught-with-honest-attribution / shipped-vs-aspirational ledger / vs-ungoverned-single-agent) as the structural spine, a **read-only live build-board as the headline exhibit** (with an archived-snapshot fallback), a copyable **one-command install + a `doctor`-to-green recording**, and a generic-profile live demo so the product noun stays consistent end to end — until the mark's top ember step links you into the running system it describes. Static single file, HTML/CSS/SVG ≤ 50KB + subset fonts ≤ 90KB, LCP < 1s on text, prints to PDF, stands alone if the demo is down. Product noun = **Muster** (`{{PRODUCT}}` token; coined fallback `Mustr`; last-resort `Elk OS` via token swap). The mark never changes with the name.

---

## 7. Cross-document requirements the companion WHITEPAPER must adopt (non-negotiable for apex coherence)

The two deliverables currently disagree on the name — that is incoherent at the apex URL and must be closed by the whitepaper conforming to this brief:
1. **Name:** the whitepaper is retitled and rewritten end-to-end as **{{PRODUCT}} = Muster** (or whatever clears same-day), via the same token. Shipping "Cairn homepage over an Elk OS paper" is a hard fail.
2. **Baseline label:** "out-of-box Claude Code" → **"an ungoverned single-agent workflow"** everywhere; reframe the contribution as architecture, not missing primitives.
3. **One receipt inline** (the `:9100` false-green walked board-row → verifier → fix commit) and **repo + one-command install + the `CLAUDE.md §1–§10` constitution linked**, in the paper, not just the homepage.
4. **Re-attribute catches** (clean-room/loop-proof vs fleet-dependent), **firewall the three costs**, **soften "0 shipped" → "0 known-shipped,"** **add the claim-atomicity + board-as-SPOF paragraph**, and **address the public-board security posture (read-only) and the TLS click-through** in the paper too.

---

**Follow-up flagged (DevProd §1 — surfacing for the orchestrator to log to `os_tasks`, not creating the row from this synthesis subagent):** run a same-day npm + `.dev`/`.sh` + GitHub-org availability check on **`muster`** (org `muster-os` / `getmuster`); fall to **`Mustr`** if any handle is blocked; do NOT gate publish on USPTO. Separately: stand up the **`generic`-profile public demo** (fixes the paper↔demo seam) and issue a **real Let's Encrypt cert via Caddy** for the demo host before the page links it. Both are publish-blockers for the de-emphasis mandate, not parallel nice-to-haves.