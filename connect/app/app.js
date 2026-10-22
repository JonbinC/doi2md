/* Live Connect UI. All product state comes from the same-origin bridge. */
(() => {
  "use strict";
  const api = window.MdteroConnectApi;
  const views = ["start", "library", "fulltext", "connections", "settings"];
  const state = {
    view: views.includes(location.hash.slice(1)) ? location.hash.slice(1) : "start",
    step: 1, session: null, libraryVerified: false, libraryError: "",
    papers: [], tags: [], selected: [], query: "", tag: "", tagDraft: "", tagPreview: null,
    busy: false, notice: "", error: "", relay: null, zotero: null, agent: null,
    collections: [], collectionKey: "", zoteroDetail: "", entitlement: null,
    ftDoi: "", ftJob: null,
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
    (state.busy ? '<p class="hint" role="status">正在核验，请稍候…</p>' : "");
  const accountStatus = () => state.libraryVerified ? "文献库已核验" : configured() ? "已检测到本机 Key，文献接口未核验" : "未检测到本机 API Key";
  const setupHint = '<p class="hint">在终端运行 <code>mdtero login</code> 或 <code>mdtero setup</code>。配置后重启 <code>mdtero connect</code>，再打开新地址。本页面不接收密钥。</p>';

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
        '<p>现有账户文献可以直接筛选、标记和导出。出版社 API Key 属于文献访问凭据，与模型 API Key 分开配置。</p>' +
        '<ul class="fact-list"><li>此客户端尚未提供出版社 Key 校验或可见 CARSI 登录。</li>' +
        '<li>Relay 传输、授权浏览器和具体文章的全文权限分别核验。</li>' +
        '<li>学校密码与 Cookie 留在本机；Markdown 导出为纯文本，不含图片。</li></ul>' +
        '<div class="actions">' + b("下一步：本机连接", "step-3", "primary") + b("先用已有文献", "view-library") + b("上一步", "step-1") + "</div></article>";
    } else {
      content = '<div class="grid"><article class="card"><h2>本机连接</h2>' +
        status(state.session ? "本机桥接可用" : "本机桥接待核验", !!state.session) +
        status(state.relay ? (state.relay.transport_online ? "Relay 传输在线" : "Relay 传输离线") : "Relay 尚未检测", !!state.relay?.transport_online) +
        status(state.zotero ? (state.zotero.available ? "Zotero connector 可达" : "未检测到本机 Zotero") : "Zotero 尚未检测", !!state.zotero?.available) +
        '<div class="actions">' + b("检测本机连接", "connections-refresh", "primary") + b("打开连接中心", "view-connections") +
        '</div><p class="hint">Zotero connector 可达仅代表端口探测成功。集合读取与导入预览需另行检查。</p></article>' +
        '<article class="card"><h2>AI 与研究模式（可选）</h2><p>云端 MCP Reader 尚未嵌入 Connect。普通文献整理不要求 ChatGPT 或模型 Key。</p>' +
        status("Agent 未启用，运行时尚未发布") + '<p class="hint">Pi/OpenCode、BYOK、工具审批与预算控制仍待实现。</p></article></div>' +
        '<div class="actions">' + b("进入文献库", "view-library", "primary") + b("上一步", "step-2") + "</div>";
    }
    return h("一处整理文献，随处继续研究。", "三步了解账户、文献访问和本机连接。可选连接可稍后设置，继续按钮不会改变实际核验结果。") + steps + content;
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
      '</div><p class="hint">先勾选文献才能操作。Markdown ≤2 MiB/篇，批量内联 ≤4 MiB；导出不含图片，不能作为完整离线包。</p></div></section></div>';
  }

  function connectionCards() {
    const relay = state.relay;
    const zotero = state.zotero;
    return '<div class="grid"><article class="card"><h2>校园 Relay</h2>' +
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

  function settings() {
    return h("设置", "账户配置与可选研究模式。") + '<div class="grid"><section class="card"><h2>账户</h2>' + status(accountStatus(), state.libraryVerified) +
      '<p>API：' + esc(state.session?.api_base_url || "尚未连接") + '</p><p>凭据来源：' + esc(state.session?.auth_source || "无") + "</p>" + setupHint +
      '<div class="actions">' + b("打开三步引导", "view-start") + '</div></section><section class="card"><h2>研究模式 / Agent（可选）</h2>' +
      status("Agent 未启用，运行时尚未发布") + '<p>' + esc(state.agent?.action_hint || "Pi/OpenCode、BYOK、工具审批与预算控制仍待实现。") +
      '</p><p class="hint">云端 MCP Reader 尚未嵌入；官网/Dashboard 的 Connect 入口尚未对齐。</p></section></div>';
  }

  function draw() {
    document.querySelectorAll("[data-view]").forEach((el) => {
      const active = el.dataset.view === state.view;
      el.classList.toggle("active", active);
      el.setAttribute("aria-current", active ? "page" : "false");
      el.disabled = state.busy;
    });
    $("current-account").textContent = accountStatus();
    $("auth-badge").textContent = state.libraryVerified ? "已核验" : configured() ? "待核验" : "未配置";
    $("auth-detail").textContent = state.session ? "本机桥接可用" : "等待本机桥接";
    $("screen").setAttribute("aria-busy", String(state.busy));
    $("screen").innerHTML = ({ start, library, fulltext, connections, settings }[state.view])();
    document.querySelectorAll('[data-action="refresh"]').forEach((el) => { el.disabled = state.busy; });
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
      await loadLibrary();
    });
  }

  async function refreshConnections() {
    await withBusy(async () => {
      state.relay = null;
      state.zotero = null;
      state.entitlement = null;
      const results = await Promise.allSettled([api.relayDiagnostics(), api.zoteroStatus()]);
      if (results[0].status === "fulfilled") state.relay = results[0].value;
      if (results[1].status === "fulfilled") state.zotero = results[1].value;
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
    draw();
    $("screen").focus();
    if (view === "connections") refreshConnections();
    if (view === "settings") withBusy(async () => { state.agent = await api.agentStatus(); });
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
    const el = ev.target.closest("button");
    if (!el || el.disabled || state.busy) return;
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
    if (action === "relay-refresh") {
      withBusy(async () => { state.relay = null; state.entitlement = null; state.relay = await api.relayDiagnostics(); });
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
    if (el.id === "zotero-collection") { state.collectionKey = el.value; state.zoteroDetail = ""; draw(); return; }
    if (!el.matches("[data-id]")) return;
    const id = Number(el.dataset.id);
    state.selected = el.checked ? [...new Set([...state.selected, id])] : state.selected.filter((value) => value !== id);
    state.tagPreview = null;
    draw();
  });

  document.addEventListener("input", (ev) => {
    const el = ev.target;
    if (state.busy || !["find-paper", "new-tag", "ft-doi"].includes(el.id)) return;
    const offset = el.selectionStart;
    if (el.id === "ft-doi") state.ftDoi = el.value;
    else if (el.id === "new-tag") { state.tagDraft = el.value; state.tagPreview = null; }
    else state.query = el.value;
    draw();
    const replacement = $(el.id);
    replacement?.focus();
    replacement?.setSelectionRange(offset, offset);
  });

  window.addEventListener("hashchange", () => {
    const view = location.hash.slice(1);
    if (view !== state.view) navigate(view);
  });
  refreshAll();
})();
