/* Gap-fix re-capture for the four failed client-portal sections. Logs in as
 * the client demo user and asserts the FINAL url still matches the requested
 * route before saving (the original failure saved a redirected employee
 * dashboard under every client filename). */
const { chromium } = require(
  "/Users/michaelwalliser/Desktop/DevProd/analog-elk-front-end/node_modules/@playwright/test"
);
const fs = require("fs");

const SP =
  "/private/tmp/claude-501/-Users-michaelwalliser-Desktop-DevProd/193697dd-78a5-425e-9fd6-28042c7dfd65/scratchpad";
const SHOTS = SP + "/shots";
const BASE = "https://app.musterr.dev";

async function settle(page, extra) {
  try {
    await page.waitForLoadState("networkidle", { timeout: 25000 });
  } catch (e) {
    /* polling pages never go idle */
  }
  await page.waitForTimeout(extra || 3000);
}

(async () => {
  const results = { shots: [], errors: [] };
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  try {
    await page.goto(BASE + "/login", { waitUntil: "domcontentloaded", timeout: 45000 });
    await page.waitForSelector("#email", { timeout: 20000 });
    await page.fill("#email", "client@muster.dev");
    await page.fill("#password", "muster-demo");
    await Promise.all([
      page.waitForURL(/portal/, { timeout: 30000 }).catch(() => null),
      page.click('button[type="submit"]'),
    ]);
    await settle(page);
    results.post_login = page.url();

    const targets = [
      ["tasks", "fixed-client-tasks.png", 4000],
      ["invoices", "fixed-client-invoices.png", 3000],
      ["products", "fixed-client-products.png", 3000],
      ["analytics", "fixed-client-analytics.png", 9000],
    ];
    for (const [section, out, extra] of targets) {
      const url = `${BASE}/client-portal/${section}`;
      try {
        await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
        await settle(page, extra);
        const finalUrl = page.url();
        if (!finalUrl.startsWith(url)) {
          throw new Error(`REDIRECTED: wanted ${url} but landed on ${finalUrl}`);
        }
        await page.screenshot({ path: `${SHOTS}/${out}`, fullPage: true });
        results.shots.push({ section: "client/" + section, finalUrl, out });
      } catch (e) {
        results.errors.push(section + ": " + (e && e.message ? e.message : String(e)));
      }
    }
  } catch (e) {
    results.errors.push("login: " + (e && e.message ? e.message : String(e)));
  }

  await browser.close();
  fs.writeFileSync(SHOTS + "/gapfix4-results.json", JSON.stringify(results, null, 2));
  console.log(JSON.stringify(results, null, 2));
  process.exit(results.errors.length ? 1 : 0);
})();
