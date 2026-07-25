#!/usr/bin/env bash
# =============================================================================
# Muster terminology gate
# =============================================================================
# Enforces the verbiage doctrine on TIER 1 surfaces: the copy that sells the
# product today. Exits non-zero on any retired term, banned word, em dash, or
# undated metric.
#
# TIER 2 (the dated records: whitepaper, build log, WHITEPAPER-LOG, CHANGELOG,
# identity-brief) is deliberately NOT scanned. Those are preserved evidence,
# corrected by dated note, never by silent revision. Rewriting them to match
# current positioning is the one move that would undercut a project whose whole
# argument is that it publishes what it cannot do.
#
# Usage: site/check-terms.sh [repo-root]
# =============================================================================
set -uo pipefail

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT" || exit 2

TIER1=(
  site/index.html
  site/privacy.html
  site/og.svg
  README.md
  commands/connect.md
  commands/board.md
  commands/up.md
  commands/doctor.md
  skills/muster-protocol/SKILL.md
  .claude-plugin/plugin.json
  .claude-plugin/marketplace.json
)

# Retired positioning (doctrine section 2 + amendment A7).
# "board" alone stays legal: it is the literal Tasks board and /muster:board.
RETIRED=(
  "shared task board"
  "task board for your Claude agents"
  "agency OS"
  "agency operating system"
  "operating system for agentic software teams"
  "Claude-side OS"
  "runs itself"
  "built itself"
  "ships itself"
  "agent-native"
  "AI-native"
  "vibecoder"
  "vibe-coded"
  "one stop shop"
  "one-stop-shop"
  "all-in-one"
  "employee portal"
  "admin portal"
  "live board"
  "intelligent layer"
  "Elk Chat"
  "permission-aware"
  "Elk OS"
  "fully populated"
  "one-click"
  "zero-click connection"
  "nothing to clone"
  "no setup"
)

# Hype vocabulary (doctrine section 3).
BANNED=(
  "revolutionary" "game-changing" "seamless" "effortless" "turnkey"
  "enterprise-grade" "production-ready" "single source of truth"
  "AI-powered" "cutting-edge" "best-in-class"
)

# Metrics that may not ship without an as-of date (doctrine section 7).
UNDATED=(
  "0\.1\.3"
  "11 projects"
  "69 tasks"
  "81 tasks"
  "27-section"
  "14-section"
  "2\.5 hours"
  "2M tokens"
)

fail=0
hit() { printf '  %-46s %s\n' "$1" "$2"; fail=1; }

# A retired term is banned as a CLAIM, not as a denial. "There is no zero-click
# connection" is the honest catch doing its job; "zero-click connect" is the lie
# it exists to prevent. Report only NON-negated occurrences.
#
# The negator often lands on the previous line, because prose wraps. Testing a
# single line misses that and flags the honest catch as a violation, which is
# how this gate would train someone to delete their own disclosures. So test a
# two-line window: the match plus the line before it.
claim_lines() {
  local term="$1" file="$2"
  awk -v term="$term" '
    BEGIN { IGNORECASE = 1 }
    {
      window = prev " " $0
      if (index(tolower($0), tolower(term)) > 0) {
        if (window !~ /(no|not|never|without|isn.t|cannot) [^\n]{0,40}$/ ||
            window !~ tolower(term)) { }
        # negated if a negator appears within ~40 chars before the term
        lw = tolower(window); lt = tolower(term)
        pos = index(lw, lt)
        pre = substr(lw, (pos > 60 ? pos - 60 : 1), (pos > 60 ? 60 : pos - 1))
        if (pre ~ /(there is no|there.s no|is no|are no|no |not |never |without |cannot |does not )/) next
        print NR ":" $0
      }
      prev = $0
    }
  ' "$file" 2>/dev/null
}

echo "Muster terminology gate: ${#TIER1[@]} tier-1 surfaces"
echo

for f in "${TIER1[@]}"; do
  [ -f "$f" ] || continue

  for term in "${RETIRED[@]}"; do
    line="$(claim_lines "$term" "$f" | head -1 | cut -d: -f1)"
    [ -n "$line" ] && hit "RETIRED  \"$term\"" "$f:$line"
  done

  for term in "${BANNED[@]}"; do
    line="$(claim_lines "$term" "$f" | head -1 | cut -d: -f1)"
    [ -n "$line" ] && hit "BANNED   \"$term\"" "$f:$line"
  done

  for term in "${UNDATED[@]}"; do
    if grep -qiE -- "$term" "$f" 2>/dev/null; then
      hit "UNDATED  \"$term\"" "$f:$(grep -inE -m1 -- "$term" "$f" | cut -d: -f1)"
    fi
  done

  # Em dash, literal and encoded. Mike's standing rule.
  if grep -qE -- '—|&mdash;|&#8212;|&#x2014;' "$f" 2>/dev/null; then
    hit "EM DASH" "$f:$(grep -nE -m1 -- '—|&mdash;|&#8212;|&#x2014;' "$f" | cut -d: -f1)"
  fi
done

echo
if [ "$fail" -eq 0 ]; then
  echo "PASS: no retired terms, banned words, undated metrics, or em dashes on tier 1."
  exit 0
fi
echo "FAIL: fix the hits above, or amend the doctrine deliberately."
exit 1
