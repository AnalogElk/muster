# Analog Elk profile

Analog Elk's own demo data — the reference instance. `elk-os init
--profile analogelk` merges [`env.defaults`](./env.defaults) into the generated
`.env`.

- **Brand (seed data):** `Analog Elk`. Note the portal UI itself ships
  Muster-branded for every profile (rebrand applied at image build by
  `portal/prepare-context.sh`); per-profile portal branding is a tracked
  follow-up.
- **Seed (P2):** Analog Elk's representative projects/sprints/releases.
- This is the profile that makes Elk OS its own final test case: Analog Elk
  using its CMS, agents, and constitution to build the thing that ships itself
  (see [`WHITEPAPER-LOG.md`](../../WHITEPAPER-LOG.md)).
