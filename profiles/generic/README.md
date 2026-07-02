# Generic profile

The blank-slate profile: schema + seed data scrubbed of any Analog Elk origin.
`elk-os init --profile generic` merges [`env.defaults`](./env.defaults) into the
generated `.env`. (The portal UI itself ships Muster-branded — branding is
applied at image build by `portal/prepare-context.sh`, not per profile;
per-profile portal branding is a tracked follow-up.)

- **Brand:** `Demo Co` (placeholder — rebrand freely)
- **Seed (P2):** a synthetic "Demo Co" org with sample tasks/sprints/projects so
  the board is non-empty on first boot.
- **Marketing content:** `USE_STATIC_FALLBACK=true` — the portal reads committed
  JSON instead of requiring live Directus marketing collections.

This profile is the public **demo URL** and the starting point for anyone
self-hosting Elk OS for their own agency.
