// Built UI + real local API + disposable PostgreSQL + separate keyless Docker Worker.
const { chromium } = require(process.env.SAMESCALE_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const { execFile } = require('node:child_process'), { promisify } = require('node:util');
const exec = promisify(execFile);
const base = process.env.PHASE2_BROWSER_URL, output = process.env.PHASE2_BROWSER_OUTPUT;
const root = process.env.PHASE2_BROWSER_FIXTURE, repo = process.env.PHASE2_BROWSER_REPO;
const token = process.env.PHASE2_BROWSER_TOKEN;
assert(base && output && root && repo && token);
assert(['127.0.0.1','localhost'].includes(new URL(base).hostname));
const taskPolicy = path.join(root, 'task-policy.json'), executionPolicy = path.join(root, 'execution-policy.json');
assert(fs.existsSync(taskPolicy) && fs.existsSync(executionPolicy));
const headers = { Authorization: `Bearer ${token}`, Origin: base };
const checks = [], errors = [], external = [], results = [];
function check(name, value) { assert(value, name); checks.push(name); }
async function worker() {
 const env = { PATH: process.env.PATH, HOME: process.env.HOME, DATABASE_URL: process.env.DATABASE_URL,
  HARNESSLAB_ENVIRONMENT:'test', HARNESSLAB_LOCAL_CONFIGURATION_TOKEN:token, HARNESSLAB_LOCAL_TASK_POLICY:taskPolicy,
  HARNESSLAB_LOCAL_EXECUTION_POLICY:executionPolicy, HARNESSLAB_GPT56_RELAY_BASE_URL:'https://phase2.invalid/never-called',
  HARNESSLAB_GPT56_RELAY_API_KEY:'phase2-reference-only' };
 assert(env.DATABASE_URL.includes('samescale_phase2_test'));
 return exec('uv', ['run','--locked','harnesslab','local-worker','once'], { cwd:repo, env, timeout:60000 });
}
async function unlock(page) { await page.locator('[data-test=operator]').fill(token); await page.locator('[data-test=operator]').locator('xpath=ancestor::form').getByRole('button').click(); await page.locator('[data-test=source]').waitFor(); }
async function create(page, name, seconds = 20) {
 await page.goto(base + '/plans'); await unlock(page);
 await page.locator('[data-test=source]').selectOption('0'); await page.locator('[data-test=import]').click();
 await page.locator('[data-test=task-inspection]').waitFor();
 const configurations = (await (await page.request.get(base+'/api/local-plans/configurations',{headers})).json()).items;
 const index = configurations.findIndex(x => x.provider_profile_id === 'gpt56-relay-gpt56-responses' && x.harness_profile_id === 'codex-gpt56-high'); assert(index >= 0);
 await page.locator('[data-test=configuration]').selectOption(String(index)); await page.locator('[data-test=name]').fill(name); await page.locator('[data-test=wall-time]').fill(String(seconds));
 await page.locator('[data-test=preflight]').click(); await page.locator('[data-test=confirmation]').waitFor();
 check(name+'-plan-separate-confirmation', await page.locator('[data-test=save]').isDisabled());
 await page.locator('[data-test=confirmation]').check(); await page.locator('[data-test=save]').click();
 await page.locator('[data-test=execution-state]').waitFor();
 check(name+'-not-authorized-after-plan-save', (await page.locator('[data-test=execution-state]').textContent()).includes('未授权执行'));
 check(name+'-execution-confirmation-required', await page.locator('[data-test=authorize]').isDisabled());
 check(name+'-reference-budgets-visible', (await page.locator('[data-test=execution-panel]').textContent()).includes('不是硬上限'));
 return page.url().split('/').pop();
}
async function authorize(page) {
 await page.locator('[data-test=execute-confirmation]').check(); const response = page.waitForResponse(r => r.url().endsWith('/authorize') && r.request().method() === 'POST');
 await page.locator('[data-test=authorize]').click(); const r=await response; check('authorization-success', r.status()===200);
 const state=await r.json();check('one-queued-attempt',state.status==='QUEUED'&&state.attempt.attempt_number===0);return state;
}
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 // Restart may return before the API is listening. Readiness has no execution side effect.
 let ready=false;for(let i=0;i<120;i++){try{const r=await fetch(base+'/api/local-plans/status');if(r.ok){ready=true;break}}catch{}await new Promise(r=>setTimeout(r,250))}
 assert(ready,'isolated control API readiness');
 const browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}});
 page.on('pageerror',e=>errors.push(String(e)));page.on('console',m=>{if(m.type()==='error') errors.push(m.text())});
 await page.route('**/*',route=>{if(new URL(route.request().url()).origin!==base){external.push(route.request().url());return route.abort()}return route.continue()});
 try {
  const id=await create(page,'Browser isolated Fake success'); const queued=await authorize(page);
  check('real-mode-closed',queued.real_execution_enabled===false);
  await page.screenshot({path:path.join(output,'queued.png'),fullPage:true});
  await page.reload();await unlock(page);await page.locator('[data-test=execution-state]').waitFor();
  check('queue-survives-refresh',(await page.locator('[data-test=execution-state]').textContent()).includes('等待独立 Worker'));
  const first=await worker();check('worker-produced-run',JSON.parse(first.stdout.trim()).run_id===queued.attempt.run_id);
  await page.locator('[data-test=execution-refresh]').click();await page.locator('[data-test=execution-result]').waitFor();
  check('independent-fake-pass',(await page.locator('[data-test=execution-state]').textContent()).includes('独立验收通过 · Fake'));
  const result=(await(await page.request.get(base+'/api/local-execution/plans/'+id,{headers})).json()).result;
  check('actual-workspace-change',result.episode.changed_file_count===1);check('independent-checks-collected',result.episode.verifier_check_count>0);check('normalized-trace-collected',result.episode.event_count>0);check('zero-model-calls',result.model_calls===0&&result.model_cost_usd===0);check('synthetic-evidence-scope',result.episode.source_kind==='synthetic');
  results.push(result);await page.screenshot({path:path.join(output,'verified-pass.png'),fullPage:true});
  check('no-repeat-control',await page.locator('[data-test=authorize]').count()===0);
  check('second-worker-idle',JSON.parse((await worker()).stdout.trim()).run_id===null);
  const policy=JSON.parse(fs.readFileSync(executionPolicy));policy.scenario='wrong_workspace';fs.writeFileSync(executionPolicy,JSON.stringify(policy));
  const failId=await create(page,'Browser self-report rejected');await authorize(page);await worker();await page.locator('[data-test=execution-refresh]').click();await page.locator('[data-test=execution-result]').waitFor();
  const failed=(await(await page.request.get(base+'/api/local-execution/plans/'+failId,{headers})).json()).result;
  check('self-report-rejected',failed.acceptance==='RECORDED_FAIL'&&failed.episode.changed_file_count===0);results.push(failed);
  await page.screenshot({path:path.join(output,'verified-fail.png'),fullPage:true});
  const cancelId=await create(page,'Browser queued cancellation');await authorize(page);await page.locator('[data-test=cancel-execution]').click();
  await page.waitForFunction(()=>document.querySelector('[data-test=execution-state]')?.textContent.includes('已取消'));
  check('queued-cancel-no-launch',JSON.parse((await worker()).stdout.trim()).run_id===null);
  check('cancel-persisted',(await(await page.request.get(base+'/api/local-execution/plans/'+cancelId,{headers})).json()).status==='CANCELLED');
  check('desktop-no-overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  check('token-never-stored',await page.evaluate(()=>!localStorage.length||!Object.values(localStorage).some(v=>v.includes('local-operator-test-placeholder'))));
  const forbidden=await page.request.post(base+'/api/local-execution/plans/'+id+'/authorize',{headers:{...headers,Authorization:'Bearer invalid'},data:{}});check('permission-denied',forbidden.status()===403);
  // Mutate one actually collected trace byte; UI must suppress the old result.
  const trace=path.join(policy.artifact_root,result.run_id,'trace/normalized.json');fs.appendFileSync(trace,' ');
  await page.goto(base+'/plans/'+id);await unlock(page);await page.locator('[data-test=execution-error]').waitFor();
  check('tampered-evidence-rejected',(await page.locator('[data-test=execution-error]').textContent()).includes('EXECUTION_EVIDENCE_INTEGRITY_ERROR'));
  check('no-substitute-result',await page.locator('[data-test=execution-result]').count()===0);
  await page.screenshot({path:path.join(output,'tampered-evidence.png'),fullPage:true});
  check('no-external-network',external.length===0);
  // The deliberate 409/403 above may generate HTTP console lines; no runtime errors allowed.
  check('no-runtime-errors',errors.every(e=>e.includes('409')||e.includes('403')));
  fs.writeFileSync(path.join(output,'browser.json'),JSON.stringify({status:'PASS',browser:browser.version(),checks,errors,external,results},null,2));
  console.log(JSON.stringify({status:'PASS',checks:checks.length,browser:browser.version()}));
 }catch(e){fs.writeFileSync(path.join(output,'failure.json'),JSON.stringify({error:String(e),checks,errors,external},null,2));throw e}finally{await browser.close()}
})();
