const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const puppeteer = require(process.env.PUPPETEER_MODULE || 'puppeteer');
(async()=>{
 const root=process.cwd(), out=path.join(root,'docs/evidence/s4-job-search-freeze-20260921');
 const browser=await puppeteer.launch({executablePath:process.env.CHROMIUM_EXECUTABLE,headless:true,args:['--no-sandbox','--disable-background-networking']});
 const results=[];
 try {
 for(const [name,width,height] of [['desktop',1360,900],['mobile',390,844]]) {
  const page=await browser.newPage(); await page.setViewport({width,height}); await page.setOfflineMode(true);
  const network=[],errors=[]; page.on('request',req=>{if(/^https?:/.test(req.url()))network.push(req.url())}); page.on('pageerror',e=>errors.push(e.message));
  const url='file://'+path.join(root,'docs/recruiter/demo/index.html'); await page.goto(url);
  assert.equal(await page.title(),'SameScale · 从一次 coding task 到可复验的工程证据');
  assert.equal(await page.$$eval('nav a',a=>a.length),7);
  for(const id of ['task','configurations','result','trace','diagnosis','replay','ci']) {
   await page.click(`nav a[href="#${id}"]`); assert.equal(await page.evaluate(()=>location.hash),'#'+id);
  }
  for(const el of await page.$$('summary')) {await el.click();assert.equal(await el.evaluate(e=>e.parentElement.open),true)}
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(network,[]);assert.deepEqual(errors,[]);
  await page.click('a.back'); await page.reload(); assert.equal(await page.evaluate(()=>location.hash),'#top');
  await page.evaluate(()=>scrollTo(0,0)); await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});
  if(name==='desktop') await page.screenshot({path:path.join(out,'preview.png')});
  await page.keyboard.press('Tab'); const focus=await page.evaluate(()=>document.activeElement.className); assert.equal(focus,'skip');
  results.push({viewport:name,width,height,anchors:7,details:3,refresh:'PASS',keyboard_skip_link:'PASS',horizontal_overflow:false,http_requests:network.length,page_errors:errors.length});
  await page.close();
 }
 fs.writeFileSync(path.join(out,'browser-acceptance.json'),JSON.stringify({status:'PASS',mode:'file:// + offline browser',checks:results},null,2)+'\n');
 console.log(JSON.stringify(results));
 } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
