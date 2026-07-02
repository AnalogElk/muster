#!/bin/bash
# =============================================================================
# Elk OS — RAG KB migration runner (vendored from Analog Elk v3)
# =============================================================================
# Applies all SQL migrations in order against the RAG knowledge-base Postgres
# container (elkos-rag-postgres in this stack — see compose/compose.rag.yaml).
#
# OPTIONAL: the RAG API self-creates the `documents` table on first boot (see
# PROVENANCE.md), so a fresh stack works without ever running this. Run it to
# apply the full reference schema (FTS indexes, SEO history, v3 optimizations).
#
# Usage:
#   ./migrations/migrate.sh           # Apply pending migrations
#   ./migrations/migrate.sh --force   # Re-apply all migrations (destructive)
#
# Requirements:
#   - the elkos-rag-postgres container must be running (./bin/elk-os up)
#   - docker CLI available on PATH
#
# Overrides (match compose.rag.yaml / your .env when customized):
#   RAG_CONTAINER=elkos-rag-postgres  RAG_POSTGRES_DB=analog_elk  RAG_POSTGRES_USER=analog_elk
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

info()    { echo -e "${CYAN}[migrate]${RESET} $*"; }
success() { echo -e "${GREEN}[migrate]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[migrate]${RESET} $*"; }
error()   { echo -e "${RED}[migrate]${RESET} $*" >&2; }
die()     { error "$*"; exit 1; }

# ---------------------------------------------------------------------------
# Configuration (matches compose/compose.rag.yaml defaults; override via env)
# ---------------------------------------------------------------------------
CONTAINER="${RAG_CONTAINER:-elkos-rag-postgres}"
DB="${RAG_POSTGRES_DB:-analog_elk}"
USER="${RAG_POSTGRES_USER:-analog_elk}"

# Resolve migrations directory relative to this script's location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIGRATIONS_DIR="${SCRIPT_DIR}"

FORCE=false
if [[ "${1:-}" == "--force" ]]; then
    FORCE=true
    warn "Force mode: all migrations will be re-applied."
fi

# ---------------------------------------------------------------------------
# Preflight: verify elk-postgres is running
# ---------------------------------------------------------------------------
info "Checking elk-postgres container..."

if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${CONTAINER}$"; then
    die "Container '${CONTAINER}' is not running. Start the engine first:
    ./bin/elk-engine start"
fi

# Quick connection check
if ! docker exec "${CONTAINER}" pg_isready -U "${USER}" -d "${DB}" -q 2>/dev/null; then
    die "PostgreSQL inside '${CONTAINER}' is not ready. Try again in a few seconds."
fi

success "Container '${CONTAINER}' is healthy."

# ---------------------------------------------------------------------------
# Migration tracking table
# ---------------------------------------------------------------------------
# Create a migrations table so we know which files have already been applied.
docker exec -i "${CONTAINER}" psql -U "${USER}" -d "${DB}" -q <<'SQL'
CREATE TABLE IF NOT EXISTS _elk_migrations (
    id          SERIAL PRIMARY KEY,
    filename    VARCHAR(255) NOT NULL UNIQUE,
    applied_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
SQL

# ---------------------------------------------------------------------------
# Discover and apply migration files
# ---------------------------------------------------------------------------
MIGRATION_FILES=$(find "${MIGRATIONS_DIR}" -maxdepth 1 -name '*.sql' | sort)

if [[ -z "${MIGRATION_FILES}" ]]; then
    warn "No .sql files found in ${MIGRATIONS_DIR}."
    exit 0
fi

APPLIED=0
SKIPPED=0
FAILED=0

for filepath in ${MIGRATION_FILES}; do
    filename=$(basename "${filepath}")

    # Check if already applied (unless --force)
    if [[ "${FORCE}" == "false" ]]; then
        already_applied=$(docker exec "${CONTAINER}" psql -U "${USER}" -d "${DB}" -t -c \
            "SELECT COUNT(*) FROM _elk_migrations WHERE filename = '${filename}';" 2>/dev/null | tr -d '[:space:]')
        if [[ "${already_applied}" == "1" ]]; then
            info "Skipping ${filename} (already applied)"
            SKIPPED=$((SKIPPED + 1))
            continue
        fi
    fi

    info "Applying ${BOLD}${filename}${RESET}..."

    # Apply the migration
    if docker exec -i "${CONTAINER}" psql -U "${USER}" -d "${DB}" \
            --set ON_ERROR_STOP=1 -q < "${filepath}"; then

        # Record successful application
        docker exec "${CONTAINER}" psql -U "${USER}" -d "${DB}" -q -c \
            "INSERT INTO _elk_migrations (filename) VALUES ('${filename}')
             ON CONFLICT (filename) DO UPDATE SET applied_at = NOW();" 2>/dev/null

        success "Applied ${filename}"
        APPLIED=$((APPLIED + 1))
    else
        error "Failed to apply ${filename}"
        FAILED=$((FAILED + 1))
        # Stop on first failure to avoid cascading errors
        break
    fi
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}Migration summary${RESET}"
echo -e "  Applied : ${GREEN}${APPLIED}${RESET}"
echo -e "  Skipped : ${YELLOW}${SKIPPED}${RESET}"
echo -e "  Failed  : ${RED}${FAILED}${RESET}"

if [[ "${FAILED}" -gt 0 ]]; then
    die "One or more migrations failed. See output above."
fi

success "All migrations complete."
