#!/usr/bin/env bash
# =============================================================================
# Elk OS — one-shot VPS provisioner (the reliable full-stack path)
# =============================================================================
# Run this on a FRESH Ubuntu 22.04/24.04 VPS (root) to stand up a live Elk OS:
# Docker + the elk-os stack (Postgres + Directus + RAG + optional portal) behind
# Caddy with automatic TLS on ${ELK_OS_DOMAIN}, then migrate + seed + wire so a
# Claude session on the box reads the deployment's own os_* board.
#
# Usage (as cloud-init user-data, or `sudo bash cloud-init.sh`):
#   export ELK_OS_DOMAIN=demo.example.com        # or 1.2.3.4.sslip.io (no DNS needed)
#   export ELK_OS_ADMIN_EMAIL=you@example.com    # optional (default admin@<domain>)
#   export ELK_OS_PROFILE=generic                # generic | analogelk
#   # --- full-stack portal (optional) — needs PUBLISHED images (see README) ---
#   export PORTAL_IMAGE=ghcr.io/<owner>/elk-os-portal:0.1.0
#   export RAG_IMAGE=ghcr.io/<owner>/elk-os-rag-api:0.1.0
#   # --- where to get elk-os ---
#   export ELK_OS_REPO=https://github.com/<owner>/elk-os.git   # git source, OR
#   export ELK_OS_SOURCE_DIR=/root/elk-os                      # a pre-copied tree
#   bash cloud-init.sh
#
# Portal note (honest): a fresh box CANNOT build the portal image — it needs the
# private analog-elk-front-end source and a heavy Next build. So the portal runs
# only when PORTAL_IMAGE + RAG_IMAGE point at PUBLISHED images. Without them this
# script still stands up Directus + the RAG engine + the os_* board + the wired
# Claude loop (the portal is the only surface omitted), and says so.
#
# Idempotent-ish: re-running is safe (init is skipped if .env exists; up/migrate/
# seed/wire are each idempotent).
# =============================================================================
set -euo pipefail

log() { echo "[elk-os-provision] $*"; }
die() { echo "[elk-os-provision] ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 0. Config + preconditions
# ---------------------------------------------------------------------------
ELK_OS_DOMAIN="${ELK_OS_DOMAIN:-}"
ELK_OS_PROFILE="${ELK_OS_PROFILE:-generic}"
ELK_OS_INSTALL_DIR="${ELK_OS_INSTALL_DIR:-/opt/elk-os}"
ELK_OS_REPO="${ELK_OS_REPO:-}"
ELK_OS_REF="${ELK_OS_REF:-main}"
ELK_OS_SOURCE_DIR="${ELK_OS_SOURCE_DIR:-}"
PORTAL_IMAGE="${PORTAL_IMAGE:-}"
RAG_IMAGE="${RAG_IMAGE:-}"

[ -n "$ELK_OS_DOMAIN" ] || die "ELK_OS_DOMAIN is required (a domain, or <ip>.sslip.io)."
ELK_OS_ADMIN_EMAIL="${ELK_OS_ADMIN_EMAIL:-admin@${ELK_OS_DOMAIN}}"

if [ "$(id -u)" -ne 0 ]; then
  die "Run as root (sudo). Needs to install Docker + bind ports 80/443."
fi

# ---------------------------------------------------------------------------
# 1. Base packages + Docker Engine (official convenience script)
# ---------------------------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive
log "Installing base packages (git, curl, openssl, python3, ca-certificates)…"
apt-get update -y
apt-get install -y --no-install-recommends \
  ca-certificates curl git openssl python3 rsync

if ! command -v docker >/dev/null 2>&1; then
  log "Installing Docker Engine via get.docker.com…"
  curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
  sh /tmp/get-docker.sh
  rm -f /tmp/get-docker.sh
else
  log "Docker already installed — skipping."
fi
systemctl enable --now docker
docker compose version >/dev/null 2>&1 || die "docker compose plugin missing after install."

# ---------------------------------------------------------------------------
# 2. Place the elk-os source tree at $ELK_OS_INSTALL_DIR
# ---------------------------------------------------------------------------
if [ -d "${ELK_OS_INSTALL_DIR}/.git" ] || [ -f "${ELK_OS_INSTALL_DIR}/bin/elk-os" ]; then
  log "elk-os already present at ${ELK_OS_INSTALL_DIR} — reusing."
elif [ -n "$ELK_OS_SOURCE_DIR" ]; then
  [ -f "${ELK_OS_SOURCE_DIR}/bin/elk-os" ] || die "ELK_OS_SOURCE_DIR has no bin/elk-os: $ELK_OS_SOURCE_DIR"
  log "Copying elk-os from ${ELK_OS_SOURCE_DIR} → ${ELK_OS_INSTALL_DIR}…"
  mkdir -p "$ELK_OS_INSTALL_DIR"
  rsync -a --exclude '.env' --exclude '.elk-os-state.json' \
    --exclude 'wire/' --exclude 'portal/.build/' \
    "${ELK_OS_SOURCE_DIR}/" "${ELK_OS_INSTALL_DIR}/"
elif [ -n "$ELK_OS_REPO" ]; then
  log "Cloning ${ELK_OS_REPO} (ref ${ELK_OS_REF}) → ${ELK_OS_INSTALL_DIR}…"
  git clone --branch "$ELK_OS_REF" --depth 1 "$ELK_OS_REPO" "$ELK_OS_INSTALL_DIR"
else
  die "No source: set ELK_OS_REPO (git URL) or ELK_OS_SOURCE_DIR (pre-copied tree)."
fi

cd "$ELK_OS_INSTALL_DIR"
chmod +x bin/elk-os

# ---------------------------------------------------------------------------
# 3. Decide portal mode (published image vs omit). The RAG engine always builds
#    locally on the box (it is self-contained); only the portal needs an image.
# ---------------------------------------------------------------------------
USE_PORTAL=0
if [ -n "$PORTAL_IMAGE" ] && [ -n "$RAG_IMAGE" ]; then
  USE_PORTAL=1
  log "Portal mode: PUBLISHED images (portal + rag pulled, no local build)."
elif [ -n "$PORTAL_IMAGE" ] && [ -z "$RAG_IMAGE" ]; then
  die "PORTAL_IMAGE is set but RAG_IMAGE is not. The published-images toggle pulls BOTH. Set RAG_IMAGE too (or unset PORTAL_IMAGE to run without the portal)."
else
  log "Portal mode: OMITTED. No PORTAL_IMAGE given and a fresh box cannot build the"
  log "portal (needs the private front-end source). Standing up Directus + RAG +"
  log "the os_* board + the wired Claude loop. Publish a portal image and re-run"
  log "with PORTAL_IMAGE+RAG_IMAGE to add the portal surface."
fi

# ---------------------------------------------------------------------------
# 4. init (.env) for the box target — skipped if .env already exists
# ---------------------------------------------------------------------------
if [ ! -f .env ]; then
  log "Generating .env (profile=${ELK_OS_PROFILE}, target=box)…"
  ./bin/elk-os init --profile "$ELK_OS_PROFILE" --target box
else
  log ".env already exists — keeping it (init skipped)."
fi
# Belt-and-braces: .env carries every stack secret — owner-only, even if it
# pre-existed from an older install that wrote it world-readable.
chmod 600 .env

# Box-target wiring: pin the public origins so the host CLI + portal + Directus
# all agree. Directus lives on cms.${ELK_OS_DOMAIN}; the portal lives on
# app.${ELK_OS_DOMAIN}; the apex serves the static whitepaper landing (site/).
set_kv() { # key value — replace or append in .env
  local k="$1" v="$2"
  if grep -qE "^${k}=" .env; then
    python3 - "$k" "$v" <<'PY'
import sys
k, v = sys.argv[1], sys.argv[2]
lines = open(".env").read().splitlines()
out = [(k + "=" + v) if l.split("=", 1)[0] == k else l for l in lines]
open(".env", "w").write("\n".join(out) + "\n")
PY
  else
    printf '%s=%s\n' "$k" "$v" >> .env
  fi
}
set_kv ELK_OS_DOMAIN "$ELK_OS_DOMAIN"
set_kv DIRECTUS_ADMIN_EMAIL "$ELK_OS_ADMIN_EMAIL"
# Host CLI (up/migrate/seed/wire) reaches Directus through its public cms origin.
set_kv DIRECTUS_URL "https://cms.${ELK_OS_DOMAIN}"
set_kv NEXT_PUBLIC_DIRECTUS_URL "https://cms.${ELK_OS_DOMAIN}"

if [ "$USE_PORTAL" -eq 1 ]; then
  set_kv ELK_OS_WITH_PORTAL true
  set_kv ELK_OS_USE_PUBLISHED_IMAGES true
  set_kv PORTAL_IMAGE "$PORTAL_IMAGE"
  set_kv RAG_IMAGE "$RAG_IMAGE"
else
  set_kv ELK_OS_WITH_PORTAL false
  set_kv ELK_OS_USE_PUBLISHED_IMAGES false
fi

# ---------------------------------------------------------------------------
# 5. up → migrate → seed → wire → doctor
# ---------------------------------------------------------------------------
log "Bringing the stack up (Caddy provisions TLS for ${ELK_OS_DOMAIN} + app.${ELK_OS_DOMAIN} + cms.${ELK_OS_DOMAIN})…"
./bin/elk-os up

log "Applying schema (migrate)…"
./bin/elk-os migrate

log "Seeding profile data (seed)…"
./bin/elk-os seed

log "Wiring the Claude-side OS + enabling the native Directus MCP (wire)…"
./bin/elk-os wire

log "Health board (doctor)…"
./bin/elk-os doctor || log "doctor reported a red row — inspect: cd ${ELK_OS_INSTALL_DIR} && ./bin/elk-os logs <service>"

log "Done."
log "  Landing (whitepaper): https://${ELK_OS_DOMAIN}"
log "  Portal (if enabled):  https://app.${ELK_OS_DOMAIN}"
log "  Directus board:       https://cms.${ELK_OS_DOMAIN}"
log "  Native MCP endpoint:  https://cms.${ELK_OS_DOMAIN}/mcp"
log "  Wired Claude config:  ${ELK_OS_INSTALL_DIR}/wire (run ./run-claude.sh)"
