#!/usr/bin/env bash
# =============================================================================
# Elk OS — Directus admin static-token minter (non-interactive)
# =============================================================================
# The agencyos-test prototype required a human to click "Generate Static Token"
# in the Directus UI. We automate it:
#
#   1. Directus auto-creates the admin user from ADMIN_EMAIL/ADMIN_PASSWORD on
#      first boot of an empty database.
#   2. We log in over REST to get a short-lived access token.
#   3. We generate a strong random static token and PATCH it onto the admin user.
#   4. We verify the static token authenticates, then write it back to .env.
#
# Idempotent: if DIRECTUS_ADMIN_TOKEN is already populated in .env, we no-op.
# The token is NEVER echoed to stdout/stderr (constitution rule).
#
# Usage: mint-token.sh <path-to-.env>
# =============================================================================
set -euo pipefail

# Owner-only perms for the .env rewrite (the awk tmp file inherits this umask).
umask 077

ENV_FILE="${1:?usage: mint-token.sh <path-to-.env>}"
[ -f "$ENV_FILE" ] || { echo "[bootstrap] env file not found: $ENV_FILE" >&2; exit 1; }

# --- minimal .env get/set (self-contained so this script stands alone) -------
get_env() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | head -n1 | cut -d= -f2- || true
}

set_env() {
  local key="$1" val="$2"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    awk -v k="$key" -v v="$val" 'BEGIN{FS="="} $1==k{print k"="v; next} {print}' \
      "$ENV_FILE" > "$ENV_FILE.tmp" && mv "$ENV_FILE.tmp" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$val" >> "$ENV_FILE"
  fi
}

# curl with a Bearer token — the Authorization header travels via a /dev/fd
# header file (process substitution, curl's `-H @file`), NEVER argv, for the
# same `ps`/procfs reason the request bodies below travel over stdin.
curl_tok() {
  local tok="$1"; shift
  curl -H @<(printf 'Authorization: Bearer %s\n' "$tok") "$@"
}

URL="$(get_env DIRECTUS_URL)";            URL="${URL:-http://localhost:8056}"
EMAIL="$(get_env DIRECTUS_ADMIN_EMAIL)";  EMAIL="${EMAIL:-admin@example.com}"
PASSWORD="$(get_env DIRECTUS_ADMIN_PASSWORD)"
EXISTING="$(get_env DIRECTUS_ADMIN_TOKEN)"

# --- idempotency: a token already present and working? -----------------------
if [ -n "$EXISTING" ]; then
  if curl_tok "$EXISTING" -sf -o /dev/null "${URL}/users/me?fields=id" 2>/dev/null; then
    echo "[bootstrap] admin static token already present and valid — skipping mint."
    exit 0
  fi
  echo "[bootstrap] existing DIRECTUS_ADMIN_TOKEN did not authenticate — re-minting."
fi

if [ -z "$PASSWORD" ]; then
  echo "[bootstrap] DIRECTUS_ADMIN_PASSWORD is empty in .env — cannot log in." >&2
  exit 1
fi

# --- 1. log in for a short-lived access token --------------------------------
# The body is piped over stdin (--data @-), NOT passed as an argv literal: curl
# arguments are visible to every user on the host via `ps`/procfs, and this body
# carries the admin password.
# JSON-escape backslash + double-quote: init auto-generates a hex password, but
# a user-set DIRECTUS_ADMIN_PASSWORD containing either character would corrupt
# the body and turn a good password into a login failure.
json_escape() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'; }
LOGIN_BODY=$(printf '{"email":"%s","password":"%s"}' "$(json_escape "$EMAIL")" "$(json_escape "$PASSWORD")")
LOGIN_RESP=$(printf '%s' "$LOGIN_BODY" | curl -sf -X POST "${URL}/auth/login" \
  -H "Content-Type: application/json" \
  --data @- 2>/dev/null) || {
  echo "[bootstrap] login to ${URL} failed — is Directus healthy?" >&2
  exit 1
}

ACCESS=$(printf '%s' "$LOGIN_RESP" | grep -o '"access_token":"[^"]*"' | head -n1 | cut -d'"' -f4)
if [ -z "$ACCESS" ]; then
  echo "[bootstrap] could not parse access_token from login response." >&2
  exit 1
fi

# --- 2. resolve the admin user id --------------------------------------------
ME=$(curl_tok "$ACCESS" -sf "${URL}/users/me?fields=id" 2>/dev/null) || {
  echo "[bootstrap] /users/me lookup failed." >&2; exit 1; }
USER_ID=$(printf '%s' "$ME" | grep -o '"id":"[^"]*"' | head -n1 | cut -d'"' -f4)
if [ -z "$USER_ID" ]; then
  echo "[bootstrap] could not resolve admin user id." >&2
  exit 1
fi

# --- 3. generate + assign a strong static token ------------------------------
# Token travels over stdin for the same reason as the login body above.
NEW_TOKEN=$(openssl rand -hex 32)
printf '{"token":"%s"}' "$NEW_TOKEN" | curl_tok "$ACCESS" -sf -o /dev/null -X PATCH "${URL}/users/${USER_ID}" \
  -H "Content-Type: application/json" \
  --data @- 2>/dev/null || {
  echo "[bootstrap] failed to PATCH static token onto admin user." >&2
  exit 1
}

# --- 4. verify the static token, then persist to .env ------------------------
if ! curl_tok "$NEW_TOKEN" -sf -o /dev/null "${URL}/users/me?fields=id" 2>/dev/null; then
  echo "[bootstrap] minted token did not authenticate — aborting without writing .env." >&2
  exit 1
fi

set_env DIRECTUS_ADMIN_TOKEN "$NEW_TOKEN"
unset NEW_TOKEN ACCESS
echo "[bootstrap] admin static token minted and written to .env (value hidden)."
