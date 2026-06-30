# Analog Elk demo seed

AE-flavored profile seed for Elk OS. Loaded by `elk-os seed --profile analogelk`
(P5). Mirrors the `generic` seed structure but showcases Analog Elk's own
internal-platform style: a studio running its delivery, sprints, and releases on
the CMS it ships.

## Files

| File                   | Collection      | Rows | What it shows                                              |
|------------------------|-----------------|------|-----------------------------------------------------------|
| `organizations.json`   | organizations   | 1    | The `Analog Elk` reference org                            |
| `contacts.json`        | contacts        | 3    | Founder, design lead, ops — synthetic people             |
| `projects.json`        | projects        | 2    | Elk OS Platform + Internal Delivery Portal               |
| `sprints.json`         | sprints         | 2    | Foundation (done) + Schema & Seed (active)               |
| `tasks.json`           | tasks           | 5    | A walkable board spanning both sprints/projects          |
| `releases.json`        | releases        | 2    | v0.1.0 published + v0.2.0 draft, with markdown changelogs |

## Safety

Every row is **synthetic** and tagged `is_test_data: true`.

- **No real secrets / tokens / passwords.** None appear in any file.
- **No real client PII.** People are fictional; emails use the reserved
  `analogelk.example` / `.example` domains; phones are in the reserved
  `555-01xx` range; websites use `.example`.
- This profile is Mike's reproducer/showcase, **not** a backup of production
  data. It demonstrates the platform with safe, demo-grade content.

## Referential integrity

IDs are stable string slugs so cross-references resolve on load:

- `contacts.organization` → `organizations.id`
- `projects.organization` → `organizations.id`
- `sprints.project` → `projects.id`
- `tasks.project` / `tasks.sprint` / `tasks.assigned_to_contact` → respective ids
- `releases.project` → `projects.id`
