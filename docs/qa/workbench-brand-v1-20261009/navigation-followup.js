async page => {
  const checks = [], errors = [];
  const add = (name, pass, detail) => checks.push({name,pass:!!pass,detail});
  const c = await page.context().browser().newContext({viewport:{width:320,height:960},reducedMotion:'reduce'});
  const p = await c.newPage();
  p.on('pageerror', e => errors.push(e.message));
  p.on('console', m => { if(m.type()==='error') errors.push(m.text()); });
  p.on('requestfailed', r => errors.push(r.failure()?.errorText));
  p.on('response', r => { if(r.status()>=400) errors.push('HTTP '+r.status()); });
  for(const base of ['http://127.0.0.1:5190','http://127.0.0.1:5191']) {
    for(const width of [320,390,768]) {
      await p.setViewportSize({width,height:960}); await p.goto(base+'/analyst'); await p.waitForLoadState('networkidle');
      await p.locator('.mobile-menu-button').click();
      await p.locator('.advanced-nav summary').focus(); await p.keyboard.press('Tab');
      add(base+' '+width+' forward focus trap',await p.locator('.nav-close-button').evaluate(e=>e===document.activeElement));
      await p.keyboard.press('Shift+Tab');
      add(base+' '+width+' reverse focus trap',await p.locator('.advanced-nav summary').evaluate(e=>e===document.activeElement));
      await p.locator('.sidebar a[href="/demo"]').click(); await p.waitForURL(base+'/demo'); await p.locator('.demo-walkthrough').waitFor(); await p.waitForLoadState('networkidle');
      add(base+' '+width+' mobile navigation loads Demo and closes drawer',await p.locator('.mobile-menu-button').getAttribute('aria-expanded')==='false');
    }
    await p.setViewportSize({width:1440,height:960}); await p.locator('.advanced-nav summary').click();
    await p.locator('.sidebar a[href="/settings"]').click(); await p.waitForURL(base+'/settings'); await p.waitForLoadState('networkidle');
    add(base+' advanced navigation route settled',await p.locator('.advanced-nav').getAttribute('open')!==null && p.url()===base+'/settings');
  }
  await c.close();
  return {passed:checks.filter(c=>c.pass).length,total:checks.length,checks,errors,
    supersedes:['mobile navigation retains keyboard focus trap','advanced navigation and settings remain available'],
    cause:'Closed details descendants had client rects but were not focusable; settings assertion ran before router navigation settled. Both baseline and candidate pass with correct focus selection and route wait. No product code correction.'};
}
