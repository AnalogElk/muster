/* Gap-fix re-capture: tools + help (employee demo user) and dashboard +
 * projects (client demo user). Hardened: after navigation, page.url() MUST
 * still be inside the expected portal prefix or the shot FAILS LOUD instead
 * of saving a redirect target (the cli-*.png byte-identical failure mode). */
const { chromium } = require(
  "/Users/michaelwalliser/Desktop/DevProd/analog-elk-front-end/node_modules/@playwright/test"
);
const fs = require("fs");

const SP =
  "/private/tmp/claude-501/-Users-michaelwalliser-Desktop-DevProd/193697dd-78a5-425e-9fd6-28042c7dfd65/scratchpad";
const SHOTS = SP + "/shots";
const BASE = "https://app.musterr.dev";

async function settle(page) {
  try {
    await page.waitForLoadState("networkidle", { timeout: 20000 });
  } catch (e) {
    /* polling pages never go idle */
  }
  await page.waitForTimeout(2500);
}

async function login(context, email, password) {
  const page = await context.newPage();
  await page.goto(BASE + "/login", { waitUntil: "domcontentloaded", timeout: 45000 });
  await page.waitForSelector("#email", { timeout: 20000 });
  await page.fill("#email", email);
  await page.fill("#password", password);
  await Promise.all([
    page.waitForURL(/portal/, { timeout: 30000 }).catch(() => null),
    page.click('button[type="submit"]'),
  ]);
  await settle(page);
  return page;
}

async function shoot(page, url, outPath, mustPrefix) {
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
  await settle(page);
  const finalUrl = page.url();
  if (!finalUrl.startsWith(mustPrefix)) {
    throw new Error(
      `REDIRECTED: wanted prefix ${mustPrefix} but landed on ${finalUrl} (refusing to save ${outPath})`
    );
  }
  await page.screenshot({ path: outPath, fullPage: true });
  return finalUrl;
}

(async () => {
  const results = { shots: [], errors: [] };
  const browser = await chromium.launch({ headless: true });

  // ── Employee session: tools + help ────────────────────────────────────
  try {
    const empCtx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await login(empCtx, "demo@muster.dev", "muster-demo");
    results.emp_post_login = page.url();

    for (const [section, out] of [
      ["tools", "fixed-tools.png"],
      ["help", "fixed-help.png"],
    ]) {
      const finalUrl = await shoot(
        page,
        `${BASE}/employee-portal/${section}`,
        `${SHOTS}/${out}`,
        `${BASE}/employee-portal/${section}`
      );
      results.shots.push({ section: "employee/" + section, finalUrl, out });
    }
    await empCtx.close();
  } catch (e) {
    results.errors.push("employee: " + (e && e.message ? e.message : String(e)));
  }

  // ── Client session: dashboard + projects ─────────────────────────────
  try {
    const cliCtx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await login(cliCtx, "client@muster.dev", "muster-demo");
    results.cli_post_login = page.url();

    for (const [section, out] of [
      ["dashboard", "fixed-client-dashboard.png"],
      ["projects", "fixed-client-projects.png"],
    ]) {
      const finalUrl = await shoot(
        page,
        `${BASE}/client-portal/${section}`,
        `${SHOTS}/${out}`,
        `${BASE}/client-portal/${section}`
      );
      results.shots.push({ section: "client/" + section, finalUrl, out });
    }
    await cliCtx.close();
  } catch (e) {
    results.errors.push("client: " + (e && e.message ? e.message : String(e)));
  }

  await browser.close();
  fs.writeFileSync(SHOTS + "/gapfix-thc-results.json", JSON.stringify(results, null, 2));
  console.log(JSON.stringify(results, null, 2));
  process.exit(results.errors.length ? 1 : 0);
})();
