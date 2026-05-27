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
  const withoutTraceOnly = trimmed.replace(/\s+--trace(?!\S)/g, "");
  const withoutJson = withoutTraceOnly.replace(/\s+--json(?!\S)/g, "");
  const withoutTimeout = withoutJson.replace(/\s+--timeout\s+\S+/g, "").replace(/\s+--interval\s+\S+/g, "");
  const withoutWait = withoutTimeout.replace(/\s+--wait(?!\S)/g, "");
  return `${withoutWait} --trace --wait --timeout 300 --json`;
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
  return `mdtero parse --file ${shellQuote(path)} --trace --wait --timeout 300 --json`;
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
var SENSITIVE_QUERY_KEYS = "(api[_-]?key|access[_-]?token|security-token|x-oss-security-token|signature|x-amz-signature|x-amz-credential|ossaccesskeyid|expires|token)";
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
  return body;
}
function fallbackArtifactFilename(artifact, preferredFilename) {
  if (preferredFilename && preferredFilename.trim()) {
    return preferredFilename.trim();
  }
  if (artifact === "paper_bundle") return "paper_bundle.zip";
  if (artifact === "paper_md") return "paper.md";
  if (artifact === "paper_pdf") return "paper.pdf";
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
        sourceInput: payload.sourceInput
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
function createRouterSSOTClient(getSettings) {
  async function requireSignedInSettings() {
    const settings = await getSettings();
    if (!settings.token) {
      throw new Error("Sign in required before fetching route plan.");
    }
    return settings;
  }
  function getRuntimeVersion() {
    const runtimeVersion = globalThis.chrome?.runtime?.getManifest?.().version;
    return runtimeVersion ? `extension-${runtimeVersion}` : "extension-dev";
  }
  async function request(path, init) {
    const settings = await requireSignedInSettings();
    const headers = new Headers(init?.headers ?? {});
    if (!(init?.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    headers.set("Authorization", `Bearer ${settings.token}`);
    headers.set("X-Client-Channel", "extension");
    headers.set("X-Client-Version", getRuntimeVersion());
    const response = await fetch(`${settings.apiBaseUrl}${path}`, {
      ...init,
      headers
    });
    if (response.status === 404 && path === "/api/v1/route") {
      return new Response(JSON.stringify({
        input_kind: "unknown",
        input_value: "",
        top_connector: "server_parse",
        route_kind: "server",
        acquisition_mode: "server_parse",
        requires_browser_capture: false,
        allows_current_tab: false,
        action_sequence: ["server_parse"],
        acceptance_rules: {},
        fail_closed: true,
        matched_connectors: ["server_parse"],
        requires_raw_upload: false,
        action_hint: "The backend route planner is not available; submit the DOI or URL directly to /api/v1/tasks/parse.",
        server_entrypoint: "/api/v1/tasks/parse",
        upload_entrypoint: "/api/v1/tasks/upload",
        route_planner_fallback: true
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    }
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
  return {
    /**
     * Fetch canonical route plan from backend SSOT.
     * Extension should use this instead of local routing rules.
     */
    fetchRoutePlan(payload) {
      return request("/api/v1/route", {
        method: "POST",
        body: JSON.stringify(payload)
      }).then((response) => response.json());
    }
  };
}

// src/lib/file-upload.ts
async function runBrowserFileParseRequest(client2, message) {
  const filename = String(message.filename || "").trim() || "paper.bin";
  return client2.createUploadedParseTask({
    paperFile: message.file,
    filename,
    sourceInput: filename
  });
}

// src/lib/page-capture.ts
var CHALLENGE_MARKERS = [
  "just a moment",
  "access denied",
  "captcha",
  "cf-browser-verification",
  "window._cf_chl_opt",
  "__cf_chl_tk=",
  "/cdn-cgi/challenge-platform/",
  "ctype: 'managed'",
  "verify you are human",
  "checking if the site connection is secure",
  "enable javascript and cookies to continue",
  "pardon the interruption"
];
var LOGIN_MARKERS = [
  "sign in",
  "institutional access",
  "shibboleth",
  "openathens",
  "access through your institution",
  "login via your institution",
  "institutional login",
  "institutional sign in",
  "your institution does not have access",
  "purchase a subscription to gain access"
];
var ARTICLE_XML_MARKERS = [
  "<article",
  "<body",
  "<sec",
  "<jats:",
  "full-text-retrieval-response",
  "originaltext"
];
function classifyAccessShell(html) {
  const lowered = String(html || "").toLowerCase();
  if (CHALLENGE_MARKERS.some((marker) => lowered.includes(marker))) {
    return "challenge";
  }
  if (LOGIN_MARKERS.some((marker) => lowered.includes(marker)) || lowered.includes("password") && lowered.includes("sign in")) {
    return "login";
  }
  return null;
}
function isLikelyChallengeOrLoginShell(html) {
  return classifyAccessShell(html) !== null;
}
function isLikelyHtmlDocument(text) {
  const lowered = String(text || "").trim().toLowerCase();
  return lowered.startsWith("<!doctype html") || lowered.startsWith("<html") || lowered.includes("<html");
}
function hasAnyMarker(text, markers) {
  return markers.some((marker) => text.includes(marker));
}
function isLikelyStructuredArticleXml(text) {
  const lowered = String(text || "").trim().toLowerCase();
  if (!lowered.startsWith("<") && !lowered.startsWith("<?xml")) {
    return false;
  }
  if (isLikelyHtmlDocument(lowered) || isLikelyChallengeOrLoginShell(lowered)) {
    return false;
  }
  return hasAnyMarker(lowered, ARTICLE_XML_MARKERS);
}
async function fetchXmlArtifact(candidateUrls) {
  for (const candidate of candidateUrls.map((item) => String(item || "").trim()).filter(Boolean)) {
    const response = await fetch(candidate, {
      credentials: "include"
    });
    if (!response.ok) {
      continue;
    }
    const text = await response.text();
    const normalized = text.trim();
    if (!normalized) {
      continue;
    }
    if (!normalized.startsWith("<")) {
      continue;
    }
    if (isLikelyHtmlDocument(normalized) || isLikelyChallengeOrLoginShell(normalized)) {
      continue;
    }
    if (isLikelyStructuredArticleXml(normalized)) {
      return {
        ok: true,
        payloadText: normalized,
        payloadName: "paper.xml",
        sourceUrl: candidate
      };
    }
  }
  return {
    ok: false,
    failureCode: "artifact_download_missing",
    failureMessage: "Browser page context could not download an XML payload."
  };
}

// src/lib/action-executor.ts
async function executeAction(action, context, routePlan) {
  switch (action) {
    case "capture_current_tab_html":
      return executeCaptureCurrentTabHtml(context);
    case "native_arxiv_parse":
      return { success: true };
    case "fetch_structured_xml":
      return executeFetchStructuredXml(context, routePlan);
    case "fetch_remote_html":
      return executeFetchBrowserSource(context, routePlan);
    case "fetch_epub_asset":
      return executeFetchEpubAsset(context, routePlan);
    case "fetch_oa_repository":
      return executeFetchOaRepository(context, routePlan);
    case "fetch_browser_source":
      return executeFetchBrowserSource(context, routePlan);
    case "fallback_pdf_parse":
      return {
        success: false,
        requiresUpload: true,
        error: routePlan.user_message || "PDF upload required. Please download and upload the PDF manually.",
        nextCommand: buildCliParseCommand(context.input)
      };
    default:
      return { success: false, error: `Unknown action: ${action}` };
  }
}
async function executeCaptureCurrentTabHtml(context) {
  if (!context.tabId) {
    return { success: false, error: "No tab ID for current tab capture" };
  }
  try {
    const response = await chrome.tabs.sendMessage(context.tabId, {
      type: "mdtero.capture_current_tab.request"
    });
    if (response?.xml?.ok && response.xml.payloadText) {
      return {
        success: true,
        rawArtifact: new Blob([response.xml.payloadText], { type: "application/xml" }),
        filename: response.xml.payloadName || "paper.xml",
        sourceDoi: inferSourceDoi(context.input)
      };
    }
    const capture = response?.capture;
    if (!response?.ok) {
      return { success: false, error: "Content script unavailable. Reload the page and try again." };
    }
    if (!capture?.ok || !capture.html) {
      return {
        success: false,
        error: capture?.failureMessage || "Page capture failed",
        nextCommand: buildCliParseCommand(context.input)
      };
    }
    return {
      success: true,
      rawArtifact: new Blob([capture.html], { type: "text/html" }),
      filename: capture.payloadName || "paper.html",
      sourceDoi: inferSourceDoi(context.input)
    };
  } catch (error) {
    return { success: false, error: String(error) };
  }
}
async function executeFetchStructuredXml(context, routePlan) {
  const candidates = routePlan.acquisition_candidates || [];
  for (const candidate of candidates) {
    if (isStructuredXmlCandidate(candidate)) {
      const candidateUrl = candidate.url;
      if (candidateUrl) {
        try {
          const result = await fetchXmlArtifact([candidateUrl]);
          if (result.ok) {
            return {
              success: true,
              rawArtifact: new Blob([result.payloadText], { type: "application/xml" }),
              filename: result.payloadName,
              sourceDoi: inferSourceDoi(context.input)
            };
          }
        } catch {
        }
      }
    }
  }
  return { success: false, error: "No structured XML source available" };
}
async function executeFetchEpubAsset(context, routePlan) {
  if (!context.tabId) {
    return {
      success: false,
      error: routePlan.user_message || "Open the article page in the current tab and retry EPUB capture.",
      nextCommand: buildCliParseCommand(context.input)
    };
  }
  const candidate = pickEpubCandidate(routePlan);
  if (!candidate?.epub_url) {
    return { success: false, error: "No EPUB acquisition URL available for this route." };
  }
  try {
    const response = await chrome.tabs.sendMessage(context.tabId, {
      type: "mdtero.download_epub.request",
      artifactUrl: candidate.epub_url
    });
    const download = response?.download;
    if (!response?.ok || !download?.ok || !download.payloadBase64) {
      return {
        success: false,
        error: download?.failureMessage || "Browser page context could not download the EPUB artifact.",
        nextCommand: buildCliParseCommand(context.input)
      };
    }
    return {
      success: true,
      rawArtifact: new Blob([base64ToBytes(download.payloadBase64)], { type: "application/epub+zip" }),
      filename: download.payloadName || "paper.epub",
      sourceDoi: inferSourceDoi(context.input)
    };
  } catch (error) {
    return { success: false, error: String(error) };
  }
}
async function executeFetchOaRepository(context, routePlan) {
  const oaUrl = routePlan.best_oa_url;
  if (!oaUrl) {
    return { success: false, error: "No OA repository URL available" };
  }
  try {
    const isPdf = oaUrl.toLowerCase().includes(".pdf") || oaUrl.includes("/pdf") || oaUrl.includes("download");
    if (isPdf) {
      return {
        success: false,
        requiresUpload: true,
        error: "OA source is PDF. Please download and upload manually.",
        nextCommand: buildCliParseCommand(context.input)
      };
    }
    const response = await fetch(oaUrl, { credentials: "include" });
    if (!response.ok) {
      return { success: false, error: `OA fetch failed: ${response.status}` };
    }
    const html = await response.text();
    const finalUrl = response.url;
    return {
      success: true,
      rawArtifact: new Blob([html], { type: "text/html" }),
      filename: "paper.html",
      sourceDoi: inferSourceDoi(context.input)
    };
  } catch (error) {
    return { success: false, error: String(error) };
  }
}
async function executeFetchBrowserSource(context, routePlan) {
  if (!context.tabId) {
    return {
      success: false,
      requiresUpload: true,
      error: "This source requires browser capture. Open the article page and retry.",
      nextCommand: buildCliParseCommand(context.input)
    };
  }
  return executeCaptureCurrentTabHtml(context);
}
function inferSourceDoi(input) {
  const trimmed = String(input || "").trim();
  return /^10\.\S+/i.test(trimmed) ? trimmed : void 0;
}
function isStructuredXmlCandidate(candidate) {
  const format = String(candidate.format || "").trim().toLowerCase();
  const handoff = String(candidate.handoff || "").trim().toLowerCase();
  const connector = String(candidate.connector || "").trim().toLowerCase();
  if (format === "xml" || format === "jats" || format === "jats_xml" || format === "structured_xml") {
    return true;
  }
  if (handoff.includes("xml_to_markdown") || handoff.includes("xml_upload_or_native_xml_parse")) {
    return true;
  }
  return [
    "europe_pmc_fulltext_xml",
    "plos_jats_xml",
    "biorxiv_jats_xml",
    "medrxiv_jats_xml",
    "springer_openaccess_api",
    "springer_full_text_tdm"
  ].includes(connector);
}
function pickEpubCandidate(routePlan) {
  const candidates = routePlan.acquisition_candidates || [];
  const topConnector = String(routePlan.top_connector || "").trim();
  return candidates.find((candidate) => candidate.connector === topConnector && candidate.epub_url) || candidates.find((candidate) => candidate.epub_url);
}
function base64ToBytes(payloadBase64) {
  const decoded = globalThis.atob(payloadBase64);
  const bytes = new Uint8Array(decoded.length);
  for (let index = 0; index < decoded.length; index += 1) {
    bytes[index] = decoded.charCodeAt(index);
  }
  return bytes;
}

// src/lib/ssot-route.ts
async function fetchRoutePlanFromSsot(routeClient, input, pageContext) {
  return routeClient.fetchRoutePlan({
    input,
    page_url: pageContext?.tabUrl,
    page_title: pageContext?.tabTitle
  });
}
async function executeSsotActionSequence(parseClient, routePlan, context) {
  if (routePlan.route_planner_fallback || routePlan.action_sequence.includes("server_parse")) {
    try {
      const task = await parseClient.createParseTask({ input: context.input });
      return { success: true, taskId: task.task_id, task };
    } catch (error) {
      return {
        success: false,
        error: String(error),
        nextCommand: buildCliParseCommand(context.input)
      };
    }
  }
  for (const action of routePlan.action_sequence) {
    const result = await executeAction(action, context, {
      top_connector: routePlan.top_connector,
      fail_closed: routePlan.fail_closed,
      user_message: routePlan.user_message,
      best_oa_url: routePlan.best_oa_url,
      acquisition_candidates: routePlan.acquisition_candidates
    });
    if (result.success) {
      if (result.rawArtifact) {
        try {
          const task = await parseClient.createRawUploadTask({
            rawFile: result.rawArtifact,
            filename: result.filename || "paper.fulltext",
            sourceDoi: result.sourceDoi,
            sourceInput: context.input
          });
          return { success: true, taskId: task.task_id, task };
        } catch (error) {
          if (routePlan.fail_closed) {
            return { success: false, error: String(error), nextCommand: result.nextCommand || buildCliParseCommand(context.input) };
          }
          continue;
        }
      }
      if (result.taskId) {
        return { success: true, taskId: result.taskId };
      }
      continue;
    }
    if (result.requiresBrowserCapture || result.requiresUpload) {
      return {
        success: false,
        requiresBrowserCapture: result.requiresBrowserCapture,
        requiresUpload: result.requiresUpload,
        error: result.error,
        nextCommand: result.nextCommand || buildCliParseCommand(context.input)
      };
    }
    if (routePlan.fail_closed) {
      return { success: false, error: result.error || "Action failed", nextCommand: result.nextCommand || buildCliParseCommand(context.input) };
    }
  }
  return { success: false, error: "No executable action succeeded", nextCommand: buildCliParseCommand(context.input) };
}

// ../shared/src/api-contract.ts
var DEFAULT_API_BASE_URL = "https://api.mdtero.com";

// src/lib/storage.ts
var SETTINGS_KEY = "mdtero_settings";
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

// src/background.ts
var client = createApiClient(readSettings);
var routerSSOT = createRouterSSOTClient(readSettings);
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "mdtero.auth.save_token") {
    readSettings().then((settings) => {
      return writeSettings({
        ...settings,
        token: message.token,
        email: message.email
      });
    }).then(() => sendResponse({ ok: true })).catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type === "mdtero.parse.ssot.request") {
    (async () => {
      const settings = await readSettings();
      if (!settings.token) {
        throw new Error("Sign in required before parsing or translating.");
      }
      const routePlan = await fetchRoutePlanFromSsot(
        routerSSOT,
        message.input,
        message.pageContext?.tabUrl ? {
          tabUrl: message.pageContext.tabUrl,
          tabTitle: message.pageContext.tabTitle
        } : void 0
      );
      const result = await executeSsotActionSequence(
        client,
        routePlan,
        {
          tabId: message.pageContext?.tabId,
          tabUrl: message.pageContext?.tabUrl,
          tabTitle: message.pageContext?.tabTitle,
          input: message.input
        }
      );
      if (result.success && result.taskId) {
        return result.task ?? { task_id: result.taskId };
      }
      return {
        ok: false,
        error: formatSsotFailure(result),
        nextCommand: result.nextCommand
      };
    })().then((result) => {
      if (result && typeof result === "object" && "ok" in result && result.ok === false) {
        sendResponse(result);
        return;
      }
      sendResponse({ ok: true, result });
    }).catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type === "mdtero.parse.file.request") {
    (async () => {
      const settings = await readSettings();
      if (!settings.token) {
        throw new Error("Sign in required before parsing or translating.");
      }
      if (!message.file) {
        throw new Error("No local file was provided.");
      }
      return runBrowserFileParseRequest(client, {
        file: message.file,
        filename: message.filename,
        artifactKind: message.artifactKind
      });
    })().then((result) => sendResponse({ ok: true, result })).catch(
      (error) => sendResponse({
        ok: false,
        error: error.message,
        nextCommand: buildFileParseCommand(message.filename, message.artifactKind)
      })
    );
    return true;
  }
  if (message?.type === "mdtero.task.get") {
    client.getTask(message.taskId).then((result) => sendResponse({ ok: true, result })).catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type === "mdtero.translate.request") {
    (async () => {
      const settings = await readSettings();
      if (!settings.token) {
        throw new Error("Sign in required before parsing or translating.");
      }
      if (message.sourceMarkdownPath) {
        return client.createTranslateTask({
          source_markdown_path: message.sourceMarkdownPath,
          target_language: message.targetLanguage,
          mode: message.mode
        });
      }
      if (!message.sourceTaskId || !message.sourceArtifactKey) {
        throw new Error("Parse a paper to Markdown first; no source Markdown artifact is available for translation.");
      }
      const artifact = await client.downloadArtifact(
        message.sourceTaskId,
        message.sourceArtifactKey,
        message.sourceFilename
      );
      const sourceMarkdownText = await artifact.blob.text();
      if (!sourceMarkdownText.trim()) {
        throw new Error("The Markdown artifact is empty and cannot be translated.");
      }
      return client.createTranslateTask({
        source_markdown_path: "",
        source_markdown_text: sourceMarkdownText,
        source_markdown_filename: artifact.filename || message.sourceFilename || "paper.md",
        target_language: message.targetLanguage,
        mode: message.mode
      });
    })().then((result) => sendResponse({ ok: true, result })).catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  return false;
});
function formatSsotFailure(result) {
  if (result.requiresBrowserCapture) {
    return result.error || "Open the article page in this browser, make sure the full text is loaded, then retry current-page parse or upload the PDF/EPUB directly.";
  }
  if (result.requiresUpload) {
    return result.error || "Upload the PDF/EPUB/XML/HTML file directly so Mdtero can parse it.";
  }
  return result.error || "Action sequence failed";
}
function buildFileParseCommand(filename, artifactKind) {
  return buildCliFileParseCommand(filename, artifactKind);
}
//# sourceMappingURL=background.js.map
