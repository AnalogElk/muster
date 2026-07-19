# Demo-box daily refresh

The Muster demo (app.musterr.dev) seeds three families of perishable rows that
decay without a scheduler:

| Collection | Freshness window | Refresher |
|---|---|---|
| `analytics_snapshots` | 26 h (`SNAPSHOT_MAX_AGE_HOURS`) | `provision/seed-full/gapfix-clientdash-topup.py` |
| `os_insights` | same UTC day | `provision/seed-full/insights-seed.py` |
| `infra_snapshots` | newest row drives the dashboard; 14-day trend | `provision/demo-refresh/infra-snapshots-refresh.py` |

`refresh-demo.sh` runs all three (idempotent, add-only, token read inside
python from `~/elk-os/.env`) and logs to `~/elk-os/logs/refresh.log`.

## Install (on the box)

```bash
sudo cp ~/elk-os/provision/demo-refresh/elk-os-demo-refresh.cron /etc/cron.d/elk-os-demo-refresh
sudo chmod 644 /etc/cron.d/elk-os-demo-refresh
```

The cron.d unit runs daily at 05:17 UTC as the `ubuntu` user. Verify with:

```bash
grep -R elk-os /etc/cron.d/
tail ~/elk-os/logs/refresh.log
```
