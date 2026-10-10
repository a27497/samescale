/* Local browser acceptance: only explicitly approved saved records, zero Agent execution. */
const { chromium } = require(process.env.SAMESCALE_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const base = process.env.EVIDENCE_BROWSER_URL, out = process.env.EVIDENCE_BROWSER_OUTPUT;
const token = process.env.EVIDENCE_BROWSER_TOKEN, store = process.env.EVIDENCE_BROWSER_STORE;
assert(base && out && token && store && ['127.0.0.1', 'localhost'].includes(new URL(base).hostname));
const checks = [], errors = [], external = [];
function check(name, value) { assert(value, name); checks.push(name); }
async function unlock(page) {
  await page.locator('[data-test=operator]').fill(token);
  await page.locator('[data-test=operator]').locator('xpath=ancestor::form').getByRole('button').click();
  await page.locator('[data-test=source]').waitFor();
}
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
    await context.route('**/*', route => {
      const url = new URL(route.request().url());
      if (!['127.0.0.1', 'localhost'].includes(url.hostname)) { external.push(url.origin); return route.abort(); }
      return route.continue();
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    let evidenceReads = 0;
    page.on('request', r => { if (r.url().includes('/api/external-evidence/')) evidenceReads++; });
    await page.goto(base + '/external-runs');
    await page.locator('[data-test=operator]').waitFor();
    check('No private discovery before unlock', evidenceReads === 0);
    await unlock(page);
    await page.locator('[data-test=source]').selectOption('approved-historical-real');
    check('Consent required', await page.locator('[data-test=import]').isDisabled());
    await page.locator('[data-test=consent]').check();
    await page.locator('[data-test=import]').click();
    await page.locator('[data-test=detail]').waitFor();
    const identity = new URL(page.url()).pathname.split('/').at(-1);
    check('Saved real record opened', /^[a-f0-9]{64}$/.test(identity));
    check('Independent historical 5/5', /VERIFIED_PASS.*5\/5/.test(await page.locator('[data-test=acceptance]').innerText()));
    check('Original Episode retained', (await page.locator('[data-test=detail]').innerText()).includes('NOT_VERIFIED'));
    check('Missing fields and origin disclosed', (await page.locator('[data-test=detail]').innerText()).includes('NOT_ATTESTED') && (await page.locator('[data-test=detail]').innerText()).includes('tool_exit_codes'));
    const downloadEvent = page.waitForEvent('download');
    await page.locator('[data-test=export]').click();
    const download = await downloadEvent;
    await download.saveAs(path.join(out, 'saved-evidence.json'));
    await page.getByText('单独保存可信导出摘要供离线核验', { exact: false }).waitFor();
    const digest = await page.locator('p code').first().innerText();
    fs.writeFileSync(path.join(out, 'export-digest.txt'), digest);
    const exported = JSON.parse(fs.readFileSync(path.join(out, 'saved-evidence.json')));
    check('Export excludes hidden assets', exported.hidden_assets_included === false && !JSON.stringify(exported).includes('verifier-source'));
    check('No credential in browser storage or export', !JSON.stringify(await page.evaluate(() => [Object.entries(localStorage), Object.entries(sessionStorage)])).includes(token) && !JSON.stringify(exported).includes(token));
    await page.screenshot({ path: path.join(out, 'historical-real.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    check('Mobile page stays within viewport', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await page.screenshot({ path: path.join(out, 'mobile.png'), fullPage: true });
    await page.reload();
    await page.locator('[data-test=operator]').waitFor();
    check('Reload forgets operator token', await page.locator('[data-test=operator]').inputValue() === '');
    await unlock(page); await page.locator('[data-test=detail]').waitFor();
    check('Restart reads existing identity', page.url().endsWith(identity));
    await page.locator('[data-test=source]').selectOption('synthetic-native');
    await page.locator('[data-test=consent]').check(); await page.locator('[data-test=import]').click();
    await page.waitForURL(url => !url.pathname.endsWith(identity));
    await page.locator('[data-test=detail]').waitFor();
    check('Fixture and missing task remain synthetic/unverified', (await page.locator('[data-test=detail]').innerText()).includes('synthetic') && (await page.locator('[data-test=acceptance]').innerText()).includes('NOT_VERIFIED'));
    await page.screenshot({ path: path.join(out, 'unverified.png'), fullPage: true });
    await page.getByRole('link', { name: 'approved-historical-real', exact: true }).click();
    await page.locator('[data-test=detail]').waitFor();
    fs.appendFileSync(path.join(store, identity, 'workspace/events.py'), '\n# controlled tamper\n');
    await page.getByRole('button', { name: '刷新独立验收', exact: true }).click();
    await page.locator('[role=alert]').waitFor();
    check('Tamper fails closed without replacement pass', !(await page.locator('[data-test=detail]').count()) && (await page.locator('[role=alert]').innerText()).includes('EVIDENCE_INTEGRITY_ERROR'));
    check('Zero external requests', external.length === 0);
    check('Zero browser exceptions', errors.length === 0);
    fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify({ status: 'PASS', checks, errors, external, real_source: 'saved-native-hook-20261007', synthetic_source: 'controlled-native-hook-fixture', agent_runs: 0, model_calls: 0, export_digest: digest }, null, 2));
    console.log(JSON.stringify({ status: 'PASS', checks: checks.length, agent_runs: 0, model_calls: 0 }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
