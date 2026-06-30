# =============================================================================
# Elk OS — portal image (P4)
# =============================================================================
# Production build of the analog-elk-front-end Next.js 16 portal, packaged for
# self-hosting alongside the elk-os Directus stack.
#
# Build context is ./.build — a FROZEN extraction of a pinned origin/main commit
# (see ./PINNED_COMMIT) with a small set of self-host patches applied by
# ./prepare-context.sh (standalone output, private 3D pkg removed, build gates
# relaxed). The source repo is never touched. Run prepare-context.sh before
# `docker build`; bin/elk-os does this automatically.
#
# Node 22 (the app's .nvmrc; Next 16 requires >=20.9). Debian slim, not Alpine,
# so native deps (sharp) use prebuilt binaries cleanly. pnpm 9 (lockfile v9).
# =============================================================================

ARG NODE_IMAGE=node:22-bookworm-slim

# ---------------------------------------------------------------------------
# deps — install node_modules (cached unless manifests change)
# ---------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS deps
WORKDIR /app
ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    NEXT_TELEMETRY_DISABLED=1
RUN corepack enable && corepack prepare pnpm@9 --activate
# Manifests first for layer caching. prepare-context.sh has already stripped the
# private @analogelk registry from .npmrc and the dep from package.json, so the
# lockfile is intentionally stale here → --no-frozen-lockfile reconciles it.
COPY package.json pnpm-lock.yaml .npmrc ./
RUN pnpm install --no-frozen-lockfile

# ---------------------------------------------------------------------------
# builder — compile the Next standalone server
# ---------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS builder
WORKDIR /app
ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production \
    NODE_OPTIONS=--max-old-space-size=4096 \
    # The prebuild step prefetches marketing content from Directus, which is not
    # reachable at image-build time. Skip it → the committed app/data/*.json
    # last-good fallback ships as-is. At runtime USE_STATIC_FALLBACK governs
    # whether the server reads that JSON or live Directus.
    SKIP_DIRECTUS_PREFETCH=true \
    USE_STATIC_FALLBACK=true
RUN corepack enable && corepack prepare pnpm@9 --activate
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build

# ---------------------------------------------------------------------------
# runner — minimal runtime image (Next standalone)
# ---------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# Non-root runtime user.
RUN groupadd --system --gid 1001 nodejs \
    && useradd --system --uid 1001 --gid nodejs nextjs

# Standalone bundle: a self-contained server.js + a pruned node_modules.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
# Hashed client assets and public/ are NOT part of standalone — copy explicitly.
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000
# server.js is emitted at the standalone root by Next's standalone output.
CMD ["node", "server.js"]
