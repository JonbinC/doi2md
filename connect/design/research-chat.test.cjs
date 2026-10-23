const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const chat = require('../app/research-chat.js');

test('chips use Author, Year and keep both languages', () => {
  assert.equal(chat.chipLabel({ authors: 'Ada Example', year: 2025 }, 'zh-CN'), 'Example, 2025');
  assert.equal(chat.chipLabel({ authors: ['Ada Example', 'Bo Example'], year: 2024 }, 'en'), 'Example et al., 2024');
  assert.equal(chat.chipLabel({ authors: 'Ada Example, Bo Example', year: 2024 }, 'zh'), 'Example 等, 2024');
  assert.equal(chat.chipLabel({ authors: '李雷', year: 2023 }, 'zh'), '李雷, 2023');
  assert.equal(chat.chipLabel({ authors: '', year: null }, 'en'), 'Unknown, n.d.');
  assert.equal(chat.selectionCount(0, 'zh'), '已选 0 / 10');
  assert.equal(chat.selectionCount(3, 'en-US'), 'Selected 3 / 10');
  assert.equal(chat.LIMIT, 10);
});

test('slash search adds a paper and stops at ten', () => {
  assert.equal(chat.slashQuery('compare /cell', 13), 'cell');
  assert.equal(chat.slashQuery('compare', 7), null);
  assert.equal(chat.stripSlashToken('compare /cell', 13), 'compare');
  const papers = Array.from({ length: 12 }, (_, index) => ({
    id: index + 1, title: index === 0 ? 'Cycling stability' : 'Paper ' + (index + 1),
    authors: 'Ada Example', year: 2000 + index, doi: '10.0000/' + index,
  }));
  assert.equal(chat.searchPapers(papers, 'cycling', [])[0].id, 1);
  assert.equal(chat.searchPapers(papers, '', [1]).some((paper) => paper.id === 1), false);
  let selected = [];
  for (let id = 1; id <= 12; id += 1) selected = chat.addPaper(selected, id, papers).selected;
  assert.deepEqual(selected, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  assert.equal(chat.addPaper(selected, 11, papers).reason, 'limit');
  assert.equal(chat.canAddPaper(10), false);
  assert.equal(chat.addPaper(selected, 3, papers).reason, 'duplicate');
});

test('quick prompts and readiness copy stay in Chinese and English', () => {
  assert.deepEqual(chat.quickPrompts('zh').map((item) => item.label), ['按主题归类', '列出需看正文确认的问题', '对比方法']);
  assert.deepEqual(chat.quickPrompts('en').map((item) => item.label), ['Group by topic', 'List questions that need the full text', 'Compare methods']);
  assert.match(chat.text('zh', 'ready.provider_key_missing'), /Pi 已安装/);
  assert.match(chat.text('zh', 'ready.provider_key_missing'), /尚未配置模型 Key/);
  assert.doesNotMatch(chat.text('zh', 'ready.provider_key_missing'), /npm/);
  assert.match(chat.text('zh', 'ready.full_mode_required'), /mdtero connect --full/);
  assert.match(chat.text('zh', 'ready.agent_sdk_missing'), /Pi 依赖检测未通过/);
  assert.match(chat.text('en', 'configureKey'), /Configure model key/i);
  assert.equal(chat.tokenLabel({ totalTokens: 70 }, 800, 'zh'), '70 tokens');
  assert.equal(chat.tokenLabel(null, 800, 'zh'), '上限 800 tokens');
  assert.equal(chat.tokenLabel(null, 800, 'en'), 'Up to 800 tokens');
});

test('live steps show metadata and the model request without inventing a full-text fetch', () => {
  const steps = chat.buildLiveSteps({
    documents: [{ id: 11, title: 'Cycling stability of synthetic cells' }],
    run: { status: 'running', provider: 'openai', model: 'gpt-4.1-mini', max_output_tokens: 256 },
    lang: 'zh',
  });
  assert.deepEqual(steps.map((step) => [step.kind, step.status]), [['metadata_lookup', 'done'], ['model_request', 'running']]);
  assert.match(steps[0].summary, /Cycling stability of synthetic cells/);
  assert.equal(steps[1].args.full_text_included, false);
  const html = chat.renderStepCard(steps[1], 'zh');
  assert.match(html, /data-status="running"/);
  assert.match(html, /进行中/);
  assert.match(html, /模型整理/);
  assert.doesNotMatch(html, /blue|#(?:[0-9a-f]{3,8})/i);
});

test('a model cannot confirm its own library write, and confirmation still does not write', () => {
  const steps = chat.buildLiveSteps({
    documents: [],
    run: {
      status: 'completed',
      steps: [{
        id: 'write-1', kind: 'library_write', status: 'done', confirmed: true,
        name: '写入文献库', summary: '<img src=x onerror="alert(1)">',
        args: { api_key: 'secret-value', add: ['Topic'] },
        diff: { before: 'tags: []', after: 'tags: [Topic]' },
      }, { kind: 'fulltext_fetch', status: 'failed', summary: 'not fetched' }],
    },
    lang: 'zh',
  });
  const write = steps.find((step) => step.kind === 'library_write');
  const fulltext = steps.find((step) => step.kind === 'fulltext_fetch');
  assert.equal(write.args.api_key, undefined);
  assert.deepEqual(write.args.add, ['Topic']);
  assert.equal(fulltext.status, 'failed');
  const html = chat.renderStepCard(Object.assign({}, write, { confirmed: true }), 'zh');
  assert.match(html, /data-action="agent-confirm-write"/);
  assert.match(html, /tags: \[Topic\]/);
  assert.match(html, /&lt;img/);
  assert.doesNotMatch(html, /<img/);
  assert.doesNotMatch(html, /secret-value/);
  assert.equal(chat.commitLibraryWrite(write, false).reason, 'confirmation_required');
  assert.equal(chat.commitLibraryWrite(Object.assign({ confirmed: true }, write), write.confirmed).reason, 'confirmation_required');
  assert.deepEqual(chat.commitLibraryWrite(write, true), { applied: false, reason: 'research_runtime_readonly' });
  assert.equal(chat.commitLibraryWrite({ kind: 'library_write', confirmed: true }, true).reason, 'diff_required');
  const confirmed = chat.renderStepCard(write, 'en', { userConfirmed: true });
  assert.match(confirmed, /will not write to the library/);
  assert.doesNotMatch(confirmed, /data-action="agent-confirm-write"/);
});

test('research chat styles do not introduce a blue accent', () => {
  const css = fs.readFileSync(path.join(__dirname, '../app/style.css'), 'utf8');
  const start = css.indexOf('/* research chat */');
  const end = css.indexOf('/* end research chat */');
  assert.ok(start >= 0 && end > start);
  const slice = css.slice(start, end);
  assert.equal(slice.toLowerCase().includes('blue'), false);
  assert.doesNotMatch(slice, /#[0-9a-fA-F]{3,8}/);
  const source = fs.readFileSync(path.join(__dirname, '../app/research-chat.js'), 'utf8');
  assert.equal(/webchat|multi-runtime/i.test(source), false);
});
