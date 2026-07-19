#!/usr/bin/env bash
# =============================================================================
# Muster portal -- container smoke test.
# =============================================================================
# Boots a built portal image and proves it serves a rebranded portal without a
# live Directus (USE_STATIC_FALLBACK is baked true; the login route renders
# standalone). The backstop behind prepare-context.sh's patch assertions.
#
#   portal/smoke-test.sh <image-ref>        boot + probe /login and /
#   portal/smoke-test.sh --assert-only FILE  run only the HTML assertion
# =============================================================================
set -uo pipefail

# assert_login_html <file> -- the brand assertion, factored out so it is unit
# testable against a saved HTML fixture (no Docker).
assert_login_html() {
  local body
  body="$(cat "$1")"
  if ! grep -q 'Muster' <<<"$body"; then
    echo "[smoke] /login body does not contain 'Muster' -- rebrand did not reach the rendered page" >&2
    return 1
  fi
  if grep -q 'Analog Elk' <<<"$body"; then
    echo "[smoke] /login body still contains 'Analog Elk' -- half-rebranded image" >&2
    return 1
  fi
  echo "[smoke] /login brand assertion passed (Muster present, Analog Elk absent)"
  return 0
}

if [ "${1:-}" = "--assert-only" ]; then
  [ -n "${2:-}" ] || { echo "[smoke] --assert-only needs an HTML file" >&2; exit 2; }
  assert_login_html "$2"
  exit $?
fi

IMAGE="${1:?usage: smoke-test.sh <image-ref>}"
PORT="${SMOKE_PORT:-3999}"
NAME="muster-portal-smoke-$$"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "[smoke] booting ${IMAGE} on :${PORT}"
# USE_STATIC_FALLBACK is baked true; DIRECTUS_TOKEN/URL are dummies so the
# production instrumentation hook does not fail-fast on a missing token.
docker run -d --name "$NAME" -p "${PORT}:3000" \
  -e USE_STATIC_FALLBACK=true \
  -e DIRECTUS_TOKEN=smoke \
  -e DIRECTUS_URL=http://127.0.0.1:8055 \
  "$IMAGE" >/dev/null

# Wait for readiness (up to ~40s).
ready=0
for _ in $(seq 1 40); do
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/login" || true)"
  if [ "$code" = "200" ]; then ready=1; break; fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  echo "[smoke] /login never returned 200 (last=${code:-none}). Container logs:" >&2
  docker logs "$NAME" 2>&1 | tail -30 >&2
  exit 1
fi
echo "[smoke] /login 200"

root="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/" || true)"
case "$root" in 200|307|308) echo "[smoke] / ${root}";; *) echo "[smoke] / returned ${root} (expected 200/redirect)" >&2; exit 1;; esac

curl -s "http://127.0.0.1:${PORT}/login" > "/tmp/${NAME}.html"
assert_login_html "/tmp/${NAME}.html" || exit 1
echo "[smoke] PASS"
