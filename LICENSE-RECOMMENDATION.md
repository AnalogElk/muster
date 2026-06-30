# License recommendation (for Mike to decide)

Elk OS does **not** yet carry a binding `LICENSE` file — on purpose. The license
choice directly shapes how Elk OS can be monetized, so it should be a deliberate
decision, not a default dropped in at scaffold time. This document lays out the
options and a recommendation. **Pick one, then add the corresponding `LICENSE`
file** (and keep [`NOTICE`](./NOTICE), which credits the Agency OS lineage,
regardless of choice).

## The one hard constraint

Elk OS's `os_*` schema is **derived from
[directus-labs/agency-os](https://github.com/directus-labs/agency-os), which is
MIT**. MIT permits modification, redistribution, **and resale** — including as
part of a commercial product — **provided the upstream MIT notice is retained**.
[`NOTICE`](./NOTICE) does that. So the upstream does **not** force Elk OS to be
MIT or open source; you are free to choose any license for *your* combined work,
as long as the Agency OS attribution rides along. (The portal source carries the
same lineage and its own `ATTRIBUTION.md`.)

## The options

### Option A — MIT + attribution (permissive, fully open)

- **What:** ship Elk OS itself under MIT; keep `NOTICE` for Agency OS.
- **Pros:** maximum adoption and trust; zero friction for self-hosters and
  contributors; consistent with how the portal template is already licensed
  ([`portal/.build/LICENSE`](./portal/.build/LICENSE) is MIT, © Michael Walliser).
- **Cons:** anyone can take Elk OS, host it, and sell it as a service with no
  obligation back to you. Monetization must come from *services* (hosting,
  support, custom builds), not from the code itself.
- **Sell model:** open core + paid hosting/support/consulting.

### Option B — Source-available (BSL 1.1 or PolyForm) — *recommended for a paid product*

- **What:** ship under a **source-available** license — the source is public and
  self-hosters can run it, but **competing commercial/hosted use is restricted**.
  Two concrete choices:
  - **Business Source License 1.1 (BSL)** — used by HashiCorp, MariaDB, Sentry.
    Grant production use *except* offering Elk OS as a competing hosted service;
    set a **Change Date** (e.g. 3 years) on which each version converts to a true
    open license (e.g. Apache-2.0/MIT). Define an "Additional Use Grant" for what
    self-hosters may do for free.
  - **PolyForm Perimeter / PolyForm Shield / PolyForm Noncommercial** — a clean,
    modern family. *Perimeter* forbids competing with your product; *Shield*
    forbids competing-product use; *Noncommercial* forbids all commercial use
    (strongest, but blocks paying customers' own commercial self-hosting — usually
    too strong here).
- **Pros:** you can publish the full source (great for trust + evaluation) while
  reserving the right to be the paid/hosted provider. The BSL Change Date keeps it
  honest and community-friendly long-term.
- **Cons:** not OSI "open source"; some users/companies avoid source-available;
  slightly more to explain. You must still retain the Agency OS MIT notice (you're
  relicensing *your* additions + the combined work, not the upstream MIT grant).
- **Sell model:** paid licenses / paid hosting, with free self-host within the
  Additional Use Grant.

### Option C — Dual license (open core + commercial)

- **What:** offer Elk OS under a copyleft open license (e.g. **AGPL-3.0**) *and*
  sell a separate **commercial license** to anyone who wants to use it without
  AGPL's network-copyleft obligations.
- **Pros:** AGPL deters SaaS free-riding (they'd have to open their whole stack);
  the commercial license is the revenue line. Proven model (GitLab, Grafana-era).
- **Cons:** AGPL scares off some corporate users even for self-host; dual-licensing
  requires you to own/clear all contributions (a CLA) and adds admin overhead.
- **Sell model:** AGPL public + paid commercial exception.

## Recommendation

**Option B — Business Source License 1.1**, with:

- **Additional Use Grant:** free for self-hosting and internal/agency use
  (including paying clients running their own instance); the only restriction is
  offering Elk OS *itself* as a competing hosted/managed service.
- **Change Date:** 3 years per released version, **Change License: Apache-2.0**.

Rationale: Elk OS is positioned as a **sellable self-host product**, not a
services-only open-core play, so a permissive MIT (Option A) gives away the exact
thing being sold (a hostable agency OS). AGPL (Option C) protects against SaaS
clones but is heavier than needed and deters self-host adoption — the primary
audience. BSL threads the needle: **publish the full source** (maximal trust and
evaluation, which sells a product like this), let everyone self-host freely, and
reserve only the "don't resell my hosted Elk OS" lane — with a Change Date that
keeps the project credible and eventually-open.

If a fully-open posture is later preferred for community growth, **MIT + a hosted
paid tier (Option A)** is the clean fallback.

## When you decide

1. Add the chosen `LICENSE` file at the repo root (for BSL, also fill the BSL
   parameter block: Licensor, Licensed Work, Additional Use Grant, Change Date,
   Change License).
2. Keep [`NOTICE`](./NOTICE) unchanged (Agency OS MIT attribution is required
   under every option).
3. Update the README "License" section to point at the chosen license.
4. If Option C, add a `CONTRIBUTING.md` with a CLA before accepting outside PRs.
