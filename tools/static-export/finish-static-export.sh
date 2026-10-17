#!/usr/bin/env bash
# finish-static-export.sh: post-crawl finishing for the Muster static export.
# Usage: finish-static-export.sh [OUT]   (default ./static-export)
# Idempotent: safe to re-run on an already-finished tree.
# Needs: bash, file(1), python3.
set -euo pipefail
OUT="$(cd "${1:-${OUT:-static-export}}" && pwd)"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -d "$OUT/app" ] || { echo "no $OUT/app: run muster-static-export.mjs first" >&2; exit 2; }

# 1. App-site redirects. Login is dead by design: the root, /login and the bare
#    /employee-portal (a 307 upstream) go to the real dashboard route, and any
#    uncaptured deep link falls back to it instead of a Netlify 404. Non-forced
#    rules only fire when no file matches, so captured pages always win.
cat > "$OUT/app/_redirects" <<'R'
/	/employee-portal/dashboard/	302
/login	/employee-portal/dashboard/	302
/login/*	/employee-portal/dashboard/	302
/employee-portal	/employee-portal/dashboard/	302
/employee-portal/	/employee-portal/dashboard/	302
/*	/employee-portal/dashboard/	302
R

# 3. CMS assets: files are saved at their exact request path (assets/<uuid>,
#    no extension), so Netlify would serve them as application/octet-stream
#    (_headers cannot set Content-Type). Give each a MIME-detected extension and
#    emit a 200 rewrite from the original path. Rewrites are rebuilt from every
#    extensioned asset, so a second run does not lose the first run's rules.
mkdir -p "$OUT/cms"
cd "$OUT/cms"
if [ -d assets ]; then
  find assets -type f ! -name '*.*' | while read -r f; do
    case "$(file -b --mime-type "$f")" in
      image/jpeg) ext=jpg;; image/png) ext=png;; image/svg+xml) ext=svg;;
      image/webp) ext=webp;; image/gif) ext=gif;; image/avif) ext=avif;;
      application/pdf) ext=pdf;; video/mp4) ext=mp4;; text/html) ext=html;;
      application/json) ext=json;; *) ext=bin;;
    esac
    mv "$f" "$f.$ext"
  done
fi
: > _redirects
if [ -d assets ]; then
  find assets -type f -name '*.*' | sort | while read -r f; do
    printf '/%s\t/%s\t200\n' "${f%.*}" "$f" >> _redirects
  done
fi
echo "cms rewrites: $(wc -l < _redirects | tr -d ' ')"
echo "app html pages: $(find "$OUT/app" -name index.html | wc -l | tr -d ' ')"
echo "cms files: $(find "$OUT/cms" -type f ! -name _redirects | wc -l | tr -d ' ')"
