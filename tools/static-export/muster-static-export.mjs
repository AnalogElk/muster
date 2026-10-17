// muster-static-export.mjs: crawl a running Muster demo into a static tree.
//
// Logs in as the team and client demo users, walks every same-host link, and
// writes every 200 GET from the app and cms hosts to disk keyed by host+path
// (HTML -> <path>/index.html, JSON/assets -> raw path). RSC flight payloads
// (?_rsc= / text/x-component) are skipped so they never clobber the HTML for
// the same pathname; Next falls back to hard navigation on the static site.
//
// Env:
//   MUSTER_DEMO_PASSWORD  required. Password of both demo users on the box.
//   OUT                   output dir (default ./static-export)
//   APP_HOST / CMS_HOST   default app.musterr.dev / cms.musterr.dev
//   TEAM_EMAIL            default demo@muster.dev
//   CLIENT_EMAIL          default client@muster.dev
//   PAGE_CAP              max pages per user (default 1200)
//   IGNORE_HTTPS_ERRORS   1 to accept the box's expired/self-issued Caddy certs
//   PLAYWRIGHT_FROM       a package.json whose node_modules has @playwright/test,
//                         if it is not resolvable from this directory
//
// See README.md in this directory for the full update runbook.
import { createRequire } from 'module';
import fs from 'node:fs';
import path from 'node:path';

function loadPlaywright() {
  const bases = [process.env.PLAYWRIGHT_FROM, path.join(process.cwd(), 'package.json'), import.meta.url].filter(Boolean);
  for (const base of bases) {
    try { return createRequire(base)('@playwright/test'); } catch { /* try next */ }
  }
  console.error('Cannot resolve @playwright/test. Install it here or set PLAYWRIGHT_FROM=/path/to/package.json');
  process.exit(2);
}
const { chromium } = loadPlaywright();

const DEMO_PW = process.env.MUSTER_DEMO_PASSWORD;
if (!DEMO_PW) { console.error('Set MUSTER_DEMO_PASSWORD (the demo users\' password on the box).'); process.exit(2); }
const APP_HOST = process.env.APP_HOST || 'app.musterr.dev';
const CMS_HOST = process.env.CMS_HOST || 'cms.musterr.dev';
const APP = `https://${APP_HOST}`;
const OUT = path.resolve(process.env.OUT || 'static-export');
const HOST_DIR = { [APP_HOST]: 'app', [CMS_HOST]: 'cms' };
const PAGE_CAP = Number(process.env.PAGE_CAP || 1200);
const TEAM_EMAIL = process.env.TEAM_EMAIL || 'demo@muster.dev';
const CLIENT_EMAIL = process.env.CLIENT_EMAIL || 'client@muster.dev';
const IGNORE_HTTPS = process.env.IGNORE_HTTPS_ERRORS === '1';
const saved = new Set();
const savedRoutes = [];
const stats = { html: 0, json: 0, asset: 0, skippedRsc: 0, errors: 0 };

function fileFor(rawUrl, ct) {
  let url;
  try { url = new URL(rawUrl); } catch { return null; }
  const root = HOST_DIR[url.hostname];
  if (!root) return null;
  let p = decodeURIComponent(url.pathname) || '/';
  if ((ct || '').includes('text/html')) p = p.endsWith('/') ? p + 'index.html' : p + '/index.html';
  else if (p.endsWith('/')) p += 'index';
  const fp = path.join(OUT, root, p.replace(/^\//, ''));
  if (!fp.startsWith(path.join(OUT, root) + path.sep)) return null; // no ../ escapes
  return fp;
}

function attach(context) {
  context.on('response', async (res) => {
    try {
      const req = res.request();
      if (req.method() !== 'GET' || res.status() !== 200) return;
      const u = new URL(req.url());
      if (u.searchParams.has('_rsc')) { stats.skippedRsc++; return; }
      const ct = res.headers()['content-type'] || '';
      if (ct.includes('text/x-component') || ct.includes('text/event-stream')) { stats.skippedRsc++; return; }
      const fp = fileFor(req.url(), ct);
      if (!fp || saved.has(fp)) return;
      const body = await res.body().catch(() => null);
      if (!body || body.length === 0) return;
      saved.add(fp);
      fs.mkdirSync(path.dirname(fp), { recursive: true });
      fs.writeFileSync(fp, body);
      if (ct.includes('text/html')) { stats.html++; savedRoutes.push(u.pathname); }
      else if (ct.includes('json')) stats.json++;
      else stats.asset++;
    } catch { stats.errors++; }
  });
}

async function login(page, email) {
  await page.goto(APP + '/login', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', DEMO_PW);
  await Promise.all([
    page.waitForURL((u) => !String(u).includes('/login'), { timeout: 45000 }),
    page.click('button[type="submit"]'),
  ]);
}

async function crawl(browser, email, startPaths, label) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 }, ignoreHTTPSErrors: IGNORE_HTTPS });
  attach(context);
  const page = await context.newPage();
  await login(page, email);
  console.log(`[${label}] logged in`);
  const seen = new Set();
  const queue = [...startPaths];
  let count = 0;
  while (queue.length && count < PAGE_CAP) {
    const route = queue.shift();
    if (seen.has(route)) continue;
    seen.add(route);
    count++;
    try {
      await page.goto(APP + route, { waitUntil: 'networkidle', timeout: 45000 }).catch(() => page.waitForTimeout(1500));
      await page.waitForTimeout(700);
      if (page.url().includes('/login')) { console.log(`[${label}] AUTH-BOUNCE ${route}`); continue; }
      const hrefs = await page.$$eval('a[href]', (as) => as.map((a) => a.getAttribute('href')));
      for (let h of hrefs) {
        if (!h) continue;
        if (h.startsWith('http')) {
          try { const hu = new URL(h); if (hu.hostname !== APP_HOST) continue; h = hu.pathname; } catch { continue; }
        }
        if (!h.startsWith('/')) continue;
        h = h.split('#')[0].split('?')[0];
        if (!h || h === '/') continue;
        if (/logout|signout|sign-out|\/api\/|\/_next\//.test(h)) continue;
        if (/\.(pdf|zip|png|jpg|jpeg|svg|webp|ico|css|js|txt|xml)$/.test(h)) continue;
        if (!seen.has(h)) queue.push(h);
      }
      if (count % 10 === 0) console.log(`[${label}] ${count} pages, queue ${queue.length}`);
    } catch (e) {
      console.log(`[${label}] FAIL ${route}: ${String(e).slice(0, 120)}`);
      stats.errors++;
    }
  }
  await context.close();
  return count;
}

const EMP_SEEDS = ['/employee-portal', '/employee-portal/tasks', '/employee-portal/projects', '/employee-portal/organizations', '/employee-portal/contacts', '/employee-portal/invoices', '/employee-portal/releases', '/employee-portal/analytics', '/employee-portal/kb', '/employee-portal/settings', '/employee-portal/tools'];
const CLI_SEEDS = ['/client-portal'];

const browser = await chromium.launch();
const n1 = await crawl(browser, TEAM_EMAIL, EMP_SEEDS, 'employee');
const n2 = await crawl(browser, CLIENT_EMAIL, CLI_SEEDS, 'client');
await browser.close();
fs.mkdirSync(OUT, { recursive: true });
fs.writeFileSync(
  path.join(OUT, 'export-report.json'),
  JSON.stringify({ generatedAt: new Date().toISOString(), pagesEmployee: n1, pagesClient: n2, stats, files: saved.size, htmlRoutes: savedRoutes.sort() }, null, 2)
);
console.log('DONE', JSON.stringify(stats), 'files:', saved.size);
