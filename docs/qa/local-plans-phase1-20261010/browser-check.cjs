// Actual built UI + private API + disposable PostgreSQL, no mocked product responses.
// Run only against the synthetic tests/local_plan_helpers.py fixture, never a real task source.
const { chromium } = require(process.env.SAMESCALE_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.PHASE1_BROWSER_URL;
const output = process.env.PHASE1_BROWSER_OUTPUT;
const token = process.env.PHASE1_BROWSER_TOKEN;
const fixture = process.env.PHASE1_BROWSER_FIXTURE;
assert(base && output && token && fixture, 'Explicit isolated browser environment required');
assert(['127.0.0.1', 'localhost'].includes(new URL(base).hostname));
const workspace = path.join(fixture, 'sources/phase1-fixture/1.0.0/workspace/answer.py');
assert(fs.readFileSync(path.join(fixture, 'sources/phase1-fixture/1.0.0/instruction.md'), 'utf8').startsWith('Synthetic Phase-1 planning fixture;'));
const headers = { Authorization: `Bearer ${token}`, Origin: base };
const checks = [], errors = [], external = [], saved = [];
function check(name, condition) { assert(condition, name); checks.push(name); }
async function unlock(page) {
  await page.locator('[data-test=operator]').fill(token);
  await page.locator('[data-test=operator]').locator('xpath=ancestor::form').getByRole('button').click();
  await page.locator('[data-test=source]').waitFor();
}
async function select(page, name) {
  await page.locator('[data-test=source]').selectOption('0');
  await page.locator('[data-test=import]').click();
  await page.locator('[data-test=task-inspection]').waitFor();
  const response = await page.request.get(`${base}/api/local-plans/configurations`, { headers });
  const configs = (await response.json()).items;
  const index = configs.findIndex(c => c.provider_profile_id === 'gpt56-relay-gpt56-responses' && c.harness_profile_id === 'codex-gpt56-high');
  assert(index >= 0);
  await page.locator('[data-test=configuration]').selectOption(String(index));
  await page.locator('[data-test=name]').fill(name);
}
async function preflight(page) {
  const response = page.waitForResponse(r => r.url().endsWith('/preflight') && r.request().method() === 'POST');
  await page.locator('[data-test=preflight]').click();
  const receipt = await (await response).json();
  check('preflight-ready-with-no-calls', receipt.status === 'READY_TO_SAVE' && receipt.provider_calls === 0 && receipt.verifier_calls === 0 && receipt.execution_authorized === false);
  await page.locator('[data-test=confirmation]').waitFor();
  return receipt;
}
(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const report = { status: 'RUNNING', browser: browser.version(), source: 'ACTUAL_BUILT_UI_PRIVATE_API_ISOLATED_POSTGRES_SYNTHETIC_PRIOR_EVIDENCE', checks, errors, external, saved };
  try {
    for (const width of [1366, 1440]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 } });
      await context.route('**/*', route => {
        if (route.request().url().startsWith(base + '/')) return route.continue();
        external.push(route.request().url()); return route.abort();
      });
      const page = await context.newPage();
      page.on('pageerror', e => errors.push(e.message));
      page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
      await page.goto(`${base}/plans`);
      check(`operator-required-${width}`, await page.locator('[data-test=operator]').isVisible() && await page.locator('[data-test=preflight]').count() === 0);
      await unlock(page); await select(page, `Browser planning ${width}`);
      check(`prior-evidence-not-new-verification-${width}`, (await page.locator('[data-test=task-inspection]').innerText()).includes('本轮未执行 Verifier'));
      const receipt = await preflight(page);
      check(`one-task-one-attempt-${width}`, receipt.material.custom_plan.targets.length === 1 && receipt.material.custom_plan.tasks.length === 1 && receipt.material.custom_plan.run_slots.length === 1);
      check(`confirmation-required-${width}`, await page.locator('[data-test=save]').isDisabled());
      await page.locator('[data-test=confirmation]').check();
      const response = page.waitForResponse(r => r.url().endsWith('/plans') && r.request().method() === 'POST');
      await page.locator('[data-test=save]').click();
      const plan = await (await response).json();
      saved.push({ plan_id: plan.plan_id, plan_digest: plan.plan_digest, width });
      await page.waitForURL(`${base}/plans/${plan.plan_id}`);
      await page.locator('[data-test=saved-plan]').waitFor();
      await page.waitForFunction(() => !document.querySelector('[data-test=preflight]').disabled);
      check(`persisted-plan-only-${width}`, plan.runs_created === 0 && plan.episodes_created === 0 && plan.execution_authorized === false);
      check(`execute-disabled-${width}`, await page.locator('[data-test=saved-plan]').getByRole('button', { name: '执行暂未开放', exact: true }).isDisabled());
      check(`no-horizontal-overflow-${width}`, await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({ path: path.join(output, `saved-${width}.png`), fullPage: true });
      await page.reload(); await unlock(page);
      const restored = await (await page.request.get(`${base}/api/local-plans/plans/${plan.plan_id}`, { headers })).json();
      check(`refresh-restores-exact-plan-${width}`, restored.plan.plan_digest === plan.plan_digest && restored.current_status === 'UNCHANGED_RECHECK_REQUIRED');
      check(`operator-not-in-browser-storage-${width}`, await page.evaluate(value => !JSON.stringify([localStorage, sessionStorage]).includes(value), token));
      await context.close();
    }
    const api = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    for (const [name, method, endpoint, data, customHeaders, expected] of [
      ['unauthorized-read', 'get', '/plans', undefined, {}, 403],
      ['cross-origin-write', 'post', '/tasks/import', { root_id: 'trusted', relative_path: 'phase1-fixture/1.0.0' }, { ...headers, Origin: 'https://outside.invalid' }, 403],
      ['traversal-rejected', 'post', '/tasks/import', { root_id: 'trusted', relative_path: '../outside' }, headers, 422],
      ['execute-api-closed', 'post', `/plans/${saved[0].plan_id}/execute`, {}, headers, 403],
    ]) {
      const response = await api.request[method](`${base}/api/local-plans${endpoint}`, { headers: customHeaders, ...(data ? { data } : {}) });
      check(name, response.status() === expected);
    }
    const request = { name: 'Missing explicit budget', task_reference: 'phase1-fixture@1.0.0', provider_profile_id: 'gpt56-relay-gpt56-responses', harness_profile_id: 'codex-gpt56-high' };
    const blocked = await (await api.request.post(`${base}/api/local-plans/preflight`, { headers, data: request })).json();
    check('missing-budget-blocks-plan', blocked.status === 'BLOCKED' && blocked.material === null);
    const ready = await (await api.request.post(`${base}/api/local-plans/preflight`, { headers, data: { ...request, name: 'Drift rejection', budget: { wall_time_seconds: 90, output_tokens_estimate: 1000, cost_budget_usd: 1 } } })).json();
    assert.equal(ready.status, 'READY_TO_SAVE');
    fs.writeFileSync(workspace, 'ANSWER = 1\n');
    const drift = await api.request.post(`${base}/api/local-plans/plans`, { headers, data: { receipt_id: ready.receipt_id, receipt_digest: ready.receipt_digest, idempotency_key: require('node:crypto').randomUUID(), confirm_plan_only: true } });
    check('source-drift-invalidates-preflight', drift.status() === 409 && (await drift.json()).error.code === 'PREFLIGHT_STALE');
    const original = await (await api.request.get(`${base}/api/local-plans/plans/${saved[0].plan_id}`, { headers })).json();
    check('stale-plan-original-preserved', original.current_status === 'STALE' && original.plan.plan_digest === saved[0].plan_digest);
    const page = await api.newPage();
    await page.goto(`${base}/plans/${saved[0].plan_id}`); await unlock(page);
    await page.locator('[data-test=current-status]').waitFor();
    check('stale-ui-remains-readable', (await page.locator('[data-test=current-status]').innerText()).includes('原计划保留'));
    await page.screenshot({ path: path.join(output, 'stale-1440.png'), fullPage: true });
    fs.writeFileSync(workspace, 'ANSWER = 0\n');
    check('normal-ui-no-runtime-errors', errors.length === 0);
    check('zero-external-browser-requests', external.length === 0);
    report.status = 'PASS';
  } catch (error) { report.status = 'FAIL'; report.failure = error.message; throw error; }
  finally { fs.writeFileSync(path.join(output, 'browser.json'), JSON.stringify(report, null, 2)); await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
