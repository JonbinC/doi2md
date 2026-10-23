/* Live Connect UI. All product state comes from the same-origin bridge. */
(() => {
  "use strict";
  const api = window.MdteroConnectApi;
  const chat = window.MdteroResearchChat;
  const uiLang = () => document.documentElement.lang || "zh-CN";
  const views = ["start", "library", "fulltext", "connections", "research", "settings"];
  const state = {
    view: views.includes(location.hash.slice(1)) ? location.hash.slice(1) : "start",
    step: 1, session: null, libraryVerified: false, libraryError: "",
    papers: [], tags: [], selected: [], query: "", tag: "", tagDraft: "", tagPreview: null,
    busy: false, notice: "", error: "", relay: null, relayRuntime: null, relayConsent: false, zotero: null, agent: null,
    collections: [], collectionKey: "", zoteroDetail: "", entitlement: null,
    ftDoi: "", ftJob: null,
    providers: null, providerId: "openalex", providerStorage: "session",
    agentPrompt: "", agentProvider: "anthropic", agentModel: "", agentMaxTokens: 800,
    agentPreview: null, agentRun: null, agentPollError: "",
    agentMessages: [], agentHistory: [], agentHistoryOpen: false, agentThreadId: "",
    agentSettingsOpen: false, agentCursor: 0, agentSlashDismissed: false,
    agentExpanded: {}, agentWriteConfirmed: {}, agentUsage: null, agentSent: null,
    discoveryQuery: "", discoveryResults: null, discoveryOpen: false,
  };
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const configured = () => !!state.session?.authenticated;
  const selectedIds = () => state.selected.filter((id) => state.papers.some((p) => p.id === id));
  const b = (name, action, kind = "tool", disabled = false) =>
    '<button type="button" class="' + kind + '" data-action="' + action + '"' +
    (state.busy || disabled ? " disabled" : "") + ">" + esc(name) + "</button>";
  const status = (label, good = false) =>
    '<div class="status ' + (good ? "ok" : "") + '"><span class="dot" aria-hidden="true"></span>' + esc(label) + "</div>";
  const h = (title, desc) => '<h1>' + esc(title) + '</h1><p class="lead">' + esc(desc) + "</p>" +
    (state.error ? '<div class="notice error" role="alert">' + esc(state.error) + "</div>" : "") +
    (state.notice ? '<div class="status ok" role="status">' + esc(state.notice) + "</div>" : "") +
    (state.busy ? '<p class="hint busy" role="status">' + spinner + '正在处理，请稍候…</p>' : "");
  const accountStatus = () => state.libraryVerified ? "文献库已核验" : configured() ? "已检测到本机 Key，文献接口未核验" : "未检测到本机 API Key";
  const setupHint = '<p class="hint">点击“登录 Mdtero 账户”，在打开的浏览器页面完成登录，Connect 会自动连接。</p><details class="hint"><summary>使用命令行？</summary><p>在终端运行 <code>mdtero login</code>，然后重新运行 <code>mdtero connect</code>。</p></details>';
  const loginLink = (label = "登录 Mdtero 账户", kind = "primary") => '<a class="button ' + kind + '" href="mdtero-action:login">' + esc(label) + "</a>";
  const spinner = '<span class="spinner" aria-hidden="true"></span>';

  function gateMode() {
    if (!state.session) return state.busy || !state.error ? "boot" : "error";
    return configured() ? "app" : "login";
  }

  function gate(mode) {
    const brand = '<div class="gate-brand"><span class="brand-icon" aria-hidden="true">M</span><span class="brand-name">Mdtero<small>Connect</small></span></div>';
    if (mode === "boot") return '<div class="gate-card center">' + brand + spinner + '<h1>正在启动</h1><p class="lead">正在连接本机服务，通常只需几秒。</p></div>';
    if (mode === "error") return '<div class="gate-card center">' + brand + '<div class="gate-icon warn" aria-hidden="true">!</div><h1>暂时连接不上本机服务</h1><p class="lead">Connect 会自动重试。也可以现在手动重试；如果一直失败，请退出后重新打开 Mdtero Connect。</p>' +
      '<div class="actions center">' + b("重试", "refresh", "primary") + '</div><details class="hint"><summary>错误详情</summary><p>' + esc(state.error) + '</p></details></div>';
    return '<div class="gate-card">' + brand + '<h1>登录后开始使用</h1><p class="lead">登录 Mdtero 账户后，即可在这台电脑上整理文献库、获取全文并用 AI 继续研究。</p>' +
      '<ul class="gate-points"><li><b>文献库</b><span>筛选、标记、导出你账户里的文献</span></li><li><b>全文获取</b><span>用你自己的浏览器和机构权限打开文章</span></li><li><b>研究模式</b><span>用自己的模型账户整理选中文献</span></li></ul>' +
      '<div class="actions">' + loginLink() + b("我已登录，刷新", "refresh", "ghost") + '</div>' +
      (state.error ? '<div class="notice error" role="alert">' + esc(state.error) + '</div>' : '') +
      '<details class="hint"><summary>使用命令行？</summary><p>在终端运行 <code>mdtero login</code>，然后重新运行 <code>mdtero connect</code>。</p></details></div>';
  }
  const providerNames = { openalex: "OpenAlex · 学术检索", mineru: "MinerU · PDF 解析", voyage: "Voyage · 向量与重排", anthropic: "Anthropic · AI", openai: "OpenAI · AI", google: "Google · AI", openrouter: "OpenRouter · AI" };
  const agentActive = () => ["running", "starting", "pending"].includes(state.agentRun?.status);
  const agentLabel = () => !state.agent?.enabled ? "文献整理模式，Pi 未开启" : state.agent.ready ? "Pi 研究模式已就绪（模型凭据未远程核验）" : "完整版已开启，Pi 尚未就绪";

  function agentReadiness() {
    if (state.agent?.ready) return "";
    const lang = uiLang();
    const reason = state.agent?.reason_code || state.agent?.reason;
    const message = chat.has(lang, "ready." + reason) ? chat.text(lang, "ready." + reason) : chat.text(lang, "ready.unknown");
    const diagnostics = {};
    for (const key of ["reason_code", "node_version", "sdk_version", "probe_stage", "probe_code", "probe_os_error", "probe_exit_code"]) {
      if (state.agent?.dependencies?.[key] !== undefined) diagnostics[key] = state.agent.dependencies[key];
    }
    return '<div class="notice" id="agent-readiness"><p>' + esc(message) + '</p>' +
      (reason === "full_mode_required" ? '<details><summary>' + esc(chat.text(lang, "sourceSummary")) + '</summary><p>' + esc(chat.text(lang, "sourceBody")) + '</p></details>' : '') +
      (Object.keys(diagnostics).length && reason !== "provider_key_missing" ? '<details><summary>' + esc(chat.text(lang, "diagSummary")) + '</summary><pre class="diagnostic">' + esc(JSON.stringify(diagnostics, null, 2)) + '</pre></details>' : '') +
      '<div class="actions">' + b(chat.text(lang, "recheck"), "providers-refresh") + (reason === "provider_key_missing" ? b(chat.text(lang, "configureKey"), "view-settings") : '') + '</div></div>';
  }

  function start() {
    const labels = ["连接账户", "配置文献访问", "连接电脑与 AI"];
    const facts = [accountStatus(), "按需配置，可先用已有文献", state.session ? "本机桥接可用，扩展按需连接" : "本机桥接待核验"];
    const steps = '<nav class="steps" aria-label="三步开始使用">' + labels.map((label, i) =>
      '<button type="button" class="step ' + (state.step === i + 1 ? "active" : "") + '" data-action="step-' + (i + 1) +
      '"' + (state.step === i + 1 ? ' aria-current="step"' : "") + (state.busy ? " disabled" : "") +
      '><span class="number">' + (i === 0 && state.libraryVerified ? "✓" : i + 1) +
      '</span><span><b>' + label + '</b><small>' + esc(facts[i]) + "</small></span></button>"
    ).join("") + "</nav>";
    let content;
    if (state.step === 1) {
      content = '<article class="card onboarding"><h2>从你的账户文献库开始</h2>' + status(accountStatus(), state.libraryVerified) +
        '<p>Connect 使用本机 CLI 的账户配置。只有成功读取账户文献列表后，才会显示“文献库已核验”。</p>' + setupHint +
        (state.libraryError ? '<div class="notice">' + esc(state.libraryError) + "</div>" : "") +
        '<div class="actions">' + b("刷新账户与文献", "refresh", "primary") + b("下一步：文献访问", "step-2") + "</div></article>";
    } else if (state.step === 2) {
      content = '<article class="card onboarding"><h2>先整理已有文献，访问能力按需配置</h2>' +
        '<p>现有账户文献可以直接筛选、标记和导出。BYOK 分为 OpenAlex 检索、MinerU 解析、Voyage 检索增强和 AI 模型；出版社访问凭据单独处理。</p>' +
        '<ul class="fact-list"><li>此客户端尚未提供出版社 Key 校验或可见 CARSI 登录。</li>' +
        '<li>Relay 传输、授权浏览器和具体文章的全文权限分别核验。</li>' +
        '<li>学校密码与 Cookie 留在本机；Markdown 导出为纯文本，不含图片。</li></ul>' +
        '<div class="actions">' + b("下一步：本机连接", "step-3", "primary") + b("设置 BYOK", "view-settings") + b("先用已有文献", "view-library") + b("上一步", "step-1") + "</div></article>";
    } else {
      content = '<div class="grid"><article class="card"><h2>本机连接</h2>' +
        status(state.session ? "本机桥接可用" : "本机桥接待核验", !!state.session) +
        status(state.relay ? (state.relay.transport_online ? "Relay 传输在线" : "Relay 传输离线") : "Relay 尚未检测", !!state.relay?.transport_online) +
        status(state.zotero ? (state.zotero.available ? "Zotero connector 可达" : "未检测到本机 Zotero") : "Zotero 尚未检测", !!state.zotero?.available) +
        '<div class="actions">' + b("检测本机连接", "connections-refresh", "primary") + b("打开连接中心", "view-connections") +
        '</div><p class="hint">Zotero connector 可达仅代表端口探测成功。集合读取与导入预览需另行检查。</p></article>' +
        '<article class="card"><h2>AI 与研究模式（可选）</h2><p>完整版内置 Pi 研究运行时。普通文献整理不要求 ChatGPT 或模型 Key。</p>' +
        status(agentLabel(), !!state.agent?.ready) + '<p class="hint">研究模式只读取选中文献的元数据。</p><div class="actions">' + b("打开研究模式", "view-research") + '</div></article></div>' +
        '<div class="actions">' + b("进入文献库", "view-library", "primary") + b("上一步", "step-2") + "</div>";
    }
    return h("一处整理文献，随处继续研究。", "三步了解账户、文献访问和本机连接。可选项可以稍后再设置。") + steps + content;
  }

  function filteredPapers() {
    const q = state.query.toLowerCase();
    return state.papers.filter((p) => (!q || (p.title + " " + p.authors + " " + (p.doi || "")).toLowerCase().includes(q)) && (!state.tag || (p.tags || []).includes(state.tag)));
  }

  function library() {
    const filtered = filteredPapers();
    const selection = selectedIds();
    const validSelection = state.libraryVerified && selection.length > 0 && selection.length <= 200;
    const allTags = [...new Set([...state.tags, ...state.papers.flatMap((p) => p.tags || [])])].sort((a, b) => a.localeCompare(b));
    const list = filtered.map((p) => '<label class="listrow ' + (selection.includes(p.id) ? "selected" : "") + '">' +
      '<input type="checkbox" data-id="' + esc(p.id) + '" ' + (selection.includes(p.id) ? "checked" : "") + (state.busy ? " disabled" : "") + ">" +
      '<span><b>' + esc(p.title) + '</b><small>' + esc(p.authors || "Unknown authors") + " · " + esc(p.year || "—") + " · " + esc(p.venue) +
      '</small><small>' + esc(p.status || (p.has_saved_text ? "source ready" : "metadata")) + " · " +
      (p.tags || []).map((t) => "#" + esc(t)).join(" ") + "</small></span></label>"
    ).join("");
    const preview = state.tagPreview;
    return h("我的文献库", state.libraryVerified ? "筛选、标记和导出账户文献。批量操作仅针对当前勾选，最多 200 篇。" : "账户文献尚未核验。请先检查本机配置并刷新。") +
      (!state.libraryVerified ? setupHint + '<div class="actions">' + b("刷新账户与文献", "refresh", "primary") + b("打开三步引导", "view-start") + "</div>" : "") +
      '<div class="split"><section class="pane"><header>标签</header><div class="collection-list"><div class="chipset">' +
      '<button type="button" data-tag="" class="' + (!state.tag ? "active" : "") + '"' + (state.busy ? " disabled" : "") + '>全部</button>' +
      allTags.map((t) => '<button type="button" data-tag="' + esc(t) + '" class="' + (state.tag === t ? "active" : "") + '"' + (state.busy ? " disabled" : "") + ">" + esc(t) + "</button>").join("") +
      '</div><p class="hint">标签目录：' + allTags.length + '</p></div></section><section class="pane"><header>文献 · 可见 ' + filtered.length + " / 已加载 " + state.papers.length +
      '</header><div class="searchbox"><label class="label" for="find-paper">标题、作者或 DOI</label><input type="search" id="find-paper" placeholder="搜索文献" value="' + esc(state.query) +
      '"' + (state.busy ? " disabled" : "") + "></div>" + (list || '<p class="empty">' + (state.libraryVerified ? "没有匹配的文献。可清空搜索或选择全部标签。" : "核验成功后显示账户文献。") + "</p>") +
      '</section><section class="pane"><header>条目与操作</header><div class="details"><p class="hint">已选 ' + selection.length + ' 篇（当前勾选）。批量上限 200。</p>' +
      (selection.length > 200 ? '<div class="notice">请减少勾选至 200 篇以内。</div>' : "") +
      '<label class="label" for="new-tag">为选中条目添加标签</label><input id="new-tag" type="text" maxlength="80" placeholder="例如 Cycling stability" value="' + esc(state.tagDraft) + '"' + (state.busy ? " disabled" : "") + ">" +
      '<div class="actions">' + b("预览标签变更", "tag-preview", "primary", !validSelection) + b("移除当前筛选标签（预览）", "tag-remove", "tool", !validSelection || !state.tag) + "</div>" +
      (preview ? '<div class="notice" id="tag-preview-result"><strong>待确认的标签变更</strong><p>' + esc(preview.payload.add.length ? "添加：" + preview.payload.add.join(", ") : "移除：" + preview.payload.remove.join(", ")) +
        " · " + preview.payload.document_ids.length + " 篇已选；预计变更 " + esc(preview.result.changed_count ?? "由服务端决定") +
        " 篇。dry_run=true，未写入。</p></div>" : '<p class="hint">先预览变更，再应用。修改标签、选区或标签筛选后需重新预览。</p>') +
      '<div class="actions">' + b("应用标签", "tag-apply", "tool", !preview || !validSelection) + "</div>" +
      '<div class="label">导出选中文献</div><div class="actions">' + b("BibTeX", "export-bibtex", "primary", !validSelection) + b("CSL JSON", "export-csl_json", "tool", !validSelection) +
      b("Markdown ZIP（纯文本）", "export-markdown_zip", "tool", !validSelection) + b("单篇 Markdown", "export-markdown", "tool", !validSelection || selection.length !== 1) +
      '</div><div class="actions">' + b("用选中文献研究", "view-research", "tool", !validSelection) + '</div><p class="hint">先勾选文献才能操作。Markdown ≤2 MiB/篇，批量内联 ≤4 MiB；导出不含图片，不能作为完整离线包。</p></div></section></div>' + discovery();
  }

  function connectionCards() {
    const relay = state.relay;
    const runtime = state.relayRuntime || state.session?.relay_runtime;
    const zotero = state.zotero;
    return '<div class="grid"><article class="card"><h2>校园 Relay</h2>' +
      '<div id="relay-runtime-panel">' + status(runtime?.running ? "本客户端管理的 Relay：运行中" : "本客户端管理的 Relay：未运行", !!runtime?.running) +
      '<p class="hint">' + esc(runtime?.action_hint || "桌面版内置 Relay；命令行模式仅提供诊断。") + '</p>' +
      '<label class="hint"><input id="relay-consent" type="checkbox"' + (state.relayConsent ? " checked" : "") + (state.busy || !runtime?.available ? " disabled" : "") + '> 允许通过这台电脑的网络出口传输 Mdtero 文献请求</label>' +
      '<div class="actions">' + b("启动本机 Relay", "relay-start", "primary", !runtime?.available || !!runtime?.running || !state.relayConsent || !configured()) +
      b("停止本机 Relay", "relay-stop", "tool", !runtime?.running) + b("重启本机 Relay", "relay-restart", "tool", !runtime?.available || !runtime?.running || !state.relayConsent || !configured()) + '</div>' +
      '<p class="hint">只管理此客户端启动的进程，关闭客户端时停止；不安装后台服务，账户已有 Relay 在线时不会再启动。此模式不启动机构浏览器；进程运行不代表云端在线或全文可读。</p></div>' +
      status(relay ? (relay.transport_online ? "Relay 传输在线" : "Relay 传输离线") : "Relay 尚未检测", !!relay?.transport_online) +
      status(relay ? (relay.browser_ready ? "本机授权浏览器就绪" : "本机浏览器未就绪") : "浏览器状态尚未检测", !!relay?.browser_ready) +
      '<p class="hint">' + esc(relay?.cloud_status?.action_hint || relay?.notes?.[0] || "传输在线不代表全文可读。") + "</p>" +
      '<div class="actions">' + b("刷新诊断", "relay-refresh", "primary") + b("运行 entitlement 诊断", "relay-entitlement", "tool", !state.libraryVerified) + "</div>" +
      '<p class="hint">使用后端诊断样本，confirm_fulltext=false。此操作不核验当前选中文献，也不执行完整全文确认。</p>' +
      (state.entitlement ? '<details open><summary>本次诊断结果</summary><pre class="diagnostic">' + esc(JSON.stringify(state.entitlement, null, 2)) + "</pre></details>" : "") +
      '</article><article class="card"><h2>Zotero 书目预览</h2>' + status(zotero ? (zotero.available ? "本机 connector 可达" : "未检测到本机 Zotero") : "Zotero 尚未检测", !!zotero?.available) +
      '<p class="hint">仅连接 127.0.0.1:23119。请选择集合后预览 metadata-only 导入；当前 UI 不应用导入。</p>' +
      '<div class="actions">' + b("检测 Zotero", "zotero-status", "primary") + b("列出集合", "zotero-collections") + "</div>" +
      '<label class="label" for="zotero-collection">预览集合</label><select id="zotero-collection"' + (state.busy ? " disabled" : "") + '><option value="">请选择集合</option>' +
      state.collections.map((c) => '<option value="' + esc(c.key) + '"' + (state.collectionKey === c.key ? " selected" : "") + ">" + esc(c.name || c.key) + "</option>").join("") + "</select>" +
      '<div class="actions">' + b("预览导入（dry-run）", "zotero-import-preview", "tool", !state.collectionKey || !state.libraryVerified) + "</div>" +
      '<pre class="diagnostic" id="zotero-panel">' + esc(state.zoteroDetail) + '</pre><p class="hint">需要账户文献核验成功才能请求导入预览。最多读取首批 50 条；分页、去重检查点和删除同步仍待实现。</p></article></div>';
  }

  const FT_LABELS = {
    fulltext: "已获取全文（本机解析）",
    paywall: "页面没有全文：可能是付费墙或仅摘要。未做任何绕过。",
    challenge: "出版社要求人机验证：请在弹出的 Chrome 窗口里自己点击完成，然后重试。Connect 不会自动处理验证。",
    error: "获取失败",
  };

  function fulltext() {
    const job = state.ftJob;
    const r = job?.result;
    let out = "";
    if (job && job.state === "running") out = status("正在用你的 Chrome 打开文章…如出现验证页，请在窗口里自己完成。");
    else if (job && job.state === "error") out = '<div class="notice error" role="alert">' + esc(job.error || "获取失败") + "</div>";
    else if (r) {
      const s = r.signals || {};
      out = status(FT_LABELS[r.status] || r.status, r.status === "fulltext") +
        '<ul class="fact-list"><li>正文字符：' + esc(s.body_length ?? "-") + "；章节：" + esc(s.section_count ?? "-") + "；参考文献：" + esc(s.reference_count ?? "-") + "</li>" +
        (s.companion_tables_merged != null ? "<li>表格页合并：" + esc(s.companion_tables_merged) + "，未匹配：" + esc(Array.isArray(s.companion_tables_unmatched) ? s.companion_tables_unmatched.join(", ") || "无" : (s.companion_tables_unmatched ?? 0)) + "（正文已含完整表格时未匹配属正常）</li>" : "") +
        (r.markdown_path ? "<li>Markdown：<code>" + esc(r.markdown_path) + "</code></li>" : "") +
        (r.raw_path ? "<li>原始 HTML（仅存本机）：<code>" + esc(r.raw_path) + "</code></li>" : "") +
        (r.detail ? "<li>" + esc(r.detail) + "</li>" : "") + "</ul>";
    }
    return h("全文获取", "在你自己的 Chrome 里打开订阅文章，原始页面只存本机，并用本机解析器转换为 Markdown，不上传任何服务器。") +
      '<article class="card"><label class="label" for="ft-doi">DOI</label><input id="ft-doi" value="' + esc(state.ftDoi) + '" placeholder="10.1007/…"' + (state.busy ? " disabled" : "") + ">" +
      '<div class="actions">' + b("获取全文", "ft-fetch", "primary", !state.ftDoi.trim() || job?.state === "running") + "</div>" + out +
      '<p class="hint">遇到验证页时由你本人点击完成；付费墙会如实报告，不会绕过。</p></article>';
  }

  async function pollFulltext(id) {
    while (state.ftJob && state.ftJob.id === id && state.ftJob.state === "running") {
      await new Promise((res) => setTimeout(res, 2000));
      try { state.ftJob = await api.fulltextJob(id); } catch (err) { state.ftJob = { id, state: "error", error: err.message }; }
      if (state.view === "fulltext") draw();
    }
  }

  function connections() {
    return h("连接状态，分开核验", "Relay 在线 ≠ 全文可读。学校密码与 Cookie 留在本机；CARSI 可见登录全流程尚未接入。") + connectionCards();
  }

  function discovery() {
    const data = state.discoveryResults;
    const items = data?.items || data?.results || [];
    return '<details class="card discovery"' + (state.discoveryResults || state.discoveryOpen ? ' open' : '') + '><summary>用 OpenAlex 找文献</summary><p class="hint">直接从本机访问 OpenAlex，使用设置里的 OpenAlex Key。搜索会计入该服务的用量；失败时不切换云端检索。</p>' +
      '<label class="label" for="discovery-query">检索主题</label><input id="discovery-query" type="text" maxlength="500" value="' + esc(state.discoveryQuery) + '"' + (state.busy ? " disabled" : "") + '>' +
      '<div class="actions">' + b("本机检索 OpenAlex", "discovery-search", "primary") + b("配置 OpenAlex Key", "view-settings") + '</div>' +
      (data ? '<p class="hint">已返回 ' + items.length + ' 条元数据；这些结果尚未加入账户文献库。</p><ul class="discovery-results">' + items.map((p) => '<li><strong>' + esc(p.title) + '</strong><p class="hint">' + esc(p.year) + ' · ' + esc(Array.isArray(p.authors) ? p.authors.join(", ") : p.authors || "") +
        (p.doi ? ' · DOI ' + esc(p.doi) : '') + '</p></li>').join("") + '</ul>' : '') + '</details>';
  }

  function providerSettings() {
    const rows = state.providers?.providers || [];
    const verification = { not_checked: "未远程校验", verified: "已通过 OpenAlex 单条查询校验", failed: "校验失败", configuration_only: "仅配置检查", unsupported: "无免费校验接口" };
    const sources = { session: "仅此次运行", os: "系统凭据库", environment: "环境变量", legacy_config: "旧 CLI 配置", missing: "未配置" };
    const rowButton = (name, action, row, disabled = false) => '<button type="button" class="tool" data-action="' + action + '" data-provider="' + esc(row.id) + '" data-storage="' + (row.source === "os" ? "os" : "session") + '"' + (state.busy || disabled ? " disabled" : "") + '>' + name + '</button>';
    return '<section class="card provider-settings"><h2>BYOK 服务凭据</h2><p>OpenAlex 用于本机学术检索，MinerU 用于 PDF 解析，Voyage 用于向量与重排，AI Key 用于完整版 Pi。各服务的 Key 分开保管。</p>' +
      '<div class="notice">当前 MinerU、Voyage 只支持本机凭据管理；云解析、云 RAG 仍使用服务端配置，不会自动消费这里保存的 Key。</div>' +
      '<div class="provider-list">' + rows.map((row) => '<div class="provider-row"><div><strong>' + esc(providerNames[row.id] || row.name) + '</strong><p class="hint">' +
        esc(row.configured ? "已配置 · " + (sources[row.source] || row.source) : "未配置") + ' · ' + esc(verification[row.verification] || row.verification) + '</p><p class="hint">' + esc(row.capability === "credential_only" ? "仅本机凭据管理；云端任务尚未消费此 Key" : row.capability === "pi" ? "用于完整版 Pi；调用前另行确认" : "用于本机 OpenAlex 检索") + '</p></div><div class="actions">' +
        rowButton(row.id === "openalex" ? "校验 OpenAlex" : "检查配置", "provider-check", row, !row.configured) +
        rowButton("清除保存的 Key", "provider-clear", row, !["session", "os"].includes(row.source)) + '</div></div>').join("") + '</div>' +
      (!state.providers ? '<p class="hint">服务配置尚未读取，请刷新设置。</p>' : '') +
      '<div class="provider-form"><div><label class="label" for="provider-id">服务</label><select id="provider-id"' + (state.busy ? " disabled" : "") + '>' + Object.entries(providerNames).map(([id, name]) => '<option value="' + id + '"' + (state.providerId === id ? " selected" : "") + '>' + name + '</option>').join("") + '</select></div>' +
      '<div><label class="label" for="provider-storage">保管方式</label><select id="provider-storage"' + (state.busy ? " disabled" : "") + '><option value="session"' + (state.providerStorage === "session" ? " selected" : "") + '>仅此次运行，关闭桥后清除</option><option value="os"' + (state.providerStorage === "os" ? " selected" : "") + (!state.providers?.storage?.os ? " disabled" : "") + '>系统凭据库</option></select></div>' +
      '<div class="provider-key-field"><label class="label" for="provider-key">新的服务 API Key</label><input id="provider-key" type="password" autocomplete="new-password" spellcheck="false" maxlength="8192"' + (state.busy ? " disabled" : "") + '><p class="hint">仅写入本机桥。提交后清空输入，不回显保存值，也不写入浏览器存储。</p></div></div>' +
      '<p class="hint">' + (state.providers?.storage?.os ? "系统凭据库可用。" : "此设备的系统凭据库不可用；可使用仅此次运行模式，不会自动回退到明文文件。") + ' 环境变量与旧 CLI 配置需在原处修改。保存 Key 不会自动请求服务。</p>' +
      '<div class="actions">' + b("保存服务 Key", "provider-save", "primary", !state.providers) + b("刷新设置", "providers-refresh") + '</div></section>';
  }

  function selectedPapers() {
    return selectedIds().map((id) => state.papers.find((paper) => paper.id === id)).filter(Boolean);
  }

  function paperChipHtml(papers, removable, lang) {
    return papers.map((paper) => {
      const label = chat.chipLabel(paper, lang);
      const remove = removable ? '<button type="button" data-action="agent-remove-paper" data-id="' + esc(paper.id) + '" aria-label="' + esc(chat.text(lang, "removeChip", { label })) + '">×</button>' : "";
      return '<span class="paper-chip' + (removable ? "" : " static") + '" data-id="' + esc(paper.id) + '" title="' + esc(paper.title) + '">' + esc(label) + remove + "</span>";
    }).join("");
  }

  function researchStepsHtml(steps, lang, prefix) {
    return steps.map((step) => {
      const id = prefix + step.id;
      return chat.renderStepCard(Object.assign({}, step, { id }), lang, {
        open: !!state.agentExpanded[id],
        userConfirmed: !!state.agentWriteConfirmed[id],
      });
    }).join("");
  }

  function researchTranscript(lang) {
    if (!state.agentMessages.length) {
      if (state.agentPreview || agentActive()) return "";
      const prompts = chat.quickPrompts(lang).map((item) => '<button type="button" data-action="agent-quick" data-quick="' + esc(item.id) + '" data-prompt="' + esc(item.prompt) + '">' + esc(item.label) + "</button>").join("");
      return '<div class="research-empty"><p>' + esc(chat.text(lang, "emptyLead")) + '</p><div class="quick-prompts">' + prompts + "</div></div>";
    }
    const latestId = state.agentMessages.reduce((found, item) => item.runId || found, "");
    return state.agentMessages.map((message) => {
      const run = message.run ? Object.assign({}, message.run, {
        provider: message.run.provider || message.provider,
        model: message.run.model || message.model,
        max_output_tokens: message.run.max_output_tokens || message.maxOutputTokens,
      }) : null;
      const steps = chat.buildLiveSteps({ documents: message.documents || [], run, lang });
      const text = run?.text || run?.error?.action_hint || run?.error?.hint || run?.error?.message || run?.error?.reason_code || (typeof run?.error === "string" ? run.error : "");
      const resultId = message.runId && message.runId === latestId ? ' id="agent-result"' : "";
      const cancel = agentActive() && state.agentRun?.run_id === message.runId ? '<div class="actions">' + b(chat.text(lang, "cancelRun"), "agent-cancel") + "</div>" : "";
      const poll = state.agentPollError && state.agentRun?.run_id === message.runId ? '<div class="notice">' + esc(chat.text(lang, "pollError")) + '<div class="actions">' + b(chat.text(lang, "refreshRun"), "agent-run-refresh") + "</div></div>" : "";
      return '<article class="chat-message user"><p>' + esc(message.prompt) + '</p><div class="composer-chips">' + (message.chips || []).map((label) => '<span class="paper-chip static">' + esc(label) + "</span>").join("") + "</div></article>" +
        '<article class="chat-message assistant">' + researchStepsHtml(steps, lang, message.runId + ":") + poll +
        '<pre class="agent-result"' + resultId + ">" + esc(text) + "</pre>" + cancel + "</article>";
    }).join("");
  }

  function confirmationCard(lang) {
    const preview = state.agentPreview;
    if (!preview) return "";
    const documents = preview.documents || [];
    const steps = chat.buildLiveSteps({ documents, run: null, lang });
    const titles = documents.map((doc) => doc.title).filter(Boolean);
    return '<section class="card confirm-card" id="agent-preview"><h2>' + esc(chat.text(lang, "confirmTitle")) + "</h2><p>" + esc(preview.provider) + " / " + esc(preview.model) + '</p><p class="hint">' +
      esc(chat.text(lang, "confirmScope", { n: preview.document_count ?? documents.length, bytes: preview.input_bytes ?? 0, tokens: preview.max_output_tokens ?? state.agentMaxTokens })) + "</p>" +
      (titles.length ? '<ul class="confirm-titles">' + titles.map((title) => "<li>" + esc(title) + "</li>").join("") + "</ul>" : "") +
      "<p>" + esc(preview.prompt) + "</p>" + researchStepsHtml(steps, lang, "preview:") +
      "<details><summary>" + esc(chat.text(lang, "confirmMetadata")) + '</summary><pre class="diagnostic">' + esc(JSON.stringify(documents, null, 2)) + "</pre></details>" +
      '<p class="hint">' + esc(chat.text(lang, "confirmCaveat")) + '</p><div class="actions">' + b(chat.text(lang, "confirmSend"), "agent-run", "primary", agentActive()) + "</div></section>";
  }

  function slashMenu(lang, papers) {
    const query = chat.slashQuery(state.agentPrompt, state.agentCursor);
    if (query === null || state.agentSlashDismissed) return "";
    if (!chat.canAddPaper(papers.length)) return '<div id="agent-slash" class="slash-menu" role="listbox"><p class="hint">' + esc(chat.text(lang, "slashLimit")) + "</p></div>";
    const matches = chat.searchPapers(state.papers, query, papers.map((paper) => paper.id));
    if (!matches.length) return '<div id="agent-slash" class="slash-menu" role="listbox"><p class="hint">' + esc(chat.text(lang, "slashEmpty")) + "</p></div>";
    return '<div id="agent-slash" class="slash-menu" role="listbox">' + matches.map((paper) => '<button type="button" data-action="agent-add-paper" data-id="' + esc(paper.id) + '"><b>' + esc(chat.chipLabel(paper, lang)) + "</b><small>" + esc(paper.title) + "</small></button>").join("") + "</div>";
  }

  function historyDrawer(lang) {
    if (!state.agentHistoryOpen) return "";
    const items = state.agentHistory.length ? state.agentHistory.map((item) => '<button type="button" class="history-item" data-action="agent-history-restore" data-thread="' + esc(item.id) + '"><b>' + esc(item.title) + "</b></button>").join("") : '<p class="empty">' + esc(chat.text(lang, "historyEmpty")) + "</p>";
    return '<button type="button" class="history-backdrop" data-action="agent-history-close" aria-label="' + esc(chat.text(lang, "close")) + '"></button><aside id="agent-history" class="history-drawer" role="dialog" aria-label="' + esc(chat.text(lang, "history")) + '"><header><h2>' + esc(chat.text(lang, "history")) + "</h2>" + b(chat.text(lang, "close"), "agent-history-close", "ghost") + "</header>" + items + "</aside>";
  }

  function research() {
    const lang = uiLang();
    const active = agentActive();
    const papers = selectedPapers();
    const locked = state.busy || active;
    const models = state.agent?.models?.[state.agentProvider] || [];
    const providerIds = ["anthropic", "openai", "google", "openrouter"];
    const modelSummary = state.agentModel.trim() || chat.text(lang, "chooseModel");
    const providerShort = { anthropic: "Anthropic", openai: "OpenAI", google: "Google", openrouter: "OpenRouter" };
    const sendLocked = !state.agent?.ready || active || papers.length < 1 || papers.length > chat.LIMIT || !state.agentPrompt.trim();
    const readyText = !state.agent?.enabled ? chat.text(lang, "statusOff") : state.agent.ready ? chat.text(lang, "statusReady") : chat.text(lang, "statusNotReady");
    const notices = (state.error ? '<div class="notice error" role="alert">' + esc(state.error) + "</div>" : "") +
      (state.notice ? '<div class="status ok" role="status">' + esc(state.notice) + "</div>" : "") +
      (state.busy ? '<p class="hint busy" role="status">' + spinner + "正在处理，请稍候…</p>" : "");
    return notices + '<div class="research-chat"><header class="research-toolbar"><div><h1>' + esc(chat.text(lang, "pageTitle")) + '</h1><p class="hint">' + esc(chat.text(lang, "pageHint")) + '</p></div><div class="research-toolbar-actions">' +
      b(chat.text(lang, "newChat"), "agent-new", "ghost", active) + b(chat.text(lang, "history"), "agent-history", "ghost") + "</div></header>" +
      '<div class="research-stream">' + agentReadiness() + researchTranscript(lang) + "</div>" + confirmationCard(lang) +
      '<div class="research-composer"><div class="composer-card"><div class="composer-chips">' + paperChipHtml(papers, true, lang) +
      '<span id="agent-selection-count" class="chip-count' + (papers.length > chat.LIMIT ? " warn" : "") + '">' + esc(chat.selectionCount(papers.length, lang)) + "</span></div>" +
      (papers.length > chat.LIMIT ? '<p class="hint">' + esc(chat.text(lang, "overLimit")) + "</p>" : "") +
      '<label class="visually-hidden" for="agent-prompt">' + esc(chat.text(lang, "promptLabel")) + '</label><textarea id="agent-prompt" rows="3" maxlength="4000" placeholder="' + esc(chat.text(lang, "placeholder")) + '"' + (locked ? " disabled" : "") + ">" + esc(state.agentPrompt) + "</textarea>" +
      slashMenu(lang, papers) + '<div class="composer-tools"><button type="button" class="tool composer-settings" data-action="agent-settings-toggle" aria-expanded="' + (state.agentSettingsOpen ? "true" : "false") + '" aria-controls="agent-settings"' + (state.busy ? " disabled" : "") + ">" + esc(providerShort[state.agentProvider] || state.agentProvider) + " · " + esc(modelSummary) + " · " + esc(state.agentMaxTokens) + "</button>" +
      b(chat.text(lang, "send"), "agent-prepare", "primary", sendLocked) + "</div>" +
      '<div id="agent-settings" class="settings-popover' + (state.agentSettingsOpen ? " open" : "") + '"><div class="research-settings"><div><label class="label" for="agent-provider">' + esc(chat.text(lang, "providerLabel")) + '</label><select id="agent-provider"' + (locked ? " disabled" : "") + ">" + providerIds.map((id) => '<option value="' + id + '"' + (id === state.agentProvider ? " selected" : "") + ">" + esc(chat.text(lang, "provider." + id)) + "</option>").join("") + '</select></div><div><label class="label" for="agent-model">' + esc(chat.text(lang, "modelLabel")) + '</label><input id="agent-model" type="text" list="agent-models" maxlength="200" value="' + esc(state.agentModel) + '"' + (locked ? " disabled" : "") + '><datalist id="agent-models">' + models.map((model) => '<option value="' + esc(model.id) + '">' + esc(model.name) + "</option>").join("") + '</datalist></div><div><label class="label" for="agent-max-tokens">' + esc(chat.text(lang, "tokensLabel")) + '</label><input id="agent-max-tokens" type="number" min="128" max="4096" value="' + esc(state.agentMaxTokens) + '"' + (locked ? " disabled" : "") + "></div></div>" +
      '<div class="actions">' + b(chat.text(lang, "configureKey"), "view-settings") + "</div></div></div>" +
      '<div class="composer-status">' + status(readyText, !!state.agent?.ready) + '<span id="agent-token-count">' + esc(chat.tokenLabel(state.agentUsage, state.agentMaxTokens, lang)) + "</span></div></div></div>" + historyDrawer(lang);
  }

  function settings() {
    return h("设置", "账户、BYOK 服务与可选研究模式。") + '<div class="grid"><section class="card"><h2>账户</h2>' + status(accountStatus(), state.libraryVerified) +
      '<p>API：' + esc(state.session?.api_base_url || "尚未连接") + '</p><p>凭据来源：' + esc(state.session?.auth_source || "无") + "</p>" + setupHint +
      '<div class="actions">' + b("打开三步引导", "view-start") + '</div></section><section class="card"><h2>研究模式 / Agent（可选）</h2>' +
      status(agentLabel(), !!state.agent?.ready) + '<p>完整版包含 Pi 运行时，通过 <code>mdtero connect --full</code> 显式开启。初版支持选中文献元数据上的一次只读研究。</p><div class="actions">' + b("打开研究模式", "view-research") +
      '</div></section></div>' + providerSettings();
  }

  function draw() {
    const activeId = document.activeElement && document.activeElement.id;
    const activeField = activeId ? document.getElementById(activeId) : null;
    const selection = activeField && typeof activeField.selectionStart === "number" ? [activeField.selectionStart, activeField.selectionEnd] : null;
    const streamScroll = document.querySelector(".research-stream")?.scrollTop || 0;
    document.querySelectorAll("[data-view]").forEach((el) => {
      const active = el.dataset.view === state.view;
      el.classList.toggle("active", active);
      el.setAttribute("aria-current", active ? "page" : "false");
      el.disabled = state.busy;
    });
    $("current-account").textContent = accountStatus();
    $("auth-badge").textContent = state.libraryVerified ? "已核验" : configured() ? "待核验" : "未配置";
    $("auth-detail").textContent = state.session ? "本机桥接可用" : "等待本机桥接";
    const mode = gateMode();
    document.body.dataset.mode = mode;
    $("gate").innerHTML = mode === "app" ? "" : gate(mode);
    const navButton = document.querySelector('[data-view="' + state.view + '"]');
    $("breadcrumb").textContent = navButton ? navButton.textContent.trim() : "Mdtero Connect";
    $("screen").setAttribute("aria-busy", String(state.busy));
    $("screen").classList.toggle("research-mode", state.view === "research");
    document.body.dataset.research = state.view === "research" ? "true" : "false";
    $("screen").innerHTML = ({ start, library, fulltext, connections, research, settings }[state.view])();
    document.querySelectorAll('[data-action="refresh"]').forEach((el) => { el.disabled = state.busy; });
    const stream = document.querySelector(".research-stream");
    if (stream) stream.scrollTop = streamScroll;
    if (["agent-prompt", "agent-model"].includes(activeId)) {
      const next = document.getElementById(activeId);
      if (next) {
        next.focus({ preventScroll: true });
        if (selection && next.setSelectionRange) next.setSelectionRange(selection[0], selection[1]);
      }
    }
  }

  async function withBusy(fn) {
    if (state.busy) return;
    state.busy = true;
    state.error = "";
    state.notice = "";
    draw();
    try { await fn(); }
    catch (err) {
      state.error = err.message || String(err);
      if (err.status === 401 || err.status === 403) {
        state.libraryVerified = false;
        state.tagPreview = null;
      }
    } finally { state.busy = false; draw(); }
  }

  async function loadLibrary() {
    state.libraryVerified = false;
    state.libraryError = "";
    state.tagPreview = null;
    state.agentPreview = null;
    // Clear data before a refresh so failed credentials never leave a stale library.
    state.papers = [];
    state.tags = [];
    if (!configured()) { state.selected = []; return; }
    try {
      const docs = await api.listDocuments();
      state.papers = docs.items || [];
      state.selected = selectedIds();
      state.libraryVerified = true;
    } catch (err) {
      state.libraryError = "文献接口核验失败：" + (err.message || String(err)) + "。请检查本机配置或网络后重试。";
      throw new Error(state.libraryError);
    }
    try {
      const tags = await api.listTags();
      state.tags = (tags.items || tags.tags || []).map((row) => typeof row === "string" ? row : row.name || row.tag).filter(Boolean);
    } catch (err) {
      state.error = "文献列表已加载，但标签目录读取失败：" + err.message + "。可刷新重试。";
    }
  }

  async function refreshAll() {
    await withBusy(async () => {
      state.libraryVerified = false;
      state.session = null;
      state.papers = [];
      state.tags = [];
      state.tagPreview = null;
      state.session = await api.session();
      state.agent = state.session.agent || null;
      recoverActiveRun();
      await loadLibrary();
    });
  }

  async function refreshConnections() {
    await withBusy(async () => {
      state.relay = null;
      state.zotero = null;
      state.entitlement = null;
      const results = await Promise.allSettled([api.relayDiagnostics(), api.zoteroStatus(), api.relayRuntime()]);
      if (results[0].status === "fulfilled") state.relay = results[0].value;
      if (results[1].status === "fulfilled") state.zotero = results[1].value;
      if (results[2].status === "fulfilled") state.relayRuntime = results[2].value;
      const errors = results.filter((r) => r.status === "rejected").map((r) => r.reason.message);
      if (errors.length) throw new Error("部分连接未能核验：" + errors.join("；"));
    });
  }

  function navigate(view) {
    if (!views.includes(view) || state.busy) return;
    state.view = view;
    history.replaceState(null, "", "#" + view);
    state.error = "";
    state.notice = "";
    state.agentHistoryOpen = false;
    state.agentSettingsOpen = false;
    draw();
    $("screen").focus({ preventScroll: true });
    window.scrollTo(0, 0);
    if (view === "connections") refreshConnections();
    if (["settings", "research"].includes(view)) withBusy(loadResearchSettings);
  }

  async function loadResearchSettings() {
    const results = await Promise.allSettled([api.agentStatus(), api.providerStatus()]);
    if (results[0].status === "fulfilled") state.agent = results[0].value;
    recoverActiveRun();
    if (results[1].status === "fulfilled") state.providers = results[1].value;
    const errors = results.filter((r) => r.status === "rejected").map((r) => r.reason.message);
    if (errors.length) throw new Error("部分设置未能读取：" + errors.join("；"));
  }

  let agentPollTimer;
  function syncRunMessage() {
    const run = state.agentRun;
    if (!run?.run_id) return;
    if (!state.agentThreadId) state.agentThreadId = "t" + Date.now().toString(36);
    const sent = state.agentSent || {};
    const existing = state.agentMessages.find((item) => item.runId === run.run_id);
    const entry = {
      runId: run.run_id,
      prompt: existing?.prompt || sent.prompt || "",
      documents: existing?.documents || sent.documents || [],
      chips: existing?.chips || sent.chips || [],
      provider: existing?.provider || sent.provider || run.provider || "",
      model: existing?.model || sent.model || run.model || "",
      maxOutputTokens: existing?.maxOutputTokens || sent.maxOutputTokens || run.max_output_tokens || state.agentMaxTokens,
      run,
    };
    if (existing) Object.assign(existing, entry);
    else state.agentMessages.push(entry);
    if (run.usage && typeof run.usage === "object") state.agentUsage = run.usage;
  }
  function archiveResearchThread() {
    if (!state.agentMessages.length || !state.agentThreadId) return;
    if (state.agentHistory.some((item) => item.id === state.agentThreadId)) return;
    state.agentHistory.unshift({
      id: state.agentThreadId,
      title: chat.threadTitle(state.agentMessages[0].prompt || "", uiLang()),
      messages: JSON.parse(JSON.stringify(state.agentMessages)),
      usage: state.agentUsage,
    });
    if (state.agentHistory.length > 20) state.agentHistory.length = 20;
  }
  function recoverActiveRun() {
    const active = state.agent?.active_run;
    if (active?.run_id && active.run_id !== state.agentRun?.run_id) {
      state.agentRun = active;
      syncRunMessage();
      agentPollTimer = setTimeout(pollAgentRun, 200);
    }
  }
  async function pollAgentRun() {
    clearTimeout(agentPollTimer);
    const runId = state.agentRun?.run_id;
    if (!runId) return;
    try {
      const run = await api.agentRun(runId);
      if (state.agentRun?.run_id !== runId) return;
      state.agentRun = run;
      state.agentPollError = "";
      syncRunMessage();
      if (state.view === "research" && !state.busy) draw();
      if (agentActive()) agentPollTimer = setTimeout(pollAgentRun, 500);
    } catch {
      state.agentPollError = chat.text(uiLang(), "pollError");
      if (state.view === "research" && !state.busy) draw();
    }
  }
  function findWriteStep(stepId) {
    for (const message of state.agentMessages) {
      const run = message.run ? Object.assign({}, message.run, {
        provider: message.run.provider || message.provider,
        model: message.run.model || message.model,
        max_output_tokens: message.run.max_output_tokens || message.maxOutputTokens,
      }) : null;
      const steps = chat.buildLiveSteps({ documents: message.documents || [], run, lang: uiLang() });
      const found = steps.find((step) => message.runId + ":" + step.id === stepId);
      if (found) return Object.assign({}, found, { id: stepId });
    }
    const previewSteps = state.agentPreview ? chat.buildLiveSteps({ documents: state.agentPreview.documents || [], run: null, lang: uiLang() }) : [];
    const preview = previewSteps.find((step) => "preview:" + step.id === stepId);
    return preview ? Object.assign({}, preview, { id: stepId }) : null;
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  document.addEventListener("click", (ev) => {
    const closedSettings = !state.busy && state.agentSettingsOpen && !ev.target.closest(".research-composer, .agent-step");
    if (closedSettings) state.agentSettingsOpen = false;
    const el = ev.target.closest("button");
    if (!el || el.disabled || state.busy) {
      if (closedSettings) draw();
      return;
    }
    if (el.dataset.view) { navigate(el.dataset.view); return; }
    if (el.hasAttribute("data-tag")) {
      state.tag = el.dataset.tag;
      state.tagPreview = null;
      draw();
      return;
    }
    const action = el.dataset.action || "";
    if (action.startsWith("view-")) { navigate(action.slice(5)); return; }
    if (/^step-[123]$/.test(action)) { state.step = Number(action.slice(5)); draw(); return; }
    if (action === "refresh") { refreshAll(); return; }
    if (action === "ft-fetch") {
      withBusy(async () => {
        state.ftJob = await api.fetchFulltext(state.ftDoi.trim());
      }).then(() => { if (state.ftJob?.id) pollFulltext(state.ftJob.id); });
      return;
    }
    if (action === "connections-refresh") { refreshConnections(); return; }
    if (["relay-start", "relay-stop", "relay-restart"].includes(action)) {
      withBusy(async () => {
        const operation = action.slice(6);
        state.relayRuntime = await api.controlRelay(operation, state.relayConsent);
        if (operation === "stop") state.relayConsent = false;
        state.notice = operation === "stop" ? "本客户端启动的 Relay 已停止。" : "已请求启动本机 Relay；请刷新诊断核验云端传输状态。";
      });
      return;
    }
    if (action === "providers-refresh") { withBusy(loadResearchSettings); return; }
    if (action === "provider-save") {
      // Capture once, then remove the password from the DOM before any redraw.
      const key = $("provider-key")?.value || "";
      const provider = $("provider-id")?.value;
      const storage = $("provider-storage")?.value || "session";
      if ($("provider-key")) $("provider-key").value = "";
      withBusy(async () => {
        if (!key.trim()) throw new Error("请输入新的服务 Key。");
        await api.saveProvider({ provider, key, storage });
        state.agentPreview = null;
        await loadResearchSettings();
        state.notice = "服务 Key 已保存" + (storage === "session" ? "（仅此次运行）" : "（系统凭据库）") + "；尚未远程校验，也未发起计费调用。";
      });
      return;
    }
    if (action === "provider-clear" || action === "provider-check") {
      const provider = el.dataset.provider;
      withBusy(async () => {
        if (action === "provider-clear") {
          await api.clearProvider({ provider, storage: el.dataset.storage || "session" });
          state.agentPreview = null;
        } else await api.checkProvider(provider);
        await loadResearchSettings();
      });
      return;
    }
    if (action === "discovery-search") {
      const query = state.discoveryQuery.trim();
      state.discoveryOpen = true;
      withBusy(async () => {
        if (!query) throw new Error("请输入检索主题。");
        state.discoveryResults = null;
        state.discoveryResults = await api.localDiscovery(query);
      });
      return;
    }
    if (action === "agent-settings-toggle") { state.agentSettingsOpen = !state.agentSettingsOpen; draw(); return; }
    if (action === "agent-history") { state.agentHistoryOpen = !state.agentHistoryOpen; state.agentSettingsOpen = false; draw(); return; }
    if (action === "agent-history-close") { state.agentHistoryOpen = false; draw(); return; }
    if (action === "agent-new") {
      if (agentActive()) return;
      archiveResearchThread();
      state.agentMessages = [];
      state.agentThreadId = "";
      state.agentPrompt = "";
      state.agentPreview = null;
      state.agentRun = null;
      state.agentSent = null;
      state.agentUsage = null;
      state.agentExpanded = {};
      state.agentWriteConfirmed = {};
      state.agentHistoryOpen = false;
      state.agentCursor = 0;
      draw();
      return;
    }
    if (action === "agent-history-restore") {
      if (agentActive()) return;
      const item = state.agentHistory.find((entry) => entry.id === el.dataset.thread);
      if (!item) return;
      archiveResearchThread();
      state.agentHistory = state.agentHistory.filter((entry) => entry.id !== item.id);
      state.agentThreadId = item.id;
      state.agentMessages = JSON.parse(JSON.stringify(item.messages || []));
      state.agentUsage = item.usage || null;
      state.agentRun = null;
      state.agentPreview = null;
      state.agentPrompt = "";
      state.agentHistoryOpen = false;
      draw();
      return;
    }
    if (action === "agent-quick") {
      state.agentPrompt = el.dataset.prompt || "";
      state.agentCursor = state.agentPrompt.length;
      state.agentPreview = null;
      state.agentSlashDismissed = false;
      draw();
      $("agent-prompt")?.focus();
      return;
    }
    if (action === "agent-remove-paper") {
      const id = Number(el.dataset.id);
      state.selected = state.selected.filter((value) => value !== id);
      state.agentPreview = null;
      draw();
      return;
    }
    if (action === "agent-add-paper") {
      const added = chat.addPaper(state.selected, Number(el.dataset.id), state.papers);
      state.selected = added.selected;
      if (added.added) {
        state.agentPrompt = chat.stripSlashToken(state.agentPrompt, state.agentCursor);
        state.agentCursor = state.agentPrompt.length;
        state.agentPreview = null;
      }
      draw();
      $("agent-prompt")?.focus();
      return;
    }
    if (action === "agent-confirm-write") {
      const step = findWriteStep(el.dataset.stepId || "");
      const decision = chat.commitLibraryWrite(step || { id: el.dataset.stepId, kind: "library_write" }, true);
      if (decision.reason === "research_runtime_readonly" && el.dataset.stepId) state.agentWriteConfirmed[el.dataset.stepId] = true;
      state.notice = chat.text(uiLang(), decision.reason === "research_runtime_readonly" ? "writeNotApplied" : "writeBlocked");
      draw();
      return;
    }
    if (action === "agent-prepare") {
      const payload = { document_ids: selectedIds(), prompt: state.agentPrompt.trim(), provider: state.agentProvider, model: state.agentModel.trim(), max_output_tokens: state.agentMaxTokens };
      state.agentSettingsOpen = false;
      withBusy(async () => {
        state.agentPreview = null;
        state.agentPreview = await api.prepareAgent(payload);
      });
      return;
    }
    if (action === "agent-run") {
      const preview = state.agentPreview;
      const approvalId = preview?.approval_id;
      withBusy(async () => {
        if (!approvalId || !preview) throw new Error(chat.text(uiLang(), "needPreview"));
        state.agentRun = await api.startAgent(approvalId);
        state.agentSent = {
          prompt: preview.prompt,
          documents: preview.documents || [],
          chips: (preview.documents || []).map((doc) => chat.chipLabel(doc, uiLang())),
          provider: preview.provider,
          model: preview.model,
          maxOutputTokens: preview.max_output_tokens,
        };
        state.agentPrompt = "";
        state.agentCursor = 0;
        state.agentPreview = null;
        state.agentPollError = "";
        state.agentSettingsOpen = false;
        syncRunMessage();
        agentPollTimer = setTimeout(pollAgentRun, 200);
      });
      return;
    }
    if (action === "agent-cancel") {
      const runId = state.agentRun?.run_id;
      withBusy(async () => {
        if (!runId) return;
        state.agentRun = await api.cancelAgent(runId);
        state.agentPollError = "";
        syncRunMessage();
        clearTimeout(agentPollTimer);
      });
      return;
    }
    if (action === "agent-run-refresh") { pollAgentRun(); return; }
    if (action === "relay-refresh") {
      withBusy(async () => {
        state.relay = null; state.entitlement = null;
        state.relayRuntime = await api.relayRuntime();
        state.relay = await api.relayDiagnostics();
      });
      return;
    }
    if (action === "relay-entitlement") {
      withBusy(async () => { state.entitlement = null; state.entitlement = await api.entitlementCheck(false); });
      return;
    }
    if (action === "zotero-status") {
      withBusy(async () => {
        state.zotero = null;
        state.zotero = await api.zoteroStatus();
        state.zoteroDetail = JSON.stringify(state.zotero, null, 2);
      });
      return;
    }
    if (action === "zotero-collections") {
      withBusy(async () => {
        state.collections = [];
        state.collectionKey = "";
        const data = await api.zoteroCollections();
        state.zotero = data;
        state.collections = data.collections || [];
        state.zoteroDetail = state.collections.length ? "请选择要预览的集合。" : data.action_hint || data.reason_code || "此集合列表为空。";
      });
      return;
    }
    if (action === "zotero-import-preview") {
      const key = state.collectionKey;
      withBusy(async () => {
        if (!key || !state.libraryVerified) throw new Error("请先核验账户，并选择 Zotero 集合。");
        const result = await api.zoteroImport({ collection_key: key, dry_run: true, request_id: "connect-" + Date.now() });
        state.zoteroDetail = JSON.stringify(result, null, 2).slice(0, 4000);
        state.notice = "集合 " + key + " 的 metadata-only 预览已返回（dry_run=true，未写入）";
      });
      return;
    }
    if (action === "tag-preview" || action === "tag-remove") {
      const ids = selectedIds();
      const payload = { document_ids: ids, add: action === "tag-preview" ? [state.tagDraft.trim()] : [], remove: action === "tag-remove" ? [state.tag] : [], dry_run: true };
      withBusy(async () => {
        state.tagPreview = null;
        if (!state.libraryVerified || !ids.length || ids.length > 200) throw new Error("请先核验账户并选择 1–200 篇文献。");
        if (payload.add.includes("") || payload.remove.includes("")) throw new Error("请输入标签，或选择要移除的筛选标签。");
        const result = await api.updateTags(payload);
        state.tagPreview = { payload, result };
      });
      return;
    }
    if (action === "tag-apply") {
      const preview = state.tagPreview;
      withBusy(async () => {
        if (!preview) throw new Error("请先预览当前标签变更。");
        const result = await api.updateTags({ ...preview.payload, dry_run: false });
        state.tagPreview = null;
        state.notice = "标签已保存（" + (result.changed_count ?? "由服务端返回") + " 篇变更）";
        await loadLibrary();
      });
      return;
    }
    if (action.startsWith("export-")) {
      const format = action.slice(7);
      const ids = selectedIds();
      withBusy(async () => {
        if (!state.libraryVerified || !ids.length || ids.length > 200) throw new Error("请先核验账户并选择 1–200 篇文献。");
        if (format === "markdown" && ids.length !== 1) throw new Error("单篇 Markdown 只支持选择一篇文献。");
        const { blob, filename, exportLabel } = await api.exportSelection({ document_ids: ids, format });
        downloadBlob(blob, filename);
        state.notice = "已准备下载 " + filename + "（" + exportLabel + "）";
      });
    }
  });

  document.addEventListener("change", (ev) => {
    const el = ev.target;
    if (state.busy) return;
    if (el.id === "relay-consent") { state.relayConsent = el.checked; draw(); return; }
    if (el.id === "zotero-collection") { state.collectionKey = el.value; state.zoteroDetail = ""; draw(); return; }
    if (el.id === "provider-id") { state.providerId = el.value; draw(); return; }
    if (el.id === "provider-storage") { state.providerStorage = el.value; return; }
    if (el.id === "agent-provider") { state.agentProvider = el.value; state.agentModel = ""; state.agentPreview = null; draw(); return; }
    if (!el.matches("[data-id]")) return;
    const id = Number(el.dataset.id);
    state.selected = el.checked ? [...new Set([...state.selected, id])] : state.selected.filter((value) => value !== id);
    state.tagPreview = null;
    state.agentPreview = null;
    draw();
  });

  document.addEventListener("input", (ev) => {
    const el = ev.target;
    if (state.busy || !["find-paper", "new-tag", "ft-doi", "agent-prompt", "agent-model", "agent-max-tokens", "discovery-query"].includes(el.id)) return;
    const offset = el.selectionStart;
    if (el.id === "ft-doi") state.ftDoi = el.value;
    else if (el.id === "new-tag") { state.tagDraft = el.value; state.tagPreview = null; }
    else if (el.id === "find-paper") state.query = el.value;
    else if (el.id === "discovery-query") { state.discoveryQuery = el.value; return; }
    else {
      if (el.id === "agent-prompt") {
        state.agentPrompt = el.value;
        state.agentCursor = el.selectionStart || 0;
        state.agentSlashDismissed = false;
      }
      if (el.id === "agent-model") state.agentModel = el.value;
      if (el.id === "agent-max-tokens") state.agentMaxTokens = Number(el.value);
      state.agentPreview = null;
    }
    draw();
    const replacement = $(el.id);
    replacement?.focus();
    if (el.type !== "number") replacement?.setSelectionRange(offset, offset);
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") {
      const query = chat.slashQuery(state.agentPrompt, state.agentCursor);
      if (query !== null && !state.agentSlashDismissed) {
        state.agentSlashDismissed = true;
        draw();
        return;
      }
      if (state.agentHistoryOpen || state.agentSettingsOpen) {
        state.agentHistoryOpen = false;
        state.agentSettingsOpen = false;
        draw();
      }
      return;
    }
    if (ev.target.id !== "agent-prompt" || ev.key !== "Enter" || ev.shiftKey || ev.isComposing || state.busy) return;
    const query = chat.slashQuery(state.agentPrompt, ev.target.selectionStart);
    if (query !== null && !state.agentSlashDismissed) {
      const match = chat.searchPapers(state.papers, query, selectedIds())[0];
      if (match && chat.canAddPaper(selectedIds().length)) {
        ev.preventDefault();
        const added = chat.addPaper(state.selected, match.id, state.papers);
        state.selected = added.selected;
        if (added.added) {
          state.agentPrompt = chat.stripSlashToken(state.agentPrompt, ev.target.selectionStart);
          state.agentCursor = state.agentPrompt.length;
          state.agentPreview = null;
        }
        draw();
        $("agent-prompt")?.focus();
      }
      return;
    }
    const send = document.querySelector('[data-action="agent-prepare"]');
    if (!send || send.disabled) return;
    ev.preventDefault();
    send.click();
  });

  document.addEventListener("toggle", (ev) => {
    const card = ev.target;
    if (!card.classList || !card.classList.contains("agent-step") || !card.dataset.stepId) return;
    state.agentExpanded[card.dataset.stepId] = card.open;
  }, true);

  window.addEventListener("hashchange", () => {
    const view = location.hash.slice(1);
    if (view !== state.view) navigate(view);
  });
  refreshAll();
})();
