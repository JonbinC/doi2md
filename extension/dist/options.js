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
    getSourceConnectivityEnvironmentSummary() {
      return request("/diagnostics/source-connectivity/environment", void 0, { requireAuth: true }).then(
        (response) => response.json()
      );
    },
    explainSourceConnectivity(payload) {
      return request("/diagnostics/source-connectivity/explain", {
        method: "POST",
        body: JSON.stringify(payload)
      }, { requireAuth: true }).then((response) => response.json());
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
    downloadArtifact(taskId, artifact, preferredFilename) {
      return request(`/tasks/${taskId}/download/${artifact}`, void 0, { requireAuth: true }).then(async (response) => ({
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

// ../shared/src/api-contract.ts
var DEFAULT_API_BASE_URL = "https://api.mdtero.com";

// ../shared/src/publisher-capability-matrix.ts
var GROUPS = [
  {
    id: "helper_only",
    label: {
      en: "Helper only",
      zh: "\u53EA\u9700\u672C\u5730 helper"
    },
    description: {
      en: "Install the local helper and parse directly from supported open full-text sources.",
      zh: "\u5B89\u88C5\u672C\u5730 helper \u540E\uFF0C\u76F4\u63A5\u4ECE\u53D7\u652F\u6301\u7684\u5F00\u653E\u5168\u6587\u6765\u6E90\u89E3\u6790\u3002"
    }
  },
  {
    id: "api_key",
    label: {
      en: "Helper + API key",
      zh: "\u9700\u8981 helper \u548C API key"
    },
    description: {
      en: "Install the local helper and add the required publisher key in settings.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\uFF0C\u5E76\u5728\u8BBE\u7F6E\u91CC\u586B\u5199\u6240\u9700\u7684\u51FA\u7248\u793E key\u3002"
    }
  },
  {
    id: "browser_assisted",
    label: {
      en: "Helper + browser extension",
      zh: "\u9700\u8981 helper \u548C\u6D4F\u89C8\u5668\u6269\u5C55"
    },
    description: {
      en: "Keep the article page open locally when Mdtero needs browser-assisted capture.",
      zh: "\u5F53 Mdtero \u9700\u8981\u6D4F\u89C8\u5668\u8F85\u52A9\u6293\u53D6\u65F6\uFF0C\u8BF7\u5728\u672C\u5730\u4FDD\u6301\u6587\u7AE0\u9875\u9762\u6253\u5F00\u3002"
    }
  }
];
function localize(text, language) {
  return text[language];
}
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
    accessVariant: "publisher_tdm",
    presentationGroup: "api_key",
    rightsMode: "licensed",
    acquisitionMode: "official_api",
    requiresHelper: false,
    requiresBrowser: false,
    requiresApiKey: true,
    mayNeedInstitutionAccess: true,
    whatYouNeed: {
      en: "Add your Wiley TDM token. Institutional sign-in or DOI-level entitlement may still be required.",
      zh: "\u586B\u5199 Wiley TDM token\u3002\u67D0\u4E9B DOI \u4ECD\u53EF\u80FD\u8981\u6C42\u673A\u6784\u767B\u5F55\u6216\u76F8\u5E94\u6388\u6743\u3002"
    },
    howMdteroGetsIt: {
      en: "Wiley TDM PDF retrieval first, then local browser or on-device fallback if that route is unavailable.",
      zh: "\u4F18\u5148\u8D70 Wiley TDM PDF \u63A5\u53E3\uFF1B\u5982\u679C\u8BE5\u94FE\u8DEF\u4E0D\u53EF\u7528\uFF0C\u518D\u56DE\u9000\u5230\u672C\u5730\u6D4F\u89C8\u5668\u6216\u8BBE\u5907\u4FA7\u83B7\u53D6\u3002"
    },
    configureTarget: "connector_keys",
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
function localizePublisherCapabilityEntry(entry, language) {
  return {
    id: entry.id,
    label: localize(entry.label, language),
    variantOf: entry.variantOf,
    accessVariant: entry.accessVariant,
    presentationGroup: entry.presentationGroup,
    rightsMode: entry.rightsMode,
    acquisitionMode: entry.acquisitionMode,
    requiresHelper: entry.requiresHelper,
    requiresBrowser: entry.requiresBrowser,
    requiresApiKey: entry.requiresApiKey,
    mayNeedInstitutionAccess: entry.mayNeedInstitutionAccess,
    whatYouNeed: localize(entry.whatYouNeed, language),
    howMdteroGetsIt: localize(entry.howMdteroGetsIt, language),
    configureTarget: entry.configureTarget,
    status: entry.status,
    fallbacks: [...entry.fallbacks],
    validationRef: entry.validationRef,
    links: entry.links.map((item) => ({
      href: item.href,
      label: localize(item.label, language)
    }))
  };
}
function getPublisherCapabilityGroups(language) {
  return GROUPS.map((group) => ({
    id: group.id,
    label: localize(group.label, language),
    description: localize(group.description, language),
    entries: PUBLISHER_CAPABILITY_MATRIX.filter((entry) => entry.presentationGroup === group.id).map(
      (entry) => localizePublisherCapabilityEntry(entry, language)
    )
  })).filter((group) => group.entries.length > 0);
}

// ../shared/src/shadow-status.ts
var CONNECTOR_LABELS = {
  springer_subscription_connector: {
    en: "Springer subscription",
    zh: "Springer \u8BA2\u9605\u94FE\u8DEF"
  },
  wiley_tdm: {
    en: "Wiley TDM",
    zh: "Wiley TDM"
  },
  taylor_francis_tdm: {
    en: "Taylor & Francis TDM",
    zh: "Taylor & Francis TDM"
  },
  springer_openaccess_api: {
    en: "Springer OA",
    zh: "Springer OA"
  },
  elsevier_article_retrieval_api: {
    en: "Elsevier API",
    zh: "Elsevier API"
  }
};
function connectorLabel(connector, language) {
  return CONNECTOR_LABELS[connector]?.[language] ?? connector;
}
function summarizeParserV2ShadowDiagnostics(diagnostics, language, maxVisible = 2) {
  const enabled = (diagnostics.connectors || []).filter((item) => item.enabled);
  if (enabled.length === 0) {
    return language === "zh" ? "\u5F53\u524D\u8FD8\u6CA1\u6709\u542F\u7528\u4EFB\u4F55\u5B9E\u9A8C connector shadow\u3002" : "No experimental connector shadows are enabled yet.";
  }
  const visible = enabled.slice(0, maxVisible).map((item) => connectorLabel(item.connector, language));
  const remaining = enabled.length - visible.length;
  const visibleText = visible.join(language === "zh" ? "\u3001" : ", ");
  if (language === "zh") {
    return remaining > 0 ? `\u5F53\u524D\u5DF2\u542F\u7528 ${enabled.length} \u6761\u5B9E\u9A8C shadow\uFF1A${visibleText}\uFF0C\u53E6\u6709 ${remaining} \u6761\u3002` : `\u5F53\u524D\u5DF2\u542F\u7528 ${enabled.length} \u6761\u5B9E\u9A8C shadow\uFF1A${visibleText}\u3002`;
  }
  return remaining > 0 ? `${enabled.length} experimental shadows enabled: ${visibleText}, plus ${remaining} more.` : `${enabled.length} experimental shadows enabled: ${visibleText}.`;
}

// src/lib/storage.ts
var SETTINGS_KEY = "mdtero_settings";
function resolveUiLanguage(preferred, browserLanguage) {
  if (preferred === "en" || preferred === "zh") {
    return preferred;
  }
  return browserLanguage?.toLowerCase().startsWith("zh") ? "zh" : "en";
}
function mergeSettings(current, next) {
  return {
    ...current,
    ...next
  };
}
async function readSettings() {
  const stored = await chrome.storage.local.get(SETTINGS_KEY);
  const current = stored[SETTINGS_KEY] ?? { apiBaseUrl: DEFAULT_API_BASE_URL };
  return {
    apiBaseUrl: current.apiBaseUrl ?? DEFAULT_API_BASE_URL,
    token: current.token,
    email: current.email,
    elsevierApiKey: current.elsevierApiKey,
    wileyTdmToken: current.wileyTdmToken,
    springerOpenAccessApiKey: current.springerOpenAccessApiKey,
    uiLanguage: resolveUiLanguage(current.uiLanguage, globalThis.navigator?.language)
  };
}
async function writeSettings(next) {
  await chrome.storage.local.set({ [SETTINGS_KEY]: next });
}

// src/lib/publisher-capability-view.ts
var STATUS_LABELS = {
  stable: { en: "Stable", zh: "\u7A33\u5B9A" },
  demo: { en: "Demo", zh: "\u6F14\u793A" },
  experimental: { en: "Experimental", zh: "\u5B9E\u9A8C" }
};
var FALLBACK_LABELS = {
  pdf: { en: "PDF", zh: "PDF" },
  browser_page_capture: { en: "Browser page capture", zh: "\u6D4F\u89C8\u5668\u9875\u9762\u6293\u53D6" },
  no_fallback_yet: { en: "No fallback yet", zh: "\u6682\u672A\u63D0\u4F9B\u515C\u5E95" }
};
var READINESS_LABELS = {
  ready: { en: "Ready now", zh: "\u73B0\u5728\u53EF\u7528" },
  needs_helper: { en: "Install helper", zh: "\u9700\u8981\u5B89\u88C5 helper" },
  needs_api_key: { en: "Add API key", zh: "\u9700\u8981\u586B\u5199 API key" },
  browser_required: { en: "Open in browser when needed", zh: "\u9700\u8981\u65F6\u5728\u6D4F\u89C8\u5668\u4E2D\u6253\u5F00" },
  institution_access: { en: "Institution sign-in may be required", zh: "\u53EF\u80FD\u9700\u8981\u673A\u6784\u767B\u5F55" }
};
function formatCapabilityStatusLabel(status, language) {
  return STATUS_LABELS[status][language];
}
function formatCapabilityFallbacks(fallbacks, language) {
  return fallbacks.map((item) => FALLBACK_LABELS[item][language]).join(" \u2192 ");
}
function hasRequiredApiKey(entry, context) {
  if (!entry.requiresApiKey) {
    return true;
  }
  if (entry.id === "elsevier") {
    return context.hasElsevierApiKey;
  }
  if (entry.id === "wiley") {
    return context.hasWileyTdmToken;
  }
  if (entry.id === "springer_oa") {
    return context.hasSpringerOpenAccessApiKey;
  }
  return false;
}
function resolveCapabilityReadiness(entry, context) {
  if (context.helperState !== "connected" && context.helperState !== "busy") {
    return "needs_helper";
  }
  if (!hasRequiredApiKey(entry, context)) {
    return "needs_api_key";
  }
  if (entry.requiresBrowser) {
    return "browser_required";
  }
  if (entry.mayNeedInstitutionAccess) {
    return "institution_access";
  }
  return "ready";
}
function describeCapabilityReadiness(readiness, language) {
  return READINESS_LABELS[readiness][language];
}

// src/options/index.ts
var COPY = {
  en: {
    title: "Mdtero Account",
    subtitle: "Sign in faster, check balance and quota, and tune publisher API, TDM, and on-device fallback preferences.",
    supportSummary: "Keep licensed retrieval on your own machine and see which publisher APIs, TDM routes, and local fallbacks are ready with your current setup.",
    browserAssistedNote: "When a source cannot use a direct publisher API or TDM route, Mdtero can still fall back to local browser capture or on-device cffi/curl retrieval where that route is supported.",
    connectorKeysTitle: "Connector keys",
    connectorKeysNote: "Only fill the keys you actually need. Everything stays on your own machine.",
    capabilityNeed: "What you need",
    capabilityRoute: "How Mdtero gets it",
    capabilityFallback: "Fallback",
    permissionsTitle: "Why Mdtero asks for these permissions",
    permissionsTabs: "`tabs` lets the extension reuse or open supported paper pages for local capture.",
    permissionsDownloads: "`downloads` saves Markdown files, translations, fallback ZIPs, and source files back to your own machine.",
    permissionsNative: "`nativeMessaging` connects the extension to your local Mdtero runtime so supported routes can fall back to on-device acquisition when direct publisher APIs or TDM routes are unavailable.",
    permissionsHosts: "Publisher host permissions stay limited to supported scholarly sites and the Mdtero / publisher APIs already used by the product.",
    helperReady: "Local runtime ready for on-device fallback and browser capture when needed.",
    helperBusy: "Local runtime is connected and currently handling an on-device acquisition task.",
    helperUnavailable: "Local runtime not detected yet. Install or restart mdtero to enable on-device fallback routes.",
    helperDisconnected: "Local runtime disconnected. Restart mdtero or reload the extension to reconnect.",
    helperUnknown: "Local runtime status unknown.",
    shadowSignedOut: "Sign in to view experimental connector shadow status.",
    shadowUnavailable: "Experimental connector shadow status unavailable.",
    notSignedIn: "Not signed in.",
    usagePending: "Balance and quota appear after sign-in.",
    signedIn: (email) => `Signed in as ${email}`,
    usageSummary: (wallet, parse, translation) => `Balance ${wallet} \xB7 Parse ${parse} \xB7 Translation ${translation}`,
    email: "Email",
    password: "Password",
    passwordMode: "Password",
    codeMode: "Email Code",
    signIn: "Sign In",
    useEmailCode: "Use Email Code",
    sendCode: "Send Code",
    verifyLogin: "Verify Login",
    code: "Verification Code",
    uiLanguage: "Interface language",
    advanced: "Advanced",
    elsevierApiKey: "Elsevier API Key",
    wileyTdmToken: "Wiley TDM Token",
    springerOpenAccessApiKey: "Springer OA API Key",
    apiUrl: "API URL",
    save: "Save",
    sent: (email) => `Verification code sent to ${email}.`,
    passwordLoginFailed: "Password login failed.",
    historyTitle: "Document History",
    historyNote: "Downloads from your history are always free.",
    historyEmpty: "No parsing or translation history found yet.",
    historyError: "Failed to load history: ",
    downloadFailed: "Download failed:",
    historyRefresh: "Refresh",
    historyRefreshing: "Refreshing..."
  },
  zh: {
    title: "Mdtero \u8D26\u6237",
    subtitle: "\u767B\u5F55\u540E\u67E5\u770B\u4F59\u989D\u3001\u989D\u5EA6\uFF0C\u5E76\u914D\u7F6E publisher API\u3001TDM \u4E0E\u8BBE\u5907\u4FA7\u56DE\u9000\u504F\u597D\u3002",
    supportSummary: "\u628A\u53D7\u9650\u5168\u6587\u83B7\u53D6\u7559\u5728\u4F60\u81EA\u5DF1\u7684\u8BBE\u5907\u4E0A\uFF0C\u5E76\u67E5\u770B\u5F53\u524D\u8FD9\u5957 publisher API\u3001TDM \u4E0E\u672C\u5730\u515C\u5E95\u5DF2\u7ECF\u9002\u5408\u54EA\u4E9B\u6765\u6E90\u3002",
    browserAssistedNote: "\u5F53\u67D0\u4E2A\u6765\u6E90\u4E0D\u80FD\u76F4\u63A5\u8D70 publisher API \u6216 TDM \u65F6\uFF0CMdtero \u4ECD\u53EF\u5728\u652F\u6301\u7684\u94FE\u8DEF\u4E0A\u56DE\u9000\u5230\u672C\u5730\u6D4F\u89C8\u5668\u6293\u53D6\u6216\u8BBE\u5907\u4FA7 cffi/curl \u83B7\u53D6\u3002",
    connectorKeysTitle: "Connector keys",
    connectorKeysNote: "\u53EA\u586B\u5199\u4F60\u5B9E\u9645\u9700\u8981\u7684 key\uFF1B\u8FD9\u4E9B\u4FE1\u606F\u90FD\u4FDD\u7559\u5728\u4F60\u81EA\u5DF1\u7684\u673A\u5668\u4E0A\u3002",
    capabilityNeed: "\u4F60\u9700\u8981\u51C6\u5907\u4EC0\u4E48",
    capabilityRoute: "Mdtero \u600E\u4E48\u83B7\u53D6",
    capabilityFallback: "\u515C\u5E95\u65B9\u5F0F",
    permissionsTitle: "\u4E3A\u4EC0\u4E48 Mdtero \u9700\u8981\u8FD9\u4E9B\u6743\u9650",
    permissionsTabs: "`tabs` \u7528\u6765\u590D\u7528\u6216\u6253\u5F00\u53D7\u652F\u6301\u7684\u8BBA\u6587\u9875\u9762\uFF0C\u4EE5\u4FBF\u5728\u672C\u673A\u5B8C\u6210\u6293\u53D6\u3002",
    permissionsDownloads: "`downloads` \u7528\u6765\u628A Markdown\u3001\u8BD1\u6587\u3001\u515C\u5E95\u538B\u7F29\u5305\u548C\u6E90\u6587\u4EF6\u4FDD\u5B58\u56DE\u4F60\u7684\u7535\u8111\u3002",
    permissionsNative: "`nativeMessaging` \u7528\u6765\u628A\u6269\u5C55\u8FDE\u63A5\u5230\u4F60\u672C\u5730\u7684 Mdtero \u8FD0\u884C\u65F6\uFF0C\u5728\u76F4\u8FDE publisher API \u6216 TDM \u4E0D\u53EF\u7528\u65F6\u56DE\u9000\u5230\u8BBE\u5907\u4FA7\u83B7\u53D6\u94FE\u8DEF\u3002",
    permissionsHosts: "\u7AD9\u70B9\u6743\u9650\u53EA\u8986\u76D6\u5DF2\u652F\u6301\u7684\u5B66\u672F\u7AD9\u70B9\uFF0C\u4EE5\u53CA\u4EA7\u54C1\u5DF2\u7ECF\u4F7F\u7528\u7684 Mdtero / \u51FA\u7248\u5546 API\u3002",
    helperReady: "\u672C\u5730\u8FD0\u884C\u65F6\u5DF2\u5C31\u7EEA\uFF0C\u53EF\u5728\u9700\u8981\u65F6\u5904\u7406\u8BBE\u5907\u4FA7\u56DE\u9000\u4E0E\u6D4F\u89C8\u5668\u6293\u53D6\u3002",
    helperBusy: "\u672C\u5730\u8FD0\u884C\u65F6\u5DF2\u8FDE\u63A5\uFF0C\u6B63\u5728\u5904\u7406\u8BBE\u5907\u4FA7\u83B7\u53D6\u4EFB\u52A1\u3002",
    helperUnavailable: "\u6682\u672A\u68C0\u6D4B\u5230\u672C\u5730\u8FD0\u884C\u65F6\u3002\u8BF7\u5B89\u88C5\u6216\u91CD\u542F mdtero \u4EE5\u542F\u7528\u8BBE\u5907\u4FA7\u56DE\u9000\u94FE\u8DEF\u3002",
    helperDisconnected: "\u672C\u5730\u8FD0\u884C\u65F6\u5DF2\u65AD\u5F00\u3002\u8BF7\u91CD\u542F mdtero \u6216\u91CD\u8F7D\u6269\u5C55\u540E\u518D\u8BD5\u3002",
    helperUnknown: "\u672C\u5730\u8FD0\u884C\u65F6\u72B6\u6001\u672A\u77E5\u3002",
    shadowSignedOut: "\u767B\u5F55\u540E\u53EF\u67E5\u770B\u5B9E\u9A8C connector shadow \u72B6\u6001\u3002",
    shadowUnavailable: "\u6682\u65F6\u65E0\u6CD5\u83B7\u53D6\u5B9E\u9A8C connector shadow \u72B6\u6001\u3002",
    notSignedIn: "\u5C1A\u672A\u767B\u5F55\u3002",
    usagePending: "\u767B\u5F55\u540E\u53EF\u67E5\u770B\u4F59\u989D\u4E0E\u989D\u5EA6\u3002",
    signedIn: (email) => `\u5DF2\u767B\u5F55\uFF1A${email}`,
    usageSummary: (wallet, parse, translation) => `\u4F59\u989D ${wallet} \xB7 \u89E3\u6790 ${parse} \xB7 \u7FFB\u8BD1 ${translation}`,
    email: "\u90AE\u7BB1",
    password: "\u5BC6\u7801",
    passwordMode: "\u5BC6\u7801\u767B\u5F55",
    codeMode: "\u90AE\u7BB1\u9A8C\u8BC1\u7801",
    signIn: "\u767B\u5F55",
    useEmailCode: "\u6539\u7528\u9A8C\u8BC1\u7801",
    sendCode: "\u53D1\u9001\u9A8C\u8BC1\u7801",
    verifyLogin: "\u9A8C\u8BC1\u767B\u5F55",
    code: "\u9A8C\u8BC1\u7801",
    uiLanguage: "\u754C\u9762\u8BED\u8A00",
    advanced: "\u9AD8\u7EA7\u8BBE\u7F6E",
    elsevierApiKey: "Elsevier API Key",
    wileyTdmToken: "Wiley TDM Token",
    springerOpenAccessApiKey: "Springer OA API Key",
    apiUrl: "API \u5730\u5740",
    save: "\u4FDD\u5B58",
    sent: (email) => `\u9A8C\u8BC1\u7801\u5DF2\u53D1\u9001\u5230 ${email}\u3002`,
    passwordLoginFailed: "\u5BC6\u7801\u767B\u5F55\u5931\u8D25\u3002",
    historyTitle: "\u5386\u53F2\u6587\u6863",
    historyNote: "\u4ECE\u5386\u53F2\u8BB0\u5F55\u4E0B\u8F7D\u5185\u5BB9\u6C38\u8FDC\u514D\u8D39\uFF0C\u4E0D\u6263\u9664\u989D\u5EA6\u3002",
    historyEmpty: "\u6682\u65E0\u89E3\u6790\u6216\u7FFB\u8BD1\u8BB0\u5F55\u3002",
    historyError: "\u52A0\u8F7D\u5386\u53F2\u6587\u6863\u5931\u8D25\uFF1A",
    downloadFailed: "\u4E0B\u8F7D\u5931\u8D25\uFF1A",
    historyRefresh: "\u5237\u65B0",
    historyRefreshing: "\u5237\u65B0\u4E2D..."
  }
};
var titleEl = document.querySelector("#settings-title");
var subtitleEl = document.querySelector("#settings-subtitle");
var supportSummaryEl = document.querySelector("#support-summary");
var browserAssistedNoteEl = document.querySelector("#browser-assisted-note");
var publisherCapabilityGroupsEl = document.querySelector("#publisher-capability-groups");
var connectorKeysTitleEl = document.querySelector("#connector-keys-title");
var connectorKeysNoteEl = document.querySelector("#connector-keys-note");
var permissionsTitleEl = document.querySelector("#permissions-title");
var permissionsTabsEl = document.querySelector("#permissions-tabs");
var permissionsDownloadsEl = document.querySelector("#permissions-downloads");
var permissionsNativeEl = document.querySelector("#permissions-native");
var permissionsHostsEl = document.querySelector("#permissions-hosts");
var languageToggleEl = document.querySelector("#language-toggle");
var elsevierApiKeyInput = document.querySelector("#elsevier-api-key");
var wileyTdmTokenInput = document.querySelector("#wiley-tdm-token");
var springerOpenAccessApiKeyInput = document.querySelector("#springer-oa-api-key");
var apiBaseUrlInput = document.querySelector("#api-base-url");
var emailInput = document.querySelector("#email-input");
var passwordInput = document.querySelector("#password-input");
var codeInput = document.querySelector("#code-input");
var uiLanguageSelect = document.querySelector("#ui-language");
var accountStatus = document.querySelector("#account-status");
var usageStatus = document.querySelector("#usage-status");
var helperStatus = document.querySelector("#helper-status");
var shadowStatus = document.querySelector("#shadow-status");
var saveButton = document.querySelector("#save-settings");
var sendCodeButton = document.querySelector("#send-code");
var verifyButton = document.querySelector("#verify-code");
var passwordLoginButton = document.querySelector("#password-login");
var passwordUseCodeButton = document.querySelector("#password-use-code");
var authModePasswordButton = document.querySelector("#auth-mode-password");
var authModeCodeButton = document.querySelector("#auth-mode-code");
var emailLabel = document.querySelector("#email-label");
var passwordLabel = document.querySelector("#password-label");
var codeLabel = document.querySelector("#code-label");
var uiLanguageLabel = document.querySelector("#ui-language-label");
var advancedSummary = document.querySelector("#advanced-summary");
var elsevierApiKeyLabel = document.querySelector("#elsevier-api-key-label");
var wileyTdmTokenLabel = document.querySelector("#wiley-tdm-token-label");
var springerOpenAccessApiKeyLabel = document.querySelector("#springer-oa-api-key-label");
var apiBaseUrlLabel = document.querySelector("#api-base-url-label");
var historySection = document.querySelector("#history-section");
var historyList = document.querySelector("#history-list");
var historyTitle = document.querySelector("#history-title");
var historyNote = document.querySelector("#history-note");
var refreshHistoryBtn = document.querySelector("#refresh-history");
var passwordAuthPanel = document.querySelector("#password-auth-panel");
var codeAuthPanel = document.querySelector("#code-auth-panel");
var client = createApiClient(readSettings);
var uiLanguage = "en";
var authMode = "password";
var currentHelperState = "unavailable";
function setLabeledParagraph(paragraph, label, value) {
  paragraph.textContent = "";
  const strong = document.createElement("strong");
  strong.textContent = `${label}:`;
  paragraph.appendChild(strong);
  paragraph.append(" ");
  paragraph.appendChild(document.createTextNode(value));
}
function renderHistoryNotice(message, color) {
  if (!historyList) return;
  historyList.textContent = "";
  const paragraph = document.createElement("p");
  paragraph.className = "meta-label";
  paragraph.textContent = message;
  if (color) {
    paragraph.style.color = color;
  }
  historyList.appendChild(paragraph);
}
function copyFor(language) {
  return COPY[language];
}
function toggleLanguageLabel(language) {
  return language === "en" ? "\u4E2D\u6587" : "EN";
}
function applyAuthMode() {
  const passwordActive = authMode === "password";
  if (passwordAuthPanel) passwordAuthPanel.hidden = !passwordActive;
  if (codeAuthPanel) codeAuthPanel.hidden = passwordActive;
  authModePasswordButton?.classList.toggle("active-chip", passwordActive);
  authModeCodeButton?.classList.toggle("active-chip", !passwordActive);
}
function formatUsageSummary(usage) {
  const wallet = usage.wallet_balance_display?.trim() || (uiLanguage === "zh" ? "\xA50.00" : "$0.00");
  const parse = Number.isFinite(usage.parse_quota_remaining) ? Number(usage.parse_quota_remaining) : 0;
  const translation = Number.isFinite(usage.translation_quota_remaining) ? Number(usage.translation_quota_remaining) : 0;
  return copyFor(uiLanguage).usageSummary(wallet, parse, translation);
}
function renderPublisherCapabilityMatrix() {
  if (!publisherCapabilityGroupsEl) {
    return;
  }
  const copy = copyFor(uiLanguage);
  const groups = getPublisherCapabilityGroups(uiLanguage);
  const settingsSnapshot = {
    helperState: currentHelperState,
    hasElsevierApiKey: Boolean(elsevierApiKeyInput?.value.trim()),
    hasWileyTdmToken: Boolean(wileyTdmTokenInput?.value.trim()),
    hasSpringerOpenAccessApiKey: Boolean(springerOpenAccessApiKeyInput?.value.trim())
  };
  publisherCapabilityGroupsEl.innerHTML = "";
  for (const group of groups) {
    const section = document.createElement("section");
    section.className = "capability-group-card";
    const head = document.createElement("div");
    head.className = "capability-group-head";
    const title = document.createElement("h3");
    title.className = "capability-group-title";
    title.textContent = group.label;
    const description = document.createElement("p");
    description.className = "meta-label";
    description.textContent = group.description;
    head.appendChild(title);
    head.appendChild(description);
    section.appendChild(head);
    const list = document.createElement("div");
    list.className = "capability-entry-list";
    for (const entry of group.entries) {
      const readiness = resolveCapabilityReadiness(entry, settingsSnapshot);
      const card = document.createElement("article");
      card.className = "capability-entry-card";
      const row = document.createElement("div");
      row.className = "capability-entry-top";
      const label = document.createElement("h4");
      label.className = "capability-entry-title";
      label.textContent = entry.label;
      const badges = document.createElement("div");
      badges.className = "capability-badges";
      const statusBadge = document.createElement("span");
      statusBadge.className = `capability-badge capability-badge-${entry.status}`;
      statusBadge.textContent = formatCapabilityStatusLabel(entry.status, uiLanguage);
      const readinessBadge = document.createElement("span");
      readinessBadge.className = `capability-badge capability-badge-${readiness}`;
      readinessBadge.textContent = describeCapabilityReadiness(readiness, uiLanguage);
      badges.appendChild(statusBadge);
      badges.appendChild(readinessBadge);
      row.appendChild(label);
      row.appendChild(badges);
      card.appendChild(row);
      const need = document.createElement("p");
      need.className = "capability-copy";
      setLabeledParagraph(need, copy.capabilityNeed, entry.whatYouNeed);
      card.appendChild(need);
      const route = document.createElement("p");
      route.className = "capability-copy";
      setLabeledParagraph(route, copy.capabilityRoute, entry.howMdteroGetsIt);
      card.appendChild(route);
      const fallback = document.createElement("p");
      fallback.className = "capability-copy capability-copy-muted";
      setLabeledParagraph(
        fallback,
        copy.capabilityFallback,
        formatCapabilityFallbacks(entry.fallbacks, uiLanguage)
      );
      card.appendChild(fallback);
      if (entry.links.length > 0) {
        const links = document.createElement("div");
        links.className = "capability-links";
        for (const item of entry.links) {
          const anchor = document.createElement("a");
          anchor.href = item.href;
          anchor.target = "_blank";
          anchor.rel = "noopener noreferrer";
          anchor.className = "guide-doc-link capability-link";
          anchor.textContent = item.label;
          links.appendChild(anchor);
        }
        card.appendChild(links);
      }
      list.appendChild(card);
    }
    section.appendChild(list);
    publisherCapabilityGroupsEl.appendChild(section);
  }
}
function applyLanguage() {
  const copy = copyFor(uiLanguage);
  document.documentElement.lang = uiLanguage === "zh" ? "zh-CN" : "en";
  if (titleEl) titleEl.textContent = copy.title;
  if (subtitleEl) subtitleEl.textContent = copy.subtitle;
  if (supportSummaryEl) supportSummaryEl.textContent = copy.supportSummary;
  if (browserAssistedNoteEl) browserAssistedNoteEl.textContent = copy.browserAssistedNote;
  if (connectorKeysTitleEl) connectorKeysTitleEl.textContent = copy.connectorKeysTitle;
  if (connectorKeysNoteEl) connectorKeysNoteEl.textContent = copy.connectorKeysNote;
  if (permissionsTitleEl) permissionsTitleEl.textContent = copy.permissionsTitle;
  if (permissionsTabsEl) permissionsTabsEl.textContent = copy.permissionsTabs;
  if (permissionsDownloadsEl) permissionsDownloadsEl.textContent = copy.permissionsDownloads;
  if (permissionsNativeEl) permissionsNativeEl.textContent = copy.permissionsNative;
  if (permissionsHostsEl) permissionsHostsEl.textContent = copy.permissionsHosts;
  if (languageToggleEl) languageToggleEl.textContent = toggleLanguageLabel(uiLanguage);
  if (emailLabel) emailLabel.textContent = copy.email;
  if (passwordLabel) passwordLabel.textContent = copy.password;
  if (authModePasswordButton) authModePasswordButton.textContent = copy.passwordMode;
  if (authModeCodeButton) authModeCodeButton.textContent = copy.codeMode;
  if (passwordLoginButton) passwordLoginButton.textContent = copy.signIn;
  if (passwordUseCodeButton) passwordUseCodeButton.textContent = copy.useEmailCode;
  if (sendCodeButton) sendCodeButton.textContent = copy.sendCode;
  if (verifyButton) verifyButton.textContent = copy.verifyLogin;
  if (codeLabel) codeLabel.textContent = copy.code;
  if (uiLanguageLabel) uiLanguageLabel.textContent = copy.uiLanguage;
  if (advancedSummary) advancedSummary.textContent = copy.advanced;
  if (elsevierApiKeyLabel) elsevierApiKeyLabel.textContent = copy.elsevierApiKey;
  if (wileyTdmTokenLabel) wileyTdmTokenLabel.textContent = copy.wileyTdmToken;
  if (springerOpenAccessApiKeyLabel) springerOpenAccessApiKeyLabel.textContent = copy.springerOpenAccessApiKey;
  if (apiBaseUrlLabel) apiBaseUrlLabel.textContent = copy.apiUrl;
  if (saveButton) saveButton.textContent = copy.save;
  if (historyTitle) historyTitle.textContent = copy.historyTitle || "Document History";
  if (historyNote) historyNote.textContent = copy.historyNote || "Downloads from your history are always free.";
  if (refreshHistoryBtn) refreshHistoryBtn.textContent = copy.historyRefresh || "Refresh";
  applyAuthMode();
  renderPublisherCapabilityMatrix();
}
async function refreshBridgeStatus() {
  if (!helperStatus) {
    return;
  }
  const copy = copyFor(uiLanguage);
  try {
    const response = await chrome.runtime.sendMessage({
      type: "mdtero.bridge.status"
    });
    const state = response?.result?.state;
    const runnerState = response?.result?.runnerState;
    if (state === "connected" && runnerState === "busy") {
      currentHelperState = "busy";
      helperStatus.textContent = copy.helperBusy;
      renderPublisherCapabilityMatrix();
      return;
    }
    if (state === "connected") {
      currentHelperState = "connected";
      helperStatus.textContent = copy.helperReady;
      renderPublisherCapabilityMatrix();
      return;
    }
    if (state === "disconnected") {
      currentHelperState = "disconnected";
      helperStatus.textContent = copy.helperDisconnected;
      renderPublisherCapabilityMatrix();
      return;
    }
    currentHelperState = "unavailable";
    helperStatus.textContent = copy.helperUnavailable;
  } catch {
    currentHelperState = "unavailable";
    helperStatus.textContent = copy.helperUnavailable;
  }
  renderPublisherCapabilityMatrix();
}
async function refreshShadowDiagnostics() {
  if (!shadowStatus) {
    return;
  }
  const settings = await readSettings();
  if (!settings.token) {
    shadowStatus.textContent = copyFor(uiLanguage).shadowSignedOut;
    return;
  }
  try {
    const diagnostics = await client.getParserV2ShadowDiagnostics();
    shadowStatus.textContent = summarizeParserV2ShadowDiagnostics(diagnostics, uiLanguage);
  } catch {
    shadowStatus.textContent = copyFor(uiLanguage).shadowUnavailable;
  }
}
async function refreshHistory() {
  if (!historyList) return;
  const copy = copyFor(uiLanguage);
  try {
    const { items } = await client.getMyTasks();
    if (items.length === 0) {
      renderHistoryNotice(copy.historyEmpty || "No history found.");
      return;
    }
    historyList.textContent = "";
    for (const task of items) {
      const row = document.createElement("div");
      row.className = "history-item";
      const header = document.createElement("div");
      header.className = "history-item-header";
      const inputDiv = document.createElement("div");
      inputDiv.className = "history-item-input";
      const rawTask = task;
      const inputVal = rawTask.paper_input || "Unknown Input";
      inputDiv.textContent = inputVal.length > 50 ? inputVal.substring(0, 50) + "..." : inputVal;
      const statusBadge = document.createElement("span");
      statusBadge.className = "history-status-badge";
      statusBadge.textContent = task.status;
      if (task.status === "succeeded") {
        statusBadge.classList.add("history-status-badge-succeeded");
      } else if (task.status === "failed") {
        statusBadge.classList.add("history-status-badge-failed");
      }
      header.appendChild(inputDiv);
      header.appendChild(statusBadge);
      row.appendChild(header);
      if (task.status === "succeeded" && task.result?.artifacts) {
        const artifactsRow = document.createElement("div");
        artifactsRow.className = "history-actions";
        for (const [key, desc] of Object.entries(task.result.artifacts)) {
          const dlBtn = document.createElement("button");
          dlBtn.className = "ghost-chip history-download-button";
          dlBtn.textContent = `${copyFor(uiLanguage).historyRefresh === "\u5237\u65B0" ? "\u4E0B\u8F7D" : "Download"} ${key.replace("paper_", "").toUpperCase()}`;
          dlBtn.addEventListener("click", async () => {
            try {
              dlBtn.textContent = uiLanguage === "zh" ? "\u4E0B\u8F7D\u4E2D..." : "Downloading...";
              const result = await client.downloadArtifact(task.task_id, key, desc.filename);
              triggerBlobDownload(result.blob, result.filename);
              dlBtn.textContent = `${copyFor(uiLanguage).historyRefresh === "\u5237\u65B0" ? "\u4E0B\u8F7D" : "Download"} ${key.replace("paper_", "").toUpperCase()}`;
            } catch (err) {
              renderHistoryNotice(`${copyFor(uiLanguage).downloadFailed} ${err.message}`, "#b91c1c");
              dlBtn.textContent = `${copyFor(uiLanguage).historyRefresh === "\u5237\u65B0" ? "\u4E0B\u8F7D" : "Download"} ${key.replace("paper_", "").toUpperCase()}`;
            }
          });
          artifactsRow.appendChild(dlBtn);
        }
        row.appendChild(artifactsRow);
      }
      const dateStr = rawTask.created_at ? new Date(rawTask.created_at).toLocaleString() : "";
      if (dateStr) {
        const timeDiv = document.createElement("div");
        timeDiv.className = "history-item-time";
        timeDiv.textContent = dateStr;
        row.appendChild(timeDiv);
      }
      historyList.appendChild(row);
    }
  } catch (error) {
    const errorPrefix = copy.historyError || "Failed to load history: ";
    renderHistoryNotice(`${errorPrefix}${error.message}`, "#f44336");
  }
}
async function refreshView() {
  const settings = await readSettings();
  uiLanguage = resolveUiLanguage(settings.uiLanguage, globalThis.navigator?.language);
  applyLanguage();
  await refreshBridgeStatus();
  await refreshShadowDiagnostics();
  if (elsevierApiKeyInput) elsevierApiKeyInput.value = settings.elsevierApiKey ?? "";
  if (wileyTdmTokenInput) wileyTdmTokenInput.value = settings.wileyTdmToken ?? "";
  if (springerOpenAccessApiKeyInput) springerOpenAccessApiKeyInput.value = settings.springerOpenAccessApiKey ?? "";
  if (apiBaseUrlInput) apiBaseUrlInput.value = settings.apiBaseUrl;
  if (emailInput) emailInput.value = settings.email ?? "";
  if (uiLanguageSelect) uiLanguageSelect.value = uiLanguage;
  renderPublisherCapabilityMatrix();
  if (accountStatus) {
    accountStatus.textContent = settings.email ? copyFor(uiLanguage).signedIn(settings.email) : copyFor(uiLanguage).notSignedIn;
  }
  if (!settings.token) {
    if (usageStatus) {
      usageStatus.textContent = copyFor(uiLanguage).usagePending;
    }
    if (historySection) {
      historySection.hidden = true;
      historySection.style.display = "none";
    }
    return;
  }
  if (historySection) {
    historySection.hidden = false;
    historySection.style.display = "block";
  }
  try {
    const usage = await client.getUsage();
    if (usageStatus) {
      usageStatus.textContent = formatUsageSummary(usage);
    }
  } catch (error) {
    if (usageStatus) {
      usageStatus.textContent = error.message;
    }
  }
  await refreshHistory();
}
if (refreshHistoryBtn) {
  refreshHistoryBtn.addEventListener("click", () => {
    refreshHistoryBtn.textContent = copyFor(uiLanguage).historyRefreshing || "...";
    refreshHistory().then(() => {
      refreshHistoryBtn.textContent = copyFor(uiLanguage).historyRefresh || "Refresh";
    });
  });
}
saveButton?.addEventListener("click", async () => {
  const current = await readSettings();
  await writeSettings(
    mergeSettings(current, {
      elsevierApiKey: elsevierApiKeyInput?.value.trim() || void 0,
      wileyTdmToken: wileyTdmTokenInput?.value.trim() || void 0,
      springerOpenAccessApiKey: springerOpenAccessApiKeyInput?.value.trim() || void 0,
      apiBaseUrl: apiBaseUrlInput?.value.trim() || current.apiBaseUrl,
      uiLanguage: resolveUiLanguage(uiLanguageSelect?.value, globalThis.navigator?.language)
    })
  );
  await refreshView();
});
sendCodeButton?.addEventListener("click", async () => {
  const email = emailInput?.value.trim();
  if (!email || !accountStatus) {
    return;
  }
  try {
    await client.startEmailAuth({ email });
    accountStatus.textContent = copyFor(uiLanguage).sent(email);
  } catch (error) {
    accountStatus.textContent = error.message;
  }
});
passwordLoginButton?.addEventListener("click", async () => {
  const email = emailInput?.value.trim();
  const password = passwordInput?.value ?? "";
  if (!email || !password || !accountStatus) {
    return;
  }
  try {
    const result = await client.loginWithPassword({ email, password });
    const current = await readSettings();
    await writeSettings(
      mergeSettings(current, {
        email,
        token: result.token
      })
    );
    await refreshView();
  } catch (error) {
    accountStatus.textContent = error.message || copyFor(uiLanguage).passwordLoginFailed;
  }
});
verifyButton?.addEventListener("click", async () => {
  const email = emailInput?.value.trim();
  const code = codeInput?.value.trim();
  if (!email || !code || !accountStatus) {
    return;
  }
  try {
    const result = await client.verifyEmailAuth({ email, code });
    const current = await readSettings();
    await writeSettings(
      mergeSettings(current, {
        email,
        token: result.token
      })
    );
    await refreshView();
  } catch (error) {
    accountStatus.textContent = error.message;
  }
});
authModePasswordButton?.addEventListener("click", () => {
  authMode = "password";
  applyAuthMode();
});
authModeCodeButton?.addEventListener("click", () => {
  authMode = "code";
  applyAuthMode();
});
passwordUseCodeButton?.addEventListener("click", () => {
  authMode = "code";
  applyAuthMode();
});
uiLanguageSelect?.addEventListener("change", async () => {
  uiLanguage = resolveUiLanguage(uiLanguageSelect.value, globalThis.navigator?.language);
  const current = await readSettings();
  await writeSettings(
    mergeSettings(current, {
      uiLanguage
    })
  );
  await refreshView();
});
languageToggleEl?.addEventListener("click", async () => {
  uiLanguage = uiLanguage === "en" ? "zh" : "en";
  const current = await readSettings();
  await writeSettings(
    mergeSettings(current, {
      uiLanguage
    })
  );
  await refreshView();
});
void refreshView();
//# sourceMappingURL=options.js.map
