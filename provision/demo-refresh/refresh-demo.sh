#!/usr/bin/env bash
# =============================================================================
# Elk OS demo box: daily refresh of perishable demo rows
# =============================================================================
# Three families of seeded demo rows decay and must be re-freshened daily or
# the live demo quietly reverts to empty/error states:
#
#   1. analytics_snapshots  — the portal serves a persisted Matomo overview
#      only while collected_at is < 26 h old (SNAPSHOT_MAX_AGE_HOURS).
#      Refresher: provision/seed-full/gapfix-clientdash-topup.py (upserts by
#      (matomo_site_id, range_key), PATCHes collected_at + payload).
#   2. os_insights          — the AI-insights cache only serves rows generated
#      the same UTC day. Refresher: provision/seed-full/insights-seed.py
#      (PATCHes by (organization, period)).
#   3. infra_snapshots      — the Infrastructure Operations section reads the
#      newest snapshot; the seeded window slides stale after 14 days.
#      Refresher: provision/demo-refresh/infra-snapshots-refresh.py (appends
#      one consistent row per missing day).
#
# All three refreshers are idempotent upserts/appends (safe to re-run, add-only)
# and read the Directus admin token from ~/elk-os/.env INSIDE python, so no
# secret ever reaches a command line or this log.
#
# Installed by: sudo cp provision/demo-refresh/elk-os-demo-refresh.cron \
#                        /etc/cron.d/elk-os-demo-refresh
# Logs to:      ~/elk-os/logs/refresh.log (also via the cron redirect)
# =============================================================================
set -u

ELK_ROOT="${ELK_ROOT:-$HOME/elk-os}"
LOG_DIR="${ELK_ROOT}/logs"
LOG_FILE="${LOG_DIR}/refresh.log"
mkdir -p "$LOG_DIR"

# Keep the log from growing without bound (keep last ~2000 lines).
if [ -f "$LOG_FILE" ] && [ "$(wc -l < "$LOG_FILE")" -gt 4000 ]; then
  tail -n 2000 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
fi

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG_FILE"; }

run_step() {
  local name="$1" script="$2"
  if [ ! -f "$script" ]; then
    log "SKIP  ${name}: script not found at ${script}"
    return 0
  fi
  local out rc
  out="$(python3 "$script" 2>&1)"; rc=$?
  if [ $rc -eq 0 ]; then
    log "OK    ${name}: $(printf '%s' "$out" | tail -n 3 | tr '\n' ' | ')"
  else
    log "FAIL  ${name} (rc=${rc}): $(printf '%s' "$out" | tail -n 5 | tr '\n' ' | ')"
  fi
  return 0
}

log "=== demo refresh start ==="
run_step "analytics_snapshots (clientdash topup)" "${ELK_ROOT}/provision/seed-full/gapfix-clientdash-topup.py"
run_step "os_insights (insights seed)"            "${ELK_ROOT}/provision/seed-full/insights-seed.py"
run_step "infra_snapshots (daily appender)"       "${ELK_ROOT}/provision/demo-refresh/infra-snapshots-refresh.py"
log "=== demo refresh done ==="
