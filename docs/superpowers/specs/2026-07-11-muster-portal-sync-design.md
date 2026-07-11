# Muster continuous portal + schema sync

Date: 2026-07-11
Status: Approved design, ready for implementation plan
Repo: `AnalogElk/muster` (local dir `elk-os`)

## Problem

Muster does not fork the admin panel, it vendors it. `portal/PINNED_COMMIT` holds a
short SHA of `analog-elk-front-end` (AE) `origin/main` (currently `9931464`, from
2026-06-29). `portal/prepare-context.sh` extracts a frozen `git archive` of that commit
and applies 6 host-side patches on top (drop the private registry, drop the private 3D
dep, `output: standalone`, rebrand Analog Elk to Muster by string replacement, and
self-host rewrites to `proxy.ts` + `auth.ts`), builds a Docker image, publishes it to
GHCR, and the box runs it via compose with `PORTAL_IMAGE` pinned.

Consequently the live Muster demo (`musterr.dev`) drifts behind the admin panel. Every
AE admin-panel release (for example PR #333: the mint theme, two-tier task UX,
in-app notifications, board perf, shipped 2026-07-09 as AE v1.22.0) leaves Muster on the
old portal image until someone manually re-pins, re-patches, rebuilds, and redeploys.

Two failure modes make a naive re-pin unsafe:

1. **Patch drift.** The rebrand and self-host patches key off specific source strings.
   When AE changes a lot, a patch can match zero occurrences (silent no-op) or match the
   wrong place, shipping a half-rebranded or mis-wired portal. There is currently no
   assertion that any patch actually applied.
2. **Schema drift.** Muster ships a deliberately pruned and scrubbed 49-collection
   Directus snapshot (`directus/schema/snapshot.json`, governed by `KEPT-AND-PRUNED.md`
   and `SCRUB-AUDIT.md`). It is frozen at the 2026-06-29 prune. AE's schema keeps adding
   fields and collections, so over time the portal image gets ahead of the schema and new
   features fail or degrade. Blindly regenerating the snapshot from AE would risk
   re-introducing the AE-specific collections and PII the prune removed on purpose.

## Goals

- Keep Muster's portal and Directus schema updated together with the admin panel, on a
  cadence driven by AE releases, with a human review gate.
- Do the one-time catch-up (bring the live demo from `9931464` to current AE `main`, so
  the mint theme and new task UX are visible) as the first shippable step.
- Make patch drift a loud, actionable failure instead of a silent broken image.
- Regenerate the pruned/scrubbed schema without re-introducing scrubbed content.
- Deploy to the box without opening its IP-locked security group.

## Non-goals

- Turning Muster into a live fork of AE app code. It stays a downstream consumer of a
  pinned AE commit.
- Upstreaming the branding and self-host hooks into AE as runtime config (the "one image
  serves both" refactor). Considered and set aside in favor of the downstream model.
- Multi-tenant or per-visitor schema. Muster remains single-tenant per deploy.

## Decisions (settled with Mike, 2026-07-11)

1. **Sync model: CI auto-rebuild with a PR gate.** Muster stays downstream. CI rebuilds
   the portal image and regenerates the schema, then opens a PR. Mike reviews and merges.
2. **Schema scope: full auto, app + schema.** The loop regenerates the pruned snapshot
   and the schema-apply artifact, with the prune + scrub rules codified so re-snapshotting
   AE never re-introduces removed collections/PII. The generated schema still lands in the
   PR for human review before merge.
3. **Trigger: on AE release.** A sync fires when AE ships a release, not on every commit
   and not on a fixed weekly clock.
4. **Deploy leg: box-side auto-pull agent.** On a merged Muster release the box updates
   itself (backup, pull, migrate, healthcheck, rollback on failure). No inbound CI to box
   SSH.

## Architecture

```
[AE] release-please cuts vX.Y.Z on main
      |  (a new AE release appears)
      v
[Muster CI] sync-portal workflow
  1. Resolve AE target SHA (the release commit)
  2. PORTAL leg:   archive AE@SHA -> run prepare-context.sh patches (with assertions)
                   -> build amd64 image -> smoke test -> push GHCR :vX.Y.Z (by digest)
  3. SCHEMA leg:   fetch AE schema@SHA -> apply KEEP filter -> apply SCRUB filter
                   -> candidate snapshot.json -> diff vs current -> flag NEW collections
  4. Commit:       bump PINNED_COMMIT + PORTAL_IMAGE + snapshot.json
  5. Open PR:      AE version + SHA + changelog, smoke screenshot, schema-drift report
      v
[Mike] review PR (the one decision point per sync) -> merge (conventional commit)
      v
[Muster] release-please cuts a Muster release
      v
[Box updater] systemd timer sees the new Muster release
  -> backup Directus snapshot (rollback point)
  -> docker compose pull portal + up -d
  -> directus schema apply (declarative, reuses `elk-os migrate`)
  -> healthcheck (/login 200 + a known os_task reads back)
  -> on failure: roll back image + restore snapshot + ntfy alert
```

## Components

### 1. Portal leg: hardened `prepare-context.sh`

The existing 6 patches gain pre-state and post-state assertions. Examples:

- Rebrand: assert at least N occurrences of "Analog Elk" exist before, and 0 remain
  after.
- Self-host: assert the `proxy.ts` and `auth.ts` anchor strings the patch edits exist
  before editing.
- Private-dep removal: assert the dependency is present in `package.json` before removal.

If any assertion fails, the sync fails loudly and opens a **draft** PR labeled
`patch-drift` rather than shipping a half-patched image. A container smoke test is the
backstop: boot the built image, GET `/login` and `/`, assert both return 200 and the
rendered login page shows "Muster", not "Analog Elk".

Build on GitHub Actions ubuntu runners, which are amd64 natively. This also resolves the
local arm64-under-qemu build problem (AE follow-up e1ac5e53). Pass
`NEXT_PUBLIC_DIRECTUS_URL=https://cms.musterr.dev` as a build arg so the baked browser
origin is correct (fixes the known deep-authed-call wrong-origin caveat).

### 2. Schema leg: codified prune + scrub

Convert the prose in `KEPT-AND-PRUNED.md` and `SCRUB-AUDIT.md` into machine-applied data:

- `directus/schema/keep-collections.json`: the ~49-collection allowlist. AE collections
  not on it are dropped from the candidate snapshot.
- `directus/schema/scrub-rules.json`: schema-level scrub. Drop AE-specific flows, presets,
  dashboards, and permissions embedded in the snapshot. Seed data lives separately under
  `directus/seed/` and is already generic, so PII exposure here is bounded to
  schema-embedded artifacts.

Safety valve: any collection present in AE but on neither the keep list nor a known-drop
list is flagged for human triage in the PR body. It is never silently kept or dropped.
This is what prevents re-introducing scrubbed content as AE evolves.

### 3. PR gate

The sync PR body contains:

- AE version, SHA, and a changelog excerpt for the range being pulled in.
- The portal smoke-test screenshot (satisfies CLAUDE.md §5 for UI changes).
- The schema-drift report: added and removed collections and fields, with any
  NEW-unclassified collection flagged prominently.

Mike merges or does not. Merge uses a conventional commit so Muster's release-please cuts
a release.

### 4. Trigger: on AE release

Implemented as a Muster-side poll of AE's releases API every ~30 minutes (a scheduled
workflow). It compares the latest AE release to the last-synced AE version and starts a
sync when a new one appears. This avoids a change to the hot AE repo and avoids storing a
Muster-scoped PAT in AE's secrets. Cost is up-to-30-minute latency, acceptable for a demo
box.

Upgrade path if zero latency is ever wanted: a true `repository_dispatch` step in AE's
release workflow. Deferred, since it touches AE and needs a cross-repo PAT.

### 5. Box updater

A systemd timer (or cron) on the box, running as a small script:

1. Check for a new Muster release (git pull of the deploy checkout, see call 2 below).
2. Snapshot Directus first (schema + data) as a rollback point.
3. `docker compose pull` the portal and `up -d`.
4. `directus schema apply` the committed `snapshot.json` (declarative, reusing the
   existing `elk-os migrate` path).
5. Healthcheck: `/login` returns 200 and a known `os_task` reads back through the API.
6. On failure: roll back to the previous image digest, restore the snapshot, and fire an
   ntfy alert (reuse the existing box uptime alerting).

A lock ensures only one updater runs at a time. No inbound SSH, so the IP-locked security
group stays closed.

## Implementation calls (approved)

1. **AE schema source: AE release publishes its Directus snapshot as a release asset**,
   which Muster's sync downloads. Preferred over snapshotting live `cms.analogelk.com`
   with an admin token in Muster CI, which would place a prod token in CI against
   CLAUDE.md §2. Requires a small step in AE's release workflow.
2. **Box deploy tree: convert the box's synced-not-git `~/elk-os` into a read-only git
   checkout of the public `muster` repo.** The updater becomes `git pull` + `compose up`.
   Gitignored local files (`.env`, `wire/`, `muster-site/`) stay in place. This also
   permanently fixes the "merges do not auto-deploy" pain (the box tree being
   synced-not-git is a documented gotcha).
3. **Schema apply: declarative `directus schema apply` from the committed
   `snapshot.json`**, not hand-authored imperative migrations. Reuses what Muster already
   does at `migrate`.
4. **Image refs: pin `PORTAL_IMAGE` by immutable version tag or digest** (for example
   `:1.23.0` or `@sha256:...`), never `:latest`, so the box is reproducible and rollback
   is a repin to the previous digest.

## Failure modes and safety

- **Patch drift:** caught by patch assertions + smoke test. Result is a draft PR, not a
  broken deploy.
- **Unclassified new AE collection:** flagged in the PR, blocks a clean merge until
  triaged into keep or drop.
- **Bad schema apply on the box:** guarded by a pre-apply Directus snapshot and a
  post-apply healthcheck with automatic rollback.
- **Destructive schema diff:** `directus schema apply` can drop columns removed from the
  snapshot. Acceptable on a read-only demo box given the pre-backup, and the diff is
  human-reviewed in the PR before it can reach the box.
- **Concurrent updater runs:** prevented by a lock on the box.

## Phasing (value first)

- **Phase 1:** harden `prepare-context.sh` (assertions + smoke test), then run it manually
  once to bump the pin from `9931464` to current AE `main`, rebuild, and deploy. Gets
  #333's mint theme, task UX, and notifications onto the live demo now. Satisfies "update
  Muster with all the new features" on its own.
- **Phase 2:** schema leg (keep + scrub filters, drift report), still manual trigger.
- **Phase 3:** wrap portal + schema in the CI workflow with the AE-release poll and the PR
  gate.
- **Phase 4:** box updater (auto-pull, migrate, healthcheck, rollback).

Each phase is independently shippable.

## Dependencies and open items

- A small step added to AE's release workflow to publish the Directus schema snapshot as a
  release asset (call 1). Touches the hot AE repo; a workflow file, low collision risk,
  but check active worktrees per CLAUDE.md §9 at implementation time.
- GHCR publish already exists (`.github/workflows/publish-images.yml`); confirm it can be
  driven by the sync workflow or fold publishing into it.
- Box access for setting up the updater and converting the tree to a git checkout
  (`ssh -i ~/.ssh/elk-os-demo.pem ubuntu@34.220.64.149`, SG allows Mike's IPs only).
- Reconcile the box's local untracked files with a fresh git checkout without losing
  `.env`, `wire/`, and synced `muster-site/` content.

## References

- Memory: `project_elk_os` (Muster), `project_admin_panel_life` (PR #333),
  `project_agency_os_productization` (prune lineage), `feedback_shared_working_dir_branch_switch`,
  `feedback_always_check_active_worktrees`.
- Files: `portal/PINNED_COMMIT`, `portal/prepare-context.sh`, `portal/Dockerfile`,
  `compose/compose.images.portal.yaml`, `compose/compose.portal.prod.yaml`,
  `directus/schema/{snapshot.json,KEPT-AND-PRUNED.md,SCRUB-AUDIT.md}`,
  `provision/`, `bin/elk-os`.
