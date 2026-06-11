// src/lib/cli-handoff.ts
function shellQuote(value) {
  if (/^[A-Za-z0-9_/:.=?&%+@,;#~-]+$/.test(value)) {
    return value;
  }
  return `'${value.replace(/'/g, `'"'"'`)}'`;
}
function normalizeCliHandoffCommand(command) {
  const trimmed = String(command || "").trim();
  if (!trimmed || !/^mdtero\s+parse\b/.test(trimmed)) {
    return trimmed;
  }
  const isFileParse = /^mdtero\s+parse\s+--file\b/.test(trimmed);
  const timeout = isFileParse ? 600 : 300;
  const withoutTraceOnly = trimmed.replace(/\s+--trace(?!\S)/g, "");
  const withoutJson = withoutTraceOnly.replace(/\s+--json(?!\S)/g, "");
  const withoutTimeout = withoutJson.replace(/\s+--timeout\s+\S+/g, "").replace(/\s+--interval\s+\S+/g, "");
  const withoutWait = withoutTimeout.replace(/\s+--wait(?!\S)/g, "");
  return `${withoutWait} --trace --wait --timeout ${timeout} --json`;
}
function buildCliParseCommand(input) {
  const normalized = String(input || "").trim();
  if (!normalized) {
    return "";
  }
  if (!/^https?:\/\//i.test(normalized) && !/^10\.\S+/i.test(normalized)) {
    return "";
  }
  return `mdtero parse ${shellQuote(normalized)} --trace --wait --timeout 300 --json`;
}
function buildCliFileParseCommand(filename, artifactKind) {
  const normalized = String(filename || "").trim();
  const extension = inferFileExtension(normalized, artifactKind);
  const path = normalized || `paper.${extension}`;
  return `mdtero parse --file ${shellQuote(path)} --trace --wait --timeout 600 --json`;
}
function inferFileExtension(filename, artifactKind) {
  const normalized = String(filename || "").trim().toLowerCase();
  if (normalized.endsWith(".epub") || artifactKind === "epub") {
    return "epub";
  }
  if (normalized.endsWith(".html") || normalized.endsWith(".htm") || artifactKind === "html") {
    return "html";
  }
  if (normalized.endsWith(".xml") || artifactKind === "xml") {
    return "xml";
  }
  return "pdf";
}

// src/lib/redact.ts
var SENSITIVE_QUERY_KEYS = "(?:api[_-]?key|access[_-]?token|security-token|x-oss-security-token|signature|x-amz-signature|x-amz-credential|ossaccesskeyid|expires|token)";
function redactSensitiveText(value) {
  const text = String(value ?? "");
  if (!text) {
    return "";
  }
  return text.replace(/\b(Bearer|ApiKey)\s+[A-Za-z0-9._~+/=-]+/gi, "$1 [redacted]").replace(/\b(mdtero|mdt)_(secret|live|test|key)_[A-Za-z0-9_-]+/gi, "[redacted-key]").replace(
    new RegExp(`([?&]${SENSITIVE_QUERY_KEYS}=)[^&#\\s"'<>]+`, "gi"),
    "$1[redacted]"
  ).replace(
    new RegExp(`\\b(${SENSITIVE_QUERY_KEYS})(\\s*[:=]\\s*)['"]?[^\\s&'",;]+`, "gi"),
    "$1$2[redacted]"
  ).replace(/https?:\/\/[^\s"'<>]*aliyuncs\.com[^\s"'<>]*/gi, "[redacted-url]").replace(/https?:\/\/[^\s"'<>]*oss-cn-[^\s"'<>]*/gi, "[redacted-url]");
}

// src/lib/api.ts
var MdteroApiError = class extends Error {
  constructor(message, params) {
    super(message);
    this.name = "MdteroApiError";
    this.status = params.status;
    this.reasonCode = params.reasonCode;
    this.actionHint = params.actionHint;
    this.nextCommands = params.nextCommands ?? [];
  }
};
function buildFulltextUploadBody(params) {
  const body = new FormData();
  body.set("paper_file", params.file, params.filename);
  if (params.sourceDoi) {
    body.set("source_doi", params.sourceDoi);
  }
  if (params.sourceInput) {
    body.set("source_input", params.sourceInput);
  }
  if (params.artifactKind) {
    body.set("artifact_kind", params.artifactKind);
  }
  return body;
}
function fallbackArtifactFilename(artifact, preferredFilename) {
  if (preferredFilename && preferredFilename.trim()) {
    return preferredFilename.trim();
  }
  if (artifact === "paper_bundle") return "paper_bundle.zip";
  if (artifact === "paper_md") return "paper.md";
  if (artifact === "paper_pdf") return "paper.pdf";
  if (artifact === "paper_epub") return "paper.epub";
  if (artifact === "paper_html") return "paper.html";
  if (artifact === "paper_xml") return "paper.xml";
  if (artifact === "translated_md") return "translated.md";
  return `${artifact}.bin`;
}
async function readErrorDetail(response) {
  const payload = await response.clone().json().catch(() => null);
  return describeErrorPayload(payload);
}
function describeErrorPayload(payload) {
  if (!payload || typeof payload !== "object") {
    return { message: "", nextCommands: [] };
  }
  const detail = payload.detail;
  if (typeof detail === "string" && detail.trim()) {
    return { message: redactSensitiveText(detail.trim()), nextCommands: [] };
  }
  if (!detail || typeof detail !== "object") {
    return { message: "", nextCommands: [] };
  }
  const parts = [];
  const record = detail;
  const message = firstString(record.error_message, record.message, record.detail);
  const reasonCode = firstString(record.reason_code, record.error_code);
  const actionHint = firstString(record.action_hint);
  const nextCommands = nextCommandsFromErrorDetail(record.next_commands);
  if (message) parts.push(message);
  if (reasonCode) parts.push(`Reason: ${reasonCode}`);
  if (actionHint) parts.push(`Next: ${actionHint}`);
  if (nextCommands.length === 1) {
    parts.push(`Command: ${nextCommands[0]}`);
  } else if (nextCommands.length > 1) {
    parts.push(`Commands: ${nextCommands.map((command, index) => `${index + 1}. ${command}`).join(" ")}`);
  }
  return {
    message: redactSensitiveText(parts.join(" ")),
    reasonCode: reasonCode || void 0,
    actionHint: actionHint ? redactSensitiveText(actionHint) : void 0,
    nextCommands
  };
}
function nextCommandsFromErrorDetail(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  const commands = value.map((command) => normalizeCliHandoffCommand(String(command || "").trim())).filter((command) => command.length > 0);
  return Array.from(new Set(commands));
}
function firstString(...values) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "";
}
function createApiClient(getSettings) {
  async function requireSignedInSettings() {
    const settings = await getSettings();
    if (!settings.token) {
      throw new Error("Sign in required before parsing or translating.");
    }
    return settings;
  }
  function getRuntimeVersion() {
    const runtimeVersion = globalThis.chrome?.runtime?.getManifest?.().version;
    return runtimeVersion ? `extension-${runtimeVersion}` : "extension-dev";
  }
  async function request(path, init, options) {
    const settings = options?.requireAuth ? await requireSignedInSettings() : await getSettings();
    const headers = new Headers(init?.headers ?? {});
    if (!(init?.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (settings.token) {
      headers.set("Authorization", `Bearer ${settings.token}`);
    }
    headers.set("X-Client-Channel", "extension");
    headers.set("X-Client-Version", getRuntimeVersion());
    const response = await fetch(`${settings.apiBaseUrl}${path}`, {
      ...init,
      headers
    });
    if (!response.ok) {
      const detail = await readErrorDetail(response);
      throw new MdteroApiError(detail.message || `API request failed: ${response.status}`, {
        status: response.status,
        reasonCode: detail.reasonCode,
        actionHint: detail.actionHint,
        nextCommands: detail.nextCommands
      });
    }
    return response;
  }
  function extractFilename(contentDisposition, fallback) {
    const match = contentDisposition?.match(/filename="([^"]+)"/i);
    return match?.[1] ?? fallback;
  }
  return {
    getUsage() {
      return request("/me/usage", void 0, { requireAuth: true }).then((response) => response.json());
    },
    getClientConfig() {
      return request("/client-config").then((response) => response.json());
    },
    getMyTasks() {
      return request("/me/tasks", void 0, { requireAuth: true }).then((response) => response.json());
    },
    createParseTask(payload) {
      return request("/api/v1/tasks/parse", {
        method: "POST",
        body: JSON.stringify(payload)
      }, { requireAuth: true }).then((response) => response.json());
    },
    createUploadedParseTask(payload) {
      const body = new FormData();
      const upload = payload.paperFile ?? payload.xmlFile;
      if (!upload) {
        throw new Error("No file was provided for upload.");
      }
      body.set("paper_file", upload, payload.filename ?? "paper.fulltext");
      if (payload.sourceDoi) {
        body.set("source_doi", payload.sourceDoi);
      }
      if (payload.sourceInput) {
        body.set("source_input", payload.sourceInput);
      }
      if (payload.artifactKind) {
        body.set("artifact_kind", payload.artifactKind);
      }
      return request("/api/v1/tasks/upload", {
        method: "POST",
        body
      }, { requireAuth: true }).then((response) => response.json());
    },
    createRawUploadTask(payload) {
      const body = buildFulltextUploadBody({
        file: payload.rawFile,
        filename: payload.filename ?? "paper.fulltext",
        sourceDoi: payload.sourceDoi,
        sourceInput: payload.sourceInput,
        artifactKind: payload.artifactKind
      });
      return request("/api/v1/tasks/upload", {
        method: "POST",
        body
      }, { requireAuth: true }).then((response) => response.json());
    },
    createTranslateTask(payload) {
      return request("/api/v1/tasks/translate", {
        method: "POST",
        body: JSON.stringify(payload)
      }, { requireAuth: true }).then((response) => response.json());
    },
    getTask(taskId) {
      return request(`/api/v1/tasks/${taskId}`, void 0, { requireAuth: true }).then((response) => response.json());
    },
    downloadArtifact(taskId, artifact, preferredFilename) {
      return request(`/api/v1/tasks/${taskId}/download/${artifact}`, void 0, { requireAuth: true }).then(async (response) => ({
        blob: await response.blob(),
        filename: extractFilename(
          response.headers.get("Content-Disposition"),
          fallbackArtifactFilename(artifact, preferredFilename)
        ),
        mediaType: response.headers.get("Content-Type") ?? "application/octet-stream"
      }));
    }
  };
}

// src/lib/auth-bridge.ts
var MDTERO_ACCOUNT_URL = "https://mdtero.com/auth?source=extension";

// src/lib/download.ts
var defaultDeps = {
  createObjectURL(blob) {
    return URL.createObjectURL(blob);
  },
  revokeObjectURL(url) {
    URL.revokeObjectURL(url);
  },
  createAnchor() {
    return document.createElement("a");
  }
};
function triggerBlobDownload(blob, filename, deps = defaultDeps) {
  const objectUrl = deps.createObjectURL(blob);
  try {
    const anchor = deps.createAnchor();
    anchor.href = objectUrl;
    anchor.download = filename;
    anchor.click();
    anchor.remove?.();
  } finally {
    deps.revokeObjectURL(objectUrl);
  }
}

// src/lib/runtime.ts
function createSsotParseMessage(input, pageContext) {
  const message = {
    type: "mdtero.parse.ssot.request",
    input
  };
  if (pageContext) {
    message.pageContext = pageContext;
  }
  return message;
}
function createCurrentHtmlParseMessage(input, pageContext) {
  return {
    type: "mdtero.parse.current_html.request",
    input,
    pageContext
  };
}
function createFileParseMessage(file, artifactKind) {
  const message = {
    type: "mdtero.parse.file.request",
    file,
    filename: file.name,
    mediaType: file.type,
    artifactKind
  };
  return message;
}
function createTranslateMessage(sourceMarkdown, targetLanguage, mode) {
  return {
    type: "mdtero.translate.request",
    sourceMarkdownPath: sourceMarkdown.path || void 0,
    sourceTaskId: sourceMarkdown.taskId || void 0,
    sourceArtifactKey: sourceMarkdown.artifactKey || void 0,
    sourceFilename: sourceMarkdown.filename || void 0,
    targetLanguage,
    mode
  };
}
function createDetectMessage() {
  return {
    type: "mdtero.detect.request"
  };
}

// src/lib/tab-messaging.ts
async function sendTabMessageWithInjection(tabId, message) {
  try {
    return await chrome.tabs.sendMessage(tabId, message);
  } catch (firstError) {
    if (!canInjectContentScript(firstError)) {
      throw firstError;
    }
    await chrome.scripting.executeScript({
      target: { tabId },
      files: [getContentScriptFile()]
    });
    return chrome.tabs.sendMessage(tabId, message);
  }
}
function getContentScriptFile() {
  const scripts = chrome.runtime.getManifest?.().content_scripts || [];
  for (const script of scripts) {
    const firstFile = script.js?.[0];
    if (firstFile && firstFile.includes("content.js")) {
      return firstFile;
    }
  }
  return "content.js";
}
function canInjectContentScript(error) {
  const message = error instanceof Error ? error.message : String(error || "");
  return /receiving end does not exist/i.test(message) || /could not establish connection/i.test(message) || /no tab with id/i.test(message);
}

// ../shared/src/api-contract.ts
var DEFAULT_API_BASE_URL = "https://api.mdtero.com";

// src/lib/storage.ts
var SETTINGS_KEY = "mdtero_settings";
var POPUP_STATE_KEY = "mdtero_popup_state";
var RECENT_TASKS_KEY = "mdtero_recent_tasks";
function resolveUiLanguage(preferred, browserLanguage) {
  if (preferred === "en" || preferred === "zh") {
    return preferred;
  }
  return browserLanguage?.toLowerCase().startsWith("zh") ? "zh" : "en";
}
async function readSettings() {
  const stored = await chrome.storage.local.get(SETTINGS_KEY);
  const current = stored[SETTINGS_KEY] ?? { apiBaseUrl: DEFAULT_API_BASE_URL };
  return {
    apiBaseUrl: current.apiBaseUrl ?? DEFAULT_API_BASE_URL,
    token: current.token,
    email: current.email,
    uiLanguage: resolveUiLanguage(current.uiLanguage, globalThis.navigator?.language)
  };
}
async function writeSettings(next) {
  await chrome.storage.local.set({ [SETTINGS_KEY]: next });
}
async function readPopupState() {
  const stored = await chrome.storage.local.get(POPUP_STATE_KEY);
  return stored[POPUP_STATE_KEY];
}
async function writePopupState(next) {
  await chrome.storage.local.set({ [POPUP_STATE_KEY]: next });
}
async function readRecentTasks() {
  const stored = await chrome.storage.local.get(RECENT_TASKS_KEY);
  return stored[RECENT_TASKS_KEY] ?? [];
}
async function writeRecentTasks(next) {
  await chrome.storage.local.set({ [RECENT_TASKS_KEY]: next });
}
function upsertRecentTasks(current, next, limit = 5) {
  const deduped = current.filter((item) => item.input !== next.input);
  return [next, ...deduped].slice(0, limit);
}
function getPendingPopupTask(state, detectedInput) {
  if (!state || state.input !== detectedInput || !state.pendingTaskId || !state.pendingTaskKind) {
    return void 0;
  }
  return {
    taskId: state.pendingTaskId,
    kind: state.pendingTaskKind
  };
}
function getReconnectablePendingTranslationTask(state, detectedInput, parseMarkdownRef) {
  const stateMarkdownRef = state?.parseMarkdownPath || state?.parseMarkdownTaskId;
  if (!state || state.input !== detectedInput || state.pendingTaskKind !== "translate" || !state.pendingTaskId || stateMarkdownRef !== parseMarkdownRef) {
    return void 0;
  }
  return {
    taskId: state.pendingTaskId,
    kind: "translate"
  };
}

// src/lib/supported-page.ts
var SUPPORTED_PAPER_URL_PATTERNS = [
  "arxiv.org",
  "dl.acm.org",
  "ieeexplore.ieee.org",
  "nature.com",
  "pubs.acs.org",
  "pubs.rsc.org",
  "sciencedirect.com/science/article/pii/",
  "techrxiv.org",
  "link.springer.com",
  "mdpi.com",
  "springer.com",
  "springernature.com",
  "onlinelibrary.wiley.com",
  "tandfonline.com"
];
function isSupportedPaperPage(url) {
  const normalized = String(url || "").trim().toLowerCase();
  return SUPPORTED_PAPER_URL_PATTERNS.some((pattern) => normalized.includes(pattern));
}

// src/popup/task-view.ts
var SECONDARY_ORDER = ["paper_md", "paper_bundle", "translated_md"];
var SOURCE_ORDER = ["paper_pdf", "paper_epub", "paper_html", "paper_xml"];
function getArtifactKeys(result) {
  const keyed = Object.keys(result?.artifacts ?? {});
  const listed = (result?.download_artifacts ?? []).map((artifact) => String(artifact.artifact || "").trim()).filter((artifact) => artifact.length > 0);
  return Array.from(/* @__PURE__ */ new Set([...keyed, ...listed]));
}
function getArtifactFilename(result, artifactKey) {
  return result?.artifacts?.[artifactKey]?.filename || result?.download_artifacts?.find((artifact) => artifact.artifact === artifactKey)?.filename;
}
function getPreferredArtifactKey(result) {
  const artifactKeys = getArtifactKeys(result);
  if (artifactKeys.length === 0) {
    return void 0;
  }
  if (result?.preferred_artifact && artifactKeys.includes(result.preferred_artifact)) {
    return result.preferred_artifact;
  }
  return artifactKeys[0];
}
function getSecondaryArtifactKeys(result) {
  const preferred = getPreferredArtifactKey(result);
  const artifactKeys = getArtifactKeys(result);
  return SECONDARY_ORDER.filter(
    (key) => artifactKeys.includes(key) && key !== preferred
  );
}
function getSourceArtifactKeys(result) {
  const artifactKeys = getArtifactKeys(result);
  return SOURCE_ORDER.filter((key) => artifactKeys.includes(key));
}
function getTaskProcessingSummary(task, language = "en") {
  const result = task?.result;
  const provider = firstPresentString(task?.selected_provider, result?.selected_provider);
  const strategy = firstPresentString(task?.parser_strategy, result?.parser_strategy);
  const acquisition = summarizeClientAcquisition(task?.client_acquisition || result?.client_acquisition);
  const outcome = summarizeParseOutcome(task?.parse_outcome || result?.parse_outcome);
  const reason = firstPresentString(task?.reason_code, result?.reason_code);
  const actionHint = firstPresentString(task?.action_hint, result?.action_hint);
  const preferredArtifact = firstPresentString(task?.preferred_artifact, result?.preferred_artifact);
  const artifacts = summarizeDownloadArtifacts(result);
  const lines = [];
  if (provider || strategy) {
    const value = [provider, strategy].filter(Boolean).join(" \xB7 ");
    lines.push(language === "zh" ? `\u5904\u7406\u8DEF\u5F84\uFF1A${value}` : `Processing path: ${value}`);
  }
  if (acquisition) {
    lines.push(language === "zh" ? `\u672C\u5730/\u6D4F\u89C8\u5668\u6293\u53D6\uFF1A${acquisition}` : `Acquisition: ${acquisition}`);
  }
  if (outcome) {
    lines.push(language === "zh" ? `\u89E3\u6790\u7ED3\u679C\uFF1A${outcome}` : `Outcome: ${outcome}`);
  }
  if (preferredArtifact) {
    lines.push(language === "zh" ? `\u9996\u9009\u4EA7\u7269\uFF1A${preferredArtifact}` : `Preferred artifact: ${preferredArtifact}`);
  }
  if (artifacts) {
    lines.push(language === "zh" ? `\u53EF\u4E0B\u8F7D\uFF1A${artifacts}` : `Downloads: ${artifacts}`);
  }
  if (reason) {
    lines.push(language === "zh" ? `\u539F\u56E0\uFF1A${reason}` : `Reason: ${reason}`);
  }
  if (actionHint) {
    lines.push(language === "zh" ? `\u4E0B\u4E00\u6B65\uFF1A${redactSensitiveText(actionHint)}` : `Next: ${redactSensitiveText(actionHint)}`);
  }
  return lines.map(redactSensitiveText).filter(Boolean);
}
function getDownloadLabel(artifactKey, language = "en") {
  if (language === "zh") {
    if (artifactKey === "paper_md") {
      return "\u4E0B\u8F7D Markdown";
    }
    if (artifactKey === "paper_bundle") {
      return "\u4E0B\u8F7D\u538B\u7F29\u5305";
    }
    if (artifactKey === "translated_md") {
      return "\u4E0B\u8F7D\u8BD1\u6587";
    }
    if (artifactKey === "paper_pdf") {
      return "\u4E0B\u8F7D PDF";
    }
    if (artifactKey === "paper_epub") {
      return "\u4E0B\u8F7D EPUB";
    }
    if (artifactKey === "paper_html") {
      return "\u4E0B\u8F7D HTML";
    }
    if (artifactKey === "paper_xml") {
      return "\u4E0B\u8F7D XML";
    }
    return "\u4E0B\u8F7D\u6587\u4EF6";
  }
  if (artifactKey === "paper_md") {
    return "Download Markdown";
  }
  if (artifactKey === "paper_bundle") {
    return "Download ZIP";
  }
  if (artifactKey === "translated_md") {
    return "Download Translation";
  }
  if (artifactKey === "paper_pdf") {
    return "Download PDF";
  }
  if (artifactKey === "paper_epub") {
    return "Download EPUB";
  }
  if (artifactKey === "paper_html") {
    return "Download HTML";
  }
  if (artifactKey === "paper_xml") {
    return "Download XML";
  }
  return "Download File";
}
function getActionStatusText(kind, language = "en") {
  if (language === "zh") {
    if (kind === "detecting") {
      return "\u6B63\u5728\u8BC6\u522B\u5F53\u524D\u9875\u9762\u7684 DOI...";
    }
    if (kind === "queued_parse") {
      return "\u89E3\u6790\u4EFB\u52A1\u5DF2\u63D0\u4EA4\uFF0C\u6B63\u5728\u51C6\u5907\u6587\u4EF6...";
    }
    if (kind === "running_parse") {
      return "\u6B63\u5728\u89E3\u6790\u8BBA\u6587\u5E76\u51C6\u5907 Markdown...";
    }
    if (kind === "queued_translate") {
      return "\u7FFB\u8BD1\u4EFB\u52A1\u5DF2\u63D0\u4EA4\uFF0C\u6B63\u5728\u51C6\u5907...";
    }
    if (kind === "running_translate") {
      return "\u6B63\u5728\u7FFB\u8BD1 Markdown...";
    }
    return "\u5904\u7406\u5931\u8D25\uFF0C\u8BF7\u91CD\u8BD5\u3002";
  }
  if (kind === "detecting") {
    return "Detecting DOI from this page...";
  }
  if (kind === "queued_parse") {
    return "Parse request sent. Preparing files...";
  }
  if (kind === "running_parse") {
    return "Parsing paper and preparing Markdown...";
  }
  if (kind === "queued_translate") {
    return "Translation request sent. Preparing text...";
  }
  if (kind === "running_translate") {
    return "Translating Markdown...";
  }
  return "Something went wrong. Please try again.";
}
function getUsageStatusText(usage, language = "en", errorMessage) {
  if (errorMessage?.trim()) {
    return redactSensitiveText(errorMessage.trim());
  }
  const wallet = usage?.wallet_balance_display?.trim() || (language === "zh" ? "\xA50.00" : "$0.00");
  const parse = Number.isFinite(usage?.parse_quota_remaining) ? Number(usage?.parse_quota_remaining) : 0;
  const translation = Number.isFinite(usage?.translation_quota_remaining) ? Number(usage?.translation_quota_remaining) : 0;
  return language === "zh" ? `\u4F59\u989D ${wallet} \xB7 \u89E3\u6790 ${parse} \xB7 \u7FFB\u8BD1 ${translation}` : `Balance ${wallet} \xB7 Parse ${parse} \xB7 Translation ${translation}`;
}
function getPreflightHintText(params, language = "en") {
  const input = String(params.input || "").trim();
  const pageUrl = String(params.pageUrl || "").trim();
  const bridgeState = String(params.bridgeStatus?.state || "").trim().toLowerCase();
  const bridgeReady = bridgeState === "connected";
  const bridgeMissing = bridgeState === "unavailable" || bridgeState === "disconnected";
  const candidate = pageUrl || input;
  const livePageSupported = isSupportedPaperPage(candidate);
  const looksLikePdfShell = candidate.includes("/pdf") || candidate.includes("/epdf") || candidate.includes("download=true") || candidate.includes("/epub/");
  if (looksLikePdfShell) {
    return language === "zh" ? "\u5F53\u524D\u66F4\u50CF PDF/EPUB \u9875\u9762\u3002\u5EFA\u8BAE\u76F4\u63A5\u4E0A\u4F20 PDF/EPUB\uFF0C\u6216\u5148\u5207\u5230 HTML \u6B63\u6587\u9875\u3002" : "This looks like a PDF/EPUB page. Upload the PDF/EPUB directly or open the HTML full-text page first.";
  }
  if (!livePageSupported) {
    return "";
  }
  if (bridgeMissing) {
    return language === "zh" ? "\u5F53\u524D\u9875\u9762\u53EF\u7531\u6269\u5C55\u8BFB\u53D6\u3002\u82E5\u76F4\u8FDE\u5931\u8D25\uFF0C\u8BF7\u4E0A\u4F20 PDF/EPUB\uFF0C\u6216\u5728\u7EC8\u7AEF\u7528 `mdtero parse` \u7EE7\u7EED\u3002" : "The extension can read this page. If direct routing fails, upload the PDF/EPUB or continue with `mdtero parse` in the terminal.";
  }
  if (bridgeReady) {
    return language === "zh" ? "\u5F53\u524D\u9875\u9762\u53EF\u7531\u6269\u5C55\u8BFB\u53D6\uFF0C\u5E76\u5728\u9700\u8981\u65F6\u4E0A\u4F20\u7ED9 Mdtero \u89E3\u6790\u3002" : "This page can be read by the extension and uploaded to Mdtero when needed.";
  }
  return language === "zh" ? "\u5F53\u524D\u9875\u9762\u652F\u6301\u6269\u5C55\u8BFB\u53D6\u3002\u89E3\u6790\u524D\u8BF7\u786E\u8BA4\u9875\u9762\u6B63\u6587\u5DF2\u7ECF\u52A0\u8F7D\u3002" : "This page supports extension capture. Confirm the article body has loaded before parsing.";
}
function shouldShowCliHandoffForPreflight(hint, input) {
  const normalizedHint = String(hint || "").trim().toLowerCase();
  if (!buildCliParseCommand(input)) {
    return false;
  }
  return normalizedHint.includes("mdtero parse") || normalizedHint.includes("cli") || normalizedHint.includes("\u7EC8\u7AEF");
}
function getCliHandoffNote(command, language = "en") {
  const normalized = String(command || "").trim();
  if (!normalized) {
    return "";
  }
  if (language === "zh") {
    if (/^mdtero\s+parse\s+--file\b/.test(normalized)) {
      return "\u5728\u7EC8\u7AEF\u7EE7\u7EED\u4E0A\u4F20\u672C\u5730\u6587\u4EF6\uFF1B\u590D\u5236\u547D\u4EE4\u540E\u628A\u6587\u4EF6\u8DEF\u5F84\u66FF\u6362\u4E3A\u4F60\u7684 PDF/EPUB\u3002";
    }
    return "\u5728\u7EC8\u7AEF\u7EE7\u7EED\u89E3\u6790\uFF1B\u9002\u5408\u6821\u56ED\u7F51\u3001\u53CD\u722C\u6311\u6218\u9875\u6216\u9700\u8981\u672C\u673A\u4F9D\u8D56\u7684\u8865\u6293\u53D6\u573A\u666F\u3002";
  }
  if (/^mdtero\s+parse\s+--file\b/.test(normalized)) {
    return "Continue local file upload in the terminal; replace the path with your PDF/EPUB.";
  }
  return "Continue parsing in the terminal; useful for campus networks, challenge pages, or local acquisition dependencies.";
}
function getSavedResultSummary(state, language = "en") {
  const filename = state?.translatedFilename ?? state?.parseFilename;
  if (!filename) {
    return "";
  }
  return language === "zh" ? `\u5DF2\u5C31\u7EEA\uFF1A${filename}` : `Ready: ${filename}`;
}
function getResultWarningText(result, language = "en") {
  if (!result) {
    return "";
  }
  if (result.warning_code === "publisher_abstract_only" || result.warning_code === "elsevier_abstract_only") {
    return language === "zh" ? "\u5F53\u524D\u6765\u6E90\u4EC5\u8FD4\u56DE\u6458\u8981\u3002\u8BF7\u786E\u8BA4\u6D4F\u89C8\u5668\u5DF2\u767B\u5F55\u673A\u6784\u8D44\u6E90\u3001\u5904\u4E8E\u6821\u56ED\u7F51/\u673A\u6784 IP\uFF0C\u6216\u6539\u4E3A\u4E0A\u4F20 PDF/XML/EPUB\u3002" : "The source only returned an abstract. Confirm your browser has institutional access, use a campus/IP session, or upload the PDF/XML/EPUB directly.";
  }
  return redactSensitiveText(result.warning_message ?? "");
}
function getTaskFailureText(task, fallback, language = "en") {
  const message = redactSensitiveText(task?.error_message?.trim() || fallback);
  const reason = (task?.reason_code || task?.result?.reason_code || task?.error_code || "").trim();
  const actionHint = redactSensitiveText((task?.action_hint || task?.result?.action_hint || "").trim());
  const parts = [message];
  if (reason) {
    parts.push(language === "zh" ? `\u539F\u56E0\uFF1A${reason}` : `Reason: ${reason}`);
  }
  if (actionHint) {
    parts.push(language === "zh" ? `\u4E0B\u4E00\u6B65\uFF1A${actionHint}` : `Next: ${actionHint}`);
  }
  const attempts = getTranslationAttemptSummary(task?.result?.translation_attempts, language);
  if (attempts) {
    parts.push(attempts);
  }
  const nextCommand = firstTaskNextCommand(task);
  if (nextCommand) {
    parts.push(language === "zh" ? `\u547D\u4EE4\uFF1A${nextCommand}` : `Command: ${nextCommand}`);
  }
  return parts.join(" ");
}
function getDownloadFailureText(error, fallback, language = "en") {
  const message = redactSensitiveText(
    error instanceof Error ? error.message : String(error || "")
  ).trim();
  if (!message) {
    return fallback;
  }
  return language === "zh" ? `${fallback} \u8BE6\u60C5\uFF1A${message}` : `${fallback} Detail: ${message}`;
}
function getTranslationAttemptSummary(attempts, language = "en") {
  const items = (attempts ?? []).map((attempt) => {
    const provider = String(attempt?.provider || "provider").trim();
    const reason = String(attempt?.reason_code || attempt?.provider_error_code || "failed").trim();
    const statusCode = attempt?.provider_status_code;
    const status = typeof statusCode === "number" ? String(statusCode) : String(attempt?.status || "").trim();
    const message = redactSensitiveText(String(attempt?.message || "").trim());
    const details = [status, message].filter(Boolean).join(" ");
    return `${provider}: ${reason}${details ? ` ${details}` : ""}`;
  }).filter(Boolean);
  if (!items.length) {
    return "";
  }
  return language === "zh" ? `\u670D\u52A1\u7AEF\u5C1D\u8BD5\uFF1A${items.join("; ")}` : `Provider attempts: ${items.join("; ")}`;
}
function firstTaskNextCommand(task) {
  return firstNextCommand([...task?.next_commands ?? [], ...task?.result?.next_commands ?? []]);
}
function firstNextCommand(commands) {
  const command = (commands ?? []).map((value) => String(value || "").trim()).find(Boolean) || "";
  return normalizeCliHandoffCommand(command);
}
function buildApiErrorCliHandoffPlan(error, input, kind = "parse") {
  if (!error || typeof error !== "object") {
    return buildTaskFailureCliHandoffPlan(null, input, kind);
  }
  const nextCommands = Array.isArray(error.nextCommands) ? error.nextCommands : [];
  return buildTaskFailureCliHandoffPlan({ next_commands: nextCommands }, input, kind);
}
function buildApiErrorHandoffContext(error, kind) {
  if (!error || typeof error !== "object") {
    return null;
  }
  const apiError = error;
  const nextCommands = Array.isArray(apiError.nextCommands) ? apiError.nextCommands : [];
  if (!apiError.reasonCode && !apiError.actionHint && nextCommands.length === 0) {
    return null;
  }
  return {
    kind,
    reasonCode: apiError.reasonCode,
    actionHint: apiError.actionHint,
    nextCommands: normalizeCommandList(nextCommands)
  };
}
var PARSE_HANDOFF_FOLLOWUPS = [
  "mdtero status <task-id> --wait --timeout 300 --json",
  "mdtero download <task-id> paper_md --output-dir ./mdtero-output --json",
  "mdtero project ingest --json",
  "mdtero project refresh --wait --timeout 300 --json",
  'mdtero rag query "What are the strongest findings?" --build-if-needed --json',
  "mdtero rag status --json",
  "mdtero rag build --wait --json",
  'mdtero rag query "<question>" --build-if-needed --json',
  "mdtero mcp briefing --json",
  "mdtero mcp serve"
];
function buildCliHandoffCommandPlan(primaryCommand, planCommands) {
  const commands = normalizeCommandList([primaryCommand, ...planCommands ?? []]);
  const primary = commands[0] || "";
  if (!/^mdtero\s+parse\b/.test(primary)) {
    return commands;
  }
  const statusCommands = commands.filter((command) => /^mdtero\s+status\b/.test(command));
  const downloadCommands = commands.filter((command) => /^mdtero\s+download\b/.test(command));
  const ingestCommands = commands.filter((command) => command === "mdtero project ingest --json");
  const projectRefreshCommands = commands.filter((command) => command === "mdtero project refresh --wait --timeout 300 --json");
  const ragBootstrapCommands = commands.filter((command) => command === PARSE_HANDOFF_FOLLOWUPS[4]);
  const ragStatusCommands = commands.filter((command) => command === "mdtero rag status --json");
  const ragBuildCommands = commands.filter((command) => command === "mdtero rag build --wait --json");
  const ragQueryCommands = commands.filter((command) => /^mdtero\s+rag\s+query\b/.test(command));
  const genericRagQueryCommands = ragQueryCommands.filter((command) => command !== PARSE_HANDOFF_FOLLOWUPS[4]);
  const mcpBriefingCommands = commands.filter((command) => command === "mdtero mcp briefing --json");
  const mcpServeCommands = commands.filter((command) => command === "mdtero mcp serve");
  const otherCommands = commands.filter(
    (command) => command !== primary && !/^mdtero\s+status\b/.test(command) && !/^mdtero\s+download\b/.test(command) && command !== "mdtero project ingest --json" && command !== "mdtero project refresh --wait --timeout 300 --json" && command !== "mdtero rag build --wait --json" && command !== "mdtero rag status --json" && !/^mdtero\s+rag\s+query\b/.test(command) && command !== "mdtero mcp briefing --json" && command !== "mdtero mcp serve"
  );
  return normalizeCommandList([
    primary,
    ...statusCommands.length ? statusCommands : [PARSE_HANDOFF_FOLLOWUPS[0]],
    ...downloadCommands.length ? downloadCommands : [PARSE_HANDOFF_FOLLOWUPS[1]],
    ...ingestCommands.length ? ingestCommands : [PARSE_HANDOFF_FOLLOWUPS[2]],
    ...projectRefreshCommands.length ? projectRefreshCommands : [PARSE_HANDOFF_FOLLOWUPS[3]],
    ...ragBootstrapCommands.length ? ragBootstrapCommands : [PARSE_HANDOFF_FOLLOWUPS[4]],
    ...ragStatusCommands.length ? ragStatusCommands : [PARSE_HANDOFF_FOLLOWUPS[5]],
    ...ragBuildCommands.length ? ragBuildCommands : [PARSE_HANDOFF_FOLLOWUPS[6]],
    ...genericRagQueryCommands.length ? genericRagQueryCommands : [PARSE_HANDOFF_FOLLOWUPS[7]],
    ...mcpBriefingCommands.length ? mcpBriefingCommands : [PARSE_HANDOFF_FOLLOWUPS[8]],
    ...mcpServeCommands.length ? mcpServeCommands : [PARSE_HANDOFF_FOLLOWUPS[9]],
    ...otherCommands
  ]);
}
function formatCliHandoffClipboard(primaryCommand, planCommands, context) {
  const commands = buildCliHandoffCommandPlan(primaryCommand, planCommands);
  if (commands.length <= 1) {
    return commands[0] || "";
  }
  const parseHandoff = /^mdtero\s+parse\b/.test(commands[0] || "");
  const contextLines = parseHandoff ? formatHandoffContextLines(context) : [];
  return [
    "# Mdtero CLI handoff",
    "",
    ...parseHandoff ? [
      "Use this when browser capture, publisher session access, campus-network routing, or local file upload needs to continue in the Python CLI or local agent.",
      "Preserve task_id, selected_provider, parser_strategy, reason_code, action_hint, client_acquisition, parse_outcome, download_artifacts, preferred_artifact, and next_commands when reporting results back to the browser or dashboard.",
      ""
    ] : [],
    ...contextLines.length ? ["Failure context for agent:", ...contextLines, ""] : [],
    "Run these commands in order:",
    ...commands.map((command, index) => `${index + 1}. ${command}`),
    ...parseHandoff ? [
      "",
      "Agent handoff:",
      "- Start with `mdtero mcp briefing --json` after parse/download so the local agent sees project status, RAG readiness, and extension_handoff.",
      "- Start `mdtero mcp serve` from the local project root when the agent needs live FastMCP stdio tools.",
      "- When `mcp_tool_plan` says `build_rag_index`, call `server_rag_build(wait=true)` before `rag_query(question)`.",
      '- Use `mdtero rag query "<question>" --build-if-needed --json` only after at least one Markdown artifact exists or the command can bootstrap one.',
      "- Preserve `citation_contract.required_for_final_answer`; final RAG answers must keep `citations` and `source_nodes` alongside the prose answer."
    ] : []
  ].join("\n");
}
function buildTaskHandoffContext(task, kind) {
  const downloadArtifacts = (task?.result?.download_artifacts ?? []).map((artifact) => {
    const name = String(artifact.artifact || "").trim();
    const filename = String(artifact.filename || "").trim();
    return [name, filename].filter(Boolean).join(": ");
  }).filter(Boolean);
  return {
    taskId: task?.task_id,
    status: task?.status,
    stage: task?.stage,
    kind: task?.task_kind ?? kind,
    selectedProvider: firstPresentString(task?.selected_provider, task?.result?.selected_provider),
    parserStrategy: firstPresentString(task?.parser_strategy, task?.result?.parser_strategy),
    clientAcquisition: summarizeObjectForHandoff(task?.client_acquisition || task?.result?.client_acquisition),
    parseOutcome: summarizeObjectForHandoff(task?.parse_outcome || task?.result?.parse_outcome),
    reasonCode: task?.reason_code || task?.result?.reason_code || void 0,
    actionHint: task?.action_hint || task?.result?.action_hint || void 0,
    preferredArtifact: task?.preferred_artifact || task?.result?.preferred_artifact || void 0,
    downloadArtifacts,
    nextCommands: normalizeCommandList([...task?.next_commands ?? [], ...task?.result?.next_commands ?? []])
  };
}
function formatHandoffContextLines(context) {
  if (!context) {
    return [];
  }
  const lines = [];
  appendContextLine(lines, "task_id", context.taskId);
  appendContextLine(lines, "status", context.status);
  appendContextLine(lines, "stage", context.stage);
  appendContextLine(lines, "kind", context.kind);
  appendContextLine(lines, "selected_provider", context.selectedProvider);
  appendContextLine(lines, "parser_strategy", context.parserStrategy);
  appendContextLine(lines, "client_acquisition", context.clientAcquisition);
  appendContextLine(lines, "parse_outcome", context.parseOutcome);
  appendContextLine(lines, "reason_code", context.reasonCode);
  appendContextLine(lines, "action_hint", context.actionHint);
  appendContextLine(lines, "preferred_artifact", context.preferredArtifact);
  appendContextList(lines, "download_artifacts", context.downloadArtifacts);
  appendContextList(lines, "next_commands", context.nextCommands);
  return lines;
}
function firstPresentString(...values) {
  for (const value of values) {
    const normalized = String(value || "").trim();
    if (normalized) {
      return normalized;
    }
  }
  return void 0;
}
function summarizeClientAcquisition(value) {
  if (!value || typeof value !== "object") {
    return void 0;
  }
  const record = value;
  const source = firstPresentString(record.source);
  const artifactKind = firstPresentString(record.artifact_kind, record.kind);
  const statusCode = firstPresentString(record.status_code);
  const contentType = firstPresentString(record.content_type);
  const parts = [source, artifactKind, statusCode ? `HTTP ${statusCode}` : void 0, contentType].filter(Boolean);
  return parts.length ? parts.join(" \xB7 ") : summarizeObjectForHandoff(value);
}
function summarizeParseOutcome(value) {
  if (!value || typeof value !== "object") {
    return void 0;
  }
  const record = value;
  const outcome = firstPresentString(record.outcome_code, record.outcome, record.status);
  const reason = firstPresentString(record.reason_code);
  const parts = [outcome, reason].filter(Boolean);
  return parts.length ? parts.join(" \xB7 ") : summarizeObjectForHandoff(value);
}
function summarizeDownloadArtifacts(result) {
  const listed = (result?.download_artifacts ?? []).map((artifact) => {
    const name = firstPresentString(artifact.artifact);
    const filename = firstPresentString(artifact.filename);
    return [name, filename].filter(Boolean).join(": ");
  }).filter(Boolean);
  const keyed = Object.entries(result?.artifacts ?? {}).map(([artifact, descriptor]) => [artifact, descriptor?.filename].filter(Boolean).join(": ")).filter(Boolean);
  const artifacts = Array.from(/* @__PURE__ */ new Set([...listed, ...keyed]));
  return artifacts.length ? artifacts.join("; ") : void 0;
}
function summarizeObjectForHandoff(value) {
  if (!value || typeof value !== "object") {
    return void 0;
  }
  const entries = Object.entries(value).filter(([key, item]) => key.length > 0 && item !== null && item !== void 0 && item !== "").slice(0, 12).map(([key, item]) => `${key}=${String(item)}`);
  return entries.length ? entries.join(", ") : void 0;
}
function appendContextLine(lines, label, value) {
  const normalized = redactSensitiveText(String(value || "").trim());
  if (normalized) {
    lines.push(`- ${label}: ${normalized}`);
  }
}
function appendContextList(lines, label, values) {
  const normalized = normalizeCommandList(values).map(redactSensitiveText);
  if (normalized.length) {
    lines.push(`- ${label}: ${normalized.join("; ")}`);
  }
}
function buildTaskFailureCliHandoffPlan(task, input, kind = "parse") {
  const taskCommands = normalizeCommandList(task?.next_commands);
  if (taskCommands.length > 0) {
    return {
      primaryCommand: taskCommands[0],
      commands: buildCliHandoffCommandPlan(taskCommands[0], taskCommands),
      source: "backend_task",
      kind
    };
  }
  const resultCommands = normalizeCommandList(task?.result?.next_commands);
  if (resultCommands.length > 0) {
    return {
      primaryCommand: resultCommands[0],
      commands: buildCliHandoffCommandPlan(resultCommands[0], resultCommands),
      source: "backend_result",
      kind
    };
  }
  const fallback = kind === "parse" ? buildCliParseCommand(input) : "";
  if (fallback) {
    return {
      primaryCommand: fallback,
      commands: buildCliHandoffCommandPlan(fallback),
      source: "fallback_parse",
      kind
    };
  }
  return {
    primaryCommand: "",
    commands: [],
    source: "none",
    kind
  };
}
function normalizeCommandList(commands) {
  const normalized = (commands ?? []).map((value) => normalizeCliHandoffCommand(String(value || "").trim())).filter((value) => value.length > 0);
  return Array.from(new Set(normalized));
}

// src/popup/index.ts
var COPY = {
  en: {
    title: "Mdtero",
    subtitle: "Paper parsing connected to Mdtero Account",
    guest: "Guest mode",
    signedIn: (email) => email,
    usageSummary: (wallet, parse, translation) => `Balance ${wallet} \xB7 Parse ${parse} \xB7 Translation ${translation}`,
    signInHint: "Sign in through website OAuth at mdtero.com/auth, then return here to parse, translate, and download.",
    signInButton: "Open website OAuth",
    connectionPillSignedOut: "Website OAuth",
    connectionPillSignedIn: "Connected",
    workflowAuth: "Login",
    workflowParse: "Parse / Upload",
    workflowTranslate: "Translate",
    workflowDownload: "Download",
    workflowPending: "next",
    workflowActive: "active",
    workflowDone: "done",
    inputLabel: "DOI or live page",
    inputPlaceholder: "10.1016/...",
    fileIntakeTitle: "Local file intake",
    fileIntakeNote: "Use this when you already have a local PDF, EPUB, or saved HTML page. Uploads are parsed by the Mdtero backend automatically.",
    pickPdfButton: "Use PDF",
    pickEpubButton: "Use EPUB",
    fileNameEmpty: "No local file selected.",
    localFileParsing: (filename) => `Uploading ${filename}; Mdtero will create a parse task and poll it here...`,
    localFileParseFailed: "Local file parse failed. Please try again.",
    parseButton: "Parse Paper",
    captureHtmlButton: "Capture HTML",
    captureHtmlParsing: "Capturing HTML...",
    captureHtmlHint: "Use this on a loaded full-text article page. Mdtero uploads the sanitized page HTML through the dedicated HTML parser path.",
    parsingButton: "Parsing...",
    settingsButton: "Settings",
    translateLabel: "Translate to",
    translateButton: "Translate",
    translatingButton: "Translating...",
    chinese: "Chinese",
    english: "English",
    spanish: "Spanish",
    french: "French",
    german: "German",
    japanese: "Japanese",
    korean: "Korean",
    russian: "Russian",
    turkish: "Turkish",
    arabic: "Arabic",
    sourceFiles: "Source files",
    recentTasks: "Recent items",
    noRecentTasks: "No recent papers yet.",
    openPaper: "Reuse input",
    enterDoi: "Enter a DOI or use the detected paper page first.",
    translateFirst: "Parse a paper to Markdown first; translation uses that paper_md artifact path.",
    parseReady: (filename) => `Markdown ready: ${filename}. Download it or translate from the parsed Markdown.`,
    translateReady: (filename) => `Translation ready: ${filename}.`,
    parseFailed: "Parse failed. Please try again.",
    translationFailed: "Translation failed. Please try again.",
    detected: (kind) => `Detected ${kind}.`,
    noDoi: "No DOI detected. Paste one manually.",
    noActiveTab: "No active tab available.",
    downloadFailed: "Download failed. Please try again.",
    copyCliCommand: "Copy handoff",
    cliCommandCopied: "CLI handoff copied."
  },
  zh: {
    title: "Mdtero",
    subtitle: "\u8FDE\u63A5 Mdtero \u8D26\u6237\u7684\u672C\u5730\u8BBA\u6587\u89E3\u6790",
    guest: "\u6E38\u5BA2\u6A21\u5F0F",
    signedIn: (email) => email,
    usageSummary: (wallet, parse, translation) => `\u4F59\u989D ${wallet} \xB7 \u89E3\u6790 ${parse} \xB7 \u7FFB\u8BD1 ${translation}`,
    signInHint: "\u8BF7\u901A\u8FC7 mdtero.com/auth \u7684\u7F51\u9875\u767B\u5F55\u6388\u6743\u6269\u5C55\uFF0C\u7136\u540E\u56DE\u5230\u8FD9\u91CC\u89E3\u6790\u3001\u7FFB\u8BD1\u548C\u4E0B\u8F7D\u3002",
    signInButton: "\u6253\u5F00\u7F51\u9875\u767B\u5F55",
    connectionPillSignedOut: "\u7F51\u9875\u767B\u5F55",
    connectionPillSignedIn: "\u5DF2\u8FDE\u63A5",
    workflowAuth: "\u767B\u5F55",
    workflowParse: "\u89E3\u6790 / \u4E0A\u4F20",
    workflowTranslate: "\u7FFB\u8BD1",
    workflowDownload: "\u4E0B\u8F7D",
    workflowPending: "\u4E0B\u4E00\u6B65",
    workflowActive: "\u8FDB\u884C\u4E2D",
    workflowDone: "\u5B8C\u6210",
    inputLabel: "DOI \u6216\u5B9E\u65F6\u9875\u9762",
    inputPlaceholder: "10.1016/...",
    fileIntakeTitle: "\u672C\u5730\u6587\u4EF6\u5165\u53E3",
    fileIntakeNote: "\u5982\u679C\u4F60\u624B\u91CC\u5DF2\u7ECF\u6709 PDF\u3001EPUB \u6216\u4FDD\u5B58\u7684 HTML \u9875\u9762\uFF0C\u4E5F\u53EF\u4EE5\u7EE7\u7EED\u8D70\u540C\u4E00\u6761 Markdown \u89E3\u6790\u94FE\u3002\u4E0A\u4F20\u540E\u7531\u540E\u7AEF\u81EA\u52A8\u89E3\u6790\u3002",
    pickPdfButton: "\u9009\u62E9 PDF",
    pickEpubButton: "\u9009\u62E9 EPUB",
    fileNameEmpty: "\u5C1A\u672A\u9009\u62E9\u672C\u5730\u6587\u4EF6\u3002",
    localFileParsing: (filename) => `\u6B63\u5728\u4E0A\u4F20 ${filename}\uFF0C\u540E\u7AEF\u4F1A\u521B\u5EFA\u89E3\u6790\u4EFB\u52A1\u5E76\u5728\u8FD9\u91CC\u8F6E\u8BE2...`,
    localFileParseFailed: "\u672C\u5730\u6587\u4EF6\u89E3\u6790\u5931\u8D25\uFF0C\u8BF7\u91CD\u8BD5\u3002",
    parseButton: "\u89E3\u6790\u8BBA\u6587",
    captureHtmlButton: "\u91C7\u96C6 HTML",
    captureHtmlParsing: "\u91C7\u96C6\u4E2D...",
    captureHtmlHint: "\u5728\u5DF2\u52A0\u8F7D\u5168\u6587\u7684\u7F51\u9875\u4E0A\u4F7F\u7528\u3002\u6269\u5C55\u4F1A\u91C7\u96C6\u51C0\u5316\u540E\u7684\u9875\u9762 HTML\uFF0C\u5E76\u8D70\u540E\u7AEF HTML \u4E13\u7528\u89E3\u6790\u8DEF\u5F84\u3002",
    parsingButton: "\u89E3\u6790\u4E2D...",
    settingsButton: "\u8BBE\u7F6E",
    translateLabel: "\u7FFB\u8BD1\u4E3A",
    translateButton: "\u7FFB\u8BD1",
    translatingButton: "\u7FFB\u8BD1\u4E2D...",
    chinese: "\u4E2D\u6587",
    english: "\u82F1\u6587",
    spanish: "\u897F\u73ED\u7259\u6587",
    french: "\u6CD5\u6587",
    german: "\u5FB7\u6587",
    japanese: "\u65E5\u6587",
    korean: "\u97E9\u6587",
    russian: "\u4FC4\u6587",
    turkish: "\u571F\u8033\u5176\u6587",
    arabic: "\u963F\u62C9\u4F2F\u6587",
    sourceFiles: "\u6E90\u6587\u4EF6",
    recentTasks: "\u6700\u8FD1\u5904\u7406",
    noRecentTasks: "\u8FD8\u6CA1\u6709\u6700\u8FD1\u8BBA\u6587\u3002",
    openPaper: "\u586B\u5165 DOI",
    enterDoi: "\u8BF7\u5148\u8F93\u5165 DOI \u6216\u4F7F\u7528\u68C0\u6D4B\u5230\u7684\u8BBA\u6587\u9875\u9762\u3002",
    translateFirst: "\u8BF7\u5148\u6210\u529F\u89E3\u6790\u8BBA\u6587\uFF0C\u518D\u8FDB\u884C\u7FFB\u8BD1\u3002",
    parseReady: (filename) => `Markdown \u5DF2\u5C31\u7EEA\uFF1A${filename}\u3002\u53EF\u4EE5\u4E0B\u8F7D\u6216\u57FA\u4E8E\u8BE5 Markdown \u7FFB\u8BD1\u3002`,
    translateReady: (filename) => `\u8BD1\u6587\u5DF2\u5C31\u7EEA\uFF1A${filename}\u3002`,
    parseFailed: "\u89E3\u6790\u5931\u8D25\uFF0C\u8BF7\u91CD\u8BD5\u3002",
    translationFailed: "\u7FFB\u8BD1\u5931\u8D25\uFF0C\u8BF7\u91CD\u8BD5\u3002",
    detected: (kind) => `\u5DF2\u8BC6\u522B${kind}\u3002`,
    noDoi: "\u672A\u8BC6\u522B\u5230 DOI\uFF0C\u8BF7\u624B\u52A8\u7C98\u8D34\u3002",
    noActiveTab: "\u5F53\u524D\u6CA1\u6709\u53EF\u7528\u6807\u7B7E\u9875\u3002",
    downloadFailed: "\u4E0B\u8F7D\u5931\u8D25\uFF0C\u8BF7\u91CD\u8BD5\u3002",
    copyCliCommand: "\u590D\u5236\u4EA4\u63A5\u4FE1\u606F",
    cliCommandCopied: "CLI \u4EA4\u63A5\u4FE1\u606F\u5DF2\u590D\u5236\u3002"
  }
};
var titleEl = document.querySelector("#app-title");
var subtitleEl = document.querySelector("#app-subtitle");
var languageToggleEl = document.querySelector("#language-toggle");
var accountEmailEl = document.querySelector("#account-email");
var usageStatusEl = document.querySelector("#usage-status");
var connectionPillEl = document.querySelector("#connection-pill");
var workflowAuthEl = document.querySelector("#workflow-auth");
var workflowParseEl = document.querySelector("#workflow-parse");
var workflowTranslateEl = document.querySelector("#workflow-translate");
var workflowDownloadEl = document.querySelector("#workflow-download");
var inputLabelEl = document.querySelector("#paper-input-label");
var inputEl = document.querySelector("#paper-input");
var statusEl = document.querySelector("#status");
var preflightHintEl = document.querySelector("#preflight-hint");
var fileIntakeTitleEl = document.querySelector("#file-intake-title");
var fileIntakeNoteEl = document.querySelector("#file-intake-note");
var pickPdfButton = document.querySelector("#pick-pdf-button");
var pickEpubButton = document.querySelector("#pick-epub-button");
var pickHtmlButton = document.querySelector("#pick-html-button");
var localFileInputEl = document.querySelector("#local-file-input");
var localFileNameEl = document.querySelector("#local-file-name");
var parseButton = document.querySelector("#parse-button");
var captureHtmlButton = document.querySelector("#capture-html-button");
var openSettingsButton = document.querySelector("#open-settings");
var openSettingsLoginButton = document.querySelector("#open-settings-login");
var translateLanguageLabelEl = document.querySelector("#translate-language-label");
var translateButton = document.querySelector("#translate-button");
var translateLanguageEl = document.querySelector("#translate-language");
var resultEl = document.querySelector("#result");
var taskSummaryEl = document.querySelector("#task-summary");
var taskSummaryListEl = document.querySelector("#task-summary-list");
var cliHandoffEl = document.querySelector("#cli-handoff");
var cliHandoffNoteEl = document.querySelector("#cli-handoff-note");
var cliHandoffCommandEl = document.querySelector("#cli-handoff-command");
var cliHandoffPlanEl = document.querySelector("#cli-handoff-plan");
var copyCliHandoffButton = document.querySelector("#copy-cli-handoff");
var artifactActionsEl = document.querySelector("#artifact-actions");
var downloadButton = document.querySelector("#download-link");
var secondaryDownloadsEl = document.querySelector("#secondary-downloads");
var sourceFilesEl = document.querySelector("#source-files");
var sourceFilesSummaryEl = document.querySelector("#source-files-summary");
var sourceDownloadsEl = document.querySelector("#source-downloads");
var recentTasksSummaryEl = document.querySelector("#recent-tasks-summary");
var recentTaskListEl = document.querySelector("#recent-task-list");
var client = createApiClient(readSettings);
var lastParsedMarkdownSource = null;
var currentInput = null;
var uiLanguage = "en";
var isParsing = false;
var isTranslating = false;
var isSignedIn = false;
var hasParsedArtifact = false;
var hasTranslatedArtifact = false;
var hasDownloadableArtifact = false;
var detectedPageContext = null;
var currentBridgeStatus = null;
var currentCliHandoffCommands = [];
var currentCliHandoffContext = null;
function copyFor(language) {
  return COPY[language];
}
async function openMdteroAccount() {
  await chrome.tabs.create({ url: MDTERO_ACCOUNT_URL });
}
function setResult(message) {
  if (resultEl) {
    resultEl.textContent = message;
  }
}
function setTaskSummary(lines) {
  if (!taskSummaryEl || !taskSummaryListEl) {
    return;
  }
  taskSummaryListEl.innerHTML = "";
  const visibleLines = (lines ?? []).map((line) => line.trim()).filter(Boolean).slice(0, 7);
  taskSummaryEl.hidden = visibleLines.length === 0;
  visibleLines.forEach((line) => {
    const item = document.createElement("li");
    item.textContent = line;
    taskSummaryListEl.appendChild(item);
  });
}
function setWorkflowStep(element, state) {
  if (!element) return;
  element.dataset.state = state;
  const copy = getCurrentCopy();
  const label = state === "done" ? copy.workflowDone : state === "active" ? copy.workflowActive : copy.workflowPending;
  element.setAttribute("aria-label", `${element.textContent || "Step"}: ${label}`);
}
function updateWorkflowState() {
  setWorkflowStep(workflowAuthEl, isSignedIn ? "done" : "active");
  setWorkflowStep(workflowParseEl, hasParsedArtifact ? "done" : isSignedIn ? "active" : "pending");
  setWorkflowStep(workflowTranslateEl, hasTranslatedArtifact ? "done" : isTranslating || hasParsedArtifact ? "active" : "pending");
  setWorkflowStep(workflowDownloadEl, hasDownloadableArtifact ? "done" : hasParsedArtifact || hasTranslatedArtifact ? "active" : "pending");
}
function setCliHandoff(input, commandOverride, planCommands, context) {
  const commands = normalizeHandoffCommands(planCommands);
  const command = String(commandOverride || commands[0] || "").trim() || buildCliParseCommand(input);
  const handoffCommands = command ? buildCliHandoffCommandPlan(command, commands) : [];
  if (!cliHandoffEl || !cliHandoffCommandEl || !copyCliHandoffButton || !cliHandoffNoteEl) {
    return;
  }
  cliHandoffEl.hidden = !command;
  cliHandoffNoteEl.textContent = getCliHandoffNote(command, uiLanguage);
  cliHandoffCommandEl.textContent = command;
  currentCliHandoffCommands = handoffCommands;
  currentCliHandoffContext = context ?? null;
  renderCliHandoffPlan(currentCliHandoffCommands);
  copyCliHandoffButton.textContent = getCurrentCopy().copyCliCommand;
}
function normalizeHandoffCommands(commands) {
  return Array.from(new Set((commands ?? []).map((value) => String(value || "").trim()).filter(Boolean)));
}
function renderCliHandoffPlan(commands) {
  if (!cliHandoffPlanEl) {
    return;
  }
  const unique = normalizeHandoffCommands(commands);
  cliHandoffPlanEl.innerHTML = "";
  cliHandoffPlanEl.hidden = unique.length <= 1;
  unique.slice(1).forEach((command) => {
    const item = document.createElement("li");
    item.textContent = command;
    cliHandoffPlanEl.appendChild(item);
  });
}
async function copyCliHandoff() {
  const command = cliHandoffCommandEl?.textContent?.trim();
  if (!command) {
    return;
  }
  await navigator.clipboard?.writeText(formatCliHandoffClipboard(command, currentCliHandoffCommands, currentCliHandoffContext));
  setResult(getCurrentCopy().cliCommandCopied);
}
function setStatus(message) {
  if (statusEl) {
    statusEl.textContent = message;
  }
}
function setPreflightHint(message) {
  if (preflightHintEl) {
    preflightHintEl.textContent = message;
    preflightHintEl.hidden = !message.trim();
  }
}
function getCurrentCopy() {
  return copyFor(uiLanguage);
}
async function updatePreflightHint() {
  const settings = await readSettings();
  const input = inputEl?.value.trim() || currentInput || "";
  const pageUrl = detectedPageContext?.tabUrl || "";
  const hint = getPreflightHintText(
    {
      input,
      pageUrl,
      bridgeStatus: currentBridgeStatus
    },
    uiLanguage
  );
  setPreflightHint(hint);
  if (shouldShowCliHandoffForPreflight(hint, input)) {
    setCliHandoff(input);
  } else if (!isParsing) {
    setCliHandoff(null);
  }
}
function toggleLanguageLabel(language) {
  return language === "en" ? "\u4E2D\u6587" : "EN";
}
function stripArtifactSuffix(filename) {
  if (!filename) {
    return "paper";
  }
  return filename.replace(/\.zip$/i, "").replace(/\.pdf$/i, "").replace(/\.xml$/i, "").replace(/\.(zh|en)\.md$/i, "").replace(/\.md$/i, "");
}
function createRecentTaskSummary(state) {
  if (!state?.input) {
    return null;
  }
  return {
    input: state.input,
    label: stripArtifactSuffix(state.translatedFilename ?? state.parseFilename),
    parseTaskId: state.parseTaskId,
    parseArtifactKey: state.parseArtifactKey,
    parseFilename: state.parseFilename,
    translatedTaskId: state.translatedTaskId,
    translatedFilename: state.translatedFilename
  };
}
async function saveArtifact(taskId, artifactKey, preferredFilename) {
  try {
    const artifact = await client.downloadArtifact(taskId, artifactKey, preferredFilename);
    triggerBlobDownload(artifact.blob, artifact.filename);
  } catch (error) {
    setResult(getDownloadFailureText(error, getCurrentCopy().downloadFailed, uiLanguage));
    const handoffPlan = buildApiErrorCliHandoffPlan(error, currentInput, "parse");
    if (handoffPlan.primaryCommand) {
      setCliHandoff(
        currentInput,
        handoffPlan.primaryCommand,
        handoffPlan.commands,
        buildApiErrorHandoffContext(error, "parse")
      );
    }
  }
}
function applyLanguage() {
  const copy = getCurrentCopy();
  document.documentElement.lang = uiLanguage === "zh" ? "zh-CN" : "en";
  if (titleEl) titleEl.textContent = copy.title;
  if (subtitleEl) subtitleEl.textContent = copy.subtitle;
  if (languageToggleEl) languageToggleEl.textContent = toggleLanguageLabel(uiLanguage);
  if (workflowAuthEl) workflowAuthEl.textContent = copy.workflowAuth;
  if (workflowParseEl) workflowParseEl.textContent = copy.workflowParse;
  if (workflowTranslateEl) workflowTranslateEl.textContent = copy.workflowTranslate;
  if (workflowDownloadEl) workflowDownloadEl.textContent = copy.workflowDownload;
  if (inputLabelEl) inputLabelEl.textContent = copy.inputLabel;
  if (inputEl) inputEl.placeholder = copy.inputPlaceholder;
  if (fileIntakeTitleEl) fileIntakeTitleEl.textContent = copy.fileIntakeTitle;
  if (fileIntakeNoteEl) fileIntakeNoteEl.textContent = copy.fileIntakeNote;
  if (pickPdfButton) pickPdfButton.textContent = copy.pickPdfButton;
  if (pickEpubButton) pickEpubButton.textContent = copy.pickEpubButton;
  if (localFileNameEl && !localFileNameEl.dataset.selectedName) {
    localFileNameEl.textContent = copy.fileNameEmpty;
  }
  if (translateLanguageLabelEl) translateLanguageLabelEl.textContent = copy.translateLabel;
  if (sourceFilesSummaryEl) sourceFilesSummaryEl.textContent = copy.sourceFiles;
  if (recentTasksSummaryEl) recentTasksSummaryEl.textContent = copy.recentTasks;
  if (translateLanguageEl) {
    for (let i = 0; i < translateLanguageEl.options.length; i++) {
      const option = translateLanguageEl.options[i];
      if (option) {
        switch (option.value) {
          case "zh":
            option.text = copy.chinese;
            break;
          case "en":
            option.text = copy.english;
            break;
          case "es":
            option.text = copy.spanish;
            break;
          case "fr":
            option.text = copy.french;
            break;
          case "de":
            option.text = copy.german;
            break;
          case "ja":
            option.text = copy.japanese;
            break;
          case "ko":
            option.text = copy.korean;
            break;
          case "ru":
            option.text = copy.russian;
            break;
          case "tr":
            option.text = copy.turkish;
            break;
          case "ar":
            option.text = copy.arabic;
            break;
        }
      }
    }
  }
  if (openSettingsButton) openSettingsButton.textContent = copy.settingsButton;
  if (openSettingsLoginButton) openSettingsLoginButton.textContent = copy.signInButton;
  if (copyCliHandoffButton) copyCliHandoffButton.textContent = copy.copyCliCommand;
  updateWorkflowState();
  renderActionButtons();
}
function renderActionButtons() {
  const copy = getCurrentCopy();
  if (parseButton) {
    parseButton.textContent = isParsing ? copy.parsingButton : copy.parseButton;
    parseButton.disabled = isParsing;
  }
  if (captureHtmlButton) {
    captureHtmlButton.textContent = isParsing ? copy.captureHtmlParsing : copy.captureHtmlButton;
    captureHtmlButton.disabled = isParsing;
    captureHtmlButton.title = copy.captureHtmlHint;
  }
  if (pickPdfButton) {
    pickPdfButton.disabled = isParsing;
  }
  if (pickEpubButton) {
    pickEpubButton.disabled = isParsing;
  }
  if (pickHtmlButton) {
    pickHtmlButton.disabled = isParsing;
  }
  if (translateButton) {
    translateButton.textContent = isTranslating ? copy.translatingButton : copy.translateButton;
    translateButton.disabled = isTranslating || !hasParsedMarkdownSource(lastParsedMarkdownSource);
  }
}
function hasParsedMarkdownSource(source) {
  return Boolean(source?.path || source?.taskId && source?.artifactKey);
}
function parsedMarkdownRef(source) {
  return String(source?.path || source?.taskId || "").trim();
}
function getArtifactDescriptor(result, artifactKey) {
  return result?.artifacts?.[artifactKey] ?? result?.download_artifacts?.find((artifact) => artifact.artifact === artifactKey);
}
function clearSecondaryDownloads() {
  if (secondaryDownloadsEl) {
    secondaryDownloadsEl.innerHTML = "";
  }
  if (sourceDownloadsEl) {
    sourceDownloadsEl.innerHTML = "";
  }
  if (sourceFilesEl) {
    sourceFilesEl.hidden = true;
    sourceFilesEl.open = false;
  }
}
function appendActionButton(container, taskId, artifactKey, preferredFilename) {
  if (!container) {
    return;
  }
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = getDownloadLabel(artifactKey, uiLanguage);
  button.addEventListener("click", () => {
    void saveArtifact(taskId, artifactKey, preferredFilename);
  });
  container.appendChild(button);
}
function renderArtifacts(task) {
  const preferredKey = getPreferredArtifactKey(task.result);
  clearSecondaryDownloads();
  if (!preferredKey) {
    if (artifactActionsEl) artifactActionsEl.hidden = true;
    return;
  }
  hasDownloadableArtifact = true;
  if (preferredKey === "translated_md") {
    hasTranslatedArtifact = true;
  } else {
    hasParsedArtifact = true;
  }
  updateWorkflowState();
  if (artifactActionsEl) artifactActionsEl.hidden = false;
  if (downloadButton) {
    downloadButton.hidden = false;
    downloadButton.textContent = getDownloadLabel(preferredKey, uiLanguage);
    downloadButton.onclick = () => {
      void saveArtifact(task.task_id, preferredKey, getArtifactFilename(task.result, preferredKey));
    };
  }
  getSecondaryArtifactKeys(task.result).forEach((artifactKey) => {
    appendActionButton(
      secondaryDownloadsEl,
      task.task_id,
      artifactKey,
      getArtifactFilename(task.result, artifactKey)
    );
  });
  const sourceArtifactKeys = getSourceArtifactKeys(task.result);
  if (sourceArtifactKeys.length > 0) {
    if (sourceFilesEl) {
      sourceFilesEl.hidden = false;
    }
    sourceArtifactKeys.forEach((artifactKey) => {
      appendActionButton(
        sourceDownloadsEl,
        task.task_id,
        artifactKey,
        getArtifactFilename(task.result, artifactKey)
      );
    });
  }
}
async function persistPopupState(task) {
  if (!currentInput || !task.result) {
    return;
  }
  const previous = await readPopupState();
  const preferredParseArtifact = task.result.preferred_artifact === "paper_bundle" ? "paper_bundle" : "paper_md";
  const preferredParseDescriptor = getArtifactDescriptor(task.result, preferredParseArtifact);
  const paperMarkdownDescriptor = getArtifactDescriptor(task.result, "paper_md");
  const translatedDescriptor = getArtifactDescriptor(task.result, "translated_md");
  const nextState = {
    input: currentInput,
    parseTaskId: preferredParseDescriptor ? task.task_id : previous?.parseTaskId,
    parseArtifactKey: preferredParseDescriptor ? preferredParseArtifact : previous?.parseArtifactKey,
    parseFilename: preferredParseDescriptor?.filename ?? previous?.parseFilename,
    parseMarkdownTaskId: paperMarkdownDescriptor ? task.task_id : previous?.parseMarkdownTaskId,
    parseMarkdownArtifactKey: paperMarkdownDescriptor ? "paper_md" : previous?.parseMarkdownArtifactKey,
    parseMarkdownFilename: paperMarkdownDescriptor?.filename ?? previous?.parseMarkdownFilename,
    parseMarkdownPath: task.result.artifacts?.paper_md?.path ?? previous?.parseMarkdownPath,
    translatedTaskId: translatedDescriptor ? task.task_id : previous?.translatedTaskId,
    translatedFilename: translatedDescriptor?.filename ?? previous?.translatedFilename,
    pendingTaskId: void 0,
    pendingTaskKind: void 0
  };
  await writePopupState(nextState);
  const summary = createRecentTaskSummary(nextState);
  if (summary) {
    const recent = await readRecentTasks();
    await writeRecentTasks(upsertRecentTasks(recent, summary));
  }
}
async function renderRecentTasks() {
  if (!recentTaskListEl) {
    return;
  }
  const copy = getCurrentCopy();
  recentTaskListEl.innerHTML = "";
  const recentTasks = await readRecentTasks();
  if (recentTasks.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = copy.noRecentTasks;
    recentTaskListEl.appendChild(empty);
    return;
  }
  recentTasks.forEach((task) => {
    const item = document.createElement("article");
    item.className = "recent-item";
    const title = document.createElement("p");
    title.className = "recent-title";
    title.textContent = task.label;
    item.appendChild(title);
    const meta = document.createElement("p");
    meta.className = "recent-meta";
    meta.textContent = task.input;
    item.appendChild(meta);
    const actions = document.createElement("div");
    actions.className = "recent-actions";
    const useDoi = document.createElement("button");
    useDoi.type = "button";
    useDoi.className = "secondary-button";
    useDoi.textContent = copy.openPaper;
    useDoi.addEventListener("click", () => {
      if (inputEl) {
        inputEl.value = task.input;
      }
      currentInput = task.input;
      setResult(getSavedResultSummary(task, uiLanguage));
    });
    actions.appendChild(useDoi);
    if (task.parseTaskId && task.parseArtifactKey) {
      const parseButton2 = document.createElement("button");
      parseButton2.type = "button";
      parseButton2.className = "secondary-button";
      parseButton2.textContent = getDownloadLabel(task.parseArtifactKey, uiLanguage);
      parseButton2.addEventListener("click", () => {
        void saveArtifact(task.parseTaskId, task.parseArtifactKey, task.parseFilename);
      });
      actions.appendChild(parseButton2);
    }
    if (task.translatedTaskId) {
      const translatedButton = document.createElement("button");
      translatedButton.type = "button";
      translatedButton.className = "secondary-button";
      translatedButton.textContent = getDownloadLabel("translated_md", uiLanguage);
      translatedButton.addEventListener("click", () => {
        void saveArtifact(task.translatedTaskId, "translated_md", task.translatedFilename);
      });
      actions.appendChild(translatedButton);
    }
    item.appendChild(actions);
    recentTaskListEl.appendChild(item);
  });
}
async function hydrateSavedState(detectedInput) {
  const savedState = await readPopupState();
  if (!savedState || savedState.input !== detectedInput) {
    return;
  }
  const pendingTask = getPendingPopupTask(savedState, detectedInput);
  if (pendingTask) {
    isParsing = pendingTask.kind === "parse";
    isTranslating = pendingTask.kind === "translate";
    renderActionButtons();
    setResult(getActionStatusText(pendingTask.kind === "parse" ? "running_parse" : "running_translate", uiLanguage));
    void pollTask(pendingTask.taskId, pendingTask.kind);
    return;
  }
  const summary = getSavedResultSummary(savedState, uiLanguage);
  if (summary) {
    setResult(summary);
  }
  lastParsedMarkdownSource = {
    path: savedState.parseMarkdownPath,
    taskId: savedState.parseMarkdownTaskId,
    artifactKey: savedState.parseMarkdownArtifactKey,
    filename: savedState.parseMarkdownFilename
  };
  hasParsedArtifact = Boolean(savedState.parseTaskId || hasParsedMarkdownSource(lastParsedMarkdownSource));
  hasTranslatedArtifact = Boolean(savedState.translatedTaskId || savedState.translatedFilename);
  hasDownloadableArtifact = hasParsedArtifact || hasTranslatedArtifact;
  updateWorkflowState();
  renderActionButtons();
}
async function pollTask(taskId, kind) {
  const response = await chrome.runtime.sendMessage({
    type: "mdtero.task.get",
    taskId
  });
  if (!response?.ok) {
    setResult(response?.error ?? getCurrentCopy().parseFailed);
    if (kind === "parse") {
      setCliHandoff(currentInput);
    }
    isParsing = false;
    isTranslating = false;
    if (currentInput) {
      const previous = await readPopupState();
      await writePopupState({
        ...previous ?? { input: currentInput },
        input: currentInput,
        pendingTaskId: void 0,
        pendingTaskKind: void 0
      });
    }
    renderActionButtons();
    updateWorkflowState();
    return;
  }
  const task = response.result;
  if (task.status === "failed") {
    setTaskSummary(getTaskProcessingSummary(task, uiLanguage));
    setResult(
      getTaskFailureText(
        task,
        kind === "parse" ? getCurrentCopy().parseFailed : getCurrentCopy().translationFailed,
        uiLanguage
      )
    );
    const failureHandoffPlan = buildTaskFailureCliHandoffPlan(task, currentInput, kind);
    if (failureHandoffPlan.primaryCommand) {
      setCliHandoff(
        currentInput,
        failureHandoffPlan.primaryCommand,
        failureHandoffPlan.commands,
        buildTaskHandoffContext(task, kind)
      );
    } else {
      setCliHandoff(null);
    }
    if (kind === "parse") {
      isParsing = false;
    } else {
      isTranslating = false;
    }
    if (currentInput) {
      const previous = await readPopupState();
      await writePopupState({
        ...previous ?? { input: currentInput },
        input: currentInput,
        pendingTaskId: void 0,
        pendingTaskKind: void 0
      });
    }
    renderActionButtons();
    updateWorkflowState();
    return;
  }
  if (task.status !== "succeeded") {
    setResult(
      getActionStatusText(kind === "parse" ? "running_parse" : "running_translate", uiLanguage)
    );
    setTaskSummary(getTaskProcessingSummary(task, uiLanguage));
    window.setTimeout(() => {
      void pollTask(taskId, kind);
    }, 1500);
    updateWorkflowState();
    return;
  }
  const paperMarkdownDescriptor = getArtifactDescriptor(task.result, "paper_md");
  if (paperMarkdownDescriptor) {
    lastParsedMarkdownSource = {
      path: task.result?.artifacts?.paper_md?.path ?? lastParsedMarkdownSource?.path,
      taskId: task.task_id,
      artifactKey: "paper_md",
      filename: paperMarkdownDescriptor.filename
    };
  }
  setCliHandoff(null);
  setTaskSummary(getTaskProcessingSummary(task, uiLanguage));
  renderArtifacts(task);
  await persistPopupState(task);
  await renderRecentTasks();
  if (kind === "parse") {
    isParsing = false;
    hasParsedArtifact = true;
    hasDownloadableArtifact = true;
    const preferredArtifactKey = getPreferredArtifactKey(task.result);
    const filename = preferredArtifactKey ? getArtifactDescriptor(task.result, preferredArtifactKey)?.filename : void 0;
    const warningText = getResultWarningText(task.result, uiLanguage);
    if (filename) {
      setResult([getCurrentCopy().parseReady(filename), warningText].filter(Boolean).join(" "));
    } else if (warningText) {
      setResult(warningText);
    }
  } else {
    isTranslating = false;
    hasTranslatedArtifact = true;
    hasDownloadableArtifact = true;
    const filename = getArtifactDescriptor(task.result, "translated_md")?.filename;
    if (filename) {
      setResult(getCurrentCopy().translateReady(filename));
    }
  }
  renderActionButtons();
  updateWorkflowState();
}
async function refreshUsage() {
  const settings = await readSettings();
  isSignedIn = Boolean(settings.token);
  if (connectionPillEl) {
    connectionPillEl.textContent = settings.token ? getCurrentCopy().connectionPillSignedIn : getCurrentCopy().connectionPillSignedOut;
  }
  if (accountEmailEl) {
    accountEmailEl.textContent = settings.email ? getCurrentCopy().signedIn(settings.email) : getCurrentCopy().guest;
  }
  if (!settings.token) {
    if (usageStatusEl) {
      usageStatusEl.textContent = getCurrentCopy().signInHint;
    }
    updateWorkflowState();
    return;
  }
  try {
    const usage = await client.getUsage();
    if (usageStatusEl) {
      usageStatusEl.textContent = getUsageStatusText(usage, uiLanguage);
    }
    if (accountEmailEl && usage.email) {
      accountEmailEl.textContent = getCurrentCopy().signedIn(usage.email);
    }
  } catch (error) {
    if (usageStatusEl) {
      usageStatusEl.textContent = getUsageStatusText(null, uiLanguage, error.message);
    }
  }
  updateWorkflowState();
}
async function refreshBridgeStatus() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    currentBridgeStatus = { state: "unavailable", runnerState: "idle" };
    await updatePreflightHint();
    return;
  }
  try {
    await sendTabMessageWithInjection(tab.id, createDetectMessage());
    currentBridgeStatus = { state: "connected", runnerState: "idle" };
  } catch {
    currentBridgeStatus = { state: "unavailable", runnerState: "idle" };
  }
  await updatePreflightHint();
}
async function detectCurrentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    setStatus(getCurrentCopy().noActiveTab);
    detectedPageContext = null;
    await updatePreflightHint();
    return;
  }
  try {
    setStatus(getActionStatusText("detecting", uiLanguage));
    const response = await sendTabMessageWithInjection(tab.id, createDetectMessage());
    if (response?.detected?.value && inputEl) {
      inputEl.value = response.detected.value;
      currentInput = response.detected.value;
      detectedPageContext = {
        tabId: tab.id,
        tabUrl: tab.url,
        detectedInput: response.detected.value
      };
      setStatus(getCurrentCopy().detected(response.detected.kind));
      await updatePreflightHint();
      await hydrateSavedState(response.detected.value);
      return;
    }
  } catch {
  }
  detectedPageContext = null;
  setStatus(getCurrentCopy().noDoi);
  await updatePreflightHint();
}
async function resolveParsePageContext(input) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    return void 0;
  }
  const activeTabUrl = String(tab.url || "").trim();
  if (activeTabUrl && activeTabUrl === input) {
    return {
      tabId: tab.id,
      tabUrl: activeTabUrl
    };
  }
  if (detectedPageContext && detectedPageContext.tabId === tab.id && detectedPageContext.detectedInput === input) {
    return {
      tabId: detectedPageContext.tabId,
      tabUrl: detectedPageContext.tabUrl || activeTabUrl
    };
  }
  return void 0;
}
async function initializeLanguage() {
  const settings = await readSettings();
  uiLanguage = resolveUiLanguage(settings.uiLanguage, globalThis.navigator?.language);
  applyLanguage();
}
function setLocalFileName(filename) {
  if (!localFileNameEl) {
    return;
  }
  const trimmed = String(filename || "").trim();
  localFileNameEl.dataset.selectedName = trimmed;
  localFileNameEl.textContent = trimmed || getCurrentCopy().fileNameEmpty;
}
async function submitLocalFile(file, artifactKind) {
  currentInput = file.name;
  detectedPageContext = null;
  setTaskSummary(null);
  setLocalFileName(file.name);
  isParsing = true;
  updateWorkflowState();
  renderActionButtons();
  setResult(getCurrentCopy().localFileParsing(file.name));
  const settings = await readSettings();
  if (!settings.token) {
    isParsing = false;
    updateWorkflowState();
    renderActionButtons();
    setResult(getCurrentCopy().signInHint);
    await openMdteroAccount();
    return;
  }
  const response = await chrome.runtime.sendMessage(createFileParseMessage(file, artifactKind));
  if (!response?.ok) {
    isParsing = false;
    updateWorkflowState();
    renderActionButtons();
    setResult(response?.error ?? getCurrentCopy().localFileParseFailed);
    setCliHandoff(file.name, buildCliFileParseCommand(file.name, artifactKind));
    return;
  }
  await writePopupState({
    ...await readPopupState(),
    input: file.name,
    pendingTaskId: response.result.task_id,
    pendingTaskKind: "parse"
  });
  void pollTask(response.result.task_id, "parse");
}
async function startQueuedParseTask(input, taskId) {
  await writePopupState({
    ...await readPopupState(),
    input,
    pendingTaskId: taskId,
    pendingTaskKind: "parse"
  });
  void pollTask(taskId, "parse");
}
parseButton?.addEventListener("click", async () => {
  if (isParsing) {
    return;
  }
  const input = inputEl?.value.trim();
  if (!input) {
    setResult(getCurrentCopy().enterDoi);
    return;
  }
  currentInput = input;
  setTaskSummary(null);
  isParsing = true;
  updateWorkflowState();
  renderActionButtons();
  setResult(getActionStatusText("queued_parse", uiLanguage));
  const settings = await readSettings();
  if (!settings.token) {
    isParsing = false;
    updateWorkflowState();
    renderActionButtons();
    setResult(getCurrentCopy().signInHint);
    await openMdteroAccount();
    return;
  }
  const pageContext = await resolveParsePageContext(input);
  const response = await chrome.runtime.sendMessage(
    createSsotParseMessage(input, pageContext)
  );
  if (!response?.ok) {
    isParsing = false;
    updateWorkflowState();
    renderActionButtons();
    setResult(response?.error ?? getCurrentCopy().parseFailed);
    setCliHandoff(input, response?.nextCommand);
    return;
  }
  setCliHandoff(null);
  await startQueuedParseTask(input, response.result.task_id);
});
captureHtmlButton?.addEventListener("click", async () => {
  if (isParsing) {
    return;
  }
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    setResult(getCurrentCopy().noActiveTab);
    return;
  }
  const input = inputEl?.value.trim() || tab.url || currentInput || "current-page-html";
  currentInput = input;
  setTaskSummary(null);
  isParsing = true;
  updateWorkflowState();
  renderActionButtons();
  setResult(getCurrentCopy().captureHtmlParsing);
  const settings = await readSettings();
  if (!settings.token) {
    isParsing = false;
    updateWorkflowState();
    renderActionButtons();
    setResult(getCurrentCopy().signInHint);
    await openMdteroAccount();
    return;
  }
  const response = await chrome.runtime.sendMessage(
    createCurrentHtmlParseMessage(input, {
      tabId: tab.id,
      tabUrl: tab.url
    })
  );
  if (!response?.ok) {
    isParsing = false;
    updateWorkflowState();
    renderActionButtons();
    setResult(response?.error ?? getCurrentCopy().parseFailed);
    setCliHandoff(input, response?.nextCommand);
    return;
  }
  setCliHandoff(null);
  await startQueuedParseTask(input, response.result.task_id);
});
translateButton?.addEventListener("click", async () => {
  if (isTranslating) {
    return;
  }
  if (!hasParsedMarkdownSource(lastParsedMarkdownSource)) {
    setResult(getCurrentCopy().translateFirst);
    return;
  }
  const previous = await readPopupState();
  const markdownRef = parsedMarkdownRef(lastParsedMarkdownSource);
  const reconnectableTask = getReconnectablePendingTranslationTask(
    previous,
    currentInput ?? "",
    markdownRef
  );
  if (reconnectableTask) {
    isTranslating = true;
    updateWorkflowState();
    renderActionButtons();
    setResult(getActionStatusText("running_translate", uiLanguage));
    void pollTask(reconnectableTask.taskId, "translate");
    return;
  }
  isTranslating = true;
  updateWorkflowState();
  renderActionButtons();
  setResult(getActionStatusText("queued_translate", uiLanguage));
  const response = await chrome.runtime.sendMessage(
    createTranslateMessage(
      lastParsedMarkdownSource ?? {},
      translateLanguageEl?.value ?? "zh",
      "standard"
    )
  );
  if (!response?.ok) {
    isTranslating = false;
    updateWorkflowState();
    renderActionButtons();
    setResult(response?.error ?? getCurrentCopy().translationFailed);
    return;
  }
  await writePopupState({
    ...await readPopupState(),
    input: currentInput ?? "",
    parseMarkdownPath: lastParsedMarkdownSource?.path || void 0,
    parseMarkdownTaskId: lastParsedMarkdownSource?.taskId || void 0,
    parseMarkdownArtifactKey: lastParsedMarkdownSource?.artifactKey || void 0,
    parseMarkdownFilename: lastParsedMarkdownSource?.filename || void 0,
    pendingTaskId: response.result.task_id,
    pendingTaskKind: "translate"
  });
  void pollTask(response.result.task_id, "translate");
});
openSettingsButton?.addEventListener("click", () => {
  void chrome.runtime.openOptionsPage();
});
openSettingsLoginButton?.addEventListener("click", () => {
  void openMdteroAccount();
});
copyCliHandoffButton?.addEventListener("click", () => {
  void copyCliHandoff();
});
inputEl?.addEventListener("input", () => {
  currentInput = inputEl.value.trim() || currentInput;
  setCliHandoff(null);
  void updatePreflightHint();
});
pickPdfButton?.addEventListener("click", () => {
  if (!localFileInputEl) {
    return;
  }
  localFileInputEl.accept = ".pdf,application/pdf";
  localFileInputEl.dataset.artifactKind = "pdf";
  localFileInputEl.click();
});
pickEpubButton?.addEventListener("click", () => {
  if (!localFileInputEl) {
    return;
  }
  localFileInputEl.accept = ".epub,application/epub+zip";
  localFileInputEl.dataset.artifactKind = "epub";
  localFileInputEl.click();
});
pickHtmlButton?.addEventListener("click", () => {
  if (!localFileInputEl) {
    return;
  }
  localFileInputEl.accept = ".html,.htm,text/html,application/xhtml+xml";
  localFileInputEl.dataset.artifactKind = "html";
  localFileInputEl.click();
});
localFileInputEl?.addEventListener("change", () => {
  const file = localFileInputEl.files?.[0];
  const artifactKind = resolveLocalFileArtifactKind(localFileInputEl.dataset.artifactKind);
  if (!file) {
    return;
  }
  void submitLocalFile(file, artifactKind);
  localFileInputEl.value = "";
});
function resolveLocalFileArtifactKind(value) {
  if (value === "epub" || value === "html" || value === "xml") {
    return value;
  }
  return "pdf";
}
languageToggleEl?.addEventListener("click", async () => {
  uiLanguage = uiLanguage === "en" ? "zh" : "en";
  const current = await readSettings();
  await writeSettings({
    ...current,
    uiLanguage
  });
  applyLanguage();
  await refreshUsage();
  await refreshBridgeStatus();
  await renderRecentTasks();
  const savedState = await readPopupState();
  const summary = getSavedResultSummary(savedState, uiLanguage);
  if (summary) {
    setResult(summary);
  }
  if (!currentInput) {
    await detectCurrentTab();
  }
  await updatePreflightHint();
});
void (async () => {
  await initializeLanguage();
  await refreshUsage();
  await refreshBridgeStatus();
  await renderRecentTasks();
  renderActionButtons();
  await detectCurrentTab();
  await updatePreflightHint();
})();
//# sourceMappingURL=popup.js.map
