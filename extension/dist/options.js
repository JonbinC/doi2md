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

// ../shared/src/api-contract.ts
var DEFAULT_API_BASE_URL = "https://api.mdtero.com";

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
    springerOpenAccessApiKey: current.springerOpenAccessApiKey,
    uiLanguage: resolveUiLanguage(current.uiLanguage, globalThis.navigator?.language)
  };
}
async function writeSettings(next) {
  await chrome.storage.local.set({ [SETTINGS_KEY]: next });
}

// src/options/index.ts
var COPY = {
  en: {
    title: "Mdtero Account",
    subtitle: "Sign in faster, check balance and quota, and tune preferences.",
    supportSummary: "Configure the helper-first browser surface for publisher-page capture, preprints, and account-linked downloads.",
    supportStableTitle: "Stable mainline",
    supportStableItems: "arXiv, PMC / Europe PMC, bioRxiv / medRxiv, PLOS, Springer Open Access, and Elsevier with your own local entitlement.",
    supportShadowTitle: "Bridge-assisted",
    supportShadowItems: "Springer subscription pages already use helper + browser capture when a live HTML page is available.",
    supportExperimentalTitle: "Experimental",
    supportExperimentalItems: "Wiley and Taylor & Francis can run through helper + browser capture, but challenge and login variance is still higher.",
    permissionsTitle: "Why Mdtero asks for these permissions",
    permissionsTabs: "`tabs` lets the extension reuse or open supported paper pages for local capture.",
    permissionsDownloads: "`downloads` saves Markdown bundles, translations, and source files back to your own machine.",
    permissionsNative: "`nativeMessaging` connects the extension to your local Mdtero helper for browser-assisted acquisition.",
    permissionsHosts: "Publisher host permissions stay limited to supported scholarly sites and the Mdtero / publisher APIs already used by the product.",
    helperReady: "Local helper ready for browser-assisted capture.",
    helperBusy: "Local helper is connected and currently handling a browser task.",
    helperUnavailable: "Local helper not detected yet. Install or restart mdtero-local to enable browser-assisted capture.",
    helperDisconnected: "Local helper disconnected. Restart mdtero-local or reload the extension to reconnect.",
    helperUnknown: "Local helper status unknown.",
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
    springerOpenAccessApiKey: "Springer OA API Key",
    apiUrl: "API URL",
    save: "Save",
    sent: (email) => `Verification code sent to ${email}.`,
    passwordLoginFailed: "Password login failed.",
    historyTitle: "Document History",
    historyNote: "Downloads from your history are always free.",
    historyEmpty: "No parsing or translation history found yet.",
    historyError: "Failed to load history: ",
    historyRefresh: "Refresh",
    historyRefreshing: "Refreshing..."
  },
  zh: {
    title: "Mdtero \u8D26\u6237",
    subtitle: "\u4F18\u5148\u7528\u5BC6\u7801\u767B\u5F55\uFF0C\u518D\u67E5\u770B\u4F59\u989D\u3001\u989D\u5EA6\u4E0E\u504F\u597D\u8BBE\u7F6E\u3002",
    supportSummary: "\u5728\u8FD9\u91CC\u914D\u7F6E helper-first \u6D41\u7A0B\u91CC\u7684\u6D4F\u89C8\u5668\u4FA7\u5165\u53E3\uFF0C\u7528\u4E8E\u51FA\u7248\u793E\u9875\u9762\u6293\u53D6\u3001\u9884\u5370\u672C\u548C\u4E0E\u4F60\u8D26\u6237\u5173\u8054\u7684\u4E0B\u8F7D\u5185\u5BB9\u3002",
    supportStableTitle: "\u7A33\u5B9A\u4E3B\u7EBF",
    supportStableItems: "arXiv\u3001PMC / Europe PMC\u3001bioRxiv / medRxiv\u3001PLOS\u3001Springer Open Access\uFF0C\u4EE5\u53CA\u5E26\u6709\u4F60\u672C\u5730\u6743\u9650\u7684 Elsevier\u3002",
    supportShadowTitle: "\u6D4F\u89C8\u5668\u534F\u540C",
    supportShadowItems: "Springer \u8BA2\u9605\u9875\u5DF2\u7ECF\u53EF\u4EE5\u5728\u5B9E\u65F6 HTML \u9875\u9762\u6761\u4EF6\u4E0B\u8D70 helper + \u6D4F\u89C8\u5668\u6293\u53D6\u3002",
    supportExperimentalTitle: "\u5B9E\u9A8C\u652F\u6301",
    supportExperimentalItems: "Wiley \u4E0E Taylor & Francis \u5DF2\u53EF\u901A\u8FC7 helper + \u6D4F\u89C8\u5668\u6293\u53D6\uFF0C\u4F46\u88AB challenge \u6216\u767B\u5F55\u9875\u62E6\u4F4F\u7684\u6CE2\u52A8\u4ECD\u66F4\u9AD8\u3002",
    permissionsTitle: "\u4E3A\u4EC0\u4E48 Mdtero \u9700\u8981\u8FD9\u4E9B\u6743\u9650",
    permissionsTabs: "`tabs` \u7528\u6765\u590D\u7528\u6216\u6253\u5F00\u53D7\u652F\u6301\u7684\u8BBA\u6587\u9875\u9762\uFF0C\u4EE5\u4FBF\u5728\u672C\u673A\u5B8C\u6210\u6293\u53D6\u3002",
    permissionsDownloads: "`downloads` \u7528\u6765\u628A Markdown \u538B\u7F29\u5305\u3001\u8BD1\u6587\u548C\u6E90\u6587\u4EF6\u4FDD\u5B58\u56DE\u4F60\u7684\u7535\u8111\u3002",
    permissionsNative: "`nativeMessaging` \u7528\u6765\u628A\u6269\u5C55\u8FDE\u63A5\u5230\u4F60\u672C\u5730\u7684 Mdtero helper\uFF0C\u5B8C\u6210\u6D4F\u89C8\u5668\u534F\u540C\u6293\u53D6\u3002",
    permissionsHosts: "\u7AD9\u70B9\u6743\u9650\u53EA\u8986\u76D6\u5DF2\u652F\u6301\u7684\u5B66\u672F\u7AD9\u70B9\uFF0C\u4EE5\u53CA\u4EA7\u54C1\u5DF2\u7ECF\u4F7F\u7528\u7684 Mdtero / \u51FA\u7248\u5546 API\u3002",
    helperReady: "\u672C\u5730 helper \u5DF2\u5C31\u7EEA\uFF0C\u53EF\u5904\u7406\u6D4F\u89C8\u5668\u534F\u540C\u6293\u53D6\u3002",
    helperBusy: "\u672C\u5730 helper \u5DF2\u8FDE\u63A5\uFF0C\u6B63\u5728\u5904\u7406\u6D4F\u89C8\u5668\u4EFB\u52A1\u3002",
    helperUnavailable: "\u6682\u672A\u68C0\u6D4B\u5230\u672C\u5730 helper\u3002\u8BF7\u5B89\u88C5\u6216\u91CD\u542F mdtero-local \u4EE5\u542F\u7528\u6D4F\u89C8\u5668\u534F\u540C\u6293\u53D6\u3002",
    helperDisconnected: "\u672C\u5730 helper \u5DF2\u65AD\u5F00\u3002\u8BF7\u91CD\u542F mdtero-local \u6216\u91CD\u8F7D\u6269\u5C55\u540E\u518D\u8BD5\u3002",
    helperUnknown: "\u672C\u5730 helper \u72B6\u6001\u672A\u77E5\u3002",
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
    springerOpenAccessApiKey: "Springer OA API Key",
    apiUrl: "API \u5730\u5740",
    save: "\u4FDD\u5B58",
    sent: (email) => `\u9A8C\u8BC1\u7801\u5DF2\u53D1\u9001\u5230 ${email}\u3002`,
    passwordLoginFailed: "\u5BC6\u7801\u767B\u5F55\u5931\u8D25\u3002",
    historyTitle: "\u5386\u53F2\u6587\u6863",
    historyNote: "\u4ECE\u5386\u53F2\u8BB0\u5F55\u4E0B\u8F7D\u5185\u5BB9\u6C38\u8FDC\u514D\u8D39\uFF0C\u4E0D\u6263\u9664\u989D\u5EA6\u3002",
    historyEmpty: "\u6682\u65E0\u89E3\u6790\u6216\u7FFB\u8BD1\u8BB0\u5F55\u3002",
    historyError: "\u52A0\u8F7D\u5386\u53F2\u6587\u6863\u5931\u8D25\uFF1A",
    historyRefresh: "\u5237\u65B0",
    historyRefreshing: "\u5237\u65B0\u4E2D..."
  }
};
var titleEl = document.querySelector("#settings-title");
var subtitleEl = document.querySelector("#settings-subtitle");
var supportSummaryEl = document.querySelector("#support-summary");
var supportStableTitleEl = document.querySelector("#settings-support-stable-title");
var supportStableItemsEl = document.querySelector("#settings-support-stable-items");
var supportShadowTitleEl = document.querySelector("#settings-support-shadow-title");
var supportShadowItemsEl = document.querySelector("#settings-support-shadow-items");
var supportExperimentalTitleEl = document.querySelector("#settings-support-experimental-title");
var supportExperimentalItemsEl = document.querySelector("#settings-support-experimental-items");
var permissionsTitleEl = document.querySelector("#permissions-title");
var permissionsTabsEl = document.querySelector("#permissions-tabs");
var permissionsDownloadsEl = document.querySelector("#permissions-downloads");
var permissionsNativeEl = document.querySelector("#permissions-native");
var permissionsHostsEl = document.querySelector("#permissions-hosts");
var languageToggleEl = document.querySelector("#language-toggle");
var elsevierApiKeyInput = document.querySelector("#elsevier-api-key");
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
function applyLanguage() {
  const copy = copyFor(uiLanguage);
  document.documentElement.lang = uiLanguage === "zh" ? "zh-CN" : "en";
  if (titleEl) titleEl.textContent = copy.title;
  if (subtitleEl) subtitleEl.textContent = copy.subtitle;
  if (supportSummaryEl) supportSummaryEl.textContent = copy.supportSummary;
  if (supportStableTitleEl) supportStableTitleEl.textContent = copy.supportStableTitle;
  if (supportStableItemsEl) supportStableItemsEl.textContent = copy.supportStableItems;
  if (supportShadowTitleEl) supportShadowTitleEl.textContent = copy.supportShadowTitle;
  if (supportShadowItemsEl) supportShadowItemsEl.textContent = copy.supportShadowItems;
  if (supportExperimentalTitleEl) supportExperimentalTitleEl.textContent = copy.supportExperimentalTitle;
  if (supportExperimentalItemsEl) supportExperimentalItemsEl.textContent = copy.supportExperimentalItems;
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
  if (springerOpenAccessApiKeyLabel) springerOpenAccessApiKeyLabel.textContent = copy.springerOpenAccessApiKey;
  if (apiBaseUrlLabel) apiBaseUrlLabel.textContent = copy.apiUrl;
  if (saveButton) saveButton.textContent = copy.save;
  if (historyTitle) historyTitle.textContent = copy.historyTitle || "Document History";
  if (historyNote) historyNote.textContent = copy.historyNote || "Downloads from your history are always free.";
  if (refreshHistoryBtn) refreshHistoryBtn.textContent = copy.historyRefresh || "Refresh";
  applyAuthMode();
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
      helperStatus.textContent = copy.helperBusy;
      return;
    }
    if (state === "connected") {
      helperStatus.textContent = copy.helperReady;
      return;
    }
    if (state === "disconnected") {
      helperStatus.textContent = copy.helperDisconnected;
      return;
    }
    helperStatus.textContent = copy.helperUnavailable;
  } catch {
    helperStatus.textContent = copy.helperUnknown;
  }
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
      historyList.innerHTML = `<p class="meta-label">${copy.historyEmpty || "No history found."}</p>`;
      return;
    }
    historyList.innerHTML = "";
    for (const task of items) {
      const row = document.createElement("div");
      row.style.cssText = "display: flex; flex-direction: column; gap: 0.5rem; padding: 0.75rem; background: var(--bg-color); border: 1px solid var(--border-color); border-radius: 6px;";
      const header = document.createElement("div");
      header.style.cssText = "display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem;";
      const inputDiv = document.createElement("div");
      inputDiv.style.cssText = "flex: 1; word-break: break-all; font-family: monospace; font-size: 0.8rem;";
      const rawTask = task;
      const inputVal = rawTask.paper_input || "Unknown Input";
      inputDiv.textContent = inputVal.length > 50 ? inputVal.substring(0, 50) + "..." : inputVal;
      const statusBadge = document.createElement("span");
      statusBadge.style.cssText = `font-size: 0.7rem; padding: 0.1rem 0.3rem; border-radius: 4px; border: 1px solid;`;
      statusBadge.textContent = task.status;
      if (task.status === "succeeded") {
        statusBadge.style.borderColor = "#4caf50";
        statusBadge.style.color = "#4caf50";
      } else if (task.status === "failed") {
        statusBadge.style.borderColor = "#f44336";
        statusBadge.style.color = "#f44336";
      } else {
        statusBadge.style.borderColor = "var(--border-color)";
      }
      header.appendChild(inputDiv);
      header.appendChild(statusBadge);
      row.appendChild(header);
      if (task.status === "succeeded" && task.result?.artifacts) {
        const artifactsRow = document.createElement("div");
        artifactsRow.style.cssText = "display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.25rem;";
        for (const [key, desc] of Object.entries(task.result.artifacts)) {
          const dlBtn = document.createElement("button");
          dlBtn.className = "ghost-chip";
          dlBtn.style.cssText = "padding: 0.2rem 0.4rem; font-size: 0.75rem;";
          dlBtn.textContent = `\u2B07 ${key.replace("paper_", "").toUpperCase()}`;
          dlBtn.addEventListener("click", async () => {
            try {
              dlBtn.textContent = "Downloading...";
              const result = await client.downloadArtifact(task.task_id, key);
              triggerBlobDownload(result.blob, result.filename);
              dlBtn.textContent = `\u2B07 ${key.replace("paper_", "").toUpperCase()}`;
            } catch (err) {
              alert("Download failed: " + err.message);
              dlBtn.textContent = `\u2B07 ${key.replace("paper_", "").toUpperCase()}`;
            }
          });
          artifactsRow.appendChild(dlBtn);
        }
        row.appendChild(artifactsRow);
      }
      const dateStr = rawTask.created_at ? new Date(rawTask.created_at).toLocaleString() : "";
      if (dateStr) {
        const timeDiv = document.createElement("div");
        timeDiv.style.cssText = "font-size: 0.7rem; color: var(--text-color); opacity: 0.6; text-align: right;";
        timeDiv.textContent = dateStr;
        row.appendChild(timeDiv);
      }
      historyList.appendChild(row);
    }
  } catch (error) {
    const errorPrefix = copy.historyError || "Failed to load history: ";
    historyList.innerHTML = `<p class="meta-label" style="color: #f44336;">${errorPrefix}${error.message}</p>`;
  }
}
async function refreshView() {
  const settings = await readSettings();
  uiLanguage = resolveUiLanguage(settings.uiLanguage, globalThis.navigator?.language);
  applyLanguage();
  await refreshBridgeStatus();
  await refreshShadowDiagnostics();
  if (elsevierApiKeyInput) elsevierApiKeyInput.value = settings.elsevierApiKey ?? "";
  if (springerOpenAccessApiKeyInput) springerOpenAccessApiKeyInput.value = settings.springerOpenAccessApiKey ?? "";
  if (apiBaseUrlInput) apiBaseUrlInput.value = settings.apiBaseUrl;
  if (emailInput) emailInput.value = settings.email ?? "";
  if (uiLanguageSelect) uiLanguageSelect.value = uiLanguage;
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
