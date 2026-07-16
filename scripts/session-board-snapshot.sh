#!/usr/bin/env bash
# SessionStart: print a one-line board snapshot. Never fails the session, never
# prints the token.
set -uo pipefail

URL="${CLAUDE_PLUGIN_OPTION_DIRECTUS_URL:-}"
TOKEN="${CLAUDE_PLUGIN_OPTION_DIRECTUS_TOKEN:-}"

if [ -z "$URL" ] || [ -z "$TOKEN" ]; then
  echo "Muster: no board configured. Run /muster:connect to point at one."
  exit 0
fi

# -g (globoff) is required: curl otherwise parses the [] in the Directus
# query string as URL globbing ranges and fails before making a request.
resp=$(curl -sS -g -m 8 -H "Authorization: Bearer $TOKEN" \
  "$URL/items/os_tasks?filter[status][_in]=in_progress,in_review&aggregate[count]=id" 2>/dev/null) || {
  echo "Muster: board unreachable at $URL (this is a warning, not a failure)."
  exit 0
}

count=$(printf '%s' "$resp" | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin)["data"][0]
    print(d.get("count",{}).get("id") if isinstance(d.get("count"),dict) else d.get("count","?"))
except Exception:
    print("?")' 2>/dev/null || echo "?")

echo "Muster board: ${count} task(s) in progress or in review. /muster:board for detail."
exit 0
