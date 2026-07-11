#!/usr/bin/env bash
# =============================================================================
# Muster portal - rebrand text replacement + assertions.
# =============================================================================
# Sourced by portal/prepare-context.sh. Replaces the spaced wordmark
# "Analog Elk" (and the all-caps "ANALOG ELK") with "Muster"/"MUSTER" across the
# portal source surface, and PROVES it happened. A silent no-op here ships a
# half-rebranded portal, which is exactly the drift Phase 1 exists to prevent.
#
# Domain strings like "analogelk.com" have no space, so they are NOT touched
# (the login redirect still checks hostname.endsWith("analogelk.com")).
# =============================================================================

# count_brand <dir> -> prints the number of "Analog Elk"/"ANALOG ELK" matches
# across the portal file surface under <dir>.
count_brand() {
  local dir="$1"
  grep -rIoE 'Analog Elk|ANALOG ELK' "$dir" \
    --include='*.tsx' --include='*.ts' --include='*.json' --include='*.mdx' \
    2>/dev/null | grep -vc '/node_modules/' || true
}

# rebrand_tree <dir> -> replace + assert. Exits 1 with an actionable message on
# either failure mode (brand absent before, or survivors after).
rebrand_tree() {
  local dir="$1"
  local before after
  before="$(count_brand "$dir")"
  if [ "${before:-0}" -eq 0 ]; then
    echo "[portal] rebrand: 'Analog Elk' not found in source under ${dir} - the pinned AE commit renamed or restructured the brand wordmark. Update portal/rebrand-check.sh before bumping the pin." >&2
    return 1
  fi
  find "$dir" -type f \( -name '*.tsx' -o -name '*.ts' -o -name '*.json' -o -name '*.mdx' \) \
    -not -path '*/node_modules/*' -print0 \
    | xargs -0 perl -pi -e 's/Analog Elk/Muster/g; s/ANALOG ELK/MUSTER/g'
  after="$(count_brand "$dir")"
  if [ "${after:-0}" -ne 0 ]; then
    echo "[portal] rebrand: ${after} occurrence(s) of 'Analog Elk' survived the replace under ${dir} - investigate before shipping a half-rebranded portal." >&2
    return 1
  fi
  echo "[portal] rebrand: Analog Elk -> Muster (${before} occurrence(s) replaced, 0 remain)"
  return 0
}
