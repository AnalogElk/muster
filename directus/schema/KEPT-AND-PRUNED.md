# Schema snapshot — kept vs. pruned

`snapshot.json` is a **pruned, generic-safe** Directus schema, derived from the
live Analog Elk production CMS (`cms.analogelk.com`) via
`GET /schema/snapshot?export=json`.

The goal: ship the **agency-OS core** (projects, tasks, sprints, CRM, deals,
proposals, invoices, expenses, payments, deliverables, releases, repositories)
as a sellable generic template — **without** Analog Elk's marketing-website CMS,
internal dashboards, or any real client data.

It captures **structure only** — no rows, no files, no users, no
permissions/roles/flows/presets (those live in `directus_*` data tables and are
out of scope for `/schema/snapshot`). A clean demo dataset ships separately under
`directus/seed/<profile>/`.

## Numbers

| | Source (prod) | Kept | Pruned |
|---|---:|---:|---:|
| Collections | 141 | **50** | 91 |
| Fields | 1371 | 575 | 796 |
| Relations | 219 | 110 | 109 |

5 fields on otherwise-kept collections were also dropped because they pointed
into pruned collections (see *Sanitized cross-references* below).

## Version note (important for `migrate`)

The snapshot was captured on Directus **11.15.1**, but `compose/compose.yaml`
currently pins `directus/directus:11.5.1`. Directus' schema diff enforces a
version match. `bin/elk-os migrate` works around this by reading the target's
**live** version from its own `/schema/snapshot` and rewriting the snapshot's
`directus` field to match, then calling `POST /schema/diff?force=true`. The
clean long-term fix is to **bump the compose image tag to `directus:11.15.1`**
(a `compose/` change, outside this agent's lane — flagged for the orchestrator).

## Kept (50 collections)

### Agency-OS core — all `os_*` (38)

`os_activities`, `os_activity_contacts`, `os_activity_log`,
`os_client_ticket_responses`, `os_client_tickets`, `os_deal_contacts`,
`os_deal_stages`, `os_deals`, `os_deliverable_decisions`, `os_deliverables`,
`os_email_templates`, `os_expense_items`, `os_expenses`, `os_insights`,
`os_invoice_items`, `os_invoices`, `os_items`, `os_message_threads`,
`os_messages`, `os_notifications`, `os_payments`, `os_products`,
`os_project_contacts`, `os_project_subscriptions`, `os_project_templates`,
`os_project_updates`, `os_projects`, `os_proposal_approvals`,
`os_proposal_contacts`, `os_proposals`, `os_seo_snapshots`, `os_settings`,
`os_sprint_snapshots`, `os_sprints`, `os_subscriptions`, `os_task_files`,
`os_tasks`, `os_token_usage`

### Supporting agency-OS collections (named in scope) (6)

`contacts`, `organizations`, `organizations_contacts`, `organization_addresses`
(CRM entities + their junction/address tables), plus `releases` and
`repositories` (the per-project release log & repo registry the OS links to).

### UI folder/group containers (no table; kept so kept collections stay grouped) (6)

`projects`, `billing`, `sales`, `business`, `crm`, `hidden_Fields` — these are
Directus "folder" collections (no schema) that organize the kept collections in
the admin UI. Kept transitively because a kept collection declares them as its
`meta.group`. (Pruned children simply drop out of these folders.)

## Pruned (91 collections)

### Marketing site CMS — pages / blocks / components (45)

`Static_Pages`, `about`, `contact`, `home`, `pages`, `page_portfolio`,
`page_services`, `components`, `component_library`, `website`, `globals`,
`tech_stack_components`, and the entire page-builder block/UI library:
`block_*` (animated_list, bento_grid, blog_listing, card_row, carousel, cta,
device_mock, faq, footer, header, hero, highlighter, icon_cloud, pricing,
terminal, …) and `ui_*` (animated_list_items, bento_cards, cards, faq_items,
feature_slides, footer_links, header_links, icon_cloud_items, pricing_tiers).

### Marketing site CMS — portfolio / media / forms (16)

`portfolio_items`, `portfolio_category_tags`, `portfolio_tag_sections`,
`portfolio_tag_sections_files`, `portfolio_tag_sections_media_galleries`,
`media_galleries`, `media_galleries_files`, `forms`, `form_actions`,
`form_analytics`, `form_condition_rules`, `form_field_conditions`,
`form_field_options`, `form_fields`, `form_steps`, `form_submissions`.

### Publishing & help center (7)

`authors`, `blog_page`, `blog_posts`, `publishing`, `help_articles`,
`help_collections`, `help_feedback`.

### Business catalog — services / packages / tools (7)

`services`, `service_categories`, `packages`, `tools`, `tool_alerts`,
`tool_alert_recipients`, `project_tools`. *(AE-specific marketing/catalog
surface; the generic OS bills via projects + invoices, not a public service
catalog.)*

### Legacy / non-`os_` CRM inbox & messaging (6)

`conversations`, `inbox`, `messages`, `internal_messages`, `project_links`,
`contract_payment_settings`. *(The canonical messaging lives in
`os_message_threads` / `os_messages` / `os_notifications`, which are kept.)*

### Alerts & telemetry (AE dashboards) (6)

`alerts`, `alerts_items`, `alert_recipients`, `subscription_alerts`,
`analytics_snapshots`, `infra_snapshots`. *(Tied to AE's own infra/analytics
dashboards and webhooks; not part of a generic template.)*

### Portal auth / KB / misc AE-specific (4)

`auth_magic_tokens` (the AE portal's magic-link store — the app owns its own
auth), `kb_pages`, `kb_spaces` (AE's Directus-headless knowledge base — elk-os
ships its own RAG engine instead), `tasks_files` (legacy duplicate of the kept
`os_task_files`).

## Sanitized cross-references

Fields/relations on **kept** collections that referenced **pruned** collections
were removed so the snapshot applies cleanly (no dangling FK or alias):

| Collection | Field | Reason |
|---|---|---|
| `os_tasks` | `form` | m2o → `forms` (pruned) |
| `os_subscriptions` | `tool_id` | m2o → `tools` (pruned) |
| `os_subscriptions` | `alerts` | o2m → `subscription_alerts` (pruned) |
| `os_projects` | `tools` | m2m → `tools` (pruned) |
| `os_projects` | `messages` | o2m → `messages` (pruned, non-`os_`) |

The built snapshot was validated to have **zero** dangling references: every
`meta.group`, every field foreign key, and both endpoints of every relation
resolve to either a kept collection or a `directus_*` system collection.

## How it's applied

`./bin/elk-os migrate` → `POST /schema/diff?force=true` then
`POST /schema/apply` (version-aligned to the live target; idempotent — a second
run diffs empty and no-ops). Permissions, roles, flows, and presets are **not**
included and must be provisioned separately.
