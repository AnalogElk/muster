# SCRUB-AUDIT — directus/schema/snapshot.json

Phase P2 sell-safety audit of the pruned Directus schema snapshot and both seed
profiles. Goal: ensure nothing real (client names, PII, secrets, internal
URLs/hosts, infra identifiers) ships in a template that will be sold publicly.

- **Date:** 2026-06-29
- **Snapshot:** Directus 11.15.1 schema export — 50 collections, 575 fields, 110 relations.
- **Snapshot kind:** *schema-only* (`collections` / `fields` / `relations`). It carries
  **no flows, presets, permissions, roles, users, or row data** — so the usual
  high-risk carriers (flow webhook secrets, presets bound to real user UUIDs,
  permissions/roles tied to real accounts) are **not present** in this file. PII
  surface is therefore limited to cosmetic field metadata: `note`, `options.placeholder`,
  `default_value`, `display_template`, `translations`, and field `choices`.
- **Result:** 6 findings, all scrubbed in place. JSON re-validated after edits.

## Method

- Parsed the snapshot and walked every string (9,659 total) for: `http(s)`, `@`,
  IPv4, `github`, `stripe`, `netlify`, `neon`, `amazonaws`, `tailscale`, `gmail`.
- Grepped for known-real identifiers from the environment: `analogelk`, `analog-elk`,
  `AnalogElk`, `cms.*`, real client brands (Station, Cascade, Boothista, Mineral
  Mandalas, StillFrames, Walliser, Outside Door), `mike`/`walliser`, known Directus
  role/user UUIDs (`2abe189f…`, `2954d30b…`, `d23007af…`, `0973c062…`), EC2/Tailscale
  IPs (`100.x`, generic IPv4), Matomo site IDs.
- Dumped and eyeballed every `note`, `default_value`, `display_template`/`template`,
  `translations` value, and field `choices` for real-world references.
- Reviewed both seed profiles (`seed/generic/`, `seed/analogelk/`) end-to-end.

## Findings & actions (snapshot.json)

All six were cosmetic metadata leaking the **AnalogElk GitHub org** and the
**analogelk.com** domain into UI hints/notes. No secrets, tokens, or PII. Each was
replaced with a neutral placeholder; no flow/preset/field had to be removed.

| # | Line | Kind | Before | After (scrubbed) |
|---|------|------|--------|------------------|
| 1 | 770 | Internal ref (note) | `Org-level client <-> AE team message threads (message center)` | `…client <-> team message threads…` |
| 2 | 25473 | Internal infra ref (note) | `Null = agency-internal (e.g. AE-paid Netlify umbrella).` | `Null = agency-internal (e.g. an agency-paid umbrella subscription).` |
| 3 | 26157 | Internal URL (placeholder) | `https://github.com/AnalogElk/repo/tree/feat/foo` | `https://github.com/your-org/your-repo/tree/feat/foo` |
| 4 | 26700 | Real domain (placeholder) | `https://analogelk.com/employee-portal/tasks` | `https://your-domain.example/employee-portal/tasks` |
| 5 | 27180 | Internal URL (placeholder) | `https://github.com/AnalogElk/repo/pull/123` | `https://github.com/your-org/your-repo/pull/123` |
| 6 | 27376 | Internal repo ref (placeholder) | `https://github.com/AnalogElk/analog-elk-front-end` | `https://github.com/your-org/your-repo` |

(Line numbers are pre-edit; the edits are 1:1 string swaps so they did not shift.)

## Reviewed and intentionally KEPT (not leaks)

- **`https://dashboard.stripe.com/test/payments/{{stripe_payment_id}}`** (display-link
  template on a payments field). Generic Stripe dashboard URL pattern with a mustache
  placeholder — contains **no account ID, key, or secret**. It is a legitimate generic
  integration convenience link, safe to ship. (`/test/` simply targets Stripe test mode.)
- **Stripe webhook notes** (`Auto-populated by Stripe webhook on subscription creation`,
  `Auto-synced from Stripe webhook events`) — generic integration documentation, no
  endpoint, secret, or signing key.
- **`os_token_usage`** collection/fields — "token" here means Claude Code **token-burn
  accounting**, not auth tokens. No secret material.
- **`matomo_site_id`** field — a field *definition* with a generic help note
  (`Find under Sites in Matomo admin.`). No real site ID baked in as a default.
- **`display_template` / `default_value` / `translations` / `choices`** — full sweep
  clean: all are field-name mustache templates, enum scaffolding (e.g. `P2`, `active`,
  `MONTHLY`, `one_time`), or sequence defaults. No real org/person/domain values.
- No emails, no real person names, no UUID-shaped user/role IDs, no IPs/Tailscale hosts,
  no `cms.analogelk.com` / EC2 / Neon / Netlify hostnames anywhere in the schema.

## Seed profiles — reviewed, no scrub needed

Both seed sets are **fully synthetic** and were authored sell-safe by the seed agents:

- **`seed/generic/`** ("Demo Co") — reserved `.example` domains (`@democo.example`,
  `democo.example`, `github.com/demo-co/…`), reserved `+1-555-01xx` phone range, every
  row `is_test_data: true`. No real data.
- **`seed/analogelk/`** ("Analog Elk" reference org) — **branded but synthetic**: people
  are fictional (Riley Hart / Devin Cole / Morgan Reyes), emails use the reserved
  `analogelk.example` domain (note: `.example`, *not* the real `analogelk.com`), phones
  in `+1-555-02xx`, websites `.example`, every row `is_test_data: true`. The "Analog Elk"
  name is intentional showcase branding for the reference profile and carries no PII,
  secret, or real contactable identifier. Left as-is by design.

## Verification

- `grep -inE "analogelk|analog-elk|analog elk|\bAE\b|AnalogElk" snapshot.json` → **no matches**.
- `python3 -c "import json; json.load(open('snapshot.json'))"` → **VALID JSON** post-edit.
- `bin/elk-os` was **not** touched. No git commit performed.

## Residual risk: LOW

The snapshot is schema-only (no flows/presets/permissions/roles/data), the six cosmetic
leaks are scrubbed, and both seed profiles are synthetic. No secrets or tokens were ever
present in these files. Remaining risk is limited to future re-exports re-introducing real
placeholders — re-run this sweep on any schema re-pull before shipping.
