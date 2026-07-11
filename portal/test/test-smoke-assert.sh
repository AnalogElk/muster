#!/usr/bin/env bash
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SMOKE="${HERE}/../smoke-test.sh"
fail=0
check() { if [ "$1" = "$2" ]; then echo "ok   - $3"; else echo "FAIL - $3 (want '$2' got '$1')"; fail=1; fi; }

bash "$SMOKE" --assert-only "${HERE}/fixtures/login-ok.html" >/dev/null 2>&1
check "$?" "0" "assert-only passes on a rebranded login page"

bash "$SMOKE" --assert-only "${HERE}/fixtures/login-bad.html" >/dev/null 2>&1
check "$?" "1" "assert-only fails on an un-rebranded login page"

exit "$fail"
