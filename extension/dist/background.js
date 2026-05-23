// src/lib/api.ts
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
      const detail = await response.clone().json().then((payload) => {
        if (payload && typeof payload.detail === "string" && payload.detail.trim()) {
          return payload.detail.trim();
        }
        return "";
      }).catch(() => "");
      throw new Error(detail || `API request failed: ${response.status}`);
    }
    return response;
  }
  async function requestWithFallback(path, fallbackPath, init, options) {
    const settings = options?.requireAuth ? await requireSignedInSettings() : await getSettings();
    const makeHeaders = () => {
      const headers = new Headers(init?.headers ?? {});
      if (!(init?.body instanceof FormData) && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
      }
      if (settings.token) {
        headers.set("Authorization", `Bearer ${settings.token}`);
      }
      headers.set("X-Client-Channel", "extension");
      headers.set("X-Client-Version", getRuntimeVersion());
      return headers;
    };
    let response = await fetch(`${settings.apiBaseUrl}${path}`, {
      ...init,
      headers: makeHeaders()
    });
    if (response.status === 404) {
      response = await fetch(`${settings.apiBaseUrl}${fallbackPath}`, {
        ...init,
        headers: makeHeaders()
      });
    }
    if (!response.ok) {
      const detail = await response.clone().json().then((payload) => {
        if (payload && typeof payload.detail === "string" && payload.detail.trim()) {
          return payload.detail.trim();
        }
        return "";
      }).catch(() => "");
      throw new Error(detail || `API request failed: ${response.status}`);
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
      return requestWithFallback("/api/v1/tasks/parse", "/tasks/parse", {
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
      return requestWithFallback("/api/v1/tasks/upload", "/tasks/parse-upload-v2", {
        method: "POST",
        body
      }, { requireAuth: true }).then((response) => response.json());
    },
    createParseFulltextV2Task(payload) {
      const body = buildFulltextUploadBody({
        file: payload.fulltextFile,
        filename: payload.filename ?? "paper.fulltext",
        sourceDoi: payload.sourceDoi,
        sourceInput: payload.sourceInput
      });
      return requestWithFallback("/api/v1/tasks/upload", "/tasks/parse-upload-v2", {
        method: "POST",
        body
      }, { requireAuth: true }).then((response) => response.json());
    },
    createTranslateTask(payload) {
      return requestWithFallback("/api/v1/tasks/translate", "/tasks/translate", {
        method: "POST",
        body: JSON.stringify(payload)
      }, { requireAuth: true }).then((response) => response.json());
    },
    getTask(taskId) {
      return requestWithFallback(`/api/v1/tasks/${taskId}`, `/tasks/${taskId}`, void 0, { requireAuth: true }).then((response) => response.json());
    },
    downloadArtifact(taskId, artifact, preferredFilename) {
      return requestWithFallback(`/api/v1/tasks/${taskId}/download/${artifact}`, `/tasks/${taskId}/download/${artifact}`, void 0, { requireAuth: true }).then(async (response) => ({
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
        route_kind: "server",
        acquisition_mode: "legacy_parse",
        requires_raw_upload: false,
        action_hint: "Production backend has not enabled /api/v1/route yet; use legacy parse.",
        server_entrypoint: "/tasks/parse",
        upload_entrypoint: "/tasks/parse-upload-v2",
        legacy_fallback: true
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    }
    if (!response.ok) {
      const detail = await response.clone().json().then((payload) => {
        if (payload && typeof payload.detail === "string" && payload.detail.trim()) {
          return payload.detail.trim();
        }
        return "";
      }).catch(() => "");
      throw new Error(detail || `API request failed: ${response.status}`);
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

// src/lib/elsevier.ts
var LOCAL_XML_DOI_PREFIXES = ["10.1016/"];
var DOI_URL_PATTERN = /^https?:\/\/(?:dx\.)?doi\.org\/(10\.\d{4,9}\/.+)$/i;
var PII_PATTERN = /^S[0-9A-Z]{16,}$/i;
var SCIENCEDIRECT_PII_PATTERN = /sciencedirect\.com\/science\/article\/pii\/(S[0-9A-Z]{16,})/i;
function usesLocalXmlAcquire(doi) {
  const lowered = doi.toLowerCase();
  return LOCAL_XML_DOI_PREFIXES.some((prefix) => lowered.startsWith(prefix));
}
function normalizeElsevierInput(input) {
  const trimmed = input.trim();
  const doiUrlMatch = trimmed.match(DOI_URL_PATTERN);
  if (doiUrlMatch && usesLocalXmlAcquire(doiUrlMatch[1])) {
    return { kind: "doi", value: doiUrlMatch[1] };
  }
  if (usesLocalXmlAcquire(trimmed)) {
    return { kind: "doi", value: trimmed };
  }
  const piiUrlMatch = trimmed.match(SCIENCEDIRECT_PII_PATTERN);
  if (piiUrlMatch) {
    return { kind: "pii", value: piiUrlMatch[1] };
  }
  if (PII_PATTERN.test(trimmed)) {
    return { kind: "pii", value: trimmed };
  }
  return null;
}
function requiresElsevierLocalAcquire(input) {
  return normalizeElsevierInput(input) !== null;
}
function buildElsevierLocalAcquireGuidance() {
  return [
    "This Elsevier or ScienceDirect paper needs licensed full-text acquisition before parsing.",
    "Use the browser extension on an already-open full-text page, upload the PDF/XML manually, or run `mdtero config academic` and retry with the CLI.",
    "If Elsevier only returns the abstract, check whether this machine is on a campus or institutional network IP."
  ].join(" ");
}

// src/lib/springer.ts
var DOI_PATTERN = /(10\.\d{4,9}\/[-._;()/:A-Z0-9]+)/i;
var DOI_URL_PATTERN2 = /^https?:\/\/(?:dx\.)?doi\.org\/(10\.\d{4,9}\/.+)$/i;
var SPRINGER_HOST_PATTERN = /(link\.springer\.com|springer\.com|springernature\.com)/i;
function normalizeSpringerInput(input, pageUrl) {
  const trimmed = String(input || "").trim();
  const doiUrlMatch = trimmed.match(DOI_URL_PATTERN2);
  if (doiUrlMatch) {
    return doiUrlMatch[1];
  }
  if (SPRINGER_HOST_PATTERN.test(trimmed)) {
    const doiMatch = trimmed.match(DOI_PATTERN);
    if (doiMatch) {
      return doiMatch[1];
    }
  }
  if (/^10\.1007\//i.test(trimmed)) {
    return trimmed;
  }
  if (SPRINGER_HOST_PATTERN.test(String(pageUrl || ""))) {
    const doiMatch = trimmed.match(DOI_PATTERN);
    if (doiMatch) {
      return doiMatch[1];
    }
  }
  return null;
}

// src/lib/legacy-parse.ts
async function runLegacyParseRequest(client2, message) {
  if (requiresElsevierLocalAcquire(message.input)) {
    throw new Error(buildElsevierLocalAcquireGuidance());
  }
  const currentTabRawUploadTask = await tryCreateCurrentTabRawUploadTask(client2, {
    input: message.input,
    pageContext: message.pageContext
  });
  if (currentTabRawUploadTask) {
    return currentTabRawUploadTask;
  }
  return client2.createParseTask({ input: message.input });
}
async function runLegacyFileParseRequest(client2, message) {
  const filename = String(message.filename || "").trim() || "paper.bin";
  return client2.createUploadedParseTask({
    paperFile: message.file,
    filename,
    sourceInput: filename
  });
}
function inferSourceDoi(input) {
  const trimmed = String(input || "").trim();
  return /^10\.\S+/i.test(trimmed) ? trimmed : void 0;
}
function isArxivAbsReference(value) {
  const lowered = String(value || "").trim().toLowerCase();
  return lowered.includes("arxiv.org/abs/") || lowered.includes("arxiv:");
}
function shouldSkipArxivCurrentTabCapture(message) {
  if (isArxivAbsReference(message.input)) {
    return true;
  }
  return isArxivAbsReference(message.pageContext?.tabUrl);
}
function describeCurrentTabCaptureFailure(params) {
  const failureCode = String(params.failureCode || "").trim().toLowerCase();
  const failureMessage = String(params.failureMessage || "").trim();
  if (failureCode === "login_required") {
    return "This page still requires institutional or account sign-in. Open the article in your browser, finish login, then retry capture.";
  }
  if (failureCode === "challenge_page_detected") {
    return "This page is still behind a browser challenge. Finish the verification in the page, wait for the article to load, then retry capture.";
  }
  if (failureCode === "article_body_missing") {
    return "No article body was detected on the current page. Open the HTML full-text page instead of a PDF or download shell, then retry capture.";
  }
  if (failureCode === "content_script_unavailable") {
    return "Browser page capture is not ready yet. Reload the paper page or reopen the extension, then try again.";
  }
  return failureMessage || "Browser page capture did not succeed on the current page.";
}
async function tryCreateCurrentTabRawUploadTask(client2, message) {
  const tabId = message.pageContext?.tabId;
  if (!tabId) {
    return null;
  }
  if (shouldSkipArxivCurrentTabCapture(message)) {
    return null;
  }
  const response = await chrome.tabs.sendMessage(tabId, {
    type: "mdtero.capture_current_tab.request"
  });
  if (response?.xml?.ok && response.xml.payloadText) {
    return client2.createParseFulltextV2Task({
      fulltextFile: new Blob([response.xml.payloadText], { type: "application/xml" }),
      filename: response.xml.payloadName || "paper.xml",
      sourceDoi: inferSourceDoi(message.input) || normalizeSpringerInput(message.input, message.pageContext?.tabUrl) || void 0,
      sourceInput: message.input
    });
  }
  const capture = response?.capture;
  if (!response?.ok) {
    throw new Error(
      describeCurrentTabCaptureFailure({
        failureCode: "content_script_unavailable"
      })
    );
  }
  if (!capture?.ok || !capture.html) {
    throw new Error(
      describeCurrentTabCaptureFailure({
        failureCode: capture?.failureCode,
        failureMessage: capture?.failureMessage
      })
    );
  }
  return client2.createParseFulltextV2Task({
    fulltextFile: new Blob([capture.html], { type: "text/html" }),
    filename: capture.payloadName || "paper.html",
    sourceDoi: inferSourceDoi(message.input),
    sourceInput: message.input
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
var CLI_ACADEMIC_KEY_HINT = "Configure academic source keys with `mdtero config academic` in the Python CLI, use the extension on an already-open full-text page, or upload the PDF/XML/EPUB file directly.";
async function executeAction(action, context, routePlan) {
  switch (action) {
    case "capture_current_tab_html":
      return executeCaptureCurrentTabHtml(context);
    case "native_arxiv_parse":
      return { success: true };
    case "fetch_structured_xml":
      return executeFetchStructuredXml(context, routePlan);
    case "fetch_elsevier_xml":
      return executeFetchElsevierXml(context, routePlan);
    case "fetch_wiley_tdm_pdf":
      return executeFetchWileyTdmPdf(context, routePlan);
    case "fetch_springer_pdf":
    case "fetch_remote_html":
      return executeFetchHelperSource(context, routePlan);
    case "fetch_epub_asset":
      return executeFetchEpubAsset(context, routePlan);
    case "fetch_oa_repository":
      return executeFetchOaRepository(context, routePlan);
    case "fetch_helper_source":
      return executeFetchHelperSource(context, routePlan);
    case "fallback_pdf_parse":
      return {
        success: false,
        requiresUpload: true,
        error: routePlan.user_message || "PDF upload required. Please download and upload the PDF manually."
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
        sourceDoi: inferSourceDoi2(context.input)
      };
    }
    const capture = response?.capture;
    if (!response?.ok) {
      return { success: false, error: "Content script unavailable. Reload the page and try again." };
    }
    if (!capture?.ok || !capture.html) {
      return {
        success: false,
        error: capture?.failureMessage || "Page capture failed"
      };
    }
    return {
      success: true,
      rawArtifact: new Blob([capture.html], { type: "text/html" }),
      filename: capture.payloadName || "paper.html",
      sourceDoi: inferSourceDoi2(context.input)
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
              sourceDoi: inferSourceDoi2(context.input)
            };
          }
        } catch {
        }
      }
    }
  }
  return { success: false, error: "No structured XML source available" };
}
async function executeFetchElsevierXml(context, routePlan) {
  return {
    success: false,
    requiresUpload: true,
    error: routePlan.user_message || buildElsevierLocalAcquireGuidance()
  };
}
async function executeFetchWileyTdmPdf(_context, routePlan) {
  return {
    success: false,
    requiresUpload: true,
    error: routePlan.user_message || `Wiley TDM requires a user token. ${CLI_ACADEMIC_KEY_HINT}`
  };
}
async function executeFetchEpubAsset(context, routePlan) {
  if (!context.tabId) {
    return {
      success: false,
      error: routePlan.user_message || "Open the article page in the current tab and retry EPUB capture."
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
        error: download?.failureMessage || "Browser page context could not download the EPUB artifact."
      };
    }
    return {
      success: true,
      rawArtifact: new Blob([base64ToBytes(download.payloadBase64)], { type: "application/epub+zip" }),
      filename: download.payloadName || "paper.epub",
      sourceDoi: inferSourceDoi2(context.input)
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
        error: "OA source is PDF. Please download and upload manually."
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
      sourceDoi: inferSourceDoi2(context.input)
    };
  } catch (error) {
    return { success: false, error: String(error) };
  }
}
async function executeFetchHelperSource(context, routePlan) {
  if (!context.tabId) {
    return {
      success: false,
      requiresUpload: true,
      error: "This source requires browser capture. Open the article page and retry."
    };
  }
  return executeCaptureCurrentTabHtml(context);
}
function inferSourceDoi2(input) {
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
    "springer_full_text_tdm",
    "elsevier_article_retrieval_api"
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
          const task = await parseClient.createParseFulltextV2Task({
            fulltextFile: result.rawArtifact,
            filename: result.filename || "paper.fulltext",
            sourceDoi: result.sourceDoi,
            sourceInput: context.input
          });
          return { success: true, taskId: task.task_id, task };
        } catch (error) {
          if (routePlan.fail_closed) {
            return { success: false, error: String(error) };
          }
          continue;
        }
      }
      if (result.taskId) {
        return { success: true, taskId: result.taskId };
      }
      continue;
    }
    if (result.requiresBrowserCapture || result.requiresHelper || result.requiresUpload) {
      return {
        success: false,
        requiresBrowserCapture: result.requiresBrowserCapture || result.requiresHelper,
        requiresHelper: result.requiresHelper,
        requiresUpload: result.requiresUpload,
        error: result.error
      };
    }
    if (routePlan.fail_closed) {
      return { success: false, error: result.error || "Action failed" };
    }
  }
  return { success: false, error: "No executable action succeeded" };
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
      throw new Error(formatSsotFailure(result));
    })().then((result) => sendResponse({ ok: true, result })).catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type === "mdtero.parse.request") {
    (async () => {
      const settings = await readSettings();
      if (!settings.token) {
        throw new Error("Sign in required before parsing or translating.");
      }
      return runLegacyParseRequest(client, {
        input: message.input,
        pageContext: message.pageContext
      });
    })().then((result) => sendResponse({ ok: true, result })).catch((error) => sendResponse({ ok: false, error: error.message }));
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
      return runLegacyFileParseRequest(client, {
        file: message.file,
        filename: message.filename,
        artifactKind: message.artifactKind
      });
    })().then((result) => sendResponse({ ok: true, result })).catch((error) => sendResponse({ ok: false, error: error.message }));
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
      return client.createTranslateTask({
        source_markdown_path: message.sourceMarkdownPath,
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
//# sourceMappingURL=background.js.map
