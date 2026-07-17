#!/usr/bin/env bash
# Surgical recreate of ONLY the mocks + portal services on the Muster demo box.
#
# Uses the exact overlay list the running stack was created with (from the
# container's com.docker.compose.project.config_files label) PLUS the mocks
# overlay, matching what the patched bin/elk-os compose() now builds with
# ELK_OS_WITH_MOCKS=true. --no-deps keeps directus & friends untouched;
# no --remove-orphans so nothing else is stopped.
#
# The env file is referenced INSIDE this script only (secrets never hit a
# command line or the transcript).
set -euo pipefail

ROOT="$HOME/elk-os"
CD="$ROOT/compose"

docker compose \
  --project-directory "$ROOT" \
  --env-file "$ROOT/.env" \
  -f "$CD/compose.yaml" \
  -f "$CD/compose.prod.yaml" \
  -f "$CD/compose.rag.yaml" \
  -f "$CD/compose.rag.prod.yaml" \
  -f "$CD/compose.images.rag.yaml" \
  -f "$CD/compose.portal.yaml" \
  -f "$CD/compose.portal.prod.yaml" \
  -f "$CD/compose.images.portal.yaml" \
  -f "$CD/compose.portal.rag.yaml" \
  -f "$CD/compose.mocks.yaml" \
  up -d --no-deps elk-os-mocks portal

echo "--- containers ---"
docker ps --filter name=elk-os-mocks --filter name=elk-os-portal \
  --format '{{.Names}}  {{.Image}}  {{.Status}}'
