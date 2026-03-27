// src/lib/api.ts
function buildHelperFirstParseBody(params) {
  const body = new FormData();
  body.set(params.fileField, params.file, params.filename);
  if (params.sourceDoi) {
    body.set("source_doi", params.sourceDoi);
  }
  if (params.sourceInput) {
    body.set("source_input", params.sourceInput);
  }
  return body;
}
function fallbackArtifactFilename(artifact) {
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
  function extractFilename(contentDisposition, fallback) {
    const match = contentDisposition?.match(/filename="([^"]+)"/i);
    return match?.[1] ?? fallback;
  }
  return {
    startEmailAuth(payload) {
      return request("/auth/email/start", {
        method: "POST",
        body: JSON.stringify(payload)
      }).then((response) => response.json());
    },
    verifyEmailAuth(payload) {
      return request("/auth/email/verify", {
        method: "POST",
        body: JSON.stringify(payload)
      }).then((response) => response.json());
    },
    loginWithPassword(payload) {
      return request("/auth/password/login", {
        method: "POST",
        body: JSON.stringify(payload)
      }).then((response) => response.json());
    },
    getUsage() {
      return request("/me/usage", void 0, { requireAuth: true }).then((response) => response.json());
    },
    getParserV2ShadowDiagnostics() {
      return request("/diagnostics/parser-v2/shadow", void 0, { requireAuth: true }).then(
        (response) => response.json()
      );
    },
    getClientConfig() {
      return request("/client-config").then((response) => response.json());
    },
    getMyTasks() {
      return request("/me/tasks", void 0, { requireAuth: true }).then((response) => response.json());
    },
    createParseTask(payload) {
      return request("/tasks/parse", {
        method: "POST",
        body: JSON.stringify(payload)
      }, { requireAuth: true }).then((response) => response.json());
    },
    createUploadedParseTask(payload) {
      const body = new FormData();
      body.set("xml_file", payload.xmlFile, payload.filename ?? "paper.xml");
      if (payload.sourceDoi) {
        body.set("source_doi", payload.sourceDoi);
      }
      if (payload.sourceInput) {
        body.set("source_input", payload.sourceInput);
      }
      return request("/tasks/parse-upload", {
        method: "POST",
        body
      }, { requireAuth: true }).then((response) => response.json());
    },
    createParseFulltextV2Task(payload) {
      const body = buildHelperFirstParseBody({
        fileField: "fulltext_file",
        file: payload.fulltextFile,
        filename: payload.filename ?? "paper.fulltext",
        sourceDoi: payload.sourceDoi,
        sourceInput: payload.sourceInput
      });
      return request("/tasks/parse-fulltext-v2", {
        method: "POST",
        body
      }, { requireAuth: true }).then((response) => response.json());
    },
    createParseHelperBundleV2Task(payload) {
      const body = buildHelperFirstParseBody({
        fileField: "helper_bundle",
        file: payload.helperBundleFile,
        filename: payload.filename ?? "helper-bundle.zip",
        sourceDoi: payload.sourceDoi,
        sourceInput: payload.sourceInput
      });
      if (payload.pdfEngine) {
        body.set("pdf_engine", payload.pdfEngine);
      }
      return request("/tasks/parse-helper-bundle-v2", {
        method: "POST",
        body
      }, { requireAuth: true }).then((response) => response.json());
    },
    createTranslateTask(payload) {
      return request("/tasks/translate", {
        method: "POST",
        body: JSON.stringify(payload)
      }, { requireAuth: true }).then((response) => response.json());
    },
    getTask(taskId) {
      return request(`/tasks/${taskId}`, void 0, { requireAuth: true }).then((response) => response.json());
    },
    downloadArtifact(taskId, artifact) {
      return request(`/tasks/${taskId}/download/${artifact}`, void 0, { requireAuth: true }).then(async (response) => ({
        blob: await response.blob(),
        filename: extractFilename(response.headers.get("Content-Disposition"), fallbackArtifactFilename(artifact)),
        mediaType: response.headers.get("Content-Type") ?? "application/octet-stream"
      }));
    }
  };
}

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

// src/lib/runtime.ts
function createParseMessage(input, elsevierApiKey, pageContext) {
  const message = {
    type: "mdtero.parse.request",
    input
  };
  if (elsevierApiKey) {
    message.elsevierApiKey = elsevierApiKey;
  }
  if (pageContext) {
    message.pageContext = pageContext;
  }
  return message;
}
function createFileParseMessage(file, artifactKind, pdfEngine) {
  const message = {
    type: "mdtero.parse.file.request",
    file,
    filename: file.name,
    mediaType: file.type,
    artifactKind
  };
  if (artifactKind === "pdf" && pdfEngine) {
    message.pdfEngine = pdfEngine;
  }
  return message;
}
function createTranslateMessage(sourceMarkdownPath, targetLanguage, mode) {
  return {
    type: "mdtero.translate.request",
    sourceMarkdownPath,
    targetLanguage,
    mode
  };
}
function createDetectMessage() {
  return {
    type: "mdtero.detect.request"
  };
}

// ../shared/src/api-contract.ts
var DEFAULT_API_BASE_URL = "https://api.mdtero.com";

// ../shared/src/publisher-capability-matrix.ts
function link(href, en, zh) {
  return {
    href,
    label: { en, zh }
  };
}
var PUBLISHER_CAPABILITY_MATRIX = [
  {
    id: "arxiv",
    label: { en: "arXiv", zh: "arXiv" },
    variantOf: "arxiv",
    accessVariant: "open_repository",
    presentationGroup: "helper_only",
    rightsMode: "open",
    acquisitionMode: "direct_open_fulltext",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: false,
    mayNeedInstitutionAccess: false,
    whatYouNeed: {
      en: "Install the local helper.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\u3002"
    },
    howMdteroGetsIt: {
      en: "Direct open full-text retrieval from arXiv.",
      zh: "\u76F4\u63A5\u4ECE arXiv \u83B7\u53D6\u5F00\u653E\u5168\u6587\u3002"
    },
    configureTarget: "none",
    status: "stable",
    fallbacks: ["pdf"],
    validationRef: "acceptance:task-arxiv-html-live-1",
    links: []
  },
  {
    id: "pmc_europe_pmc",
    label: { en: "PMC / Europe PMC", zh: "PMC / Europe PMC" },
    variantOf: "pmc",
    accessVariant: "open_access",
    presentationGroup: "helper_only",
    rightsMode: "open",
    acquisitionMode: "direct_open_fulltext",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: false,
    mayNeedInstitutionAccess: false,
    whatYouNeed: {
      en: "Install the local helper.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\u3002"
    },
    howMdteroGetsIt: {
      en: "Structured open-access full text from PMC routes.",
      zh: "\u901A\u8FC7 PMC \u8DEF\u7EBF\u83B7\u53D6\u7ED3\u6784\u5316\u5F00\u653E\u5168\u6587\u3002"
    },
    configureTarget: "none",
    status: "stable",
    fallbacks: ["pdf"],
    validationRef: "checklist:pmc-open-access",
    links: []
  },
  {
    id: "plos",
    label: { en: "PLOS", zh: "PLOS" },
    variantOf: "plos",
    accessVariant: "open_access",
    presentationGroup: "helper_only",
    rightsMode: "open",
    acquisitionMode: "direct_open_fulltext",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: false,
    mayNeedInstitutionAccess: false,
    whatYouNeed: {
      en: "Install the local helper.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\u3002"
    },
    howMdteroGetsIt: {
      en: "Structured open-access full text from PLOS.",
      zh: "\u4ECE PLOS \u83B7\u53D6\u7ED3\u6784\u5316\u5F00\u653E\u5168\u6587\u3002"
    },
    configureTarget: "none",
    status: "stable",
    fallbacks: ["pdf"],
    validationRef: "checklist:plos-open-access",
    links: []
  },
  {
    id: "biorxiv_medrxiv",
    label: { en: "bioRxiv / medRxiv", zh: "bioRxiv / medRxiv" },
    variantOf: "biorxiv_medrxiv",
    accessVariant: "preprint_server",
    presentationGroup: "helper_only",
    rightsMode: "open",
    acquisitionMode: "direct_open_fulltext",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: false,
    mayNeedInstitutionAccess: false,
    whatYouNeed: {
      en: "Install the local helper.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\u3002"
    },
    howMdteroGetsIt: {
      en: "Preprint full text from the source site.",
      zh: "\u4ECE\u9884\u5370\u672C\u6E90\u7AD9\u83B7\u53D6\u5168\u6587\u3002"
    },
    configureTarget: "none",
    status: "stable",
    fallbacks: ["pdf"],
    validationRef: "checklist:biorxiv-medrxiv-open",
    links: []
  },
  {
    id: "chemrxiv",
    label: { en: "ChemRxiv", zh: "ChemRxiv" },
    variantOf: "chemrxiv",
    accessVariant: "preprint_server",
    presentationGroup: "helper_only",
    rightsMode: "open",
    acquisitionMode: "direct_open_fulltext",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: false,
    mayNeedInstitutionAccess: false,
    whatYouNeed: {
      en: "Install the local helper.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\u3002"
    },
    howMdteroGetsIt: {
      en: "Preprint full text from ChemRxiv when available.",
      zh: "\u5728\u53EF\u7528\u65F6\u4ECE ChemRxiv \u83B7\u53D6\u9884\u5370\u672C\u5168\u6587\u3002"
    },
    configureTarget: "none",
    status: "demo",
    fallbacks: ["pdf"],
    validationRef: "checklist:chemrxiv-demo",
    links: []
  },
  {
    id: "mdpi",
    label: { en: "MDPI", zh: "MDPI" },
    variantOf: "mdpi",
    accessVariant: "publisher_open_page",
    presentationGroup: "helper_only",
    rightsMode: "open",
    acquisitionMode: "direct_open_fulltext",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: false,
    mayNeedInstitutionAccess: false,
    whatYouNeed: {
      en: "Install the local helper.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\u3002"
    },
    howMdteroGetsIt: {
      en: "Open publisher full text from MDPI pages.",
      zh: "\u4ECE MDPI \u9875\u9762\u83B7\u53D6\u5F00\u653E\u5168\u6587\u3002"
    },
    configureTarget: "none",
    status: "demo",
    fallbacks: ["pdf"],
    validationRef: "checklist:mdpi-demo",
    links: []
  },
  {
    id: "elsevier",
    label: { en: "Elsevier", zh: "Elsevier" },
    variantOf: "elsevier",
    accessVariant: "api",
    presentationGroup: "api_key",
    rightsMode: "licensed",
    acquisitionMode: "official_api",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: true,
    mayNeedInstitutionAccess: true,
    whatYouNeed: {
      en: "Install the local helper and add your Elsevier API key. Some papers may still require institutional access.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\uFF0C\u5E76\u586B\u5199 Elsevier API key\u3002\u90E8\u5206\u8BBA\u6587\u4ECD\u53EF\u80FD\u9700\u8981\u673A\u6784\u6743\u9650\u3002"
    },
    howMdteroGetsIt: {
      en: "Official full-text API for structured publisher retrieval.",
      zh: "\u901A\u8FC7\u5B98\u65B9\u5168\u6587 API \u83B7\u53D6\u7ED3\u6784\u5316\u51FA\u7248\u793E\u5185\u5BB9\u3002"
    },
    configureTarget: "connector_keys",
    status: "stable",
    fallbacks: ["pdf"],
    validationRef: "acceptance:elsevier-local-api",
    links: [
      link("https://dev.elsevier.com/", "Get Elsevier API key", "\u7533\u8BF7 Elsevier API key")
    ]
  },
  {
    id: "springer_oa",
    label: { en: "Springer Open Access", zh: "Springer Open Access" },
    variantOf: "springer",
    accessVariant: "open_access",
    presentationGroup: "api_key",
    rightsMode: "open",
    acquisitionMode: "hybrid",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: true,
    mayNeedInstitutionAccess: false,
    whatYouNeed: {
      en: "Install the local helper. Add your Springer OA API key for the best XML path.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\u3002\u586B\u5199 Springer OA API key \u53EF\u4F18\u5148\u8D70 XML \u8DEF\u5F84\u3002"
    },
    howMdteroGetsIt: {
      en: "Springer OA XML when available, otherwise open full text.",
      zh: "\u4F18\u5148\u83B7\u53D6 Springer OA XML\uFF0C\u5426\u5219\u8D70\u5F00\u653E\u5168\u6587\u3002"
    },
    configureTarget: "connector_keys",
    status: "stable",
    fallbacks: ["browser_page_capture", "pdf"],
    validationRef: "acceptance:task-springer-s12011-04820-w",
    links: [
      link("https://dev.springernature.com/", "Get Springer Nature API key", "\u7533\u8BF7 Springer Nature API key")
    ]
  },
  {
    id: "springer_subscription",
    label: { en: "Springer subscription pages", zh: "Springer \u8BA2\u9605\u9875\u9762" },
    variantOf: "springer",
    accessVariant: "subscription_page",
    presentationGroup: "browser_assisted",
    rightsMode: "licensed",
    acquisitionMode: "browser_page_capture",
    requiresHelper: true,
    requiresBrowser: true,
    requiresApiKey: false,
    mayNeedInstitutionAccess: true,
    whatYouNeed: {
      en: "Install the local helper and keep the article page open in your browser. Institutional sign-in may be required.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\uFF0C\u5E76\u5728\u6D4F\u89C8\u5668\u4E2D\u4FDD\u6301\u6587\u7AE0\u9875\u9762\u6253\u5F00\u3002\u53EF\u80FD\u9700\u8981\u673A\u6784\u767B\u5F55\u3002"
    },
    howMdteroGetsIt: {
      en: "Browser-assisted page capture from the live article page.",
      zh: "\u901A\u8FC7\u5B9E\u65F6\u6587\u7AE0\u9875\u8FDB\u884C\u6D4F\u89C8\u5668\u8F85\u52A9\u6293\u53D6\u3002"
    },
    configureTarget: "browser_assisted_sources",
    status: "demo",
    fallbacks: ["pdf"],
    validationRef: "acceptance:task-springer-s12011-04820-w",
    links: []
  },
  {
    id: "wiley",
    label: { en: "Wiley", zh: "Wiley" },
    variantOf: "wiley",
    accessVariant: "publisher_page",
    presentationGroup: "browser_assisted",
    rightsMode: "licensed",
    acquisitionMode: "browser_page_capture",
    requiresHelper: true,
    requiresBrowser: true,
    requiresApiKey: false,
    mayNeedInstitutionAccess: true,
    whatYouNeed: {
      en: "Install the local helper and keep the article page open in your browser. Institutional sign-in may be required.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\uFF0C\u5E76\u5728\u6D4F\u89C8\u5668\u4E2D\u4FDD\u6301\u6587\u7AE0\u9875\u9762\u6253\u5F00\u3002\u53EF\u80FD\u9700\u8981\u673A\u6784\u767B\u5F55\u3002"
    },
    howMdteroGetsIt: {
      en: "Browser-assisted page capture from Wiley article pages.",
      zh: "\u901A\u8FC7 Wiley \u6587\u7AE0\u9875\u8FDB\u884C\u6D4F\u89C8\u5668\u8F85\u52A9\u6293\u53D6\u3002"
    },
    configureTarget: "browser_assisted_sources",
    status: "experimental",
    fallbacks: ["pdf"],
    validationRef: "acceptance:task-wiley-validation-1",
    links: []
  },
  {
    id: "taylor_francis",
    label: { en: "Taylor & Francis", zh: "Taylor & Francis" },
    variantOf: "taylor_francis",
    accessVariant: "publisher_page",
    presentationGroup: "browser_assisted",
    rightsMode: "licensed",
    acquisitionMode: "browser_page_capture",
    requiresHelper: true,
    requiresBrowser: true,
    requiresApiKey: false,
    mayNeedInstitutionAccess: true,
    whatYouNeed: {
      en: "Install the local helper and keep the article page open in your browser. Institutional sign-in may be required.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\uFF0C\u5E76\u5728\u6D4F\u89C8\u5668\u4E2D\u4FDD\u6301\u6587\u7AE0\u9875\u9762\u6253\u5F00\u3002\u53EF\u80FD\u9700\u8981\u673A\u6784\u767B\u5F55\u3002"
    },
    howMdteroGetsIt: {
      en: "Browser-assisted page capture from Taylor & Francis pages.",
      zh: "\u901A\u8FC7 Taylor & Francis \u9875\u9762\u8FDB\u884C\u6D4F\u89C8\u5668\u8F85\u52A9\u6293\u53D6\u3002"
    },
    configureTarget: "browser_assisted_sources",
    status: "experimental",
    fallbacks: ["pdf"],
    validationRef: "acceptance:task-tf-html-live-3",
    links: []
  }
];

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
    elsevierApiKey: current.elsevierApiKey,
    springerOpenAccessApiKey: current.springerOpenAccessApiKey,
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
function getReconnectablePendingTranslationTask(state, detectedInput, parseMarkdownPath) {
  if (!state || state.input !== detectedInput || state.pendingTaskKind !== "translate" || !state.pendingTaskId || state.parseMarkdownPath !== parseMarkdownPath) {
    return void 0;
  }
  return {
    taskId: state.pendingTaskId,
    kind: "translate"
  };
}

// src/lib/bridge-wake.ts
var BRIDGE_SUPPORTED_URL_PATTERNS = [
  "arxiv.org",
  "sciencedirect.com/science/article/pii/",
  "link.springer.com",
  "springer.com",
  "springernature.com",
  "onlinelibrary.wiley.com",
  "tandfonline.com"
];
function isBridgeSupportedPage(url) {
  const normalized = String(url || "").trim().toLowerCase();
  return BRIDGE_SUPPORTED_URL_PATTERNS.some((pattern) => normalized.includes(pattern));
}

// src/popup/task-view.ts
var SECONDARY_ORDER = ["translated_md"];
var SOURCE_ORDER = ["paper_pdf", "paper_xml"];
function getPreferredArtifactKey(result) {
  if (!result?.artifacts) {
    return void 0;
  }
  if (result.preferred_artifact && result.artifacts[result.preferred_artifact]) {
    return result.preferred_artifact;
  }
  return Object.keys(result.artifacts)[0];
}
function getSecondaryArtifactKeys(result) {
  const preferred = getPreferredArtifactKey(result);
  const artifactKeys = Object.keys(result?.artifacts ?? {});
  return SECONDARY_ORDER.filter(
    (key) => artifactKeys.includes(key) && key !== preferred
  );
}
function getSourceArtifactKeys(result) {
  const artifactKeys = Object.keys(result?.artifacts ?? {});
  return SOURCE_ORDER.filter((key) => artifactKeys.includes(key));
}
function getDownloadLabel(artifactKey, language = "en") {
  if (language === "zh") {
    if (artifactKey === "paper_bundle") {
      return "\u4E0B\u8F7D\u538B\u7F29\u5305";
    }
    if (artifactKey === "translated_md") {
      return "\u4E0B\u8F7D\u8BD1\u6587";
    }
    if (artifactKey === "paper_pdf") {
      return "\u4E0B\u8F7D PDF";
    }
    if (artifactKey === "paper_xml") {
      return "\u4E0B\u8F7D XML";
    }
    return "\u4E0B\u8F7D\u6587\u4EF6";
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
      return "\u6B63\u5728\u89E3\u6790\u8BBA\u6587\u5E76\u6253\u5305\u6587\u4EF6...";
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
    return "Parsing paper and packaging files...";
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
    return errorMessage.trim();
  }
  const wallet = usage?.wallet_balance_display?.trim() || (language === "zh" ? "\xA50.00" : "$0.00");
  const parse = Number.isFinite(usage?.parse_quota_remaining) ? Number(usage?.parse_quota_remaining) : 0;
  const translation = Number.isFinite(usage?.translation_quota_remaining) ? Number(usage?.translation_quota_remaining) : 0;
  return language === "zh" ? `\u4F59\u989D ${wallet} \xB7 \u89E3\u6790 ${parse} \xB7 \u7FFB\u8BD1 ${translation}` : `Balance ${wallet} \xB7 Parse ${parse} \xB7 Translation ${translation}`;
}
function getBridgeStatusText(status, language = "en") {
  const state = String(status?.state || "").trim().toLowerCase();
  const runnerState = String(status?.runnerState || "").trim().toLowerCase();
  if (language === "zh") {
    if (state === "connected" && runnerState === "busy") {
      return "\u672C\u5730 helper \u5DF2\u8FDE\u63A5\uFF0C\u6B63\u5728\u5904\u7406\u6D4F\u89C8\u5668\u4EFB\u52A1\u3002";
    }
    if (state === "connected") {
      return "\u672C\u5730 helper \u5DF2\u5C31\u7EEA\uFF0C\u53EF\u5904\u7406\u6D4F\u89C8\u5668\u534F\u540C\u6293\u53D6\u3002";
    }
    if (state === "disconnected") {
      return "\u672C\u5730 helper \u5DF2\u65AD\u5F00\u3002\u8BF7\u91CD\u542F mdtero-local \u6216\u91CD\u8F7D\u6269\u5C55\u3002";
    }
    if (state === "unavailable") {
      return "\u6682\u672A\u68C0\u6D4B\u5230\u672C\u5730 helper\u3002\u8BF7\u5B89\u88C5\u6216\u542F\u52A8 mdtero-local\u3002";
    }
    return "\u672C\u5730 helper \u72B6\u6001\u672A\u77E5\u3002";
  }
  if (state === "connected" && runnerState === "busy") {
    return "Local helper is connected and handling a browser task.";
  }
  if (state === "connected") {
    return "Local helper ready for browser-assisted capture.";
  }
  if (state === "disconnected") {
    return "Local helper disconnected. Restart mdtero-local or reload the extension.";
  }
  if (state === "unavailable") {
    return "Local helper not detected. Install or start mdtero-local.";
  }
  return "Local helper status unknown.";
}
function getPreflightHintText(params, language = "en") {
  const input = String(params.input || "").trim();
  const pageUrl = String(params.pageUrl || "").trim();
  const bridgeState = String(params.bridgeStatus?.state || "").trim().toLowerCase();
  const bridgeReady = bridgeState === "connected";
  const bridgeMissing = bridgeState === "unavailable" || bridgeState === "disconnected";
  const candidate = pageUrl || input;
  const livePageSupported = isBridgeSupportedPage(candidate);
  const looksLikePdfShell = candidate.includes("/pdf") || candidate.includes("/epdf") || candidate.includes("download=true") || candidate.includes("/epub/");
  if (looksLikePdfShell) {
    return language === "zh" ? "\u5F53\u524D\u66F4\u50CF PDF/EPUB \u9875\u9762\u3002\u5EFA\u8BAE\u5148\u5207\u5230 HTML \u6B63\u6587\u9875\uFF0C\u518D\u8FDB\u884C\u672C\u5730\u6293\u53D6\u3002" : "This looks like a PDF/EPUB page. Open the HTML full-text page first for better local capture.";
  }
  if (input && requiresElsevierLocalAcquire(input) && !params.hasElsevierApiKey) {
    return language === "zh" ? "\u5F53\u524D\u8F93\u5165\u547D\u4E2D\u4E86 Elsevier / ScienceDirect\u3002\u8BF7\u5148\u5728\u8BBE\u7F6E\u91CC\u586B\u5199 Elsevier API Key\u3002" : "This input maps to Elsevier / ScienceDirect. Add your Elsevier API Key in Settings first.";
  }
  if (!livePageSupported) {
    return "";
  }
  if (bridgeMissing) {
    return language === "zh" ? "\u5F53\u524D\u9875\u9762\u652F\u6301\u6D4F\u89C8\u5668\u6001\u672C\u5730\u6293\u53D6\uFF0C\u4F46\u8FD8\u6CA1\u68C0\u6D4B\u5230 helper\u3002\u8BF7\u5148\u542F\u52A8 `mdtero-local`\u3002" : "This page supports browser-managed local capture, but the helper is not ready. Start `mdtero-local` first.";
  }
  if (bridgeReady) {
    return language === "zh" ? "\u5F53\u524D\u9875\u9762\u5DF2\u6EE1\u8DB3\u6D4F\u89C8\u5668\u6001\u672C\u5730\u6293\u53D6\u6761\u4EF6\uFF0C\u53EF\u4F18\u5148\u8D70 helper-first \u91C7\u96C6\u3002" : "This page is ready for browser-managed local capture through the helper-first path.";
  }
  return language === "zh" ? "\u5F53\u524D\u9875\u9762\u652F\u6301\u6D4F\u89C8\u5668\u6001\u672C\u5730\u6293\u53D6\u3002\u89E3\u6790\u524D\u8BF7\u786E\u8BA4 helper \u5DF2\u8FDE\u63A5\u3002" : "This page supports browser-managed local capture. Confirm the local helper is connected before parsing.";
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
  if (result.warning_code === "elsevier_abstract_only") {
    return language === "zh" ? "Elsevier \u4EC5\u8FD4\u56DE\u4E86\u6458\u8981\u3002\u8BF7\u786E\u8BA4\u4F60\u5F53\u524D\u662F\u5426\u5904\u4E8E\u6821\u56ED\u7F51\u6216\u673A\u6784 IP \u73AF\u5883\u3002" : "Elsevier only returned the abstract. Are you on a campus or institutional network IP?";
  }
  return result.warning_message ?? "";
}

// src/popup/index.ts
var COPY = {
  en: {
    title: "Mdtero",
    subtitle: "Helper-first local paper workflow",
    guest: "Guest mode",
    signedIn: (email) => email,
    usageSummary: (wallet, parse, translation) => `Balance ${wallet} \xB7 Parse ${parse} \xB7 Translation ${translation}`,
    signInHint: "Sign in to unlock parse bundles and translation.",
    freeHint: "PDF/XML free",
    supportSummary: "Open papers on your own machine and turn them into reusable Markdown packages.",
    supportStableTitle: "Ready now",
    supportStableItems: "arXiv, PMC / Europe PMC, bioRxiv / medRxiv, PLOS, Springer Open Access, and other open sources work best.",
    supportShadowTitle: "Use your own access",
    supportShadowItems: "Publisher pages such as Elsevier and Springer work best when you can already open the full text yourself.",
    supportExperimentalTitle: "Browser help may be needed",
    supportExperimentalItems: "Some Wiley and Taylor & Francis pages still vary by login and challenge flow.",
    inputLabel: "DOI or live page",
    inputPlaceholder: "10.1016/...",
    fileIntakeTitle: "Local file intake",
    fileIntakeNote: "Use this when you already have a local PDF or EPUB and want the same Markdown package flow.",
    pickPdfButton: "Use PDF",
    pickEpubButton: "Use EPUB",
    fileNameEmpty: "No local file selected.",
    pdfEngineLabel: "PDF engine",
    localFileParsing: (filename) => `Uploading ${filename} for helper-first parsing...`,
    localFileParseFailed: "Local file parse failed. Please try again.",
    parseButton: "Parse Paper",
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
    openPaper: "Use DOI",
    enterDoi: "Enter a DOI first.",
    translateFirst: "Parse a paper successfully before translating.",
    parseReady: (filename) => `Ready: ${filename}`,
    translateReady: (filename) => `Ready: ${filename}`,
    parseFailed: "Parse failed. Please try again.",
    translationFailed: "Translation failed. Please try again.",
    detected: (kind) => `Detected ${kind}.`,
    noDoi: "No DOI detected. Paste one manually.",
    noActiveTab: "No active tab available.",
    downloadFailed: "Download failed. Please try again.",
    campusHint: "Note: Campus network IP required for non-open access full-text.",
    elsevierKeyRequired: "ScienceDirect link detected. Please configure Elsevier API Key in settings first."
  },
  zh: {
    title: "Mdtero",
    subtitle: "helper-first \u672C\u5730\u8BBA\u6587\u5DE5\u4F5C\u6D41",
    guest: "\u6E38\u5BA2\u6A21\u5F0F",
    signedIn: (email) => email,
    usageSummary: (wallet, parse, translation) => `\u4F59\u989D ${wallet} \xB7 \u89E3\u6790 ${parse} \xB7 \u7FFB\u8BD1 ${translation}`,
    signInHint: "\u767B\u5F55\u540E\u53EF\u4F7F\u7528\u538B\u7F29\u5305\u89E3\u6790\u548C\u7FFB\u8BD1\u3002",
    freeHint: "PDF/XML \u514D\u8D39",
    supportSummary: "\u5728\u4F60\u81EA\u5DF1\u7684\u8BBE\u5907\u4E0A\u6253\u5F00\u8BBA\u6587\uFF0C\u5E76\u6574\u7406\u6210\u53EF\u590D\u7528\u7684 Markdown \u6587\u732E\u5305\u3002",
    supportStableTitle: "\u73B0\u5728\u5C31\u80FD\u7528",
    supportStableItems: "arXiv\u3001PMC / Europe PMC\u3001bioRxiv / medRxiv\u3001PLOS\u3001Springer Open Access \u7B49\u5F00\u653E\u6765\u6E90\u6700\u987A\u624B\u3002",
    supportShadowTitle: "\u4F7F\u7528\u4F60\u81EA\u5DF1\u7684\u8BBF\u95EE\u6743\u9650",
    supportShadowItems: "Elsevier\u3001Springer \u7B49\u51FA\u7248\u793E\u9875\u9762\uFF0C\u5728\u4F60\u81EA\u5DF1\u5DF2\u7ECF\u80FD\u6253\u5F00\u5168\u6587\u65F6\u901A\u5E38\u6548\u679C\u6700\u597D\u3002",
    supportExperimentalTitle: "\u6709\u65F6\u9700\u8981\u6D4F\u89C8\u5668\u8F85\u52A9",
    supportExperimentalItems: "\u90E8\u5206 Wiley \u4E0E Taylor & Francis \u9875\u9762\u4ECD\u4F1A\u53D7\u767B\u5F55\u6001\u6216\u6311\u6218\u9875\u5F71\u54CD\u3002",
    inputLabel: "DOI \u6216\u5B9E\u65F6\u9875\u9762",
    inputPlaceholder: "10.1016/...",
    fileIntakeTitle: "\u672C\u5730\u6587\u4EF6\u5165\u53E3",
    fileIntakeNote: "\u5982\u679C\u4F60\u624B\u91CC\u5DF2\u7ECF\u6709 PDF \u6216 EPUB\uFF0C\u4E5F\u53EF\u4EE5\u7EE7\u7EED\u8D70\u540C\u4E00\u6761 Markdown \u6253\u5305\u94FE\u3002",
    pickPdfButton: "\u9009\u62E9 PDF",
    pickEpubButton: "\u9009\u62E9 EPUB",
    fileNameEmpty: "\u5C1A\u672A\u9009\u62E9\u672C\u5730\u6587\u4EF6\u3002",
    pdfEngineLabel: "PDF \u5F15\u64CE",
    localFileParsing: (filename) => `\u6B63\u5728\u4E0A\u4F20 ${filename}\uFF0C\u5E76\u8D70 helper-first \u89E3\u6790...`,
    localFileParseFailed: "\u672C\u5730\u6587\u4EF6\u89E3\u6790\u5931\u8D25\uFF0C\u8BF7\u91CD\u8BD5\u3002",
    parseButton: "\u89E3\u6790\u8BBA\u6587",
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
    enterDoi: "\u8BF7\u5148\u8F93\u5165 DOI\u3002",
    translateFirst: "\u8BF7\u5148\u6210\u529F\u89E3\u6790\u8BBA\u6587\uFF0C\u518D\u8FDB\u884C\u7FFB\u8BD1\u3002",
    parseReady: (filename) => `\u5DF2\u5C31\u7EEA\uFF1A${filename}`,
    translateReady: (filename) => `\u5DF2\u5C31\u7EEA\uFF1A${filename}`,
    parseFailed: "\u89E3\u6790\u5931\u8D25\uFF0C\u8BF7\u91CD\u8BD5\u3002",
    translationFailed: "\u7FFB\u8BD1\u5931\u8D25\uFF0C\u8BF7\u91CD\u8BD5\u3002",
    detected: (kind) => `\u5DF2\u8BC6\u522B${kind}\u3002`,
    noDoi: "\u672A\u8BC6\u522B\u5230 DOI\uFF0C\u8BF7\u624B\u52A8\u7C98\u8D34\u3002",
    noActiveTab: "\u5F53\u524D\u6CA1\u6709\u53EF\u7528\u6807\u7B7E\u9875\u3002",
    downloadFailed: "\u4E0B\u8F7D\u5931\u8D25\uFF0C\u8BF7\u91CD\u8BD5\u3002",
    campusHint: "\u63D0\u793A\uFF1A\u9700\u8981\u6821\u56ED\u7F51\u6216\u673A\u6784 IP \u624D\u80FD\u83B7\u53D6\u975E\u5F00\u6E90\u5168\u6587\uFF0C\u5426\u5219\u4EC5\u89E3\u6790\u6458\u8981\u3002",
    elsevierKeyRequired: "\u68C0\u6D4B\u5230 ScienceDirect \u94FE\u63A5\uFF0C\u8BF7\u5148\u5728\u8BBE\u7F6E\u4E2D\u914D\u7F6E Elsevier API Key\u3002"
  }
};
var titleEl = document.querySelector("#app-title");
var subtitleEl = document.querySelector("#app-subtitle");
var languageToggleEl = document.querySelector("#language-toggle");
var accountEmailEl = document.querySelector("#account-email");
var usageStatusEl = document.querySelector("#usage-status");
var helperStatusEl = document.querySelector("#helper-status");
var freeHintEl = document.querySelector("#free-hint");
var supportSummaryEl = document.querySelector("#support-summary");
var supportStableTitleEl = document.querySelector("#support-stable-title");
var supportStableItemsEl = document.querySelector("#support-stable-items");
var supportShadowTitleEl = document.querySelector("#support-shadow-title");
var supportShadowItemsEl = document.querySelector("#support-shadow-items");
var supportExperimentalTitleEl = document.querySelector("#support-experimental-title");
var supportExperimentalItemsEl = document.querySelector("#support-experimental-items");
var inputLabelEl = document.querySelector("#paper-input-label");
var inputEl = document.querySelector("#paper-input");
var statusEl = document.querySelector("#status");
var preflightHintEl = document.querySelector("#preflight-hint");
var campusHintEl = document.querySelector("#campus-hint");
var fileIntakeTitleEl = document.querySelector("#file-intake-title");
var fileIntakeNoteEl = document.querySelector("#file-intake-note");
var pickPdfButton = document.querySelector("#pick-pdf-button");
var pickEpubButton = document.querySelector("#pick-epub-button");
var localFileInputEl = document.querySelector("#local-file-input");
var localFileNameEl = document.querySelector("#local-file-name");
var pdfEngineLabelEl = document.querySelector("#pdf-engine-label");
var pdfEngineSelectEl = document.querySelector("#pdf-engine-select");
var parseButton = document.querySelector("#parse-button");
var openSettingsButton = document.querySelector("#open-settings");
var translateLanguageLabelEl = document.querySelector("#translate-language-label");
var translateButton = document.querySelector("#translate-button");
var translateLanguageEl = document.querySelector("#translate-language");
var resultEl = document.querySelector("#result");
var artifactActionsEl = document.querySelector("#artifact-actions");
var downloadButton = document.querySelector("#download-link");
var secondaryDownloadsEl = document.querySelector("#secondary-downloads");
var sourceFilesEl = document.querySelector("#source-files");
var sourceFilesSummaryEl = document.querySelector("#source-files-summary");
var sourceDownloadsEl = document.querySelector("#source-downloads");
var recentTasksEl = document.querySelector("#recent-tasks");
var recentTasksSummaryEl = document.querySelector("#recent-tasks-summary");
var recentTaskListEl = document.querySelector("#recent-task-list");
var client = createApiClient(readSettings);
var lastParsedMarkdownPath = null;
var currentInput = null;
var uiLanguage = "en";
var isParsing = false;
var isTranslating = false;
var detectedPageContext = null;
var currentBridgeStatus = null;
function copyFor(language) {
  return COPY[language];
}
function setResult(message) {
  if (resultEl) {
    resultEl.textContent = message;
  }
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
  setPreflightHint(
    getPreflightHintText(
      {
        input,
        pageUrl,
        bridgeStatus: currentBridgeStatus,
        hasElsevierApiKey: Boolean(settings.elsevierApiKey)
      },
      uiLanguage
    )
  );
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
    parseFilename: state.parseFilename,
    translatedTaskId: state.translatedTaskId,
    translatedFilename: state.translatedFilename
  };
}
async function saveArtifact(taskId, artifactKey) {
  try {
    const artifact = await client.downloadArtifact(taskId, artifactKey);
    triggerBlobDownload(artifact.blob, artifact.filename);
  } catch {
    setResult(getCurrentCopy().downloadFailed);
  }
}
function applyLanguage() {
  const copy = getCurrentCopy();
  document.documentElement.lang = uiLanguage === "zh" ? "zh-CN" : "en";
  if (titleEl) titleEl.textContent = copy.title;
  if (subtitleEl) subtitleEl.textContent = copy.subtitle;
  if (languageToggleEl) languageToggleEl.textContent = toggleLanguageLabel(uiLanguage);
  if (freeHintEl) freeHintEl.textContent = copy.freeHint;
  if (supportSummaryEl) supportSummaryEl.textContent = copy.supportSummary;
  if (supportStableTitleEl) supportStableTitleEl.textContent = copy.supportStableTitle;
  if (supportStableItemsEl) supportStableItemsEl.textContent = copy.supportStableItems;
  if (supportShadowTitleEl) supportShadowTitleEl.textContent = copy.supportShadowTitle;
  if (supportShadowItemsEl) supportShadowItemsEl.textContent = copy.supportShadowItems;
  if (supportExperimentalTitleEl) supportExperimentalTitleEl.textContent = copy.supportExperimentalTitle;
  if (supportExperimentalItemsEl) supportExperimentalItemsEl.textContent = copy.supportExperimentalItems;
  if (inputLabelEl) inputLabelEl.textContent = copy.inputLabel;
  if (inputEl) inputEl.placeholder = copy.inputPlaceholder;
  if (fileIntakeTitleEl) fileIntakeTitleEl.textContent = copy.fileIntakeTitle;
  if (fileIntakeNoteEl) fileIntakeNoteEl.textContent = copy.fileIntakeNote;
  if (pickPdfButton) pickPdfButton.textContent = copy.pickPdfButton;
  if (pickEpubButton) pickEpubButton.textContent = copy.pickEpubButton;
  if (pdfEngineLabelEl) pdfEngineLabelEl.textContent = copy.pdfEngineLabel;
  if (localFileNameEl && !localFileNameEl.dataset.selectedName) {
    localFileNameEl.textContent = copy.fileNameEmpty;
  }
  if (campusHintEl) campusHintEl.textContent = copy.campusHint;
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
  renderActionButtons();
}
function renderActionButtons() {
  const copy = getCurrentCopy();
  if (parseButton) {
    parseButton.textContent = isParsing ? copy.parsingButton : copy.parseButton;
    parseButton.disabled = isParsing;
  }
  if (pickPdfButton) {
    pickPdfButton.disabled = isParsing;
  }
  if (pickEpubButton) {
    pickEpubButton.disabled = isParsing;
  }
  if (pdfEngineSelectEl) {
    pdfEngineSelectEl.disabled = isParsing;
  }
  if (translateButton) {
    translateButton.textContent = isTranslating ? copy.translatingButton : copy.translateButton;
    translateButton.disabled = isTranslating || !lastParsedMarkdownPath;
  }
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
function appendActionButton(container, taskId, artifactKey) {
  if (!container) {
    return;
  }
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = getDownloadLabel(artifactKey, uiLanguage);
  button.addEventListener("click", () => {
    void saveArtifact(taskId, artifactKey);
  });
  container.appendChild(button);
}
function renderArtifacts(task) {
  const preferredKey = getPreferredArtifactKey(task.result);
  clearSecondaryDownloads();
  if (!preferredKey || !task.result?.artifacts) {
    if (artifactActionsEl) artifactActionsEl.hidden = true;
    return;
  }
  if (artifactActionsEl) artifactActionsEl.hidden = false;
  if (downloadButton) {
    downloadButton.hidden = false;
    downloadButton.textContent = getDownloadLabel(preferredKey, uiLanguage);
    downloadButton.onclick = () => {
      void saveArtifact(task.task_id, preferredKey);
    };
  }
  getSecondaryArtifactKeys(task.result).forEach((artifactKey) => {
    appendActionButton(secondaryDownloadsEl, task.task_id, artifactKey);
  });
  const sourceArtifactKeys = getSourceArtifactKeys(task.result);
  if (sourceArtifactKeys.length > 0) {
    if (sourceFilesEl) {
      sourceFilesEl.hidden = false;
    }
    sourceArtifactKeys.forEach((artifactKey) => {
      appendActionButton(sourceDownloadsEl, task.task_id, artifactKey);
    });
  }
}
async function persistPopupState(task) {
  if (!currentInput || !task.result?.artifacts) {
    return;
  }
  const previous = await readPopupState();
  const nextState = {
    input: currentInput,
    parseTaskId: task.result.artifacts.paper_bundle ? task.task_id : previous?.parseTaskId,
    parseFilename: task.result.artifacts.paper_bundle?.filename ?? previous?.parseFilename,
    parseMarkdownPath: task.result.artifacts.paper_md?.path ?? previous?.parseMarkdownPath,
    translatedTaskId: task.result.artifacts.translated_md ? task.task_id : previous?.translatedTaskId,
    translatedFilename: task.result.artifacts.translated_md?.filename ?? previous?.translatedFilename,
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
    if (task.parseTaskId) {
      const zipButton = document.createElement("button");
      zipButton.type = "button";
      zipButton.className = "secondary-button";
      zipButton.textContent = getDownloadLabel("paper_bundle", uiLanguage);
      zipButton.addEventListener("click", () => {
        void saveArtifact(task.parseTaskId, "paper_bundle");
      });
      actions.appendChild(zipButton);
    }
    if (task.translatedTaskId) {
      const translatedButton = document.createElement("button");
      translatedButton.type = "button";
      translatedButton.className = "secondary-button";
      translatedButton.textContent = getDownloadLabel("translated_md", uiLanguage);
      translatedButton.addEventListener("click", () => {
        void saveArtifact(task.translatedTaskId, "translated_md");
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
  lastParsedMarkdownPath = savedState.parseMarkdownPath ?? null;
  renderActionButtons();
}
async function pollTask(taskId, kind) {
  const response = await chrome.runtime.sendMessage({
    type: "mdtero.task.get",
    taskId
  });
  if (!response?.ok) {
    setResult(response?.error ?? getCurrentCopy().parseFailed);
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
    return;
  }
  const task = response.result;
  if (task.status === "failed") {
    setResult(task.error_message ?? (kind === "parse" ? getCurrentCopy().parseFailed : getCurrentCopy().translationFailed));
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
    return;
  }
  if (task.status !== "succeeded") {
    setResult(
      getActionStatusText(kind === "parse" ? "running_parse" : "running_translate", uiLanguage)
    );
    window.setTimeout(() => {
      void pollTask(taskId, kind);
    }, 1500);
    return;
  }
  lastParsedMarkdownPath = task.result?.artifacts?.paper_md?.path ?? lastParsedMarkdownPath;
  renderArtifacts(task);
  await persistPopupState(task);
  await renderRecentTasks();
  if (kind === "parse") {
    isParsing = false;
    const filename = task.result?.artifacts?.paper_bundle?.filename;
    const warningText = getResultWarningText(task.result, uiLanguage);
    if (filename) {
      setResult([getCurrentCopy().parseReady(filename), warningText].filter(Boolean).join(" "));
    } else if (warningText) {
      setResult(warningText);
    }
  } else {
    isTranslating = false;
    const filename = task.result?.artifacts?.translated_md?.filename;
    if (filename) {
      setResult(getCurrentCopy().translateReady(filename));
    }
  }
  renderActionButtons();
}
async function refreshUsage() {
  const settings = await readSettings();
  if (accountEmailEl) {
    accountEmailEl.textContent = settings.email ? getCurrentCopy().signedIn(settings.email) : getCurrentCopy().guest;
  }
  if (!settings.token) {
    if (usageStatusEl) {
      usageStatusEl.textContent = getCurrentCopy().signInHint;
    }
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
}
async function refreshBridgeStatus() {
  if (!helperStatusEl) {
    return;
  }
  try {
    const response = await chrome.runtime.sendMessage({
      type: "mdtero.bridge.status"
    });
    currentBridgeStatus = response?.result ?? null;
    helperStatusEl.textContent = getBridgeStatusText(currentBridgeStatus, uiLanguage);
  } catch {
    currentBridgeStatus = null;
    helperStatusEl.textContent = getBridgeStatusText(void 0, uiLanguage);
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
    const response = await chrome.tabs.sendMessage(tab.id, createDetectMessage());
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
  setLocalFileName(file.name);
  isParsing = true;
  renderActionButtons();
  setResult(getCurrentCopy().localFileParsing(file.name));
  const settings = await readSettings();
  if (!settings.token) {
    isParsing = false;
    renderActionButtons();
    setResult(getCurrentCopy().signInHint);
    return;
  }
  const response = await chrome.runtime.sendMessage(
    createFileParseMessage(
      file,
      artifactKind,
      artifactKind === "pdf" ? pdfEngineSelectEl?.value : void 0
    )
  );
  if (!response?.ok) {
    isParsing = false;
    renderActionButtons();
    setResult(response?.error ?? getCurrentCopy().localFileParseFailed);
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
  isParsing = true;
  renderActionButtons();
  setResult(getActionStatusText("queued_parse", uiLanguage));
  const settings = await readSettings();
  if (!settings.token) {
    isParsing = false;
    renderActionButtons();
    setResult(getCurrentCopy().signInHint);
    return;
  }
  if (requiresElsevierLocalAcquire(input) && !settings.elsevierApiKey) {
    isParsing = false;
    renderActionButtons();
    setResult(getCurrentCopy().elsevierKeyRequired);
    setTimeout(() => {
      void chrome.runtime.openOptionsPage();
    }, 2e3);
    return;
  }
  const pageContext = await resolveParsePageContext(input);
  const response = await chrome.runtime.sendMessage(
    createParseMessage(input, settings.elsevierApiKey, pageContext)
  );
  if (!response?.ok) {
    isParsing = false;
    renderActionButtons();
    setResult(response?.error ?? getCurrentCopy().parseFailed);
    return;
  }
  await writePopupState({
    ...await readPopupState(),
    input,
    pendingTaskId: response.result.task_id,
    pendingTaskKind: "parse"
  });
  void pollTask(response.result.task_id, "parse");
});
translateButton?.addEventListener("click", async () => {
  if (isTranslating) {
    return;
  }
  if (!lastParsedMarkdownPath) {
    setResult(getCurrentCopy().translateFirst);
    return;
  }
  const previous = await readPopupState();
  const reconnectableTask = getReconnectablePendingTranslationTask(
    previous,
    currentInput ?? "",
    lastParsedMarkdownPath
  );
  if (reconnectableTask) {
    isTranslating = true;
    renderActionButtons();
    setResult(getActionStatusText("running_translate", uiLanguage));
    void pollTask(reconnectableTask.taskId, "translate");
    return;
  }
  isTranslating = true;
  renderActionButtons();
  setResult(getActionStatusText("queued_translate", uiLanguage));
  const response = await chrome.runtime.sendMessage(
    createTranslateMessage(
      lastParsedMarkdownPath,
      translateLanguageEl?.value ?? "zh",
      "standard"
    )
  );
  if (!response?.ok) {
    isTranslating = false;
    renderActionButtons();
    setResult(response?.error ?? getCurrentCopy().translationFailed);
    return;
  }
  await writePopupState({
    ...await readPopupState(),
    input: currentInput ?? "",
    parseMarkdownPath: lastParsedMarkdownPath,
    pendingTaskId: response.result.task_id,
    pendingTaskKind: "translate"
  });
  void pollTask(response.result.task_id, "translate");
});
openSettingsButton?.addEventListener("click", () => {
  void chrome.runtime.openOptionsPage();
});
inputEl?.addEventListener("input", () => {
  currentInput = inputEl.value.trim() || currentInput;
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
localFileInputEl?.addEventListener("change", () => {
  const file = localFileInputEl.files?.[0];
  const artifactKind = localFileInputEl.dataset.artifactKind === "epub" ? "epub" : "pdf";
  if (!file) {
    return;
  }
  void submitLocalFile(file, artifactKind);
  localFileInputEl.value = "";
});
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
