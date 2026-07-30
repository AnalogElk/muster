# Characterization coverage (baseline)

Per-script recorded request count under the synthetic responder. Partial = script hit a data/precondition gate or logic error against the empty synthetic CMS; the recorded prefix is still a valid byte-identical bar for its port. Regenerate: `.venv/bin/python gen_goldens.py --all`.

| script | requests | partial reason |
|---|---:|---|
| `provision/seed-full/seed-D4.py` | 401 | AttributeError: 'list' object has no attribute 'get' |
| `provision/seed-full/run2-P3-dam.py` | 318 |  |
| `provision/seed-full/gapfix-seed.py` | 152 |  |
| `provision/seed-full/seed-D1.py` | 150 | KeyError: 'os_activities' |
| `provision/seed-full/gapfix-tools-help-client.py` | 111 | AttributeError: 'list' object has no attribute 'get' |
| `provision/seed-full/audit-drift-perms.py` | 102 |  |
| `provision/seed-full/seed-F4.py` | 89 | KeyError: 'os_products' |
| `provision/seed-demo.py` | 87 |  |
| `provision/seed-full/seed-F3.py` | 63 | TypeError: '<' not supported between instances of 'str' and 'int' |
| `provision/seed-full/run2-P1-data.py` | 58 | AttributeError: 'list' object has no attribute 'get' |
| `provision/seed-full/gapfix-client-messages.py` | 56 |  |
| `provision/seed-full/gapfix-clientdash-topup.py` | 52 | SystemExit: FATAL: no team users found for actor field |
| `provision/seed-full/seed-F1.py` | 50 |  |
| `provision/seed-full/gapfix-client-sections.py` | 47 | AttributeError: 'list' object has no attribute 'get' |
| `provision/seed-full/run2-P2-ledgers.py` | 46 | IndexError: list index out of range |
| `provision/seed-full/gapfix-dashboard-seed.py` | 36 |  |
| `provision/seed-full/seed-D5.py` | 20 | SystemExit: gate: F1 fields absent after polling |
| `provision/re-add-kb.py` | 19 |  |
| `provision/seed-full/probe-gapfix-client4.py` | 17 |  |
| `provision/seed-full/gapfix-clientrole-audit2.py` | 16 |  |
| `provision/seed-full/gapfix4-probe-pre2.py` | 15 |  |
| `provision/seed-full/run2-P1-probe.py` | 15 |  |
| `provision/seed-full/gapfix4-probe-pre.py` | 14 |  |
| `provision/seed-full/seed-F2.py` | 13 | AttributeError: 'list' object has no attribute 'get' |
| `provision/demo-readonly-role.py` | 10 | SystemExit: 1 |
| `provision/seed-full/fetch-dam-objects.py` | 10 |  |
| `provision/seed-full/gapfix-clientrole-audit.py` | 10 |  |
| `provision/seed-full/run2-P2-preprobe.py` | 10 |  |
| `provision/seed-full/gapfix-diag.py` | 7 |  |
| `provision/seed-full/probe-broken.py` | 7 |  |
| `provision/seed-full/probe-gapfix-client4-evidence.py` | 7 |  |
| `provision/seed-full/probe-run2-rebuild.py` | 7 |  |
| `provision/seed-full/gapfix2-seed-blocked-tasks.py` | 6 |  |
| `provision/seed-full/run2-P2-postprobe.py` | 6 | IndexError: list index out of range |
| `provision/seed-full/gapfix2-probe-tasks-invoices.py` | 5 |  |
| `provision/seed-full/gapfix-client-probe.py` | 3 | KeyError: 'os_notifications' |
| `provision/seed-full/gapfix4-probe-post.py` | 3 | IndexError: list index out of range |
| `provision/seed-full/gapfix4-seed.py` | 3 | SystemExit: FATAL missing org2 projects: [] |
| `provision/seed-full/patch-dam-logo-keys.py` | 3 |  |
| `provision/seed-full/gapfix-probe.py` | 2 | KeyError: 'os_invoices' |
| `provision/seed-full/seed-D2.py` | 2 | IndexError: list index out of range |
| `provision/demo-refresh/infra-snapshots-refresh.py` | 1 |  |
| `provision/seed-full/gapfix2-gql-probe.py` | 1 |  |
| `provision/seed-full/gapfix2-nullfill-billing-interval.py` | 1 |  |
| `provision/seed-full/gapfix5-projects.py` | 1 | AssertionError: retainer row not found |
| `provision/seed-full/gapfix6-gql-probe.py` | 1 | KeyError: 'kb_spaces' |
| `provision/seed-full/insights-seed.py` | 1 |  |
| `provision/seed-full/nullfill-retainer-due.py` | 1 | SystemExit: 0 |
| `provision/seed-full/probe-infra-shape.py` | 1 | IndexError: list index out of range |
| `provision/seed-full/probe-rowan-avatar.py` | 1 | SystemExit: 1 |
| `provision/seed-full/seed-D3.py` | 1 | SystemExit: 1 |
| `provision/seed-full/seed-D6.py` | 1 | SystemExit: 1 |
| `provision/seed-full/gapfix6-brand-kb.py` | 0 | SystemExit: 1 |

**Totals:** 53 scripts, 2059 requests locked, 26 partial runs, 1 zero-request (provision/seed-full/gapfix6-brand-kb.py).
