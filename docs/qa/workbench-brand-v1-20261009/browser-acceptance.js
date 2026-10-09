async page => {
  const root = '/tmp/samescale-workbench-brand-v1';
  const origins = { baseline: 'http://127.0.0.1:5190', brand: 'http://127.0.0.1:5191' };
  const checks = [], errors = [], requests = [], layouts = {}, captures = [];
  const add = (name, pass, detail) => checks.push({ name, pass: !!pass, detail });
  const browser = page.context().browser();
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 }, reducedMotion: 'reduce' });
  await context.route('**/*', async route => {
    const r = route.request(), match = r.url().match(/^(https?:\/\/[^/]+)([^?]*)/), u = { origin: match?.[1], pathname: match?.[2] };
    if (!Object.values(origins).includes(u.origin)) { errors.push({ type: 'external-request', url: u.origin }); await route.abort(); return; }
    if (u.pathname.startsWith('/api/')) {
      requests.push({ method: r.method(), path: u.pathname });
      if (!['GET', 'HEAD'].includes(r.method()) && !(r.method() === 'POST' && u.pathname === '/api/workbench/regression/compare')) {
        errors.push({ type: 'blocked-mutation', path: u.pathname }); await route.abort(); return;
      }
    }
    await route.continue();
  });
  const p = await context.newPage();
  p.on('pageerror', e => errors.push({ type: 'page', message: e.message }));
  p.on('console', m => { if (m.type() === 'error') errors.push({ type: 'console', message: m.text() }); });
  p.on('requestfailed', r => errors.push({ type: 'request', path: r.url().replace(/^https?:\/\/[^/]+/, '').split('?')[0], message: r.failure()?.errorText }));
  p.on('response', r => { if (r.status() >= 400) errors.push({ type: 'http', path: r.url().replace(/^https?:\/\/[^/]+/, '').split('?')[0], status: r.status() }); });
  const demoResponse = await p.request.get(origins.brand + '/api/workbench/public-demo');
  const demo = await demoResponse.json();
  add('saved Demo integrity gate ready', demoResponse.ok() && demo.public_demo_ready && demo.provenance === 'FIXTURE_OFFLINE');
  const urls = {
    home: '/analyst', demo: '/demo',
    run: '/runs/' + demo.failed_run_id + '?candidate=' + demo.candidate_id,
    diagnosis: '/diagnosis?experiment=' + demo.baseline_id + '&candidate=' + demo.candidate_id + '&run=' + demo.failed_run_id,
    regression: '/regression?baseline=' + demo.baseline_id + '&candidate=' + demo.candidate_id + '&run=' + demo.failed_run_id,
  };
  const ready = { home: '.home-hero', demo: '.demo-walkthrough', run: '.outcome-panel', diagnosis: '.diagnosis-master-detail', regression: '.comparability-panel' };
  async function go(origin, name) {
    await p.goto(origin + urls[name]); await p.locator(ready[name]).waitFor();
    await p.waitForLoadState('networkidle'); await p.evaluate(() => document.fonts.ready);
  }
  async function readLayout() {
    return p.evaluate(() => {
      const rect = s => { const e = document.querySelector(s); const b = e.getBoundingClientRect(); return [b.x, b.y, b.width, b.height]; };
      const statuses = [...document.querySelectorAll('[data-status]')].map(e => {
        const s = getComputedStyle(e); return { code: e.getAttribute('data-status'), text: e.textContent, color: s.color, background: s.backgroundColor, border: s.borderColor };
      });
      return { title: document.title, language: document.documentElement.lang, mainText: document.querySelector('.page-container').innerText,
        main: rect('.main-panel'), content: rect('.page-container'), topbar: rect('.topbar'),
        scrollWidth: document.documentElement.scrollWidth, viewportWidth: innerWidth, statuses,
        navigation: [...document.querySelectorAll('.nav-link')].map(e => ({ path: e.getAttribute('href'), text: e.innerText })) };
    });
  }
  for (const width of [320, 390, 768, 1440]) {
    await p.setViewportSize({ width, height: 960 });
    for (const name of Object.keys(urls)) {
      await go(origins.baseline, name); const before = await readLayout();
      await go(origins.brand, name); const after = await readLayout();
      layouts[name + '-' + width] = { baseline: before, brand: after };
      add(name + ' ' + width + ' page content and title preserved', before.mainText === after.mainText && before.title === after.title);
      add(name + ' ' + width + ' page geometry preserved', JSON.stringify([before.main, before.content, before.topbar]) === JSON.stringify([after.main, after.content, after.topbar]), { baseline: [before.main, before.content, before.topbar], brand: [after.main, after.content, after.topbar] });
      add(name + ' ' + width + ' no additional horizontal overflow', after.scrollWidth === before.scrollWidth, { baseline: before.scrollWidth, brand: after.scrollWidth, width });
      add(name + ' ' + width + ' status colors and labels unchanged', JSON.stringify(before.statuses) === JSON.stringify(after.statuses), after.statuses);
      add(name + ' ' + width + ' navigation destinations unchanged', JSON.stringify(before.navigation) === JSON.stringify(after.navigation));
      if (width <= 860) await p.locator('.mobile-menu-button').click();
      const logo = await p.locator('.workbench-brand').evaluate(async e => {
        await Promise.all([...e.querySelectorAll('img')].map(i => i.decode()));
        const b = e.getBoundingClientRect(), sidebar = e.closest('aside').getBoundingClientRect();
        const icon = e.querySelector('.workbench-brand__symbol');
        return { x: b.x, y: b.y, width: b.width, height: b.height, sidebarRight: sidebar.right,
          sources: [...e.querySelectorAll('img')].map(i => i.getAttribute('src')), symbolWidth: icon.getBoundingClientRect().width, natural: icon.naturalWidth,
          name: e.querySelector('.workbench-brand__name').textContent };
      });
      add(name + ' ' + width + ' official 24px brand fits navigation', logo.x >= 0 && logo.x + logo.width <= logo.sidebarRight && logo.height === 24 && logo.symbolWidth === 24 && logo.natural === 24 && logo.name === 'SameScale' && Number.isInteger(logo.x), logo);
      add(name + ' ' + width + ' selected navigation uses Cobalt', await p.locator('.nav-current').first().evaluate(e => getComputedStyle(e).color === 'rgb(66, 99, 213)'));
      if (name === 'home' || width === 1440) {
        const path = root + '/' + name + '-' + width + (width <= 860 ? '-navigation' : '') + '.png';
        await p.screenshot({ path, fullPage: width === 1440 }); captures.push(path);
      }
      if (width <= 860) {
        await p.keyboard.press('Escape');
        add(name + ' ' + width + ' Escape closes nav and restores focus', await p.locator('.mobile-menu-button').evaluate(e => e === document.activeElement && e.getAttribute('aria-expanded') === 'false'));
      }
    }
  }
  // Both locales retain brand naming, actual evidence and route-specific titles.
  await p.setViewportSize({ width: 1440, height: 960 });
  for (const name of ['home', 'run', 'diagnosis', 'regression', 'demo']) {
    await go(origins.baseline, name); await p.locator('.locale-switch button').nth(1).click(); const before = await readLayout();
    await go(origins.brand, name); await p.locator('.locale-switch button').nth(1).click(); const after = await readLayout();
    add(name + ' English content, status and title preserved', before.mainText === after.mainText && before.title === after.title && JSON.stringify(before.statuses) === JSON.stringify(after.statuses) && after.language === 'en-US');
    add(name + ' English brand accessible name', await p.locator('.brand').getAttribute('href') === '/analyst' && await p.locator('.workbench-brand__name').textContent() === 'SameScale');
  }
  await go(origins.brand, 'demo');
  await p.locator('.brand').click(); await p.waitForURL(origins.brand + '/analyst'); await p.waitForLoadState('networkidle');
  add('brand link returns to investigation home', await p.locator('.home-hero').isVisible());
  const buttonColor = await p.locator('.home-action-panel button').evaluate(e => getComputedStyle(e).backgroundColor);
  add('primary action uses Cobalt', buttonColor === 'rgb(66, 99, 213)', buttonColor);
  await p.keyboard.press('Tab'); await p.locator('.brand').focus();
  add('navigation keyboard focus uses Cobalt', await p.locator('.brand').evaluate(e => getComputedStyle(e).outlineColor === 'rgb(66, 99, 213)' && getComputedStyle(e).outlineStyle !== 'none'));
  await p.setViewportSize({ width: 320, height: 960 }); await p.locator('.mobile-menu-button').click();
  await p.locator('.sidebar').evaluate(e => [...e.querySelectorAll('a, button, summary')].filter(n => { const closed = n.closest('details:not([open])'); return (!closed || n === closed.querySelector('summary')) && n.getClientRects().length > 0 && getComputedStyle(n).visibility !== 'hidden'; }).at(-1).focus()); await p.keyboard.press('Tab');
  add('mobile navigation retains keyboard focus trap', await p.locator('.nav-close-button').evaluate(e => e === document.activeElement));
  await p.locator('.sidebar a[href="/demo"]').click(); await p.locator('.demo-walkthrough').waitFor(); await p.waitForLoadState('networkidle');
  add('mobile navigation link closes drawer and loads Demo', await p.locator('.mobile-menu-button').getAttribute('aria-expanded') === 'false');
  await p.setViewportSize({ width: 1440, height: 960 });
  await p.locator('.advanced-nav summary').click();
  await p.locator('.sidebar a[href="/settings"]').click(); await p.waitForURL(origins.brand + '/settings'); await p.waitForLoadState('networkidle');
  add('advanced navigation and settings remain available', p.url() === origins.brand + '/settings' && await p.locator('.advanced-nav').getAttribute('open') !== null);
  const metadata = await p.evaluate(() => ({ description: document.querySelector('meta[name="description"]').content,
    name: document.querySelector('meta[name="application-name"]').content,
    theme: document.querySelector('meta[name="theme-color"]').content,
    icons: [...document.querySelectorAll('link[rel*="icon"]')].map(e => e.getAttribute('href')) }));
  add('product identity metadata and favicon fallbacks', metadata.name === 'SameScale' && metadata.description.includes('AI Coding Agent') && metadata.theme === '#ffffff' && ['/favicon.svg','/favicon.ico','/favicon-32x32.png','/apple-touch-icon.png'].every(i => metadata.icons.includes(i)), metadata);
  const files = ['/favicon.svg','/favicon.ico','/favicon-32x32.png','/apple-touch-icon.png',
    '/brand/samescale-lockup-cobalt.svg','/brand/samescale-lockup-cobalt-on-dark.svg',
    ...['16px','24px','32px',''].flatMap(s => ['','-dark'].map(d => '/brand/samescale-symbol-' + (s ? s + '-' : '') + 'cobalt' + d + '.svg'))];
  for (const path of files) {
    const r = await p.request.get(origins.brand + path);
    add('brand asset response ' + path, r.status() === 200 && (path.endsWith('.svg') ? r.headers()['content-type'].includes('svg') : (await r.body()).length > 0));
  }
  // Exercise the official assets on both backgrounds without inventing a product dark theme.
  for (const scheme of ['light', 'dark']) {
    await p.emulateMedia({ colorScheme: scheme });
    const pixels = await p.evaluate(async ({ scheme }) => {
      const paths = ['/favicon.svg', ...[16,24,32].map(n => '/brand/samescale-symbol-' + n + 'px-cobalt' + (scheme === 'dark' ? '-dark' : '') + '.svg'), '/brand/samescale-symbol-cobalt' + (scheme === 'dark' ? '-dark' : '') + '.svg'];
      return Promise.all(paths.map(async (path, index) => {
        const i = new Image(); i.src = path; await i.decode(); const n = index === 0 ? 16 : index === 4 ? 56 : [16,24,32][index-1];
        const canvas = document.createElement('canvas'); canvas.width = canvas.height = n; const ctx = canvas.getContext('2d'); ctx.drawImage(i, 0, 0, n, n);
        const data = ctx.getImageData(0,0,n,n).data, colors = new Set();
        for (let x=0; x<data.length; x+=4) if (data[x+3] === 255) colors.add([data[x],data[x+1],data[x+2]].join(','));
        const gapColumn = ({16:7,24:11,32:15})[n];
        const gapClear = n === 56 || Array.from({length:n},(_,y) => data[(y*n+gapColumn)*4+3]).every(a => a === 0);
        return { path, size:n, colors:[...colors], gapClear };
      }));
    }, { scheme });
    for (const item of pixels) add(scheme + ' official pixel cut / master ' + item.size + ' ' + item.path, item.colors.length === 1 && item.colors[0] === (scheme === 'dark' ? '85,121,237' : '66,99,213') && item.gapClear, item);
  }
  await p.waitForLoadState('networkidle');
  add('no console, page, failed network or HTTP errors', errors.length === 0, errors);
  await context.close();
  return { base: origins, passed: checks.filter(c => c.pass).length, total: checks.length, checks, errors, requests, layouts, captures,
    source: { demoId: demo.demo_id, manifestDigest: demo.manifest_digest, provenance: demo.provenance },
    limits: ['Local isolated production previews; no product deployment', 'Dark background asset rendering only; existing product has no dark theme', 'No Safari/Firefox, physical devices, native favicon cache or Apple installation', 'No real Agent/Provider/model execution or private persistence'] };
}
