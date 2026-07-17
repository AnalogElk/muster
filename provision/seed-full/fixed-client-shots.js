// Post-rebuild proof shots: client/dashboard and client/projects as the
// client-role demo user (Rowan Ashford), with hard URL assertions and a
// programmatic check that the header avatar <img> actually decoded.
const { chromium } = require('/Users/michaelwalliser/Desktop/DevProd/analog-elk-front-end/node_modules/@playwright/test');

const SP = '/private/tmp/claude-501/-Users-michaelwalliser-Desktop-DevProd/193697dd-78a5-425e-9fd6-28042c7dfd65/scratchpad';
const BASE = 'https://app.musterr.dev';
const ROUTES = [
  ['client-dashboard', '/client-portal/dashboard'],
  ['client-projects', '/client-portal/projects'],
];

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1200 } });
  const page = await ctx.newPage();

  await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(2500);
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await email.waitFor({ timeout: 15000 });
  await email.fill('client@muster.dev');
  await page.locator('input[type="password"], input[name="password"]').first().fill('muster-demo');
  await page.locator('button[type="submit"]').first().click();
  await page.waitForURL(/portal/, { timeout: 30000 });
  await page.waitForTimeout(2000);
  console.log('AFTER_LOGIN_URL: ' + page.url());

  const results = [];
  for (const [name, route] of ROUTES) {
    try {
      await page.goto(BASE + route, { waitUntil: 'domcontentloaded', timeout: 60000 });
      await page.waitForTimeout(1500);
      try { await page.waitForLoadState('networkidle', { timeout: 20000 }); } catch (_) {}
      await page.waitForTimeout(3000);
      const finalUrl = page.url();
      if (!new URL(finalUrl).pathname.startsWith(route)) {
        throw new Error(`URL ASSERTION FAILED: requested ${route} but landed on ${finalUrl}`);
      }
      // Programmatic avatar proof: find header imgs pointing at CMS assets or
      // the next/image optimizer and report decode state.
      const avatarState = await page.evaluate(() => {
        const imgs = Array.from(document.querySelectorAll('header img, img'));
        return imgs
          .filter((i) => (i.currentSrc || i.src || '').match(/_next\/image|assets\//))
          .slice(0, 6)
          .map((i) => ({
            src: (i.currentSrc || i.src).slice(0, 140),
            complete: i.complete,
            naturalWidth: i.naturalWidth,
            alt: (i.alt || '').slice(0, 40),
          }));
      });
      const shot = `${SP}/shots2/fixed-${name}.png`;
      await page.screenshot({ path: shot, fullPage: true });
      // Header crop for pixel-level proof of the avatar slot.
      const crop = `${SP}/shots2/fixed-${name}-header.png`;
      await page.screenshot({ path: crop, clip: { x: 1100, y: 0, width: 340, height: 60 } });
      results.push({ section: name, requested: route, finalUrl, shot, avatarState });
      console.log(`CAPTURED ${name} final=${finalUrl}`);
      console.log('AVATAR_STATE ' + name + ' ' + JSON.stringify(avatarState));
    } catch (e) {
      results.push({ section: name, requested: route, error: e.message.split('\n')[0] });
      console.log(`FAILED ${name}: ${e.message.split('\n')[0]}`);
    }
  }
  require('fs').writeFileSync(`${SP}/shots2/fixed-client-results.json`, JSON.stringify(results, null, 2));
  await browser.close();
})();
