// Stop/restart the dedicated QA API first, wait for its /status, and reuse the exact same test DB.
const { chromium } = require(process.env.SAMESCALE_PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const output = process.env.PHASE1_BROWSER_OUTPUT, base = process.env.PHASE1_BROWSER_URL, token = process.env.PHASE1_BROWSER_TOKEN;
assert(output && base && token);
assert(['127.0.0.1', 'localhost'].includes(new URL(base).hostname));
(async () => {
  const prior = JSON.parse(fs.readFileSync(output + '/browser.json'));
  assert.equal(prior.status, 'PASS');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage(), checks = [];
  try {
    await page.goto(base + '/plans/' + prior.saved[0].plan_id);
    await page.locator('[data-test=operator]').fill(token);
    await page.locator('[data-test=operator]').locator('xpath=ancestor::form').getByRole('button').click();
    await page.locator('[data-test=saved-plan]').waitFor();
    const r = await page.request.get(base + '/api/local-plans/plans/' + prior.saved[0].plan_id, { headers: { Authorization: 'Bearer ' + token } });
    const data = await r.json();
    assert.equal(data.plan.plan_digest, prior.saved[0].plan_digest);
    checks.push('exact-plan-digest-preserved-after-process-restart');
    assert.equal(data.current_status, 'UNCHANGED_RECHECK_REQUIRED');
    checks.push('current-source-revalidated-after-process-restart');
    assert.equal(data.plan.runs_created, 0); assert.equal(data.plan.episodes_created, 0); assert.equal(data.plan.execution_authorized, false);
    checks.push('no-execution-after-restart');
    await page.screenshot({ path: output + '/restarted-1440.png', fullPage: true });
    fs.writeFileSync(output + '/restart.json', JSON.stringify({ status: 'PASS', checks, browser: browser.version() }, null, 2));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
