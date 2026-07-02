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
#   6. self-host      — the app is wired to the analogelk.com multi-subdomain
#                      topology + a `.analogelk.com` cookie domain. Patch proxy.ts
#                      so any non-analogelk host runs single-domain (path-based,
#                      no cross-subdomain redirects) and auth.ts so cookies are
#                      host-only unless AUTH_COOKIE_DOMAIN is set. Without this
#                      the authed portal redirects off-box and the session never
#                      sticks on a self-host domain.
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
# Portal source checkout: set PORTAL_SOURCE_REPO (env, or via .env — elk-os
# exports it), or keep an analog-elk-front-end checkout as a SIBLING of this
# repo (../analog-elk-front-end).
SOURCE_REPO="${PORTAL_SOURCE_REPO:-${HERE}/../../analog-elk-front-end}"

# Host-tool preflight: the patch steps below run node + perl on the HOST (the
# build context is prepared before Docker is involved). Fail early with an
# actionable message instead of dying mid-patch on a bare "command not found"
# under set -e.
for tool in git node perl; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "[portal] '$tool' is required on the host to prepare the portal build context." >&2
    echo "[portal] Install it, or skip the local portal build: in .env set" >&2
    echo "[portal]   ELK_OS_WITH_PORTAL=false   (Directus-only install), or" >&2
    echo "[portal]   ELK_OS_USE_PUBLISHED_IMAGES=true + PORTAL_IMAGE/RAG_IMAGE (pull published images)." >&2
    exit 1
  }
done

[ -f "$PIN_FILE" ] || { echo "[portal] PINNED_COMMIT not found at $PIN_FILE" >&2; exit 1; }
PIN="$(tr -d '[:space:]' < "$PIN_FILE")"
[ -n "$PIN" ] || { echo "[portal] PINNED_COMMIT is empty" >&2; exit 1; }

force=0
[ "${1:-}" = "--force" ] && force=1

# Completion marker: written (containing $PIN) as the LAST step of this script.
# A context without a matching marker is either half-prepared (a previous run
# died mid-patch) or extracted from a different pin — never patch on top of it.
MARKER="${BUILD_DIR}/.elk-os-prepared"

# ---------------------------------------------------------------------------
# 1. Extract the frozen archive (read-only; never edits the source repo)
# ---------------------------------------------------------------------------
if [ "$force" -eq 1 ]; then
  echo "[portal] --force: removing ${BUILD_DIR}"
  rm -rf "$BUILD_DIR"
fi

if [ -d "$BUILD_DIR" ] && [ "$(cat "$MARKER" 2>/dev/null || true)" != "$PIN" ]; then
  echo "[portal] build context is partial or from another pin — re-extracting from scratch"
  rm -rf "$BUILD_DIR"
fi

if [ ! -f "${BUILD_DIR}/package.json" ]; then
  if [ ! -d "$SOURCE_REPO/.git" ]; then
    echo "[portal] source repo not found: $SOURCE_REPO" >&2
    echo "[portal] Set PORTAL_SOURCE_REPO to a local analog-elk-front-end checkout (or clone it" >&2
    echo "[portal] as a sibling of this repo). No checkout available? In .env set" >&2
    echo "[portal]   ELK_OS_WITH_PORTAL=false   (Directus-only install), or" >&2
    echo "[portal]   ELK_OS_USE_PUBLISHED_IMAGES=true + PORTAL_IMAGE/RAG_IMAGE (pull published images)." >&2
    exit 1
  fi
  # The pin must exist locally — a checkout that is behind origin (or shallow)
  # makes `git archive` die mid-pipe with a bare "not a valid object name".
  # Check first and say exactly how to fix it.
  if ! git -C "$SOURCE_REPO" cat-file -e "${PIN}^{commit}" 2>/dev/null; then
    echo "[portal] pinned commit ${PIN} not found in ${SOURCE_REPO}" >&2
    echo "[portal] (the checkout is behind origin, or shallow). Fetch and retry:" >&2
    echo "[portal]   git -C '${SOURCE_REPO}' fetch origin" >&2
    exit 1
  fi
  echo "[portal] extracting analog-elk-front-end @ ${PIN} → ${BUILD_DIR} (read-only archive)"
  mkdir -p "$BUILD_DIR"
  git -C "$SOURCE_REPO" archive "$PIN" | tar -x -C "$BUILD_DIR"
else
  echo "[portal] reusing existing ${BUILD_DIR} (pass --force to re-extract)"
fi

cd "$BUILD_DIR"

# Invalidate the marker while patching; it is re-written as the LAST step below.
rm -f "$MARKER"

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
  // Anchor drift guard: if the `const nextConfig = {` anchor vanished with a
  // pin bump, the replace above silently no-ops and the Docker build later
  // fails on a missing .next/standalone. Fail HERE, with the cause.
  if (!/output:\s*["'"'"']standalone["'"'"']/.test(s)) {
    console.error("[portal] next.config.js: anchor for output:standalone not found — the pinned commit changed the config shape; update prepare-context.sh step 4");
    process.exit(1);
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

# --- Self-host portability: single-domain routing + host-only cookies ---------
# The source app is wired to the analogelk.com multi-subdomain topology
# (login./client./employee.*) and scopes auth cookies to `.analogelk.com`. On a
# single-domain self-host box (sslip.io / a custom domain) that breaks the authed
# portal: the proxy 301s /employee-portal/* off to employee.analogelk.com, and
# the browser rejects the `.analogelk.com` cookies so no session ever sticks.
#
# Fix (both idempotent, guarded by a marker so re-runs are no-ops):
#  a) proxy.ts — treat any host NOT ending in analogelk.com as single-domain
#     (path-based routing, no cross-subdomain redirects). Local dev hosts already
#     matched; this generalizes it to every non-analogelk host.
#  b) lib/portal/auth.ts — drop the hardcoded `.analogelk.com` cookie domain;
#     apply a domain only when AUTH_COOKIE_DOMAIN is set, else host-only cookies.
if ! grep -q 'elk-os single-domain' proxy.ts 2>/dev/null; then
  perl -0pi -e 's/function isDevelopment\(hostname: string\): boolean \{\n/function isDevelopment(hostname: string): boolean {\n  \/\/ [elk-os single-domain] Any host that is not the analogelk.com multi-subdomain\n  \/\/ production deployment (local dev, or a self-hosted single-domain box) uses\n  \/\/ path-based routing with no cross-subdomain redirects, so the whole portal is\n  \/\/ reachable on one origin.\n  if (!hostname.endsWith("analogelk.com")) return true;\n/' proxy.ts
  # Anchor drift guard: an unmatched perl pattern is a SILENT no-op, and an
  # unpatched proxy.ts 301s the whole authed portal off to *.analogelk.com on
  # any self-host domain. Prove the marker landed.
  grep -q 'elk-os single-domain' proxy.ts || {
    echo "[portal] proxy.ts: isDevelopment() anchor not found — the pinned commit changed proxy.ts; update prepare-context.sh step 6a" >&2
    exit 1
  }
  echo "[portal] patch proxy.ts: single-domain mode for non-analogelk hosts"
fi
if grep -qF "domain: '.analogelk.com'" lib/portal/auth.ts 2>/dev/null; then
  perl -0pi -e "s/\.\.\.\(isProd && \{ domain: '\.analogelk\.com' \}\),/...(process.env.AUTH_COOKIE_DOMAIN ? { domain: process.env.AUTH_COOKIE_DOMAIN } : {}), \/* [elk-os] host-only unless AUTH_COOKIE_DOMAIN set *\//" lib/portal/auth.ts
  # Same guard: if the spread-expression anchor drifted, the hardcoded
  # `.analogelk.com` cookie domain survives and no session ever sticks on a
  # self-host box. Prove the old literal is gone.
  if grep -qF "domain: '.analogelk.com'" lib/portal/auth.ts; then
    echo "[portal] lib/portal/auth.ts: cookie-domain anchor not found — the pinned commit changed auth.ts; update prepare-context.sh step 6b" >&2
    exit 1
  fi
  echo "[portal] patch lib/portal/auth.ts: env-driven (host-only) cookie domain"
fi

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
# 6c. Demo mode — pre-fill the login credentials (idempotent, build-time gated)
# ---------------------------------------------------------------------------
# The public demo (cms/app.34.220.64.149.sslip.io) ships a single read-only user
# (demo@muster.dev / muster-demo). To make that demo one-click, seed the login
# form's email + password from a build-time flag. NEXT_PUBLIC_* is inlined at
# `pnpm build`, so this is FULLY gated on NEXT_PUBLIC_DEMO_MODE === "true": a
# normal self-host / template deploy builds WITHOUT that flag and ships EMPTY
# fields (no creds baked in). Only the demo image (built with
# --build-arg NEXT_PUBLIC_DEMO_MODE=true) prefills. The login form is a
# controlled React component, so we seed the initial useState() and add a small
# demo-only hint line. Idempotent via the `elk-os demo-prefill` marker.
LOGIN="app/login/page.tsx"
if [ -f "$LOGIN" ] && ! grep -q 'elk-os demo-prefill' "$LOGIN"; then
  node -e '
    const fs=require("fs");
    const p="app/login/page.tsx";
    let s=fs.readFileSync(p,"utf8");
    const DEMO="process.env.NEXT_PUBLIC_DEMO_MODE === \"true\"";
    // a) Seed the controlled inputs initial state (demo build only).
    s=s.replace(
      "const [email, setEmail] = useState(\"\");",
      "// [elk-os demo-prefill] one-click public demo: creds baked in ONLY when NEXT_PUBLIC_DEMO_MODE=true at build time\n  const [email, setEmail] = useState("+DEMO+" ? \"demo@muster.dev\" : \"\");"
    );
    s=s.replace(
      "const [password, setPassword] = useState(\"\");",
      "const [password, setPassword] = useState("+DEMO+" ? \"muster-demo\" : \"\");"
    );
    // b) Demo-only hint line under the heading.
    s=s.replace(
      "          {/* Error alert */}",
      "          {"+DEMO+" && (\n            <p className=\"text-center text-sm text-muted-foreground\" role=\"status\">\n              Demo credentials pre-filled — just click Sign in.\n            </p>\n          )}\n\n          {/* Error alert */}"
    );
    if (!/elk-os demo-prefill/.test(s)) {
      console.error("[portal] demo-prefill: anchor(s) not found in "+p+" — login form shape changed");
      process.exit(1);
    }
    fs.writeFileSync(p,s);
    console.log("[portal] patch app/login/page.tsx: demo-mode credential prefill (gated on NEXT_PUBLIC_DEMO_MODE)");
  '
fi

# ---------------------------------------------------------------------------
# 7. Drop the build-context .dockerignore in place (docker reads it from the
#    context root = .build). Committed source of truth lives at ../.dockerignore.
# ---------------------------------------------------------------------------
if [ -f "${HERE}/.dockerignore" ]; then
  cp "${HERE}/.dockerignore" "${BUILD_DIR}/.dockerignore"
  echo "[portal] copied .dockerignore into build context"
fi

# Completion marker — LAST step, so bin/elk-os can distinguish a fully prepared
# context (marker matches the pin) from a partial one or a pin bump.
printf '%s\n' "$PIN" > "$MARKER"

echo "[portal] build context ready at ${BUILD_DIR} (pinned ${PIN})"
