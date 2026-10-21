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

async function mutation(request, path, data) {
  const session = await (await request.get('/connect/v1/session')).json();
  return request.post(`/connect/v1/${path}`, {
    headers: { Origin: ORIGIN, 'X-Mdtero-CSRF': session.csrf }, data,
  });
}

async function configureProvider(request, provider = 'openai') {
  const response = await mutation(request, 'providers/key', {
    provider, key: `synthetic-${provider}-browser-key-never-real`, storage: 'session',
  });
  expect(response.ok()).toBeTruthy();
  return response.json();
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
  await expect(page.locator('#screen')).toContainText('Pi');
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
    for (const view of ['library', 'connections', 'research', 'settings']) {
      await page.locator(`[data-view="${view}"]`).click();
      await expect(page.locator('#screen')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    }
  });
}

test('BYOK starts unconfigured and saving a key only changes local provider status', async ({ request }) => {
  const status = await (await request.get('/connect/v1/providers')).json();
  expect(status.providers.map((provider) => provider.id)).toEqual(expect.arrayContaining(['openalex', 'mineru', 'voyage', 'openai', 'anthropic']));
  expect(status.providers.every((provider) => provider.configured === false)).toBe(true);
  expect(status.storage).toMatchObject({ session: true, os: false });
  const key = 'synthetic-provider-value-for-browser-leak-check';
  const response = await mutation(request, 'providers/key', { provider: 'openai', key, storage: 'session' });
  expect(response.ok()).toBeTruthy();
  const responseText = await response.text();
  expect(responseText).not.toContain(key);
  expect(JSON.parse(responseText)).toMatchObject({ id: 'openai', configured: true, source: 'session', verification: 'not_checked' });
  const after = await (await request.get('/connect/v1/providers')).json();
  expect(after.providers.find((provider) => provider.id === 'openai')).toMatchObject({ configured: true, verification: 'not_checked' });
  expect(JSON.stringify(after)).not.toContain(key);
  expect((await snapshot(request)).calls).toEqual([]);
  expect((await snapshot(request)).provider_calls).toEqual([]);
  expect((await snapshot(request)).agent_calls).toEqual([]);
  const clear = await mutation(request, 'providers/clear', { provider: 'openai', storage: 'session' });
  expect(clear.ok()).toBeTruthy();
  expect(await clear.json()).toMatchObject({ id: 'openai', configured: false, source: 'missing' });
});

test('BYOK rejects OS persistence when the operating system credential store is unavailable', async ({ request }) => {
  const key = 'synthetic-os-persistence-must-not-fallback';
  const response = await mutation(request, 'providers/key', { provider: 'voyage', key, storage: 'os' });
  expect(response.ok()).toBe(false);
  const text = await response.text();
  expect(text).not.toContain(key);
  expect(JSON.parse(text).reason_code).toBe('os_keyring_unavailable');
  const providers = await (await request.get('/connect/v1/providers')).json();
  expect(providers.providers.find((provider) => provider.id === 'voyage').configured).toBe(false);
  expect((await snapshot(request)).calls).toEqual([]);
});

test('provider, research and Relay writes keep bridge CSRF and Origin protection', async ({ request }) => {
  for (const [path, data] of [
    ['providers/key', { provider: 'openai', key: 'synthetic-rejected-key', storage: 'session' }],
    ['providers/clear', { provider: 'openai' }],
    ['providers/check', { provider: 'openai' }],
    ['agent/prepare', { document_ids: [11], prompt: 'Summarize', provider: 'openai', model: 'gpt-4.1-mini', max_output_tokens: 256 }],
    ['agent/runs', { approval_id: 'synthetic-unapproved' }],
    ['agent/runs/synthetic-run/cancel', {}],
    ['relay/start', { allow_campus_transport: true }],
    ['relay/stop', {}],
    ['relay/restart', { allow_campus_transport: true }],
  ]) {
    const response = await request.post(`/connect/v1/${path}`, { headers: { Origin: ORIGIN }, data });
    expect(response.status(), path).toBe(403);
    expect((await response.json()).reason_code, path).toBe('csrf_rejected');
  }
  expect((await snapshot(request)).calls).toEqual([]);
});

test('BYOK form clears secrets immediately, never echoes them or persists them in browser storage', async ({ page, request }) => {
  await page.goto('/');
  await page.locator('[data-view="settings"]').click();
  await page.locator('#provider-id').selectOption('openai');
  const key = 'synthetic-ui-key-never-a-real-provider-credential';
  await page.locator('#provider-key').fill(key);
  await page.locator('#provider-storage').selectOption('session');
  const saved = page.waitForResponse((response) => response.url().endsWith('/connect/v1/providers/key'));
  await action(page, 'provider-save').click();
  expect((await saved).ok()).toBeTruthy();
  await expect(page.locator('#provider-key')).toHaveValue('');
  expect(await page.content()).not.toContain(key);
  expect(await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }))).not.toContain(key);
  expect(JSON.stringify(await (await request.get('/connect/v1/providers')).json())).not.toContain(key);
  expect(JSON.stringify(await (await request.get('/connect/v1/session')).json())).not.toContain(key);
  expect((await snapshot(request)).provider_calls).toEqual([]);
  expect((await snapshot(request)).agent_calls).toEqual([]);
  await page.locator('[data-view="start"]').click();
  await page.locator('[data-view="settings"]').click();
  await expect(page.locator('#provider-key')).toHaveValue('');
  await page.locator('[data-action="provider-clear"][data-provider="openai"]').click();
  await expect.poll(async () => (await (await request.get('/connect/v1/providers')).json()).providers.find((provider) => provider.id === 'openai').configured).toBe(false);
});

test('provider verification is explicit and an OpenAlex probe uses the isolated provider transport', async ({ request }) => {
  await configureProvider(request, 'openalex');
  expect((await snapshot(request)).provider_calls).toEqual([]);
  const response = await mutation(request, 'providers/check', { provider: 'openalex' });
  expect(response.ok()).toBeTruthy();
  expect((await response.json()).verification).not.toBe('not_checked');
  expect((await snapshot(request)).provider_calls).toEqual([{ method: 'GET', url: 'https://api.openalex.org/works/W2741809807' }]);
  for (const provider of ['mineru', 'voyage', 'openai', 'anthropic', 'google', 'openrouter']) {
    await configureProvider(request, provider);
    const checked = await mutation(request, 'providers/check', { provider });
    expect(checked.ok()).toBeTruthy();
    expect(await checked.json()).toMatchObject({ verification: 'not_checked', scope: 'configuration_only', reason_code: 'remote_check_not_available' });
  }
  expect((await snapshot(request)).provider_calls).toHaveLength(1);
  expect((await snapshot(request)).agent_calls).toEqual([]);
});

test('local OpenAlex discovery consumes the configured local key and escapes returned titles', async ({ page, request }) => {
  await configureProvider(request, 'openalex');
  await openLibrary(page);
  await page.locator('.discovery summary').click();
  await page.locator('#discovery-query').fill('synthetic battery research');
  await action(page, 'discovery-search').click();
  await expect(page.locator('.discovery-results')).toContainText('Synthetic local discovery <script>window.discoveryXss=true</script>');
  await expect(page.locator('.discovery-results script')).toHaveCount(0);
  expect(await page.evaluate(() => window.discoveryXss)).toBeUndefined();
  const state = await snapshot(request);
  expect(state.discovery_calls).toEqual([{ query: 'synthetic battery research', providers: 'openalex', enrich: 'none', key_configured: true }]);
  expect(state.calls.every((call) => call.method === 'GET')).toBe(true);
  expect(state.agent_calls).toEqual([]);
});

test('the ordinary client cannot enable Pi by posting a full-mode field', async ({ page, request }) => {
  await configureProvider(request);
  const status = await (await request.get('/connect/v1/agent/status')).json();
  expect(status).toMatchObject({ enabled: false, engine: 'pi', ready: false });
  const response = await mutation(request, 'agent/prepare', {
    full_mode: true, enabled: true, document_ids: [11], prompt: 'Summarize selected metadata',
    provider: 'openai', model: 'gpt-4.1-mini', max_output_tokens: 256,
  });
  expect(response.ok()).toBe(false);
  expect((await snapshot(request)).agent_calls).toEqual([]);
  await page.goto('/');
  await page.locator('[data-view="research"]').click();
  await expect(page.locator('#screen')).toContainText('mdtero connect --full');
});

test('the full client reports missing local AI credentials and makes no model request', async ({ page, request }) => {
  await reset(request, { full_mode: true });
  const status = await (await request.get('/connect/v1/agent/status')).json();
  expect(status).toMatchObject({ enabled: true, engine: 'pi', ready: false });
  await openLibrary(page);
  await select(page, 11);
  await page.locator('[data-view="research"]').click();
  await page.locator('#agent-prompt').fill('Summarize this metadata');
  await expect(action(page, 'agent-prepare')).toBeDisabled();
  await expect(action(page, 'agent-run')).toHaveCount(0);
  expect((await snapshot(request)).agent_calls).toEqual([]);
});

test('Pi approval freezes selected metadata and budget, refuses overrides, and is consumed once', async ({ request }) => {
  await reset(request, { full_mode: true });
  await configureProvider(request);
  const response = await mutation(request, 'agent/prepare', {
    document_ids: [11, 22], prompt: 'Compare the selected titles only',
    provider: 'openai', model: 'gpt-4.1-mini', max_output_tokens: 256,
  });
  expect(response.ok()).toBeTruthy();
  const preview = await response.json();
  expect(preview).toMatchObject({ provider: 'openai', model: 'gpt-4.1-mini', max_output_tokens: 256, scope: 'selected_metadata', model_requests: 1 });
  expect(preview.documents.map((document) => document.id)).toEqual([11, 22]);
  expect(preview.documents[0].title).toBe('Cycling stability of synthetic cells');
  for (const document of preview.documents) expect(Object.keys(document).sort()).toEqual(['authors', 'doi', 'id', 'title', 'venue', 'year']);
  expect((await snapshot(request)).agent_calls).toEqual([]);
  const override = await mutation(request, 'agent/runs', { approval_id: preview.approval_id, prompt: 'Changed after approval', max_output_tokens: 4096 });
  expect(override.ok()).toBe(false);
  expect((await snapshot(request)).agent_calls).toEqual([]);
  const started = await mutation(request, 'agent/runs', { approval_id: preview.approval_id });
  expect(started.ok()).toBeTruthy();
  const run = await started.json();
  await expect.poll(async () => (await (await request.get(`/connect/v1/agent/runs/${run.run_id}`)).json()).status).toBe('completed');
  const calls = (await snapshot(request)).agent_calls;
  expect(calls).toHaveLength(1);
  expect(calls[0].payload).toEqual({ provider: 'openai', model: 'gpt-4.1-mini', max_output_tokens: 256, documents: preview.documents, prompt: preview.prompt });
  const replay = await mutation(request, 'agent/runs', { approval_id: preview.approval_id });
  expect(replay.ok()).toBe(false);
  expect((await snapshot(request)).agent_calls).toHaveLength(1);
  expect((await snapshot(request)).calls.every((call) => call.method === 'GET')).toBe(true);
});

test('research UI invalidates edited approvals and renders model output as plain text', async ({ page, request }) => {
  await reset(request, { full_mode: true });
  await configureProvider(request);
  await openLibrary(page);
  await select(page, 11);
  await page.locator('[data-view="research"]').click();
  await page.locator('#agent-provider').selectOption('openai');
  await page.locator('#agent-model').fill('gpt-4.1-mini');
  await page.locator('#agent-max-tokens').fill('256');
  await page.locator('#agent-prompt').fill('Summarize the selected metadata');
  await action(page, 'agent-prepare').click();
  await expect(page.locator('#agent-preview')).toContainText('Cycling stability of synthetic cells');
  await expect(action(page, 'agent-run')).toBeEnabled();
  expect((await snapshot(request)).agent_calls).toEqual([]);
  await page.locator('#agent-prompt').fill('Compare selected titles');
  await expect(action(page, 'agent-run')).toHaveCount(0);
  await action(page, 'agent-prepare').click();
  await expect(action(page, 'agent-run')).toBeEnabled();
  await action(page, 'agent-run').click();
  await expect(page.locator('#agent-result')).toContainText('<img src=x onerror="window.agentXss=true">');
  await expect(page.locator('#agent-result img')).toHaveCount(0);
  expect(await page.evaluate(() => window.agentXss)).toBeUndefined();
  expect((await snapshot(request)).agent_calls).toHaveLength(1);
  expect((await snapshot(request)).calls.every((call) => call.method === 'GET')).toBe(true);
});

test('a running metadata-only research request can be cancelled from the UI', async ({ page, request }) => {
  await reset(request, { full_mode: true, agent_delay_seconds: 5 });
  await configureProvider(request);
  await openLibrary(page);
  await select(page, 11);
  await page.locator('[data-view="research"]').click();
  await page.locator('#agent-provider').selectOption('openai');
  await page.locator('#agent-model').fill('gpt-4.1-mini');
  await page.locator('#agent-max-tokens').fill('256');
  await page.locator('#agent-prompt').fill('Summarize the metadata');
  await action(page, 'agent-prepare').click();
  await expect(action(page, 'agent-run')).toBeEnabled();
  await action(page, 'agent-run').click();
  await expect(action(page, 'agent-cancel')).toBeEnabled();
  await action(page, 'agent-cancel').click();
  await expect.poll(async () => {
    const state = await snapshot(request);
    if (!state.agent_calls.length) return '';
    return (await (await request.get(`/connect/v1/agent/runs/${state.agent_calls[0].run_id}`)).json()).status;
  }).toBe('cancelled');
  await expect(page.locator('#agent-result')).not.toContainText('Synthetic metadata summary');
});

test('reloading the page recovers a running Pi request and still allows cancellation', async ({ page, request }) => {
  await reset(request, { full_mode: true, agent_delay_seconds: 5 });
  await configureProvider(request);
  await openLibrary(page);
  await select(page, 11);
  await page.locator('[data-view="research"]').click();
  await page.locator('#agent-provider').selectOption('openai');
  await page.locator('#agent-model').fill('gpt-4.1-mini');
  await page.locator('#agent-max-tokens').fill('256');
  await page.locator('#agent-prompt').fill('Summarize the selected metadata');
  await action(page, 'agent-prepare').click();
  await expect(action(page, 'agent-run')).toBeEnabled();
  await action(page, 'agent-run').click();
  await expect(action(page, 'agent-cancel')).toBeEnabled();
  const state = await snapshot(request);
  expect(state.agent_calls).toHaveLength(1);
  const runId = state.agent_calls[0].run_id;
  const active = await (await request.get('/connect/v1/agent/status')).json();
  expect(active.active_run).toMatchObject({ run_id: runId, status: 'running' });
  await page.reload();
  await page.locator('[data-view="research"]').click();
  await expect(action(page, 'agent-cancel')).toBeEnabled();
  await action(page, 'agent-cancel').click();
  await expect.poll(async () => (await (await request.get(`/connect/v1/agent/runs/${runId}`)).json()).status).toBe('cancelled');
  expect((await snapshot(request)).agent_calls).toHaveLength(1);
  await expect(page.locator('#agent-result')).not.toContainText('Synthetic metadata summary');
});

test('mobile navigation brings the research heading below the sticky navigation', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await openLibrary(page);
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  await page.locator('[data-view="research"]').click();
  await expect(page.locator('#screen')).toHaveAttribute('aria-busy', 'false');
  const heading = await page.locator('#screen h1').boundingBox();
  const navigation = await page.locator('.sidebar').boundingBox();
  expect(heading.y).toBeGreaterThanOrEqual(navigation.y + navigation.height);
  expect(heading.y + heading.height).toBeLessThanOrEqual(900);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
});

test('the basic client shows unavailable managed Relay controls without starting a transport', async ({ page, request }) => {
  await page.goto('/');
  await page.locator('[data-view="connections"]').click();
  await expect(page.locator('#relay-runtime-panel')).toContainText('This synthetic basic client has no bundled Relay runtime.');
  await expect(page.locator('#relay-consent')).toBeDisabled();
  for (const operation of ['start', 'stop', 'restart']) await expect(action(page, `relay-${operation}`)).toBeDisabled();
  const runtime = await (await request.get('/connect/v1/relay/runtime')).json();
  expect(runtime).toMatchObject({ available: false, running: false, auto_start: false, browser_enabled: false });
  expect((await snapshot(request)).relay_runtime_calls).toEqual([]);
});

test('managed Relay start and restart require explicit current-page campus transport permission', async ({ page, request }) => {
  await reset(request, { relay_runtime_available: true });
  await page.goto('/');
  await page.locator('[data-view="connections"]').click();
  await expect(page.locator('#relay-consent')).not.toBeChecked();
  await expect(action(page, 'relay-start')).toBeDisabled();
  await expect(action(page, 'relay-restart')).toBeDisabled();
  expect((await snapshot(request)).relay_runtime_calls).toEqual([]);
  await page.locator('#relay-consent').check();
  await expect(action(page, 'relay-start')).toBeEnabled();
  const start = page.waitForResponse((response) => response.url().endsWith('/connect/v1/relay/start'));
  await action(page, 'relay-start').click();
  expect((await start).request().postDataJSON()).toEqual({ allow_campus_transport: true });
  await expect(page.locator('#relay-runtime-panel')).toContainText('本客户端管理的 Relay：运行中');
  await expect(action(page, 'relay-start')).toBeDisabled();
  await expect(action(page, 'relay-stop')).toBeEnabled();
  await page.locator('#relay-consent').uncheck();
  await expect(action(page, 'relay-restart')).toBeDisabled();
  await page.locator('#relay-consent').check();
  await expect(action(page, 'relay-restart')).toBeEnabled();
  const restart = page.waitForResponse((response) => response.url().endsWith('/connect/v1/relay/restart'));
  await action(page, 'relay-restart').click();
  expect((await restart).request().postDataJSON()).toEqual({ allow_campus_transport: true });
  await expect.poll(async () => (await snapshot(request)).relay_runtime_calls).toEqual([
    { operation: 'start', allow_campus_transport: true }, { operation: 'restart', allow_campus_transport: true },
  ]);
  await expect(page.locator('#screen')).toContainText('Relay 在线 ≠ 全文可读');
});

test('refresh restores a managed Relay process while consent stays unchecked and stop remains available', async ({ page, request }) => {
  await reset(request, { relay_runtime_available: true });
  const start = await mutation(request, 'relay/start', { allow_campus_transport: true });
  expect(start.ok()).toBeTruthy();
  await page.goto('/');
  await page.locator('[data-view="connections"]').click();
  await expect(page.locator('#relay-runtime-panel')).toContainText('本客户端管理的 Relay：运行中');
  await page.locator('#relay-consent').check();
  await page.reload();
  await expect(page.locator('#relay-runtime-panel')).toContainText('本客户端管理的 Relay：运行中');
  await expect(page.locator('#relay-consent')).not.toBeChecked();
  await expect(action(page, 'relay-start')).toBeDisabled();
  await expect(action(page, 'relay-restart')).toBeDisabled();
  await expect(action(page, 'relay-stop')).toBeEnabled();
  const session = await (await request.get('/connect/v1/session')).json();
  expect(session.relay_runtime).toMatchObject({ available: true, running: true });
  expect(JSON.stringify(session.relay_runtime)).not.toContain('synthetic-browser-fixture-not-a-credential');
  const stopped = page.waitForResponse((response) => response.url().endsWith('/connect/v1/relay/stop'));
  await action(page, 'relay-stop').click();
  expect((await stopped).ok()).toBeTruthy();
  await expect(page.locator('#relay-runtime-panel')).toContainText('本客户端管理的 Relay：未运行');
  expect((await snapshot(request)).relay_runtime_calls).toEqual([
    { operation: 'start', allow_campus_transport: true }, { operation: 'stop' },
  ]);
});

test('Relay API rejects absent, false and string campus permission before reaching the process boundary', async ({ request }) => {
  await reset(request, { relay_runtime_available: true });
  for (const operation of ['start', 'restart']) {
    for (const payload of [{}, { allow_campus_transport: false }, { allow_campus_transport: 'true' }]) {
      const response = await mutation(request, `relay/${operation}`, payload);
      expect(response.ok()).toBe(false);
      expect(response.status()).toBe(400);
    }
  }
  expect((await snapshot(request)).relay_runtime_calls).toEqual([]);
  const stop = await mutation(request, 'relay/stop', {});
  expect(stop.ok()).toBeTruthy();
  expect(await stop.json()).toMatchObject({ available: true, running: false });
});

test('an available bundled Relay still requires a local Mdtero account before UI startup', async ({ page, request }) => {
  await reset(request, { authenticated: false, relay_runtime_available: true });
  await page.goto('/');
  await page.locator('[data-view="connections"]').click();
  await page.locator('#relay-consent').check();
  await expect(action(page, 'relay-start')).toBeDisabled();
  await expect(action(page, 'relay-restart')).toBeDisabled();
  expect((await snapshot(request)).relay_runtime_calls).toEqual([]);
});
