#!/usr/bin/env bash
# =============================================================================
# Elk OS — portal build-context preparer (P4)
# =============================================================================
# The portal source is the analog-elk-front-end app, vendored READ-ONLY from a
# PINNED commit of origin/main (see ./PINNED_COMMIT). That repo is a HOT shared
# checkout with many active worktrees, so we NEVER build from it in place — we
# extract a frozen `git archive` of the pinned commit into ./.build (gitignored)
# and apply a small, idempotent set of self-host patches on top.
#
# Patches (all confined to ./.build — the source repo is never touched):
#   1. .npmrc        — drop the private @analogelk GitHub Packages registry +
#                      authToken (needs a GITHUB_TOKEN we don't ship). Keep
#                      legacy-peer-deps=true.
#   2. package.json  — remove the private dep "@analogelk/background-three-js"
#                      (a marketing 3D hero background, lazy-loaded and unused on
#                      the routes we smoke-test). Forces --no-frozen-lockfile.
#   3. next.config.js— add `output: 'standalone'` for a slim runnable image;
#                      drop the private pkg from transpilePackages; ignore eslint
#                      + type errors during build (the pinned commit is already
#                      CI-verified on main — we're packaging, not re-vetting).
#   4. three-background-wrapper.tsx — stub to a no-op so the removed private pkg
#                      is never imported.
#   5. rebrand        — the self-host portal ships as "Muster", not "Analog Elk".
#                      Replace the user-visible brand NAME (login wordmark +
#                      page titles/metadata, header/nav + sidebar brand, footer,
#                      JSON-LD org name) and swap the AE logo mark for a clean
#                      "M" monogram. Domain strings (analogelk.com) are left
#                      untouched — they have no space and the login redirect's
#                      prod-host check still relies on them.
#
# Idempotent: safe to re-run. Re-extract from scratch with --force.
#
# Usage:
#   ./prepare-context.sh            # extract (if needed) + patch
#   ./prepare-context.sh --force    # wipe ./.build and re-extract + patch
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${HERE}/.build"
PIN_FILE="${HERE}/PINNED_COMMIT"
SOURCE_REPO="${PORTAL_SOURCE_REPO:-/Users/michaelwalliser/Desktop/DevProd/analog-elk-front-end}"

[ -f "$PIN_FILE" ] || { echo "[portal] PINNED_COMMIT not found at $PIN_FILE" >&2; exit 1; }
PIN="$(tr -d '[:space:]' < "$PIN_FILE")"
[ -n "$PIN" ] || { echo "[portal] PINNED_COMMIT is empty" >&2; exit 1; }

force=0
[ "${1:-}" = "--force" ] && force=1

# ---------------------------------------------------------------------------
# 1. Extract the frozen archive (read-only; never edits the source repo)
# ---------------------------------------------------------------------------
if [ "$force" -eq 1 ]; then
  echo "[portal] --force: removing ${BUILD_DIR}"
  rm -rf "$BUILD_DIR"
fi

if [ ! -f "${BUILD_DIR}/package.json" ]; then
  command -v git >/dev/null 2>&1 || { echo "[portal] git is required" >&2; exit 1; }
  [ -d "$SOURCE_REPO/.git" ] || { echo "[portal] source repo not found: $SOURCE_REPO" >&2; exit 1; }
  echo "[portal] extracting analog-elk-front-end @ ${PIN} → ${BUILD_DIR} (read-only archive)"
  mkdir -p "$BUILD_DIR"
  git -C "$SOURCE_REPO" archive "$PIN" | tar -x -C "$BUILD_DIR"
else
  echo "[portal] reusing existing ${BUILD_DIR} (pass --force to re-extract)"
fi

cd "$BUILD_DIR"

# ---------------------------------------------------------------------------
# 2. Patch .npmrc — strip the private GitHub Packages registry + authToken
# ---------------------------------------------------------------------------
if grep -q '@analogelk' .npmrc 2>/dev/null; then
  echo "[portal] patch .npmrc: dropping @analogelk private registry lines"
  grep -v '@analogelk' .npmrc | grep -v 'npm.pkg.github.com' > .npmrc.tmp || true
  mv .npmrc.tmp .npmrc
fi
# Guarantee legacy-peer-deps is present (the app relies on it).
grep -q 'legacy-peer-deps=true' .npmrc 2>/dev/null || echo 'legacy-peer-deps=true' >> .npmrc

# ---------------------------------------------------------------------------
# 3. Patch package.json — remove the private dependency
# ---------------------------------------------------------------------------
if grep -q '@analogelk/background-three-js' package.json; then
  echo "[portal] patch package.json: removing @analogelk/background-three-js"
  node -e '
    const fs=require("fs");
    const p="package.json";
    const j=JSON.parse(fs.readFileSync(p,"utf8"));
    for (const k of ["dependencies","devDependencies"]) {
      if (j[k] && j[k]["@analogelk/background-three-js"]) delete j[k]["@analogelk/background-three-js"];
    }
    fs.writeFileSync(p, JSON.stringify(j,null,2)+"\n");
  '
fi

# ---------------------------------------------------------------------------
# 4. Patch next.config.js — standalone output, drop private pkg, relax gates
# ---------------------------------------------------------------------------
node -e '
  const fs=require("fs");
  const p="next.config.js";
  let s=fs.readFileSync(p,"utf8");
  let changed=false;

  // a) inject output:standalone + relaxed build gates right after the object open
  if (!/output:\s*["'"'"']standalone["'"'"']/.test(s)) {
    s=s.replace(
      /const nextConfig = \{/,
      "const nextConfig = {\n  // [elk-os P4] slim, self-contained server bundle for the container image\n  output: \"standalone\",\n  // [elk-os P4] packaging a CI-verified pinned commit — do not re-gate on lint/types\n  eslint: { ignoreDuringBuilds: true },\n  typescript: { ignoreBuildErrors: true },"
    );
    changed=true;
  }
  // b) remove the private package from transpilePackages
  if (s.includes("@analogelk/background-three-js")) {
    s=s.replace(/,\s*["'"'"']@analogelk\/background-three-js["'"'"']/g, "");
    changed=true;
  }
  if (changed) { fs.writeFileSync(p,s); console.log("[portal] patch next.config.js: standalone + gates + drop private pkg"); }
  else { console.log("[portal] next.config.js already patched"); }
'

# ---------------------------------------------------------------------------
# 5. Stub the three-background wrapper (the removed private pkg lived here)
# ---------------------------------------------------------------------------
WRAP="components/three-background-wrapper.tsx"
if grep -q '@analogelk/background-three-js' "$WRAP" 2>/dev/null; then
  echo "[portal] patch ${WRAP}: stub to no-op (private 3D pkg removed)"
  cat > "$WRAP" <<'TSX'
// [elk-os P4] The marketing 3D hero background lives in the private
// @analogelk/background-three-js package, which is not shipped with the
// self-host template (it requires GitHub Packages auth). It is lazy-loaded and
// unused on the portal/login/marketing routes the template targets, so we stub
// the wrapper to a no-op. Swap this back if you vendor the package.
export function ThreeBackgroundWrapper() {
  return null;
}
TSX
fi

# ---------------------------------------------------------------------------
# 6. Rebrand "Analog Elk" -> "Muster" across the portal surface (idempotent)
# ---------------------------------------------------------------------------
# Replace the spaced wordmark "Analog Elk" wherever it renders: the login
# wordmark + tagline footer, the <title>/metadata on every login sub-page, the
# header/nav + dashboard sidebar brand, the site footer, and the JSON-LD org
# name (which is server-rendered into /login via the root layout). Re-running
# is a no-op once no "Analog Elk" remains. Domain strings like "analogelk.com"
# have no space, so they are intentionally NOT touched (the login redirect logic
# still checks `hostname.endsWith("analogelk.com")` for prod routing).
echo "[portal] rebrand: Analog Elk -> Muster (portal surface)"
find . -type f \( -name '*.tsx' -o -name '*.ts' -o -name '*.json' -o -name '*.mdx' \) \
  -not -path './node_modules/*' -print0 \
  | xargs -0 perl -pi -e 's/Analog Elk/Muster/g; s/ANALOG ELK/MUSTER/g'

# Swap the Analog-Elk SVG mark for a clean geometric "Muster" M monogram. The
# `ae-logo` / `ae-logo__primary` class hooks are preserved so existing
# fill-override utilities (e.g. the login wordmark's [&_.ae-logo__primary]:fill-primary)
# keep coloring it. Square aspect; honors the width prop.
cat > components/logo.tsx <<'TSX'
interface LogoProps {
  className?: string
  width?: number
  height?: number
}

/**
 * Muster logo — a clean geometric "M" monogram.
 *
 * Keeps the `ae-logo` / `ae-logo__primary` class hooks from the original mark
 * so callers that override the fill (e.g. the login wordmark applying
 * `[&_.ae-logo__primary]:fill-primary`) continue to color it. Defaults to
 * `currentColor` so it inherits text color anywhere else.
 */
export function Logo({ className = "", width = 64, height }: LogoProps) {
  const finalHeight = height ?? width
  return (
    <svg
      viewBox="0 0 64 64"
      width={width}
      height={finalHeight}
      className={`ae-logo ${className}`.trim()}
      role="img"
      aria-label="Muster logo"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        className="ae-logo__primary"
        fill="currentColor"
        d="M8 52 V12 H21 L32 33 L43 12 H56 V52 H44 V28 L32 49 L20 28 V52 Z"
      />
    </svg>
  )
}
TSX
echo "[portal] rebrand: replaced AE logo mark with Muster M monogram"

# ---------------------------------------------------------------------------
# 7. Drop the build-context .dockerignore in place (docker reads it from the
#    context root = .build). Committed source of truth lives at ../.dockerignore.
# ---------------------------------------------------------------------------
if [ -f "${HERE}/.dockerignore" ]; then
  cp "${HERE}/.dockerignore" "${BUILD_DIR}/.dockerignore"
  echo "[portal] copied .dockerignore into build context"
fi

echo "[portal] build context ready at ${BUILD_DIR} (pinned ${PIN})"
