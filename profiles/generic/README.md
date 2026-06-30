# Generic profile

The blank, unbranded agency-OS. `elk-os init --profile generic` merges
[`env.defaults`](./env.defaults) into the generated `.env`.

- **Brand:** `Demo Co` (placeholder — rebrand freely)
- **Seed (P2):** a synthetic "Demo Co" org with sample tasks/sprints/projects so
  the board is non-empty on first boot.
- **Marketing content:** `USE_STATIC_FALLBACK=true` — the portal reads committed
  JSON instead of requiring live Directus marketing collections.

This profile is the public **demo URL** and the starting point for anyone
self-hosting Elk OS for their own agency.
