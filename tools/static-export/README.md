# Static export: how musterr.dev is published

Since 2026-08-02 every public Muster host is plain files on Netlify. Nothing runs
a server:

| Host | Netlify site | Source |
| --- | --- | --- |
| `musterr.dev` | `muster-static-home` (`0c2f246d`) | `site/` in this repo, as is |
| `app.musterr.dev` | `muster-static-app` (`822a2421`) | crawled portal, `static-export/app` |
| `cms.musterr.dev` | `muster-static-cms` (`d1930cf3`) | crawled Directus `/assets` only, `static-export/cms` |

None of the three sites is git-linked, so merging to `main` deploys nothing.
Deploys are `netlify deploy --prod --no-build` by hand.

The demo box (`i-02bb458cf55b6cfe9`, `elk-os-demo`) was **terminated on
2026-10-16**. Its last state is AMI `ami-0bb9cfefcbc86ae65`
(`backup-elk-os-demo-20261016-1113`, us-west-2). The older
`ami-02b7746d0d89ef1cb` (2026-08-02) is a fallback.

## Files

- `muster-static-export.mjs` crawls a running demo while logged in as the team
  user and the client user. It saves every 200 GET from the app and cms hosts.
  It skips RSC payloads, so the static site falls back to hard navigation.
- `finish-static-export.sh` writes the app `_redirects`. Login is dead by
  design, so `/`, `/login` and unknown paths go to `/employee-portal/dashboard/`.
  It also runs the metadata scrub and gives the extensionless CMS assets real
  extensions plus 200 rewrites. It is safe to re-run.
- `strip-origin-metadata.py` replaces the Analog Elk SEO head that the
  AE-derived portal image renders: canonical, `og:*` and `twitter:image`, three
  JSON-LD blocks and the `cms.analogelk.com` preconnects. It rewrites both the
  HTML and the RSC flight payload to the same values, so hydration does not put
  the old values back. `--check` reports without changing anything.

## Update only the homepage

No box is needed:

```bash
netlify deploy --prod --no-build --dir site --site 0c2f246d-7556-4eed-a8bb-7fe18398b463
```

## Re-crawl the demo (app + cms)

You need a running demo stack. There are two ways to get one.

**A. From the AMI (byte-exact last state).**

1. Launch a `t3.large` (x86_64; the saved portal images are amd64) from
   `ami-0bb9cfefcbc86ae65` in us-west-2. Use the `elk-os-demo` key pair and a
   security group that allows port 22 and 443 from your IP. Check that
   `sg-0b255de1b5677e320` still exists before creating a new one.
2. Note the new public IP and point the `muster-demo` alias in `~/.ssh/config`
   at it. There is no Elastic IP.
3. On the box: `docker compose ... up -d` with the prod overlays. The command is
   in the box tree's README; it needs `--project-directory ~/elk-os --env-file
   ~/elk-os/.env` and all the `-f` overlays.

**B. From local.** Bring the stack up with `bin/elk-os up` on your machine, then
restore the 2026-08-02 artifacts (Postgres dumps, uploads, Qdrant) by following
the restore steps in `_snapshots/muster-demo/2026-08-02/manifest.json`. That
snapshot lives outside git because it contains secrets. Serve it behind Caddy on
:443 with the app and cms hostnames.

**Then, on either path:**

1. Leave public DNS on Netlify. Map the hostnames to the stack for your own
   machine only, by adding to `/etc/hosts`:
   `<box-ip-or-127.0.0.1>  app.musterr.dev cms.musterr.dev`.
2. Caddy's Let's Encrypt certs will be expired or missing, so set
   `IGNORE_HTTPS_ERRORS=1`.
3. Crawl and finish:

   ```bash
   export MUSTER_DEMO_PASSWORD=...        # demo users' password; not in git
   OUT=./static-export PAGE_CAP=1200 IGNORE_HTTPS_ERRORS=1 \
     PLAYWRIGHT_FROM=/path/to/a/package.json/with/@playwright/test \
     node tools/static-export/muster-static-export.mjs
   tools/static-export/finish-static-export.sh ./static-export
   python3 tools/static-export/strip-origin-metadata.py ./static-export/app --check
   ```

4. Remove the `/etc/hosts` lines.
5. Check the result locally before deploying:
   `python3 -m http.server -d static-export/app`, then open
   `/employee-portal/dashboard/` and `/client-portal/`.
6. Deploy:

   ```bash
   netlify deploy --prod --no-build --dir static-export/app --site 822a2421-0f0a-4237-95b9-6eb90689c9bf
   netlify deploy --prod --no-build --dir static-export/cms --site d1930cf3-99fa-4d6b-b198-ebbb18acd24f
   ```

7. Terminate (path A) or stop the box. Take a new AMI first if the box state
   changed.

## Scrub the live export without re-crawling

The metadata scrub works on any existing export. To fix the live app without a
box, run `finish-static-export.sh` on a copy of the last export
(`_snapshots/muster-demo/static-export`) and redeploy `app/` (step 6). It
rewrites every HTML page. On the 2026-08-02 export that was 555 pages and 24
edits per page, and afterwards none still carried origin metadata.
