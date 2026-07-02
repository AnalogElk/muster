#!/usr/bin/env bash
# =============================================================================
# Elk OS — SessionStart banner
# =============================================================================
# Printed at the top of every Claude Code session opened in a `wire`-d
# deployment directory. Shows which deployment this session is wired to and
# whether its shared-state bus (Directus + the os_* board) is reachable.
#
# Reads DIRECTUS_URL + DIRECTUS_ADMIN_TOKEN from the deployment .env named by
# ELK_OS_ENV_FILE (set by .claude/settings.json), falling back to whatever is
# already exported in the shell. Never prints the token. Must be fast (<2s) and
# ALWAYS exit 0 — a banner must never break a session.
#
# Claude Code captures hook stdout as plain text (no ANSI interpretation), so
# colours are only emitted to a real TTY.
# =============================================================================
set -u

# --- resolve deployment credentials (env file first, then ambient env) -------
ENV_FILE="${ELK_OS_ENV_FILE:-}"
if [ -n "$ENV_FILE" ] && [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  DIRECTUS_URL="${DIRECTUS_URL:-$(grep -E '^DIRECTUS_URL=' "$ENV_FILE" 2>/dev/null | head -n1 | cut -d= -f2-)}"
  DIRECTUS_ADMIN_TOKEN="${DIRECTUS_ADMIN_TOKEN:-$(grep -E '^DIRECTUS_ADMIN_TOKEN=' "$ENV_FILE" 2>/dev/null | head -n1 | cut -d= -f2-)}"
  ELK_OS_BRAND_NAME="${ELK_OS_BRAND_NAME:-$(grep -E '^ELK_OS_BRAND_NAME=' "$ENV_FILE" 2>/dev/null | head -n1 | cut -d= -f2-)}"
fi
DIRECTUS_URL="${DIRECTUS_URL:-http://localhost:8056}"
DIRECTUS_ADMIN_TOKEN="${DIRECTUS_ADMIN_TOKEN:-}"
BRAND="${ELK_OS_BRAND_NAME:-Elk OS}"

if [ -t 1 ]; then
  GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
  CYAN='\033[0;36m'; DIM='\033[2m'; BOLD='\033[1m'; NC='\033[0m'
else
  GREEN=''; RED=''; YELLOW=''; CYAN=''; DIM=''; BOLD=''; NC=''
fi

# --- probe Directus health ----------------------------------------------------
DIR_MARK="${RED}down${NC}"
if curl -sf -o /dev/null --max-time 2 "${DIRECTUS_URL}/server/health" 2>/dev/null; then
  DIR_MARK="${GREEN}up${NC}"
fi

# --- probe the native Directus MCP server (settings.mcp_enabled gate) ---------
MCP_MARK="${DIM}unknown${NC}"
if [ -n "$DIRECTUS_ADMIN_TOKEN" ]; then
  # Header via a /dev/fd file (process substitution), never argv — argv is
  # readable host-wide via `ps`/procfs and this carries the admin token.
  CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 \
    -H @<(printf 'Authorization: Bearer %s\n' "$DIRECTUS_ADMIN_TOKEN") \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -X POST "${DIRECTUS_URL}/mcp" \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' 2>/dev/null || echo 000)
  case "$CODE" in
    200) MCP_MARK="${GREEN}live${NC}" ;;
    403) MCP_MARK="${YELLOW}disabled (run elk-os wire)${NC}" ;;
    *)   MCP_MARK="${RED}unreachable${NC}" ;;
  esac
fi

printf '\n'
printf '%b\n' "${BOLD}${CYAN}Elk OS — ${BRAND}${NC}  ${DIM}agency operating system${NC}"
printf '%b\n' "${DIM}────────────────────────────────────────────${NC}"
printf '  Directus  %b   MCP  %b\n' "$DIR_MARK" "$MCP_MARK"
printf '  %bCMS (shared os_* board): %s%b\n' "$DIM" "$DIRECTUS_URL" "$NC"
printf '%b\n' "${DIM}────────────────────────────────────────────${NC}"
printf '  %bGovernance: see CLAUDE.md — work lands on the os_tasks board.%b\n' "$DIM" "$NC"
printf '\n'

exit 0
