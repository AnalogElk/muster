# Generic seed — "Demo Co"

Fully-synthetic seed data for the **generic** elk-os profile. Loading this gives a
fresh portal a believable, alive-looking dataset with **zero real customer data**.

Everything here is fictional: the org is **Demo Co**, people use
`@democo.example` addresses, and repos/sites point at `demo-co` / `*.example`
placeholders. Every row carries `is_test_data: true` so it can be filtered or
purged.

## Files (one per collection)

| File | Collection | Rows | Notes |
|------|-----------|------|-------|
| `organizations.json` | `organizations` | 1 | Demo Co |
| `contacts.json` | `contacts` | 3 | Avery Stone (primary), Jordan Lee, Sam Rivera |
| `os_projects.json` | `os_projects` | 2 | Website Relaunch, Customer Portal |
| `os_sprints.json` | `os_sprints` | 1 | Sprint 6 — June (active) |
| `os_tasks.json` | `os_tasks` | 8 | Spread across todo / in_progress / in_review / done |
| `releases.json` | `releases` | 1 | v1.0.0 Website Relaunch beta |
| `repositories.json` | `repositories` | 1 | democo-web |

## ID / linking convention

IDs are **stable, human-readable string keys** (e.g. `org-democo`,
`proj-website-relaunch`, `task-homepage-hero`) so the seed loader can **upsert**
idempotently. Relations reference those keys:

- `contacts.organization` → `organizations.id`
- `os_projects.organization` → `organizations.id`
- `os_sprints.project` → `os_projects.id`
- `os_tasks.project` → `os_projects.id`, `os_tasks.sprint` → `os_sprints.id`
- `releases.project` / `releases.repository` and `repositories.project` → their respective ids

If the pruned schema uses integer/UUID PKs, the loader is responsible for mapping
these string keys to real PKs while preserving the relations.

## Task status spread (board looks busy)

- **done** (2): homepage hero, nav redesign
- **in_review** (1): CMS content pipeline
- **in_progress** (3): CWV tuning, blog index, portal invoice list
- **todo** (2): portal magic-link auth, contact form

Points use the Fibonacci scale (1,2,3,5,8); priorities use `P1`–`P3`.

## Safety

No real Analog Elk clients, people, emails, domains, or tokens appear here. Safe
to commit, demo, and screenshot.
