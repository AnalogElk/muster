#!/usr/bin/env bash
# =============================================================================
# Elk OS — open-task snapshot (the human <-> agent loop, made visible)
# =============================================================================
# Queries THIS deployment's Directus os_tasks board and prints the open-task
# queue at session start, so every Claude Code session opens already aware of
# the shared work. This is the agent half of the loop the human sees in the
# portal: both read and write the same os_tasks rows.
#
# Reads DIRECTUS_URL + DIRECTUS_ADMIN_TOKEN from the deployment .env named by
# ELK_OS_ENV_FILE (set by .claude/settings.json), falling back to ambient env.
# Status-tolerant: anything that is NOT a terminal state (completed/done/
# archived/cancelled) counts as open, so it survives profile status drift.
#
# Never prints the token. Fails soft: on any error it prints one line and
# exits 0 — a snapshot must never break a session.
# =============================================================================
set -u

ENV_FILE="${ELK_OS_ENV_FILE:-}"
if [ -n "$ENV_FILE" ] && [ -f "$ENV_FILE" ]; then
  DIRECTUS_URL="${DIRECTUS_URL:-$(grep -E '^DIRECTUS_URL=' "$ENV_FILE" 2>/dev/null | head -n1 | cut -d= -f2-)}"
  DIRECTUS_ADMIN_TOKEN="${DIRECTUS_ADMIN_TOKEN:-$(grep -E '^DIRECTUS_ADMIN_TOKEN=' "$ENV_FILE" 2>/dev/null | head -n1 | cut -d= -f2-)}"
fi
DIRECTUS_URL="${DIRECTUS_URL:-http://localhost:8056}"
DIRECTUS_ADMIN_TOKEN="${DIRECTUS_ADMIN_TOKEN:-}"

if [ -z "$DIRECTUS_ADMIN_TOKEN" ]; then
  printf '[tasks] snapshot skipped — no DIRECTUS_ADMIN_TOKEN (set it in the deployment .env).\n'
  exit 0
fi

# Pull a wide slice and bucket client-side (avoids brittle server-side status
# enums that vary by profile). fields kept minimal; sort newest-ish last.
# The Authorization header travels via a /dev/fd header file (process
# substitution), never argv — argv is readable host-wide via `ps`/procfs.
RAW=$(curl -sS --max-time 5 \
  -H @<(printf 'Authorization: Bearer %s\n' "$DIRECTUS_ADMIN_TOKEN") \
  "${DIRECTUS_URL}/items/os_tasks?limit=100&fields=name,status,priority&sort=priority" 2>/dev/null) || RAW=""

if [ -z "$RAW" ]; then
  printf '[tasks] snapshot: Directus unreachable or timed out (loop read failed).\n'
  exit 0
fi

if command -v python3 >/dev/null 2>&1; then
  # Pass the payload via env (NOT stdin): a `python3 - <<'PY'` heredoc already
  # claims stdin for the program text, so a piped stdin would be empty.
  ELK_TASKS_JSON="$RAW" ELK_TASKS_URL="$DIRECTUS_URL" python3 - <<'PY' || \
    printf '[tasks] snapshot: could not parse os_tasks response.\n'
import os, sys, json
url = os.environ.get("ELK_TASKS_URL", "")
try:
    rows = json.loads(os.environ.get("ELK_TASKS_JSON", "")).get("data", [])
except Exception:
    print("[tasks] snapshot: could not parse os_tasks response."); sys.exit(0)

TERMINAL = {"completed", "done", "archived", "cancelled", "closed"}
open_rows = [r for r in rows if str(r.get("status", "")).lower() not in TERMINAL]
total = len(rows)
opn = len(open_rows)

def rank(r):
    p = str(r.get("priority") or "P9")
    return (p, str(r.get("name") or ""))

open_rows.sort(key=rank)
print("[tasks] os_tasks board: %d open / %d total  (CMS: %s)" % (opn, total, url))
for r in open_rows[:8]:
    pr = r.get("priority") or "--"
    st = r.get("status") or "?"
    print("   [%s] %-34s %s" % (pr, (r.get("name") or "")[:34], st))
if opn > 8:
    print("   … +%d more open" % (opn - 8))
PY
else
  # No python3: degrade to a raw count via grep. Still fails soft.
  N=$(printf '%s' "$RAW" | grep -o '"name"' | wc -l | tr -d ' ')
  printf '[tasks] os_tasks board reachable — %s rows (install python3 for the detailed queue).\n' "${N:-?}"
fi

exit 0
