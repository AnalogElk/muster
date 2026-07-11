#!/usr/bin/env bash
# Unit test for portal/rebrand-check.sh - fixture-based, no network, no Docker.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../rebrand-check.sh
source "${HERE}/../rebrand-check.sh"

fail=0
check() { if [ "$1" = "$2" ]; then echo "ok   - $3"; else echo "FAIL - $3 (want '$2' got '$1')"; fail=1; fi; }

# --- fixture A: source HAS the brand string -> rebrand succeeds, string gone ---
A="$(mktemp -d)"
trap 'rm -rf "$A" "$B"' EXIT
mkdir -p "$A/app"
printf '%s\n' 'export const title = "Analog Elk portal";' > "$A/app/page.tsx"
printf '%s\n' '{ "name": "ANALOG ELK" }' > "$A/app/meta.json"
rebrand_tree "$A"; rc=$?
check "$rc" "0" "rebrand_tree exits 0 when brand present"
check "$(grep -rc 'Analog Elk' "$A" | awk -F: '{s+=$2} END{print s+0}')" "0" "no 'Analog Elk' remains"
check "$(grep -rl 'Muster portal' "$A" | wc -l | tr -d ' ')" "1" "'Muster portal' written"
check "$(grep -rl 'MUSTER' "$A" | wc -l | tr -d ' ')" "1" "caps variant replaced"

# --- fixture B: source has NO brand string -> rebrand FAILS loudly ---
B="$(mktemp -d)"
mkdir -p "$B/app"
printf '%s\n' 'export const title = "Some Renamed Brand";' > "$B/app/page.tsx"
out="$(rebrand_tree "$B" 2>&1)"; rc=$?
check "$rc" "1" "rebrand_tree exits 1 when brand absent (AE renamed it)"
case "$out" in *"not found in source"*) echo "ok   - error message is actionable";; *) echo "FAIL - error message missing 'not found in source'"; fail=1;; esac

exit "$fail"
