/* Research chat helpers for the local Mdtero client. No network and no storage. */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.MdteroResearchChat = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const LIMIT = 10;
  const KINDS = ["metadata_lookup", "fulltext_fetch", "classify", "model_request", "library_write"];
  const STATUSES = ["running", "done", "failed", "cancelled"];
  const COPY = {
    zh: {
      "pageTitle": "研究模式",
      "pageHint": "只发送你选中的文献元数据。发送前确认范围；不会据此声称已经读过正文。",
      "newChat": "新对话",
      "history": "历史",
      "close": "关闭",
      "historyEmpty": "还没有历史对话。",
      "untitled": "未命名对话",
      "emptyLead": "从选中的文献开始。输入 / 可以搜索并加入文献，发送前会先确认范围。",
      "quickGroup": "按主题归类",
      "quickQuestions": "列出需看正文确认的问题",
      "quickMethods": "对比方法",
      "quickGroupPrompt": "按主题归类：根据题目、作者和年份，把这些文献分成几个研究主题，并标明依据。",
      "quickQuestionsPrompt": "列出仍需查阅正文才能确认的问题。不要根据元数据声称已经读过全文。",
      "quickMethodsPrompt": "对比这些文献的方法。如果元数据里没有方法细节，请直接说明无法对比。",
      "selectedCount": "已选 {n} / {limit}",
      "overLimit": "研究模式最多 10 篇。请先移除多余的文献。",
      "removeChip": "移除 {label}",
      "placeholder": "问这些文献… 输入 / 添加文献",
      "promptLabel": "研究任务",
      "send": "发送",
      "settingsAria": "模型设置",
      "chooseModel": "选择模型",
      "providerLabel": "模型服务",
      "modelLabel": "模型 ID",
      "tokensLabel": "最多输出 tokens",
      "configureKey": "配置模型 Key",
      "slashLimit": "已选 10 / 10。先移除一篇再添加。",
      "slashEmpty": "没有匹配的文献。",
      "statusReady": "研究模式已就绪",
      "statusOff": "研究模式未开启",
      "statusNotReady": "研究模式未就绪",
      "tokensUsed": "{n} tokens",
      "tokensBudget": "上限 {n} tokens",
      "confirmTitle": "确认发送范围",
      "confirmScope": "选中元数据 {n} 篇 · 问题与元数据 {bytes} bytes · 最多输出 {tokens} tokens · 模型请求上限 1 次。",
      "confirmMetadata": "查看将发送的文献元数据",
      "confirmCaveat": "确认后，以上内容发送至所选模型服务商；不包含 Mdtero 账户 Key、全文、图片、密码或 Cookie。修改任务、模型或文献选择后需重新确认。每次最多一次模型请求；输出上限不是价格承诺。模型调用不执行 shell、任意文件操作或文献写入。",
      "confirmSend": "确认并发送",
      "cancelRun": "取消本次运行",
      "refreshRun": "刷新运行状态",
      "pollError": "运行状态暂时无法读取。可刷新状态或取消本次运行。",
      "needPreview": "请先确认当前发送范围。",
      "kind.metadata_lookup": "查阅文献元数据",
      "kind.fulltext_fetch": "获取全文",
      "kind.classify": "按主题归类",
      "kind.model_request": "模型整理",
      "kind.library_write": "写入文献库",
      "status.running": "进行中",
      "status.done": "完成",
      "status.failed": "失败",
      "status.cancelled": "已取消",
      "argsLabel": "参数",
      "resultLabel": "结果",
      "diffBefore": "当前",
      "diffAfter": "拟写入",
      "confirmWrite": "确认写入",
      "writeNotApplied": "已记下确认。当前研究运行时只读，不会写入文献库。",
      "writeBlocked": "没有可确认的写入差异，文献库不会被修改。",
      "writeNoDiff": "没有可预览的差异，因此不会写入。",
      "metadataSummary": "已读取 {n} 篇元数据：{titles}。这次不包含全文。",
      "modelRunning": "正在等待这一次模型请求。",
      "modelDone": "已根据元数据完成回答。",
      "modelCancelled": "已取消，没有采用模型输出。",
      "modelFailed": "这次请求没有完成。",
      "unknownAuthor": "佚名",
      "noYear": "不详",
      "etAl": "等",
      "recheck": "重新检测 Pi",
      "sourceSummary": "源代码运行方式",
      "diagSummary": "依赖诊断状态",
      "sourceBody": "先安装 Node 22.19+，执行 npm --prefix connect/agent ci --ignore-scripts，再运行 mdtero connect --full。",
      "ready.provider_key_missing": "Pi 已安装，尚未配置模型 Key。请在设置中选择模型服务并保存自己的 Key，然后返回研究。保存不会发起模型调用。",
      "ready.full_mode_required": "当前是基础文献模式。研究模式需要完整版 Mdtero Connect；源代码运行可用 mdtero connect --full 开启。",
      "ready.agent_node_missing": "研究模式组件缺失，请重新安装 Mdtero Connect 后重试。",
      "ready.agent_node_unavailable": "研究模式组件未能启动，请重新检测；仍失败时请重新打开 Mdtero Connect。",
      "ready.agent_node_version": "研究模式需要 Node 22.19 或更新版本，请安装与这台电脑匹配的 Mdtero Connect。",
      "ready.agent_runtime_missing": "研究模式文件不完整，请重新安装 Mdtero Connect。",
      "ready.agent_sdk_missing": "Pi 依赖检测未通过，请重新检测；仍失败时请重新安装 Mdtero Connect。",
      "ready.agent_dependency_version_mismatch": "研究模式组件版本不匹配，请重新安装最新版 Mdtero Connect。",
      "ready.agent_closed": "本机 Pi 运行时已停止，请通过 Connect 菜单重新连接客户端。",
      "ready.unknown": "尚未取得可用的 Pi 运行状态，请重新检测。",
      "provider.anthropic": "Anthropic · AI",
      "provider.openai": "OpenAI · AI",
      "provider.google": "Google · AI",
      "provider.openrouter": "OpenRouter · AI",
    },
    en: {
      "pageTitle": "Research",
      "pageHint": "Only metadata from the papers you select is sent. Confirm the scope before sending. This does not mean the full text was read.",
      "newChat": "New",
      "history": "History",
      "close": "Close",
      "historyEmpty": "No past chats yet.",
      "untitled": "Untitled chat",
      "emptyLead": "Start from the papers you select. Type / to search the library. Sending asks you to confirm the scope first.",
      "quickGroup": "Group by topic",
      "quickQuestions": "List questions that need the full text",
      "quickMethods": "Compare methods",
      "quickGroupPrompt": "Group the selected papers by topic using only the title, authors, and year, and say what you used as evidence.",
      "quickQuestionsPrompt": "List questions that still need the full text. Do not claim the full text was read.",
      "quickMethodsPrompt": "Compare the methods. If the metadata has no method detail, say the comparison cannot be made.",
      "selectedCount": "Selected {n} / {limit}",
      "overLimit": "Research can use at most 10 papers. Remove the extra ones first.",
      "removeChip": "Remove {label}",
      "placeholder": "Ask about these papers… Type / to add papers",
      "promptLabel": "Research task",
      "send": "Send",
      "settingsAria": "Model settings",
      "chooseModel": "Choose a model",
      "providerLabel": "Model service",
      "modelLabel": "Model ID",
      "tokensLabel": "Max output tokens",
      "configureKey": "Configure model key",
      "slashLimit": "Selected 10 / 10. Remove one before adding another.",
      "slashEmpty": "No matching papers.",
      "statusReady": "Research is ready",
      "statusOff": "Research is off",
      "statusNotReady": "Research is not ready",
      "tokensUsed": "{n} tokens",
      "tokensBudget": "Up to {n} tokens",
      "confirmTitle": "Confirm what will be sent",
      "confirmScope": "{n} metadata records · question and metadata {bytes} bytes · up to {tokens} output tokens · 1 model request.",
      "confirmMetadata": "Metadata that will be sent",
      "confirmCaveat": "After you confirm, this content goes to the selected model provider. It does not include the Mdtero account key, full text, images, passwords, or cookies. Editing the task, model, or papers requires confirmation again. At most one model request is made. The output cap is not a price promise. The model call does not run a shell, touch arbitrary files, or write to the library.",
      "confirmSend": "Confirm and send",
      "cancelRun": "Cancel this run",
      "refreshRun": "Refresh status",
      "pollError": "The run status could not be read. Refresh it or cancel the run.",
      "needPreview": "Confirm the current send scope first.",
      "kind.metadata_lookup": "Look up metadata",
      "kind.fulltext_fetch": "Fetch full text",
      "kind.classify": "Classify",
      "kind.model_request": "Model request",
      "kind.library_write": "Write to the library",
      "status.running": "Running",
      "status.done": "Done",
      "status.failed": "Failed",
      "status.cancelled": "Cancelled",
      "argsLabel": "Arguments",
      "resultLabel": "Result",
      "diffBefore": "Current",
      "diffAfter": "Proposed",
      "confirmWrite": "Confirm write",
      "writeNotApplied": "Confirmation recorded. This research runtime is read-only and will not write to the library.",
      "writeBlocked": "There is no diff to confirm, so the library will not be changed.",
      "writeNoDiff": "There is no diff to preview, so nothing will be written.",
      "metadataSummary": "Read metadata for {n} papers: {titles}. Full text is not included.",
      "modelRunning": "Waiting for the single model request.",
      "modelDone": "Answered from metadata only.",
      "modelCancelled": "Cancelled before the answer was kept.",
      "modelFailed": "The request did not finish.",
      "unknownAuthor": "Unknown",
      "noYear": "n.d.",
      "etAl": "et al.",
      "recheck": "Check Pi again",
      "sourceSummary": "Source checkout",
      "diagSummary": "Dependency status",
      "sourceBody": "Install Node 22.19 or newer, run npm --prefix connect/agent ci --ignore-scripts, then run mdtero connect --full.",
      "ready.provider_key_missing": "Pi is installed, and no model key is configured yet. Choose a provider in Settings and save your own key, then come back. Saving does not call the model.",
      "ready.full_mode_required": "This is the library edition. Research needs the full Mdtero client; from a source checkout, start it with mdtero connect --full.",
      "ready.agent_node_missing": "Research components are missing. Reinstall Mdtero and try again.",
      "ready.agent_node_unavailable": "Research components did not start. Check again, or reopen Mdtero if that still fails.",
      "ready.agent_node_version": "Research needs Node 22.19 or newer. Install the Mdtero build that matches this computer.",
      "ready.agent_runtime_missing": "Research files are incomplete. Reinstall Mdtero.",
      "ready.agent_sdk_missing": "The Pi dependency check did not pass. Check again, or reinstall Mdtero if that still fails.",
      "ready.agent_dependency_version_mismatch": "Research components do not match. Reinstall the latest Mdtero.",
      "ready.agent_closed": "The local Pi runtime has stopped. Reconnect the client from the Connect menu.",
      "ready.unknown": "Pi is not ready yet. Check again.",
      "provider.anthropic": "Anthropic",
      "provider.openai": "OpenAI",
      "provider.google": "Google",
      "provider.openrouter": "OpenRouter",
    },
  };

  function locale(lang) {
    return String(lang || "").toLowerCase().startsWith("en") ? "en" : "zh";
  }

  function has(lang, key) {
    const table = COPY[locale(lang)] || COPY.zh;
    return Object.prototype.hasOwnProperty.call(table, key) || Object.prototype.hasOwnProperty.call(COPY.zh, key);
  }

  function text(lang, key, vars) {
    const table = COPY[locale(lang)] || COPY.zh;
    let value = Object.prototype.hasOwnProperty.call(table, key) ? table[key] : COPY.zh[key];
    if (value == null) value = key;
    if (!vars) return value;
    return value.replace(/\{(\w+)\}/g, function (match, name) {
      return Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : match;
    });
  }

  function escapeHtml(value) {
    return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  }

  function authorList(authors) {
    if (Array.isArray(authors)) return authors.map(function (part) { return String(part).trim(); }).filter(Boolean);
    return String(authors || "").split(/\s*(?:,|;|、|\band\b|&)\s*/i).map(function (part) { return part.trim(); }).filter(Boolean);
  }

  function chipLabel(paper, lang) {
    const people = authorList(paper && paper.authors);
    const year = paper && paper.year != null && String(paper.year).trim() ? String(paper.year).trim() : text(lang, "noYear");
    if (!people.length) return text(lang, "unknownAuthor") + ", " + year;
    const words = people[0].split(/\s+/).filter(Boolean);
    const surname = words[words.length - 1] || people[0];
    const name = people.length > 1 ? surname + " " + text(lang, "etAl") : surname;
    return name + ", " + year;
  }

  function selectionCount(count, lang) {
    return text(lang, "selectedCount", { n: count, limit: LIMIT });
  }

  function slashQuery(value, cursor) {
    const source = String(value || "");
    const end = Number.isInteger(cursor) ? Math.max(0, Math.min(cursor, source.length)) : source.length;
    const match = /(?:^|\s)\/([^\s/]*)$/.exec(source.slice(0, end));
    return match ? match[1] : null;
  }

  function stripSlashToken(value, cursor) {
    const source = String(value || "");
    const end = Number.isInteger(cursor) ? Math.max(0, Math.min(cursor, source.length)) : source.length;
    const upto = source.slice(0, end);
    const match = /(?:^|\s)\/([^\s/]*)$/.exec(upto);
    if (!match) return source;
    const slashIndex = match.index + match[0].lastIndexOf("/");
    return (source.slice(0, slashIndex) + source.slice(end)).replace(/[ \t]{2,}/g, " ").trim();
  }

  function sameId(left, right) {
    const a = Number(left);
    const b = Number(right);
    return Number.isInteger(a) && a === b;
  }

  function searchPapers(papers, query, selected, limit) {
    const needle = String(query || "").trim().toLowerCase();
    const chosen = new Set((selected || []).map(function (id) { return Number(id); }));
    const found = [];
    const cap = limit || 8;
    for (const paper of papers || []) {
      if (!paper || !Number.isInteger(Number(paper.id)) || chosen.has(Number(paper.id))) continue;
      const haystack = [paper.title, paper.authors, paper.year, paper.doi, paper.venue, chipLabel(paper, "zh"), chipLabel(paper, "en")].join(" ").toLowerCase();
      if (!needle || haystack.includes(needle)) found.push(paper);
      if (found.length >= cap) break;
    }
    return found;
  }

  function canAddPaper(count, limit) {
    return Number(count) < (limit || LIMIT);
  }

  function addPaper(selected, id, papers, limit) {
    const cap = limit || LIMIT;
    const ids = Array.isArray(selected) ? selected.slice() : [];
    const numeric = Number(id);
    if (!Number.isInteger(numeric) || !(papers || []).some(function (paper) { return paper && sameId(paper.id, numeric); })) {
      return { selected: ids, added: false, reason: "missing" };
    }
    if (ids.some(function (value) { return sameId(value, numeric); })) return { selected: ids, added: false, reason: "duplicate" };
    if (ids.length >= cap) return { selected: ids, added: false, reason: "limit" };
    return { selected: ids.concat(numeric), added: true, reason: "" };
  }

  function quickPrompts(lang) {
    return [
      { id: "group", label: text(lang, "quickGroup"), prompt: text(lang, "quickGroupPrompt") },
      { id: "questions", label: text(lang, "quickQuestions"), prompt: text(lang, "quickQuestionsPrompt") },
      { id: "methods", label: text(lang, "quickMethods"), prompt: text(lang, "quickMethodsPrompt") },
    ];
  }

  function threadTitle(prompt, lang) {
    const clean = String(prompt || "").trim().replace(/\s+/g, " ");
    if (!clean) return text(lang, "untitled");
    return clean.length > 42 ? clean.slice(0, 42) + "…" : clean;
  }

  function tokenLabel(usage, maxTokens, lang) {
    const total = usage && Number(usage.totalTokens);
    if (Number.isFinite(total) && total >= 0) return text(lang, "tokensUsed", { n: Math.round(total) });
    const budget = Number(maxTokens);
    return text(lang, "tokensBudget", { n: Number.isFinite(budget) ? budget : 0 });
  }

  function safeId(value) {
    const cleaned = String(value || "").replace(/[^a-zA-Z0-9:_-]/g, "").slice(0, 80);
    return cleaned || "step";
  }

  function cleanArgs(value, depth) {
    if (depth > 4 || value == null) return null;
    if (typeof value === "number" || typeof value === "boolean") return value;
    if (typeof value === "string") return value.slice(0, 500);
    if (Array.isArray(value)) return value.slice(0, 20).map(function (item) { return cleanArgs(item, depth + 1); });
    if (typeof value === "object") {
      const out = {};
      for (const key of Object.keys(value).slice(0, 20)) {
        if (/key|token|secret|password|authorization|cookie/i.test(key)) continue;
        out[String(key).slice(0, 80)] = cleanArgs(value[key], depth + 1);
      }
      return out;
    }
    return null;
  }

  function sanitizeSteps(value) {
    if (!Array.isArray(value)) return [];
    const steps = [];
    for (const raw of value.slice(0, 8)) {
      if (!raw || typeof raw !== "object" || Array.isArray(raw) || !KINDS.includes(raw.kind)) continue;
      const summary = typeof raw.summary === "string" ? raw.summary.trim().slice(0, 500) : "";
      const diff = raw.diff && typeof raw.diff === "object" && !Array.isArray(raw.diff) ? {
        before: typeof raw.diff.before === "string" ? raw.diff.before.slice(0, 2000) : "",
        after: typeof raw.diff.after === "string" ? raw.diff.after.slice(0, 2000) : "",
      } : null;
      steps.push({
        id: "extra-" + safeId(raw.id || raw.kind + "-" + steps.length),
        kind: raw.kind,
        status: STATUSES.includes(raw.status) ? raw.status : "done",
        name: typeof raw.name === "string" ? raw.name.trim().slice(0, 80) : "",
        args: cleanArgs(raw.args, 0),
        summary: summary,
        diff: diff,
      });
    }
    return steps;
  }

  function buildLiveSteps(input) {
    const lang = input && input.lang;
    const documents = input && Array.isArray(input.documents) ? input.documents : [];
    const run = input && input.run;
    const steps = [];
    if (documents.length) {
      const titles = documents.map(function (doc) { return doc && doc.title ? String(doc.title) : ""; }).filter(Boolean).join("；").slice(0, 240);
      steps.push({
        id: "metadata-lookup",
        kind: "metadata_lookup",
        status: "done",
        name: "",
        args: {
          document_ids: documents.map(function (doc) { return doc && doc.id; }),
          scope: "selected_metadata",
          full_text_included: false,
        },
        summary: text(lang, "metadataSummary", { n: documents.length, titles: titles || "—" }),
      });
    }
    if (run) {
      const status = run.status === "completed" ? "done" : run.status === "failed" ? "failed" : run.status === "cancelled" ? "cancelled" : "running";
      const errorText = run.error && (run.error.message || run.error.reason_code) || "";
      const summary = status === "done" ? text(lang, "modelDone") : status === "running" ? text(lang, "modelRunning") : status === "cancelled" ? text(lang, "modelCancelled") : String(errorText || text(lang, "modelFailed"));
      steps.push({
        id: "model-request",
        kind: "model_request",
        status: status,
        name: "",
        args: {
          provider: run.provider || null,
          model: run.model || null,
          max_output_tokens: run.max_output_tokens || null,
          model_requests: 1,
          full_text_included: false,
        },
        summary: summary,
      });
      for (const extra of sanitizeSteps(run.steps)) steps.push(extra);
    }
    return steps;
  }

  const ICONS = {
    metadata_lookup: '<path d="M3.2 2.8h6.2c.9 0 1.6.7 1.6 1.6V13H4.4c-.7 0-1.2.5-1.2 1.1V2.8z"/><path d="M8 2.8v10.2"/>',
    fulltext_fetch: '<rect x="3.2" y="2.2" width="9.6" height="11.6" rx="1.2"/><path d="M5.6 5.6h5M5.6 8h5M5.6 10.4h3.2"/>',
    classify: '<path d="M3 4h4.5M3 8h7.5M3 12h6"/>',
    model_request: '<path d="M8 1.8l1.1 4.1L13.2 8 9.1 9.1 8 14.2 6.9 9.1 2.8 8l4.1-1.1z"/>',
    library_write: '<path d="M9.8 2.6l3.6 3.6L6.2 13.4 2.6 13.8l.4-3.6z"/><path d="M8.6 3.8l3.6 3.6"/>',
  };

  function icon(kind) {
    return '<svg class="step-glyph" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">' + (ICONS[kind] || ICONS.model_request) + "</svg>";
  }

  function stepTitle(step, lang) {
    if (step.name) return step.name;
    return text(lang, "kind." + step.kind);
  }

  function renderDiff(diff, lang) {
    return '<div class="write-diff"><div><h3>' + escapeHtml(text(lang, "diffBefore")) + '</h3><pre class="diagnostic">' + escapeHtml(diff.before || "") + '</pre></div><div><h3>' + escapeHtml(text(lang, "diffAfter")) + '</h3><pre class="diagnostic">' + escapeHtml(diff.after || "") + "</pre></div></div>";
  }

  function renderStepCard(step, lang, options) {
    if (!step || typeof step !== "object") return "";
    const opts = options || {};
    const status = STATUSES.includes(step.status) ? step.status : "running";
    const kind = KINDS.includes(step.kind) ? step.kind : "model_request";
    const id = safeId(step.id || kind);
    const spinner = status === "running" ? '<span class="spinner" aria-hidden="true"></span>' : "";
    const args = cleanArgs(step.args, 0) || {};
    let body = '<p class="label">' + escapeHtml(text(lang, "argsLabel")) + '</p><pre class="diagnostic">' + escapeHtml(JSON.stringify(args, null, 2)) + '</pre><p class="label">' + escapeHtml(text(lang, "resultLabel")) + "</p><p>" + escapeHtml(step.summary || "") + "</p>";
    if (kind === "library_write") {
      if (!step.diff) body += '<p class="hint">' + escapeHtml(text(lang, "writeNoDiff")) + "</p>";
      else {
        body += renderDiff(step.diff, lang);
        body += opts.userConfirmed
          ? '<p class="hint">' + escapeHtml(text(lang, "writeNotApplied")) + "</p>"
          : '<div class="actions"><button type="button" class="primary" data-action="agent-confirm-write" data-step-id="' + escapeHtml(id) + '">' + escapeHtml(text(lang, "confirmWrite")) + "</button></div>";
      }
    }
    return '<details class="agent-step" data-step-id="' + escapeHtml(id) + '" data-step-kind="' + kind + '" data-status="' + status + '"' + (opts.open ? " open" : "") + '><summary><span class="step-icon">' + icon(kind) + '</span><span class="step-name">' + escapeHtml(stepTitle(Object.assign({}, step, { kind: kind }), lang)) + '</span><span class="step-state">' + spinner + escapeHtml(text(lang, "status." + status)) + "</span></summary><div class=\"step-body\">" + body + "</div></details>";
  }

  function commitLibraryWrite(step, userConfirmed) {
    if (!step || step.kind !== "library_write") return { applied: false, reason: "not_a_write" };
    if (!step.diff || typeof step.diff !== "object") return { applied: false, reason: "diff_required" };
    if (userConfirmed !== true) return { applied: false, reason: "confirmation_required" };
    return { applied: false, reason: "research_runtime_readonly" };
  }

  return {
    LIMIT: LIMIT,
    locale: locale,
    has: has,
    text: text,
    escapeHtml: escapeHtml,
    chipLabel: chipLabel,
    selectionCount: selectionCount,
    slashQuery: slashQuery,
    stripSlashToken: stripSlashToken,
    searchPapers: searchPapers,
    canAddPaper: canAddPaper,
    addPaper: addPaper,
    quickPrompts: quickPrompts,
    threadTitle: threadTitle,
    tokenLabel: tokenLabel,
    buildLiveSteps: buildLiveSteps,
    sanitizeSteps: sanitizeSteps,
    renderStepCard: renderStepCard,
    commitLibraryWrite: commitLibraryWrite,
  };
});
