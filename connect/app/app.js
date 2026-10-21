/* Live Connect UI — library/tags/export via loopback bridge. */
(() => {
  "use strict";
  const api = window.MdteroConnectApi;
  const state = {
    view: "library",
    session: null,
    papers: [],
    tags: [],
    selected: [],
    query: "",
    tag: "",
    tagMatch: "all",
    busy: false,
    notice: "",
    relay: null,
    zotero: null,
    agent: null,
    error: "",
  };
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const b = (name, action, kind = "") =>
    '<button type="button" class="' + (kind || "tool") + '" data-action="' + action + '"' + (state.busy ? " disabled" : "") + ">" + esc(name) + "</button>";
  const h = (title, desc) =>
    '<div class="eyebrow">YOUR RESEARCH, CONNECTED</div><h1>' + esc(title) + "</h1><p class=\"lead\">" + esc(desc) + "</p>" +
    (state.error ? '<div class="notice">' + esc(state.error) + "</div>" : "") +
    (state.notice ? '<div class="status ok"><span class="dot"></span>' + esc(state.notice) + "</div>" : "");
  const status = (label, good) =>
    '<div class="status ' + (good ? "ok" : "") + '"><span class="dot"></span>' + esc(label) + "</div>";

  function filteredPapers() {
    const q = state.query.toLowerCase();
    return state.papers.filter((p) => {
      const hay = (p.title + " " + p.authors + " " + (p.doi || "")).toLowerCase();
      if (q && !hay.includes(q)) return false;
      if (!state.tag) return true;
      const tags = p.tags || [];
      return tags.includes(state.tag);
    });
  }

  function library() {
    const filtered = filteredPapers();
    const selection = state.selected.filter((id) => state.papers.some((p) => p.id === id));
    const allTags = [...new Set(state.papers.flatMap((p) => p.tags || []))].sort((a, b) => a.localeCompare(b));
    const list = filtered.map((p) =>
      '<label class="listrow ' + (selection.includes(p.id) ? "selected" : "") + '">' +
      '<input type="checkbox" data-id="' + p.id + '" ' + (selection.includes(p.id) ? "checked" : "") + ">" +
      "<span><b>" + esc(p.title) + "</b><small>" + esc(p.authors || "Unknown authors") +
      " · " + esc(p.year || "—") + " · " + esc(p.venue || "") + "</small><small>" +
      esc(p.status || (p.has_saved_text ? "source ready" : "metadata")) + " · " +
      (p.tags || []).map((t) => "#" + esc(t)).join(" ") +
      "</small></span></label>"
    ).join("");
    const authed = !!(state.session && state.session.authenticated);
    return h("我的文献库", authed
      ? "列表、标签与导出走后端已合并的账户文献接口；选中数量以当前勾选为准。"
      : "尚未检测到本机 API Key。请先运行 mdtero setup / mdtero login，再刷新。") +
      '<div class="split"><section class="pane"><header>标签</header><div class="collection-list">' +
      '<div class="chipset"><button type="button" data-tag="" class="' + (!state.tag ? "active" : "") + '">全部</button>' +
      allTags.map((t) => '<button type="button" data-tag="' + esc(t) + '" class="' + (state.tag === t ? "active" : "") + '">' + esc(t) + "</button>").join("") +
      "</div><p class=\"hint\">标签目录条目：" + (state.tags.length || allTags.length) + "</p></div></section>" +
      '<section class="pane"><header>文献 · 可见 ' + filtered.length + " / 全部 " + state.papers.length +
      '</header><div style="padding:12px 16px"><input type="search" id="find-paper" placeholder="搜索标题、作者或 DOI" value="' +
      esc(state.query) + '" aria-label="搜索文献"></div>' +
      (list || '<p class="empty">' + (authed ? "没有匹配的文献" : "登录后显示账户文献") + "</p>") +
      "</section>" +
      '<section class="pane"><header>条目与操作</header><div class="details">' +
      '<p class="hint">已选 ' + selection.length + " 篇（当前勾选，不是“全部匹配”）。批量上限 200。</p>" +
      '<label class="label" for="new-tag">为选中条目添加标签</label>' +
      '<input id="new-tag" type="text" maxlength="80" placeholder="例如 Cycling stability">' +
      '<div class="actions">' + b("预览标签变更", "tag-preview", "primary") + b("应用标签", "tag-apply") +
      b("移除当前筛选标签", "tag-remove") + "</div>" +
      '<div class="label">导出（后端 PR #43）</div><div class="actions">' +
      b("BibTeX", "export-bibtex", "primary") + b("CSL JSON", "export-csl_json") +
      b("Markdown ZIP（纯文本）", "export-markdown_zip") +
      (selection.length === 1 ? b("单篇 Markdown", "export-markdown") : "") +
      "</div><p class=\"hint\">Markdown 导出带 X-Mdtero-Export: markdown-text-only；不含图片，不是完整离线包。</p></div></section></div>";
  }

  function connections() {
    const relay = state.relay || {};
    const cloud = relay.cloud_status || {};
    const zotero = state.zotero || {};
    return h("连接状态，分开核验", "Relay 在线 ≠ 全文可读；学校密码与 Cookie 不上传云端。") +
      '<div class="grid"><article class="card"><h2>校园 Relay</h2>' +
      status(relay.transport_online ? "传输在线" : "传输离线", !!relay.transport_online) +
      status(relay.browser_ready ? "本机授权浏览器就绪" : "本机浏览器未就绪", !!relay.browser_ready) +
      status(cloud.egress_ip ? ("出口 IP " + cloud.egress_ip) : "尚无出口 IP", !!cloud.egress_ip) +
      '<div class="actions">' + b("刷新诊断", "relay-refresh", "primary") +
      b("单篇 entitlement 检查", "relay-entitlement") + "</div>" +
      '<p class="hint">' + esc((cloud.action_hint || (relay.notes || [])[0] || "")) + "</p></article>" +
      '<article class="card"><h2>Zotero 单向同步</h2>' +
      status(zotero.available ? "本机 connector 可达" : "未检测到本机 Zotero", !!zotero.available) +
      '<p class="hint">仅连接批准的 127.0.0.1:23119；不可粘贴任意 URL。</p>' +
      '<div class="actions">' + b("检测 Zotero", "zotero-status", "primary") +
      b("列出集合", "zotero-collections") + b("预览导入（dry-run）", "zotero-import-preview") +
      "</div><pre id=\"zotero-panel\" class=\"hint\" style=\"white-space:pre-wrap\">" +
      esc(state.zoteroDetail || "") + "</pre></article></div>";
  }

  function settings() {
    const session = state.session || {};
    const agent = state.agent || {};
    return h("设置", "账号、文献来源与可选研究模式。Agent 默认关闭。") +
      '<div class="grid"><section class="card"><h2>账号</h2>' +
      status(session.authenticated ? "已通过本机 API Key 认证" : "未认证", !!session.authenticated) +
      "<p>API：" + esc(session.api_base_url || "") + "</p>" +
      "<p>来源：" + esc(session.auth_source || "无") + "</p>" +
      '<p class="hint">在终端使用 mdtero login / mdtero setup --api-key 配置；此 UI 不收集密钥。</p></section>' +
      '<section class="card"><h2>研究模式 / Agent（可选）</h2>' +
      status(agent.enabled ? "已启用" : "未启用", !!agent.enabled) +
      "<p>" + esc(agent.action_hint || agent.reason_code || "可选层尚未发布。") + "</p>" +
      '<div class="notice">普通标签、阅读与导出不依赖 Agent，也不要求 ChatGPT。</div></section></div>';
  }

  function draw() {
    document.querySelectorAll("[data-view]").forEach((el) => {
      const active = el.dataset.view === state.view;
      el.classList.toggle("active", active);
      el.setAttribute("aria-current", active ? "page" : "false");
    });
    const session = state.session || {};
    $("current-account").textContent = session.authenticated
      ? ("已登录 · " + (session.auth_source || "api key"))
      : "未登录 — 先配置本机 API Key";
    $("auth-badge").textContent = session.authenticated ? "已连接" : "未登录";
    $("auth-detail").textContent = session.authenticated
      ? (session.api_base_url || "api.mdtero.com")
      : "等待 mdtero setup";
    $("screen").innerHTML = ({ library, connections, settings }[state.view] || library)();
  }

  async function withBusy(fn) {
    state.busy = true;
    state.error = "";
    state.notice = "";
    draw();
    try {
      await fn();
    } catch (err) {
      state.error = err.message || String(err);
    } finally {
      state.busy = false;
      draw();
    }
  }

  async function refreshAll() {
    await withBusy(async () => {
      state.session = await api.session();
      if (state.session.authenticated) {
        const docs = await api.listDocuments();
        state.papers = docs.items || [];
        try {
          const tags = await api.listTags();
          state.tags = (tags.items || tags.tags || []).map((row) => (typeof row === "string" ? row : row.name || row.tag)).filter(Boolean);
        } catch {
          state.tags = [];
        }
      } else {
        state.papers = [];
        state.tags = [];
      }
      state.notice = state.session.authenticated
        ? ("已加载 " + state.papers.length + " 篇文献")
        : "桥接正常，但尚未认证";
    });
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
    if (!el || el.disabled) return;
    if (el.dataset.view) {
      state.view = el.dataset.view;
      draw();
      if (state.view === "connections") {
        withBusy(async () => {
          state.relay = await api.relayDiagnostics();
          state.zotero = await api.zoteroStatus();
        });
      }
      if (state.view === "settings") {
        withBusy(async () => { state.agent = await api.agentStatus(); });
      }
      return;
    }
    if (el.hasAttribute("data-tag")) {
      state.tag = el.dataset.tag;
      draw();
      return;
    }
    const action = el.dataset.action;
    if (!action) return;
    if (action === "refresh") { refreshAll(); return; }
    if (action === "relay-refresh") {
      withBusy(async () => { state.relay = await api.relayDiagnostics(); state.notice = "Relay 诊断已更新"; });
      return;
    }
    if (action === "relay-entitlement") {
      withBusy(async () => {
        const result = await api.entitlementCheck(false);
        state.notice = "entitlement: " + (result.reason_code || result.status || "ok");
        state.relay = { ...(state.relay || {}), article_entitlement: result };
      });
      return;
    }
    if (action === "zotero-status") {
      withBusy(async () => {
        state.zotero = await api.zoteroStatus();
        state.zoteroDetail = JSON.stringify(state.zotero, null, 2);
        state.notice = state.zotero.available ? "Zotero connector 可达" : "未检测到 Zotero";
      });
      return;
    }
    if (action === "zotero-collections") {
      withBusy(async () => {
        const data = await api.zoteroCollections();
        state.zotero = data;
        state.zoteroDetail = (data.collections || []).map((c) => c.key + " · " + c.name).join("\n") || data.action_hint || data.reason_code;
        state._zoteroCollections = data.collections || [];
      });
      return;
    }
    if (action === "zotero-import-preview") {
      withBusy(async () => {
        const collections = state._zoteroCollections || (await api.zoteroCollections()).collections || [];
        const key = collections[0] && collections[0].key;
        if (!key) throw new Error("没有可预览的集合；请先列出集合。");
        const result = await api.zoteroImport({
          collection_key: key,
          dry_run: true,
          request_id: "connect-" + Date.now(),
        });
        state.zoteroDetail = JSON.stringify(result, null, 2).slice(0, 4000);
        state.notice = "已对集合 " + key + " 做 metadata-only dry-run 导入预览";
      });
      return;
    }
    if (action === "tag-preview" || action === "tag-apply" || action === "tag-remove") {
      withBusy(async () => {
        const ids = state.selected.filter((id) => state.papers.some((p) => p.id === id));
        if (!ids.length) throw new Error("请先选择 1–200 篇文献");
        let add = [];
        let remove = [];
        if (action === "tag-remove") {
          if (!state.tag) throw new Error("请先选择要移除的筛选标签");
          remove = [state.tag];
        } else {
          const value = $("new-tag")?.value.trim();
          if (!value) throw new Error("请输入标签");
          add = [value];
        }
        const dry_run = action === "tag-preview";
        const result = await api.updateTags({ document_ids: ids, add, remove, dry_run });
        if (dry_run) {
          state.notice = "预览：将变更 " + (result.changed_count ?? 0) + " 篇（dry_run=true，未写入）";
        } else {
          const docs = await api.listDocuments();
          state.papers = docs.items || [];
          state.notice = "标签已保存（" + (result.changed_count ?? "?") + " 篇变更）";
        }
      });
      return;
    }
    if (action.startsWith("export-")) {
      withBusy(async () => {
        const format = action.slice("export-".length);
        const ids = state.selected.filter((id) => state.papers.some((p) => p.id === id));
        if (!ids.length) throw new Error("请先选择要导出的文献");
        if (ids.length > 200) throw new Error("每次最多导出 200 篇");
        const { blob, filename, exportLabel } = await api.exportSelection({ document_ids: ids, format });
        downloadBlob(blob, filename);
        state.notice = "已准备下载 " + filename + "（" + exportLabel + "）";
      });
    }
  });

  document.addEventListener("change", (ev) => {
    const el = ev.target;
    if (!el.matches("[data-id]")) return;
    const id = Number(el.dataset.id);
    state.selected = el.checked
      ? [...new Set([...state.selected, id])]
      : state.selected.filter((value) => value !== id);
    draw();
  });

  document.addEventListener("input", (ev) => {
    if (ev.target.id !== "find-paper") return;
    const offset = ev.target.selectionStart;
    state.query = ev.target.value;
    draw();
    $("find-paper")?.focus();
    $("find-paper")?.setSelectionRange(offset, offset);
  });

  refreshAll();
})();
