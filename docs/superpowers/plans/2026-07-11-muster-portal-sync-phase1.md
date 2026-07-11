# Muster Portal Sync — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden `portal/prepare-context.sh` so a pin bump fails loudly instead of shipping a half-patched portal, then do the one-time catch-up that brings the live Muster demo from AE pin `9931464` up to current AE `main` (`42d8fb3c`), so the admin-panel work from PR #333 (mint theme, two-tier task UX, in-app notifications, board perf) is visible on `musterr.dev`.

**Architecture:** Muster vendors the AE portal by extracting a frozen `git archive` of a pinned AE commit and applying self-host patches on top (see the design spec `docs/superpowers/specs/2026-07-11-muster-portal-sync-design.md`). Phase 1 adds a testable rebrand assertion and a container smoke test to that pipeline, fixes the baked Directus origin, then rebuilds the amd64 portal image in CI and deploys it to the box. It does NOT build the automation (that is Phases 2 to 4).

**Tech Stack:** Bash, Docker + Buildx, GitHub Actions, Next.js 16 standalone image, GHCR, Directus, a single EC2 box behind Caddy.

## Global Constraints

- Muster stays a downstream consumer of a pinned AE commit. Do NOT fork or edit AE app code.
- Never build AE in place. `prepare-context.sh` archives a frozen pinned SHA; the AE repo is read-only (it has ~9 active worktrees, CLAUDE.md §9).
- Portal images are amd64 (the box is amd64). Building arm64 under qemu is the bug we are avoiding.
- Pin `PORTAL_IMAGE` by an immutable tag/digest, never `:latest`.
- Conventional Commits on every commit (release-please derives the Muster version from them).
- Branch off `origin/main`; the PR targets `main` (CLAUDE.md §8). Work happens on branch `docs/muster-portal-sync-design` (already created, holds the spec).
- Any UI-affecting PR needs a screenshot before merge (CLAUDE.md §5).
- No em dashes in any authored copy, comments, or docs (Mike's flat-voice rule).
- Do not paste live tokens into the session; reference shell env vars (CLAUDE.md §2).

## File Structure

- `portal/rebrand-check.sh` — NEW. Sourced library. Owns the rebrand text replacement plus its before/after assertions. Single responsibility: turn "Analog Elk" into "Muster" across the portal surface and prove it happened.
- `portal/smoke-test.sh` — NEW. Boots a built portal image and asserts `/login` and `/` return 200 and render "Muster", not "Analog Elk". Has an `--assert-only <html-file>` mode so the assertion logic is unit-testable without Docker.
- `portal/test/test-rebrand-check.sh` — NEW. Fixture-based unit test for `rebrand-check.sh`.
- `portal/test/test-smoke-assert.sh` — NEW. Fixture-based unit test for the smoke test's HTML assertion.
- `portal/test/fixtures/` — NEW. Tiny fixture files for the two tests.
- `portal/prepare-context.sh` — MODIFY. Replace the inline `find | perl` rebrand block (lines ~212-215) with a call into `rebrand-check.sh`.
- `portal/Dockerfile` — MODIFY. Change the `NEXT_PUBLIC_DIRECTUS_URL` / `NEXT_PUBLIC_SITE_URL` ARG defaults (lines 42-43) from the old sslip.io box to `musterr.dev`.
- `.github/workflows/publish-images.yml` — MODIFY. In the `portal` job, build with `load: true`, run the smoke test on the loaded image, then push. Wire the `workflow_dispatch` `tag` input into the image metadata so a manual catch-up build is tag-able.
- `portal/PINNED_COMMIT` — MODIFY. `9931464` to `42d8fb3c`.

---

### Task 0: Preflight — resolve the build path and box access

**Files:** none (verification only).

**Interfaces:**
- Produces: a decision recorded in the PR/NOTES: build path is either `ci` (preferred) or `local`, and confirmation the box is reachable.

- [ ] **Step 1: Confirm Docker is running locally**

Run: `docker version --format '{{.Server.Version}}'`
Expected: a version string (not "Cannot connect to the Docker daemon"). If it fails, start Docker Desktop.

- [ ] **Step 2: Check whether CI can build the portal image**

Run: `gh secret list --repo AnalogElk/muster`
Expected: look for `AE_FRONTEND_REPO`, `AE_FRONTEND_PAT`, and `GHCR_PUSH_TOKEN`.
- If all three are present, build path = `ci` (native amd64 runner, preferred).
- If any is missing, build path = `local` (buildx cross-build). Record which are missing. Minting them is optional for Phase 1; the local fallback in Task 6 does not need them.

- [ ] **Step 3: Confirm box SSH access**

Run: `ssh -i ~/.ssh/elk-os-demo.pem -o ConnectTimeout=8 ubuntu@34.220.64.149 'echo ok && ls ~/elk-os/.env >/dev/null && echo env-present'`
Expected: `ok` then `env-present`. If SSH times out, your current IP is not in the security group; add it before Task 7 (the SG allows Mike's IPs only).

- [ ] **Step 4: Record the decision**

No commit. Note the chosen build path and any missing secrets in the working notes; Task 6 branches on it.

---

### Task 1: Rebrand check library + unit test (TDD)

The current rebrand is a blind `perl` replace with no proof it applied. Extract it into a testable function that fails loudly when AE has renamed or moved the brand string.

**Files:**
- Create: `portal/rebrand-check.sh`
- Create: `portal/test/test-rebrand-check.sh`
- Create: `portal/test/fixtures/` (created by the test at runtime under a temp dir)

**Interfaces:**
- Produces: `rebrand_tree <dir>` — replaces "Analog Elk"/"ANALOG ELK" with "Muster"/"MUSTER" across `*.tsx *.ts *.json *.mdx` under `<dir>` (excluding `node_modules`). Exits non-zero with an actionable message if the brand string was absent before (AE renamed it) or if any occurrence survives after.

- [ ] **Step 1: Write the failing test**

Create `portal/test/test-rebrand-check.sh`:

```bash
#!/usr/bin/env bash
# Unit test for portal/rebrand-check.sh — fixture-based, no network, no Docker.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../rebrand-check.sh
source "${HERE}/../rebrand-check.sh"

fail=0
check() { if [ "$1" = "$2" ]; then echo "ok   - $3"; else echo "FAIL - $3 (want '$2' got '$1')"; fail=1; fi; }

# --- fixture A: source HAS the brand string -> rebrand succeeds, string gone ---
A="$(mktemp -d)"
trap 'rm -rf "$A" "$B"' EXIT
mkdir -p "$A/app"
printf '%s\n' 'export const title = "Analog Elk portal";' > "$A/app/page.tsx"
printf '%s\n' '{ "name": "ANALOG ELK" }' > "$A/app/meta.json"
rebrand_tree "$A"; rc=$?
check "$rc" "0" "rebrand_tree exits 0 when brand present"
check "$(grep -rc 'Analog Elk' "$A" | awk -F: '{s+=$2} END{print s+0}')" "0" "no 'Analog Elk' remains"
check "$(grep -rl 'Muster portal' "$A" | wc -l | tr -d ' ')" "1" "'Muster portal' written"
check "$(grep -rl 'MUSTER' "$A" | wc -l | tr -d ' ')" "1" "caps variant replaced"

# --- fixture B: source has NO brand string -> rebrand FAILS loudly ---
B="$(mktemp -d)"
mkdir -p "$B/app"
printf '%s\n' 'export const title = "Some Renamed Brand";' > "$B/app/page.tsx"
out="$(rebrand_tree "$B" 2>&1)"; rc=$?
check "$rc" "1" "rebrand_tree exits 1 when brand absent (AE renamed it)"
case "$out" in *"not found in source"*) echo "ok   - error message is actionable";; *) echo "FAIL - error message missing 'not found in source'"; fail=1;; esac

exit "$fail"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bash portal/test/test-rebrand-check.sh`
Expected: FAIL — `rebrand-check.sh` does not exist yet, so `source` errors ("No such file or directory").

- [ ] **Step 3: Write the implementation**

Create `portal/rebrand-check.sh`:

```bash
#!/usr/bin/env bash
# =============================================================================
# Muster portal — rebrand text replacement + assertions.
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
    echo "[portal] rebrand: 'Analog Elk' not found in source under ${dir} — the pinned AE commit renamed or restructured the brand wordmark. Update portal/rebrand-check.sh before bumping the pin." >&2
    return 1
  fi
  find "$dir" -type f \( -name '*.tsx' -o -name '*.ts' -o -name '*.json' -o -name '*.mdx' \) \
    -not -path '*/node_modules/*' -print0 \
    | xargs -0 perl -pi -e 's/Analog Elk/Muster/g; s/ANALOG ELK/MUSTER/g'
  after="$(count_brand "$dir")"
  if [ "${after:-0}" -ne 0 ]; then
    echo "[portal] rebrand: ${after} occurrence(s) of 'Analog Elk' survived the replace under ${dir} — investigate before shipping a half-rebranded portal." >&2
    return 1
  fi
  echo "[portal] rebrand: Analog Elk -> Muster (${before} occurrence(s) replaced, 0 remain)"
  return 0
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `bash portal/test/test-rebrand-check.sh`
Expected: all lines start with `ok`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add portal/rebrand-check.sh portal/test/test-rebrand-check.sh
git commit -m "feat(portal): testable rebrand check that fails on brand drift"
```

---

### Task 2: Wire the rebrand assertion into prepare-context.sh

**Files:**
- Modify: `portal/prepare-context.sh` (the rebrand block, currently ~lines 202-215)

**Interfaces:**
- Consumes: `rebrand_tree` from `portal/rebrand-check.sh`.

- [ ] **Step 1: Source the helper near the top of the script**

In `portal/prepare-context.sh`, immediately after the `HERE="$(cd ... )"` line (~line 55), add:

```bash
# Rebrand replacement + assertions live in a sourced, unit-tested helper.
# shellcheck source=./rebrand-check.sh
source "${HERE}/rebrand-check.sh"
```

- [ ] **Step 2: Replace the inline rebrand block with a guarded call**

Find this block (the `echo "[portal] rebrand: Analog Elk -> Muster ..."` line and the `find ... | xargs -0 perl -pi -e 's/Analog Elk/Muster/g; s/ANALOG ELK/MUSTER/g'` that follows it) and replace the whole thing with:

```bash
# Rebrand the portal surface. rebrand_tree asserts the brand string existed
# before (else AE renamed it -> fail) and that none survive after (else a
# half-rebranded portal -> fail). See portal/rebrand-check.sh.
rebrand_tree . || exit 1
```

- [ ] **Step 3: Verify the script still parses and the assertion is reachable**

Run: `bash -n portal/prepare-context.sh && echo "syntax ok"`
Expected: `syntax ok`.

Run: `command -v shellcheck >/dev/null && shellcheck -x portal/prepare-context.sh || echo "shellcheck not installed, skipping"`
Expected: no errors (or the skip notice).

- [ ] **Step 4: Confirm the helper resolves when sourced from the script's dir**

Run: `bash -c 'cd portal && bash -n prepare-context.sh && grep -q "rebrand_tree ." prepare-context.sh && echo wired'`
Expected: `wired`.

- [ ] **Step 5: Commit**

```bash
git add portal/prepare-context.sh
git commit -m "refactor(portal): use guarded rebrand_tree in prepare-context"
```

---

### Task 3: Portal smoke test + unit test (TDD)

A container smoke test is the backstop behind the patch assertions: it boots the actual image and proves the rendered portal is up and rebranded.

**Files:**
- Create: `portal/smoke-test.sh`
- Create: `portal/test/test-smoke-assert.sh`
- Create: `portal/test/fixtures/login-ok.html`, `portal/test/fixtures/login-bad.html`

**Interfaces:**
- Produces: `portal/smoke-test.sh <image-ref>` — boots the image, GETs `/login` and `/`, asserts HTTP 200 and that the `/login` body contains "Muster" and not "Analog Elk". Exit 0 on pass. Also supports `portal/smoke-test.sh --assert-only <html-file>` which runs only the HTML assertion (used by the unit test).

- [ ] **Step 1: Write the fixtures**

Create `portal/test/fixtures/login-ok.html`:

```html
<!doctype html><html><head><title>Sign in | Muster</title></head>
<body><h1>Muster</h1><form>...</form></body></html>
```

Create `portal/test/fixtures/login-bad.html`:

```html
<!doctype html><html><head><title>Sign in | Analog Elk</title></head>
<body><h1>Analog Elk</h1><form>...</form></body></html>
```

- [ ] **Step 2: Write the failing test**

Create `portal/test/test-smoke-assert.sh`:

```bash
#!/usr/bin/env bash
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SMOKE="${HERE}/../smoke-test.sh"
fail=0
check() { if [ "$1" = "$2" ]; then echo "ok   - $3"; else echo "FAIL - $3 (want '$2' got '$1')"; fail=1; fi; }

bash "$SMOKE" --assert-only "${HERE}/fixtures/login-ok.html" >/dev/null 2>&1
check "$?" "0" "assert-only passes on a rebranded login page"

bash "$SMOKE" --assert-only "${HERE}/fixtures/login-bad.html" >/dev/null 2>&1
check "$?" "1" "assert-only fails on an un-rebranded login page"

exit "$fail"
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `bash portal/test/test-smoke-assert.sh`
Expected: FAIL — `smoke-test.sh` does not exist yet.

- [ ] **Step 4: Write the implementation**

Create `portal/smoke-test.sh`:

```bash
#!/usr/bin/env bash
# =============================================================================
# Muster portal — container smoke test.
# =============================================================================
# Boots a built portal image and proves it serves a rebranded portal without a
# live Directus (USE_STATIC_FALLBACK is baked true; the login route renders
# standalone). The backstop behind prepare-context.sh's patch assertions.
#
#   portal/smoke-test.sh <image-ref>        boot + probe /login and /
#   portal/smoke-test.sh --assert-only FILE  run only the HTML assertion
# =============================================================================
set -uo pipefail

# assert_login_html <file> — the brand assertion, factored out so it is unit
# testable against a saved HTML fixture (no Docker).
assert_login_html() {
  local body
  body="$(cat "$1")"
  if ! grep -q 'Muster' <<<"$body"; then
    echo "[smoke] /login body does not contain 'Muster' — rebrand did not reach the rendered page" >&2
    return 1
  fi
  if grep -q 'Analog Elk' <<<"$body"; then
    echo "[smoke] /login body still contains 'Analog Elk' — half-rebranded image" >&2
    return 1
  fi
  echo "[smoke] /login brand assertion passed (Muster present, Analog Elk absent)"
  return 0
}

if [ "${1:-}" = "--assert-only" ]; then
  [ -n "${2:-}" ] || { echo "[smoke] --assert-only needs an HTML file" >&2; exit 2; }
  assert_login_html "$2"
  exit $?
fi

IMAGE="${1:?usage: smoke-test.sh <image-ref>}"
PORT="${SMOKE_PORT:-3999}"
NAME="muster-portal-smoke-$$"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "[smoke] booting ${IMAGE} on :${PORT}"
# USE_STATIC_FALLBACK is baked true; DIRECTUS_TOKEN/URL are dummies so the
# production instrumentation hook does not fail-fast on a missing token.
docker run -d --name "$NAME" -p "${PORT}:3000" \
  -e USE_STATIC_FALLBACK=true \
  -e DIRECTUS_TOKEN=smoke \
  -e DIRECTUS_URL=http://127.0.0.1:8055 \
  "$IMAGE" >/dev/null

# Wait for readiness (up to ~40s).
ready=0
for _ in $(seq 1 40); do
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/login" || true)"
  if [ "$code" = "200" ]; then ready=1; break; fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  echo "[smoke] /login never returned 200 (last=${code:-none}). Container logs:" >&2
  docker logs "$NAME" 2>&1 | tail -30 >&2
  exit 1
fi
echo "[smoke] /login 200"

root="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/" || true)"
case "$root" in 200|307|308) echo "[smoke] / ${root}";; *) echo "[smoke] / returned ${root} (expected 200/redirect)" >&2; exit 1;; esac

curl -s "http://127.0.0.1:${PORT}/login" > "/tmp/${NAME}.html"
assert_login_html "/tmp/${NAME}.html" || exit 1
echo "[smoke] PASS"
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `bash portal/test/test-smoke-assert.sh`
Expected: both checks `ok`, exit 0.

- [ ] **Step 6: Make both scripts executable and commit**

```bash
chmod +x portal/smoke-test.sh portal/rebrand-check.sh
git add portal/smoke-test.sh portal/test/test-smoke-assert.sh portal/test/fixtures/login-ok.html portal/test/fixtures/login-bad.html
git update-index --chmod=+x portal/smoke-test.sh portal/rebrand-check.sh 2>/dev/null || true
git commit -m "feat(portal): container smoke test with unit-testable brand assertion"
```

---

### Task 4: Fix the baked Directus origin in the Dockerfile

The image bakes `NEXT_PUBLIC_DIRECTUS_URL` at build. It still defaults to the old sslip.io box, so deep authed browser calls hit the wrong origin on `musterr.dev`. Point the defaults at the live domain.

**Files:**
- Modify: `portal/Dockerfile:42-43`

- [ ] **Step 1: Write the assertion (grep-based)**

Run: `grep -n 'ARG NEXT_PUBLIC_DIRECTUS_URL' portal/Dockerfile`
Expected: shows the current default `https://cms.34.220.64.149.sslip.io`.

- [ ] **Step 2: Update the two ARG defaults**

In `portal/Dockerfile`, change:

```dockerfile
ARG NEXT_PUBLIC_DIRECTUS_URL=https://cms.34.220.64.149.sslip.io
ARG NEXT_PUBLIC_SITE_URL=https://app.34.220.64.149.sslip.io
```

to:

```dockerfile
ARG NEXT_PUBLIC_DIRECTUS_URL=https://cms.musterr.dev
ARG NEXT_PUBLIC_SITE_URL=https://app.musterr.dev
```

- [ ] **Step 3: Verify**

Run: `grep -c 'musterr.dev' portal/Dockerfile`
Expected: `2`.

Run: `grep -c 'sslip.io' portal/Dockerfile`
Expected: `0`.

- [ ] **Step 4: Commit**

```bash
git add portal/Dockerfile
git commit -m "fix(portal): bake musterr.dev as the default Directus/site origin"
```

---

### Task 5: Run the smoke test in CI + make dispatch builds tag-able

Wire the smoke test into the portal publish job so a bad image cannot be pushed silently, and make a manual `workflow_dispatch` produce a usable image tag (needed for the catch-up in Task 6 and for Phase 3).

**Files:**
- Modify: `.github/workflows/publish-images.yml` (the `portal` job's metadata + build steps, and the `workflow_dispatch` input already exists)

**Interfaces:**
- Consumes: `portal/smoke-test.sh` (Task 3).

- [ ] **Step 1: Add the dispatch tag to the portal image metadata**

In the `portal` job's `Image metadata (tags + labels)` step, add this line to the `tags: |` block (alongside the existing `type=semver` / `type=ref` lines):

```yaml
            type=raw,value=${{ github.event.inputs.tag }},enable=${{ github.event_name == 'workflow_dispatch' && github.event.inputs.tag != '' }}
```

- [ ] **Step 2: Replace the single build+push step with build(load) -> smoke -> push**

Replace the portal job's final `Build + push portal image` step with these three steps:

```yaml
      - name: Build portal image (load locally for smoke test)
        if: steps.gate.outputs.enabled == 'true'
        uses: docker/build-push-action@v6
        with:
          context: ./portal/.build
          file: ./portal/Dockerfile
          platforms: linux/amd64
          load: true
          tags: muster-portal:smoke
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Smoke test the built image
        if: steps.gate.outputs.enabled == 'true'
        run: bash portal/smoke-test.sh muster-portal:smoke

      - name: Push portal image
        if: steps.gate.outputs.enabled == 'true'
        uses: docker/build-push-action@v6
        with:
          context: ./portal/.build
          file: ./portal/Dockerfile
          platforms: linux/amd64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

Note: the second build reuses the gha cache from the first, so it is a fast re-export, not a full rebuild.

- [ ] **Step 3: Validate the workflow YAML**

Run: `command -v actionlint >/dev/null && actionlint .github/workflows/publish-images.yml || python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/publish-images.yml')); print('yaml ok')"`
Expected: `yaml ok` (or actionlint clean).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/publish-images.yml
git commit -m "ci(portal): smoke-test the image before push; tag dispatch builds"
```

---

### Task 6: Bump the pin and build the catch-up image

Now pull AE forward. This is the first time the new assertions run against real AE #333 code, so it is also the integration test of Tasks 1 to 3.

**Files:**
- Modify: `portal/PINNED_COMMIT`

**Interfaces:**
- Produces: a published amd64 portal image ref (record it, e.g. `ghcr.io/analogelk/elk-os-portal:ae-42d8fb3c`).

- [ ] **Step 1: Bump the pin**

Set `portal/PINNED_COMMIT` contents to exactly:

```
42d8fb3c
```

- [ ] **Step 2: Prove the patches still apply against real AE main (local dry run)**

This runs `prepare-context.sh` against the real AE checkout at the new pin. It exercises every patch assertion (rebrand, proxy.ts, auth.ts, next.config, demo-prefill) on current AE code.

Run:
```bash
git -C ../analog-elk-front-end cat-file -e 42d8fb3c^{commit} || git -C ../analog-elk-front-end fetch origin
PORTAL_SOURCE_REPO="$(cd ../analog-elk-front-end && pwd)" bash portal/prepare-context.sh --force
```
Expected: ends with `[portal] build context ready ... (pinned 42d8fb3c)` and a `rebrand: ... 0 remain` line. If any patch prints an anchor-drift error and exits, STOP: the corresponding patch in `prepare-context.sh` needs updating for the new AE shape before proceeding. That is the assertion doing its job.

- [ ] **Step 3: Commit the pin bump**

```bash
git add portal/PINNED_COMMIT
git commit -m "chore(portal): bump AE pin 9931464 -> 42d8fb3c (PR #333 admin panel)"
git push -u origin docs/muster-portal-sync-design
```

- [ ] **Step 4a: Build path = ci (preferred) — dispatch the workflow**

Only if Task 0 chose `ci`. Runs on a native amd64 runner, smoke-tests, and pushes.

```bash
gh workflow run publish-images.yml --ref docs/muster-portal-sync-design -f tag=ae-42d8fb3c
gh run watch "$(gh run list --workflow=publish-images.yml --branch=docs/muster-portal-sync-design -L1 --json databaseId -q '.[0].databaseId')"
```
Expected: the `portal` job runs (not skipped), the smoke step prints `[smoke] PASS`, and the push succeeds. Resulting image: `ghcr.io/analogelk/elk-os-portal:ae-42d8fb3c`.
If the `portal` job is skipped ("set AE_FRONTEND_REPO + AE_FRONTEND_PAT"), the secrets are not configured — use Step 4b instead.

- [ ] **Step 4b: Build path = local (fallback) — cross-build amd64 and push**

Only if Task 0 chose `local` or CI skipped. The context was already prepared in Step 2.

```bash
echo "$CR_PAT" | docker login ghcr.io -u <your-gh-username> --password-stdin   # CR_PAT = classic PAT, write:packages, exported in your shell
docker buildx build --platform linux/amd64 \
  --build-arg NEXT_PUBLIC_DIRECTUS_URL=https://cms.musterr.dev \
  --build-arg NEXT_PUBLIC_SITE_URL=https://app.musterr.dev \
  -f portal/Dockerfile -t ghcr.io/analogelk/elk-os-portal:ae-42d8fb3c \
  --push portal/.build
```
Then smoke test the pushed image locally:
```bash
docker pull ghcr.io/analogelk/elk-os-portal:ae-42d8fb3c
bash portal/smoke-test.sh ghcr.io/analogelk/elk-os-portal:ae-42d8fb3c
```
Expected: `[smoke] PASS`.

- [ ] **Step 5: Record the image ref**

Note the exact ref (`ghcr.io/analogelk/elk-os-portal:ae-42d8fb3c`) and its digest (`docker buildx imagetools inspect <ref> | grep Digest`) for the box repin and for rollback.

---

### Task 7: Deploy to the box, verify #333 features, capture screenshot

**Files:** none in-repo (box `.env` edit is on the box, not tracked).

**Interfaces:**
- Consumes: the image ref from Task 6.
- Produces: the live demo running the new admin panel, a screenshot, and a list of any schema gaps (Phase 2 input).

- [ ] **Step 1: Repin PORTAL_IMAGE on the box**

```bash
ssh -i ~/.ssh/elk-os-demo.pem ubuntu@34.220.64.149
# on the box:
cd ~/elk-os
cp .env .env.bak.$(date +%s)        # rollback point for the env
sed -i 's#^PORTAL_IMAGE=.*#PORTAL_IMAGE=ghcr.io/analogelk/elk-os-portal:ae-42d8fb3c#' .env
grep -E '^(PORTAL_IMAGE|ELK_OS_USE_PUBLISHED_IMAGES)=' .env
```
Expected: `PORTAL_IMAGE` is the new ref and `ELK_OS_USE_PUBLISHED_IMAGES=true`. If the box cannot pull from GHCR, `docker login ghcr.io` on the box first (read:packages is enough to pull).

- [ ] **Step 2: Pull and restart just the portal**

```bash
# on the box, using the exact overlay set the box runs (5 -f files per project memory):
docker compose --project-directory ~/elk-os --env-file ~/elk-os/.env \
  -f compose/compose.yaml -f compose/compose.prod.yaml \
  -f compose/compose.portal.yaml -f compose/compose.portal.prod.yaml \
  -f compose/compose.images.portal.yaml \
  pull portal
docker compose --project-directory ~/elk-os --env-file ~/elk-os/.env \
  -f compose/compose.yaml -f compose/compose.prod.yaml \
  -f compose/compose.portal.yaml -f compose/compose.portal.prod.yaml \
  -f compose/compose.images.portal.yaml \
  up -d portal
```
Expected: the portal container recreates with the new image. Confirm: `docker inspect --format '{{.Config.Image}}' $(docker compose ... ps -q portal)` shows the new ref. (If the exact overlay set differs, derive it from `bin/elk-os` on the box; do not guess-flip other services.)

- [ ] **Step 3: Healthcheck the live site**

Run (from your machine):
```bash
curl -s -o /dev/null -w '%{http_code}\n' https://app.musterr.dev/login
curl -s https://app.musterr.dev/login | grep -o 'Muster' | head -1
```
Expected: `200` and `Muster`.

- [ ] **Step 4: Exercise the #333 features and look for schema gaps**

Log in at `https://app.musterr.dev/login` as the demo user (`demo@muster.dev` / `muster-demo`, read-only). Click into the task board and verify the mint theme renders, open a task via the eye icon (TaskOverviewModal) and by click (TaskDetailSlideOver), and open a full task page to load the Activity/History timeline. Watch for a 500 on `GET /api/portal/tasks/<id>/activity` or missing-field errors.

Run (spot-check the activity route directly against the API if you have a task id):
```bash
# any 500 here means os_activity_log or a field it needs is missing from the pruned snapshot -> Phase 2 input
curl -s -o /dev/null -w '%{http_code}\n' https://app.musterr.dev/api/portal/tasks/<known-id>/activity
```
Expected: 200. Record any 500s or missing-field UI errors as a "schema gaps" list; these are the concrete Phase 2 backlog, not a Phase 1 blocker (the demo is read-only).

- [ ] **Step 5: Capture the screenshot (CLAUDE.md §5)**

Use the demo-account Playwright recipe (see memory `reference_demo_account_screenshot_recipe`) to capture the mint-themed board and a task slide-over on `app.musterr.dev`. Save under `docs/screenshots/muster-portal-sync/` in the repo (or attach to the PR).

```bash
mkdir -p docs/screenshots/muster-portal-sync
# run the Playwright capture -> writes board.png + task-slideover.png here
git add docs/screenshots/muster-portal-sync
git commit -m "docs(portal): screenshots of the mint admin panel live on musterr.dev"
```

---

### Task 8: Open the PR and file the Phase 2 to 4 follow-ups

**Files:** none new.

- [ ] **Step 1: Confirm the branch is green and base is main**

```bash
bash portal/test/test-rebrand-check.sh && bash portal/test/test-smoke-assert.sh && echo "unit tests green"
gh repo view AnalogElk/muster --json defaultBranchRef -q .defaultBranchRef.name   # must be 'main'
```
Expected: `unit tests green` and `main`.

- [ ] **Step 2: Open the PR (targets main, includes the screenshot)**

```bash
gh pr create --repo AnalogElk/muster --base main --head docs/muster-portal-sync-design \
  --title "feat(portal): harden vendoring + catch demo up to AE #333 admin panel" \
  --body "$(cat <<'BODY'
Design: docs/superpowers/specs/2026-07-11-muster-portal-sync-design.md
Plan: docs/superpowers/plans/2026-07-11-muster-portal-sync-phase1.md

Phase 1 of the Muster <-> admin-panel sync:
- Rebrand check extracted into a unit-tested helper that FAILS on brand drift.
- Container smoke test (boots the image, asserts /login is up and rebranded), run in CI before push.
- Dockerfile bakes musterr.dev as the default origin.
- CI dispatch builds are now tag-able.
- AE pin bumped 9931464 -> 42d8fb3c; amd64 image rebuilt and deployed to the box.

The live demo (app.musterr.dev) now runs the PR #333 admin panel (mint theme, two-tier task UX, in-app notifications, board perf). Screenshot attached.

Follow-ups (Phases 2-4) filed in os_tasks.
BODY
)"
```
Expected: PR opened against `main`. Check the screenshot box in the PR template.

- [ ] **Step 3: File the follow-ups in os_tasks (CLAUDE.md §1)**

Create three `os_tasks` rows (status `pending`, type `task`, responsibility `team`, is_visible_to_client `false`, repo_url the muster repo), one per remaining phase, each linking the design spec:
- "Muster sync Phase 2: codify prune+scrub schema regen + drift report" — include the schema-gaps list found in Task 7 Step 4.
- "Muster sync Phase 3: CI sync workflow (poll AE releases) + PR gate".
- "Muster sync Phase 4: box-side auto-pull updater (backup, migrate, healthcheck, rollback)".

Also note the two prerequisites surfaced: AE git tags stuck at v1.21.0 (blocks the Phase 3 release-tag trigger until fixed; poll works meanwhile), and the AE_FRONTEND_PAT / GHCR_PUSH_TOKEN secrets if CI build was unavailable in Task 0.

- [ ] **Step 4: Report**

Summarize what shipped and where (PR URL, image ref, os_task ids). Do not mark anything `completed` in os_tasks until the PR merges and the box is confirmed on the new image.

---

## Self-Review

**Spec coverage:**
- Portal leg hardening (assertions + smoke test): Tasks 1, 2, 3, 5. Covered.
- Fix baked NEXT_PUBLIC_DIRECTUS_URL: Task 4. Covered.
- amd64 build: Tasks 5, 6 (CI native amd64 / buildx --platform linux/amd64). Covered.
- One-time catch-up to current AE main: Tasks 6, 7. Covered.
- Pin by immutable ref, record digest for rollback: Task 6 Step 5, Task 7 Step 1. Covered.
- Screenshot (§5): Task 7 Step 5. Covered.
- Schema leg, trigger, box updater: explicitly deferred to Phases 2 to 4, filed as follow-ups in Task 8. Covered by deferral.
- §9 (never build AE in place): honored via the frozen archive; AE is read-only throughout.

**Placeholder scan:** the only `<...>` tokens are runtime values a human must fill (`<your-gh-username>`, `<known-id>`, the image digest, os_task ids). No "TBD"/"add error handling"/"similar to Task N". Acceptable.

**Type/name consistency:** `rebrand_tree` and `count_brand` are defined in Task 1 and consumed in Task 2. `assert_login_html` and the `--assert-only` flag are defined in Task 3 and used by its test. The image ref `ghcr.io/analogelk/elk-os-portal:ae-42d8fb3c` is consistent across Tasks 6, 7, 8. The pin `42d8fb3c` is consistent across Tasks 6, 7.
