# Portal (P4) — self-hosted Next.js front-end

The Elk OS portal is the `analog-elk-front-end` Next.js 16 app, packaged as a
container image and wired to the Elk OS Directus stack.

## How the source is vendored (read-only)

`analog-elk-front-end` is a hot shared checkout (many active worktrees, root on
a feature branch). It is treated as **read-only**: the source is never built in
place. Instead, `prepare-context.sh` extracts a **frozen `git archive`** of a
pinned `origin/main` commit (`PINNED_COMMIT`) into `./.build/` (gitignored) and
applies a small set of self-host patches on top.

```
./prepare-context.sh            # extract (if needed) + patch
./prepare-context.sh --force    # wipe ./.build and re-extract + patch
```

### Patches applied to `.build/` (never to the source repo)

1. **`.npmrc`** — drop the private `@analogelk` GitHub Packages registry +
   authToken (needs a `GITHUB_TOKEN` not shipped with the template). Keep
   `legacy-peer-deps=true`.
2. **`package.json`** — remove the private dep `@analogelk/background-three-js`
   (the marketing 3D hero background — lazy-loaded and unused on the
   portal/login/marketing routes the template targets). Forces
   `pnpm install --no-frozen-lockfile`.
3. **`next.config.js`** — add `output: "standalone"` (slim runnable image),
   drop the private pkg from `transpilePackages`, and ignore eslint/type errors
   during build (the pinned commit is already CI-verified on `main` — we are
   packaging it, not re-vetting it).
4. **`components/three-background-wrapper.tsx`** — stub to a no-op so the
   removed private package is never imported.
5. **`.dockerignore`** — copied into the build-context root.

## Build + run

The portal is wired into the CLI and runs by default:

```
./bin/elk-os up           # builds the portal image on first run, starts it
./bin/elk-os doctor       # "Portal HTTP" row → green on HTTP 200
./bin/elk-os rebuild-portal   # force re-prepare + rebuild after a source bump
```

Disable it with `ELK_OS_WITH_PORTAL=false` in `.env` (skips the heavy Next
build — e.g. for a Directus-only install or a constrained box).

Served at `http://localhost:${PORTAL_PORT:-3000}`. The auth-free `/login` route
is the canonical HTTP-200 smoke target.

## Wiring

| Env (in container)         | Value                                    |
|----------------------------|------------------------------------------|
| `DIRECTUS_URL`             | `http://directus:8055` (internal network)|
| `NEXT_PUBLIC_DIRECTUS_URL` | `http://localhost:${DIRECTUS_PORT:-8056}`|
| `DIRECTUS_TOKEN`           | `${DIRECTUS_ADMIN_TOKEN}` (minted on `up`)|
| `USE_STATIC_FALLBACK`      | `true` (marketing reads committed JSON)  |

The portal's `instrumentation.ts` fail-fasts in production if `DIRECTUS_TOKEN`
is missing. Because the admin token is minted *after* the stack starts, `up`
recreates the portal once the token lands in `.env`.

## Notes / known gaps for later phases

- **Node 22** (the app's `.nvmrc`; Next 16 requires ≥20.9). Debian slim base so
  native deps (`sharp`) use prebuilt binaries.
- **Marketing content** falls to the committed `app/data/*.json` last-good (the
  generic Directus has no marketing collections). Rich marketing content is out
  of scope; the target is a clean HTTP 200.
- **Box target (Caddy):** the portal is internal-only behind Caddy; a Caddy
  site block for it is a TODO in `compose/compose.portal.prod.yaml` (P5/P6).
- **Auth'd portal routes** (`/employee-portal/*`, `/client-portal/*`) need a
  logged-in session; not exercised by the P4 smoke test.
