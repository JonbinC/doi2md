const { test, expect } = require('@playwright/test');
const fs = require('node:fs/promises');

const CONTROL = 'http://127.0.0.1:18742';
const ORIGIN = 'http://127.0.0.1:18741';
const action = (page, name) => page.locator(`[data-action="${name}"]`).first();
const tagCalls = (state) => state.calls.filter((call) => call.path === '/api/v1/library/tags/batch');
const paper = (state, id) => state.papers.find((item) => item.document_id === id);

async function snapshot(request) {
  const response = await request.get(`${CONTROL}/state`);
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function reset(request, settings = {}) {
  const response = await request.post(`${CONTROL}/reset`, { data: settings });
  expect(response.ok()).toBeTruthy();
}

async function openLibrary(page) {
  await page.goto('/');
  await page.locator('[data-view="library"]').click();
  await expect(page.locator('input[data-id]')).toHaveCount(3);
}

async function select(page, id) {
  await page.locator(`input[data-id="${id}"]`).check();
}

async function preview(page) {
  const result = page.waitForResponse((response) => response.url().endsWith('/connect/v1/library/tags/batch'));
  await action(page, 'tag-preview').click();
  expect((await result).ok()).toBeTruthy();
  await expect(action(page, 'tag-apply')).toBeEnabled();
}

function storedZipFiles(bytes) {
  const files = [];
  let offset = 0;
  while (bytes.readUInt32LE(offset) === 0x04034b50) {
    expect(bytes.readUInt16LE(offset + 8)).toBe(0); // deterministic, uncompressed fixture
    const length = bytes.readUInt32LE(offset + 18);
    const nameLength = bytes.readUInt16LE(offset + 26);
    const extraLength = bytes.readUInt16LE(offset + 28);
    const start = offset + 30;
    const contentStart = start + nameLength + extraLength;
    files.push({ name: bytes.subarray(start, start + nameLength).toString(), content: bytes.subarray(contentStart, contentStart + length).toString() });
    offset = contentStart + length;
  }
  return files;
}

// Product traffic always reaches the actual loopback HTTP bridge. Only the
// upstream account service and local Relay/Zotero providers are synthetic.
test.beforeEach(async ({ page, request }) => {
  await reset(request);
  page.fixtureBrowserErrors = [];
  page.on('pageerror', (error) => page.fixtureBrowserErrors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error' && /content.security.policy|refused to|\bCSP\b/i.test(message.text())) {
      page.fixtureBrowserErrors.push(message.text());
    }
  });
});

test.afterEach(async ({ page }) => {
  expect(page.fixtureBrowserErrors, 'No uncaught JavaScript or CSP errors').toEqual([]);
});

test('missing local credentials show terminal login guidance without collecting a key', async ({ page, request }) => {
  await reset(request, { authenticated: false });
  await page.goto('/');
  await expect(page.locator('[data-view="start"]')).toHaveAttribute('aria-current', 'page');
  await expect(page.locator('#screen')).toContainText('mdtero login');
  await expect(page.locator('#auth-badge')).not.toHaveText(/已连接|已认证|已核验/);
  await expect(page.locator('input[type="password"], input[name="api_key"], input[name="api-key"]')).toHaveCount(0);
  const session = await (await request.get('/connect/v1/session')).json();
  expect(session.authenticated).toBe(false);
  expect(JSON.stringify(session)).not.toContain('synthetic-browser-fixture-not-a-credential');
  expect((await snapshot(request)).calls).toEqual([]);
  await action(page, 'step-3').click();
  await action(page, 'view-library').click();
  await expect(page.locator('input[data-id]')).toHaveCount(0);
  await expect(page.locator('[data-view="library"]')).toHaveAttribute('aria-current', 'page');
});

test('configured but rejected credentials never produce a verified account', async ({ page, request }) => {
  await reset(request, { invalid_credentials: true });
  await page.goto('/');
  await expect(page.locator('#screen')).toContainText('Synthetic key rejected');
  await expect(page.locator('#auth-badge')).not.toHaveText(/已连接|已认证|已核验/);
  await page.locator('[data-view="settings"]').click();
  await expect(page.locator('#screen')).not.toContainText('文献库已核验');
  await expect(page.locator('#screen')).not.toContainText('已通过本机 API Key 认证');
});

test('three onboarding steps remain optional and lead to the working library', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#auth-badge')).toHaveText(/已核验/);
  await action(page, 'step-2').click();
  await expect(action(page, 'view-library')).toBeVisible();
  await action(page, 'step-3').click();
  await expect(page.locator('#screen')).toContainText('Agent');
  await action(page, 'view-library').click();
  await expect(page.locator('input[data-id]')).toHaveCount(3);
  await page.locator('[data-view="start"]').click();
  await action(page, 'step-1').click();
  await expect(page.locator('#screen')).toContainText('mdtero login');
});

test('tag draft survives selection, navigation and preview; only apply writes', async ({ page, request }) => {
  await openLibrary(page);
  await select(page, 11);
  await page.locator('#new-tag').fill('Research');
  await select(page, 22);
  await expect(page.locator('#new-tag')).toHaveValue('Research');
  await page.locator('[data-view="settings"]').click();
  await page.locator('[data-view="library"]').click();
  await expect(page.locator('#new-tag')).toHaveValue('Research');
  await preview(page);
  await expect(page.locator('#new-tag')).toHaveValue('Research');
  let state = await snapshot(request);
  expect(tagCalls(state).map((call) => call.body)).toEqual([
    { document_ids: [11, 22], add: ['Research'], remove: [], dry_run: true },
  ]);
  expect(paper(state, 11).tags).toEqual(['Batteries']);
  expect(paper(state, 22).tags).toEqual(['Review']);
  await action(page, 'tag-apply').click();
  await expect.poll(async () => tagCalls(await snapshot(request)).length).toBe(2);
  state = await snapshot(request);
  expect(tagCalls(state)[1].body).toEqual({ document_ids: [11, 22], add: ['Research'], remove: [], dry_run: false });
  expect(paper(state, 11).tags).toContain('Research');
  expect(paper(state, 22).tags).toContain('Research');
  await expect(action(page, 'tag-apply')).toBeDisabled();
});

test('selection, draft and filter changes invalidate old tag previews', async ({ page, request }) => {
  await openLibrary(page);
  await select(page, 11);
  await page.locator('#new-tag').fill('Research');
  await expect(action(page, 'tag-apply')).toBeDisabled();
  await preview(page);
  await select(page, 22);
  await expect(action(page, 'tag-apply')).toBeDisabled();
  await preview(page);
  await page.locator('#new-tag').fill('Changed draft');
  await expect(action(page, 'tag-apply')).toBeDisabled();
  await preview(page);
  await page.locator('[data-tag="Batteries"]').click();
  await expect(action(page, 'tag-apply')).toBeDisabled();
  expect(tagCalls(await snapshot(request)).every((call) => call.body.dry_run === true)).toBe(true);
});

test('removing the current tag also requires dry-run preview before apply', async ({ page, request }) => {
  await openLibrary(page);
  await page.locator('[data-tag="Batteries"]').click();
  await select(page, 11);
  await action(page, 'tag-remove').click();
  await expect(action(page, 'tag-apply')).toBeEnabled();
  let state = await snapshot(request);
  expect(tagCalls(state)[0].body).toEqual({ document_ids: [11], add: [], remove: ['Batteries'], dry_run: true });
  expect(paper(state, 11).tags).toEqual(['Batteries']);
  await action(page, 'tag-apply').click();
  await expect.poll(async () => paper(await snapshot(request), 11).tags).toEqual([]);
  state = await snapshot(request);
  expect(tagCalls(state)[1].body).toEqual({ document_ids: [11], add: [], remove: ['Batteries'], dry_run: false });
});

test('all four exports download upstream bytes, including application/json CSL', async ({ page, request }) => {
  await openLibrary(page);
  await select(page, 11);
  for (const format of ['bibtex', 'csl_json', 'markdown', 'markdown_zip']) {
    const [download, response] = await Promise.all([
      page.waitForEvent('download'),
      page.waitForResponse((response) => response.url().endsWith('/connect/v1/library/export')),
      action(page, `export-${format}`).click(),
    ]);
    expect(response.ok()).toBeTruthy();
    expect(await download.failure()).toBeNull();
    const bytes = await fs.readFile(await download.path());
    if (format === 'bibtex') {
      expect(download.suggestedFilename()).toBe('synthetic-references.bib');
      expect(bytes.toString()).toBe('@article{synthetic11,\n  title={Cycling stability of synthetic cells},\n}\n');
    } else if (format === 'csl_json') {
      expect(response.headers()['content-type']).toContain('application/json');
      expect(download.suggestedFilename()).toBe('synthetic-references.json');
      expect(JSON.parse(bytes.toString())).toEqual([{ id: '11', type: 'article-journal', title: 'Synthetic document 11' }]);
    } else if (format === 'markdown') {
      expect(download.suggestedFilename()).toBe('synthetic-11.md');
      expect(bytes.toString()).toBe('# Synthetic document 11\n\nText-only fixture. No images.\n');
    } else {
      expect(download.suggestedFilename()).toBe('synthetic-markdown-text-only.zip');
      expect(storedZipFiles(bytes)).toEqual([{ name: 'synthetic-11.md', content: '# Synthetic document 11\n\nText-only fixture. No images.\n' }]);
    }
    if (format.startsWith('markdown')) expect(response.headers()['x-mdtero-export']).toBe('markdown-text-only');
    await expect(action(page, `export-${format}`)).toBeEnabled();
  }
  expect((await snapshot(request)).calls.filter((call) => call.path === '/api/v1/library/export').map((call) => call.body))
    .toEqual(['bibtex', 'csl_json', 'markdown', 'markdown_zip'].map((format) => ({ document_ids: [11], format })));
});

test('search and tag filtering operate on normalized real-bridge documents', async ({ page }) => {
  await openLibrary(page);
  await page.locator('#find-paper').fill('10.0000/synthetic.22');
  await expect(page.locator('input[data-id]')).toHaveCount(1);
  await expect(page.locator('input[data-id="22"]')).toBeVisible();
  await page.locator('#find-paper').fill('');
  await page.locator('[data-tag="Batteries"]').click();
  await expect(page.locator('input[data-id]')).toHaveCount(1);
  await expect(page.locator('input[data-id="11"]')).toBeVisible();
  await page.locator('#find-paper').fill('Review');
  await expect(page.locator('input[data-id]')).toHaveCount(0);
  await expect(page.locator('#screen')).toContainText('没有匹配');
});

test('failed preview releases busy state, preserves the draft and allows retry', async ({ page, request }) => {
  await reset(request, { fail_next: '/api/v1/library/tags/batch' });
  await openLibrary(page);
  await select(page, 11);
  await page.locator('#new-tag').fill('Retry safely');
  await action(page, 'tag-preview').click();
  await expect(page.locator('#screen')).toContainText('Synthetic service unavailable');
  await expect(action(page, 'tag-preview')).toBeEnabled();
  await expect(action(page, 'tag-apply')).toBeDisabled();
  await expect(page.locator('#new-tag')).toHaveValue('Retry safely');
  await preview(page);
  await action(page, 'tag-apply').click();
  await expect.poll(async () => paper(await snapshot(request), 11).tags).toContain('Retry safely');
});

test('a lost bridge session clears prior verification and refresh recovers', async ({ page }) => {
  await openLibrary(page);
  await expect(page.locator('#auth-badge')).toHaveText(/已核验/);
  await page.route('**/connect/v1/session', (route) => route.fulfill({
    status: 503,
    contentType: 'application/json',
    body: JSON.stringify({ reason_code: 'synthetic_bridge_unavailable', action_hint: 'Synthetic bridge temporarily unavailable.' }),
  }));
  await action(page, 'refresh').click();
  await expect(page.locator('#screen')).toContainText('Synthetic bridge temporarily unavailable');
  await expect(page.locator('#auth-badge')).not.toHaveText(/已连接|已认证|已核验/);
  await expect(page.locator('input[data-id]')).toHaveCount(0);
  await expect(action(page, 'refresh')).toBeEnabled();
  await page.unroute('**/connect/v1/session');
  await action(page, 'refresh').click();
  await expect(page.locator('#auth-badge')).toHaveText(/已核验/);
  await expect(page.locator('input[data-id]')).toHaveCount(3);
});

test('bridge enforces Host, Origin and CSRF independently of browser UI', async ({ request }) => {
  const session = await (await request.get('/connect/v1/session')).json();
  expect(session.authenticated).toBe(true);
  expect(JSON.stringify(session)).not.toContain('synthetic-browser-fixture-not-a-credential');
  const payload = { document_ids: [11], add: ['Blocked'], remove: [], dry_run: false };
  const noCsrf = await request.post('/connect/v1/library/tags/batch', { headers: { Origin: ORIGIN }, data: payload });
  expect(noCsrf.status()).toBe(403);
  expect((await noCsrf.json()).reason_code).toBe('csrf_rejected');
  const badOrigin = await request.post('/connect/v1/library/tags/batch', {
    headers: { Origin: 'https://untrusted.invalid', 'X-Mdtero-CSRF': session.csrf }, data: payload,
  });
  expect(badOrigin.status()).toBe(403);
  expect((await badOrigin.json()).reason_code).toBe('origin_rejected');
  const badHost = await request.get('/connect/v1/session', { headers: { Host: 'untrusted.invalid:18741' } });
  expect(badHost.status()).toBe(403);
  expect((await badHost.json()).reason_code).toBe('host_rejected');
  const noOrigin = await request.post('/connect/v1/library/tags/batch', {
    headers: { 'X-Mdtero-CSRF': session.csrf }, data: payload,
  });
  expect(noOrigin.status()).toBe(403);
  expect((await noOrigin.json()).reason_code).toBe('origin_required');
  const noDryRun = await request.post('/connect/v1/library/tags/batch', {
    headers: { Origin: ORIGIN, 'X-Mdtero-CSRF': session.csrf }, data: { document_ids: [11], add: ['Blocked'] },
  });
  expect(noDryRun.status()).toBe(400);
  expect((await noDryRun.json()).reason_code).toBe('dry_run_required');
  expect(tagCalls(await snapshot(request))).toEqual([]);
});

test('Relay online stays distinct from browser readiness and article entitlement', async ({ page }) => {
  await page.goto('/');
  await page.locator('[data-view="connections"]').click();
  await expect(page.locator('#screen')).toContainText('传输在线');
  await expect(page.locator('#screen')).toContainText('Relay 在线 ≠ 全文可读');
  await expect(page.locator('#screen')).toContainText('本机浏览器未就绪');
  await action(page, 'relay-entitlement').click();
  await expect(page.locator('#screen')).toContainText('article_entitlement_unverified');
});

test('Zotero import preview remains metadata-only and explicitly dry-run', async ({ page, request }) => {
  await page.goto('/');
  await page.locator('[data-view="connections"]').click();
  await action(page, 'zotero-collections').click();
  await expect(page.locator('#zotero-collection option')).toContainText(['请选择集合', 'Synthetic collection']);
  await page.locator('#zotero-collection').selectOption('SYNTH001');
  await action(page, 'zotero-import-preview').click();
  await expect(page.locator('#zotero-panel')).toContainText('"dry_run": true');
  const calls = (await snapshot(request)).calls.filter((call) => call.path === '/api/v1/library/import');
  expect(calls).toHaveLength(1);
  expect(calls[0].body.dry_run).toBe(true);
  expect(calls[0].body.format).toBe('zotero_json');
  expect(calls[0].body.content).toContain('Synthetic import');
});

for (const width of [375, 1440]) {
  test(`onboarding and operational views fit a ${width}px viewport`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/');
    await expect(page.locator('#auth-badge')).toHaveText(/已核验/);
    for (const step of ['step-1', 'step-2', 'step-3']) {
      await action(page, step).click();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    }
    for (const view of ['library', 'connections', 'settings']) {
      await page.locator(`[data-view="${view}"]`).click();
      await expect(page.locator('#screen')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    }
  });
}
