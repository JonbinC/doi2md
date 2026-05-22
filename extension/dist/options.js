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
      const body = buildHelperFirstParseBody({
        fileField: "fulltext_file",
        file: payload.fulltextFile,
        filename: payload.filename ?? "paper.fulltext",
        sourceDoi: payload.sourceDoi,
        sourceInput: payload.sourceInput
      });
      const normalizedBody = new FormData();
      const upload = body.get("fulltext_file");
      if (upload instanceof Blob) {
        normalizedBody.set("paper_file", upload, payload.filename ?? "paper.fulltext");
      }
      const sourceDoi = body.get("source_doi");
      const sourceInput = body.get("source_input");
      if (typeof sourceDoi === "string") normalizedBody.set("source_doi", sourceDoi);
      if (typeof sourceInput === "string") normalizedBody.set("source_input", sourceInput);
      return requestWithFallback("/api/v1/tasks/upload", "/tasks/parse-upload-v2", {
        method: "POST",
        body: normalizedBody
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
      return request("/tasks/parse-helper-bundle-v2", {
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

// src/lib/auth-bridge.ts
var MDTERO_ACCOUNT_URL = "https://mdtero.com/account";

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

// src/options/index.ts
var COPY = {
  en: {
    title: "Mdtero Account",
    subtitle: "Use the website account for sign-in, check balance and quota, and tune publisher API, TDM, and on-device fallback preferences.",
    connectorKeysTitle: "Connector keys",
    connectorKeysNote: "Only fill the keys you actually need. Everything stays on your own machine.",
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
    notSignedIn: "Not signed in.",
    usagePending: "Balance and quota appear after sign-in.",
    signedIn: (email) => `Signed in as ${email}`,
    usageSummary: (wallet, parse, translation) => `Balance ${wallet} \xB7 Parse ${parse} \xB7 Translation ${translation}`,
    openAccount: "Open Mdtero Account",
    websiteAuthTitle: "Website sign-in",
    websiteAuthNote: "The extension uses Mdtero Account for sign-in. Open the website, complete login there, and the trusted auth bridge will hand the token back to this extension.",
    uiLanguage: "Interface language",
    advanced: "Advanced",
    elsevierApiKey: "Elsevier API Key",
    wileyTdmToken: "Wiley TDM Token",
    springerOpenAccessApiKey: "Springer OA API Key",
    apiUrl: "API URL",
    save: "Save",
    historyTitle: "Account history",
    historyNote: "Downloads from your history are always free.",
    historyEmpty: "No parsing or translation history found yet.",
    historyError: "Failed to load history: ",
    downloadFailed: "Download failed:",
    historyRefresh: "Refresh",
    historyRefreshing: "Refreshing..."
  },
  zh: {
    title: "Mdtero \u8D26\u6237",
    subtitle: "\u4F7F\u7528\u5B98\u7F51\u767B\u5F55\u6388\u6743\u6269\u5C55\uFF0C\u540C\u65F6\u628A\u672C\u5730 publisher \u8BBF\u95EE\u4E0E\u4E0B\u8F7D\u4FDD\u7559\u5728\u8FD9\u53F0\u7535\u8111\u4E0A\u3002",
    connectorKeysTitle: "Connector keys",
    connectorKeysNote: "\u53EA\u586B\u5199\u4F60\u5B9E\u9645\u9700\u8981\u7684 key\uFF1B\u8FD9\u4E9B\u4FE1\u606F\u90FD\u4FDD\u7559\u5728\u4F60\u81EA\u5DF1\u7684\u673A\u5668\u4E0A\u3002",
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
    notSignedIn: "\u5C1A\u672A\u767B\u5F55\u3002\u8BF7\u6253\u5F00 Mdtero Account \u6388\u6743\u6269\u5C55\u3002",
    usagePending: "\u8BF7\u5728 mdtero.com/account \u767B\u5F55\u4EE5\u540C\u6B65\u4F59\u989D\u3001\u989D\u5EA6\u548C\u5386\u53F2\u3002",
    signedIn: (email) => `\u5DF2\u767B\u5F55\uFF1A${email}`,
    usageSummary: (wallet, parse, translation) => `\u4F59\u989D ${wallet} \xB7 \u89E3\u6790 ${parse} \xB7 \u7FFB\u8BD1 ${translation}`,
    openAccount: "\u6253\u5F00 Mdtero Account",
    websiteAuthTitle: "\u5B98\u7F51\u767B\u5F55",
    websiteAuthNote: "\u6269\u5C55\u7EDF\u4E00\u4F7F\u7528 Mdtero Account \u767B\u5F55\u3002\u8BF7\u6253\u5F00\u5B98\u7F51\u5B8C\u6210\u767B\u5F55\uFF0C\u53D7\u4FE1\u4EFB auth bridge \u4F1A\u628A token \u4EA4\u56DE\u6269\u5C55\u3002",
    uiLanguage: "\u754C\u9762\u8BED\u8A00",
    advanced: "\u9AD8\u7EA7\u8BBE\u7F6E",
    elsevierApiKey: "Elsevier API Key",
    wileyTdmToken: "Wiley TDM Token",
    springerOpenAccessApiKey: "Springer OA API Key",
    apiUrl: "API \u5730\u5740",
    save: "\u4FDD\u5B58",
    historyTitle: "\u8D26\u6237\u5386\u53F2",
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
var uiLanguageSelect = document.querySelector("#ui-language");
var accountStatus = document.querySelector("#account-status");
var usageStatus = document.querySelector("#usage-status");
var helperStatus = document.querySelector("#helper-status");
var saveButton = document.querySelector("#save-settings");
var openAccountButton = document.querySelector("#open-account");
var websiteAuthTitleEl = document.querySelector("#website-auth-title");
var websiteAuthNoteEl = document.querySelector("#website-auth-note");
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
var client = createApiClient(readSettings);
var uiLanguage = "en";
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
async function openMdteroAccount() {
  await chrome.tabs.create({ url: MDTERO_ACCOUNT_URL });
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
  if (connectorKeysTitleEl) connectorKeysTitleEl.textContent = copy.connectorKeysTitle;
  if (connectorKeysNoteEl) connectorKeysNoteEl.textContent = copy.connectorKeysNote;
  if (permissionsTitleEl) permissionsTitleEl.textContent = copy.permissionsTitle;
  if (permissionsTabsEl) permissionsTabsEl.textContent = copy.permissionsTabs;
  if (permissionsDownloadsEl) permissionsDownloadsEl.textContent = copy.permissionsDownloads;
  if (permissionsNativeEl) permissionsNativeEl.textContent = copy.permissionsNative;
  if (permissionsHostsEl) permissionsHostsEl.textContent = copy.permissionsHosts;
  if (languageToggleEl) languageToggleEl.textContent = toggleLanguageLabel(uiLanguage);
  if (uiLanguageLabel) uiLanguageLabel.textContent = copy.uiLanguage;
  if (advancedSummary) advancedSummary.textContent = copy.advanced;
  if (elsevierApiKeyLabel) elsevierApiKeyLabel.textContent = copy.elsevierApiKey;
  if (wileyTdmTokenLabel) wileyTdmTokenLabel.textContent = copy.wileyTdmToken;
  if (springerOpenAccessApiKeyLabel) springerOpenAccessApiKeyLabel.textContent = copy.springerOpenAccessApiKey;
  if (apiBaseUrlLabel) apiBaseUrlLabel.textContent = copy.apiUrl;
  if (openAccountButton) openAccountButton.textContent = copy.openAccount;
  if (websiteAuthTitleEl) websiteAuthTitleEl.textContent = copy.websiteAuthTitle;
  if (websiteAuthNoteEl) websiteAuthNoteEl.textContent = copy.websiteAuthNote;
  if (saveButton) saveButton.textContent = copy.save;
  if (historyTitle) historyTitle.textContent = copy.historyTitle;
  if (historyNote) historyNote.textContent = copy.historyNote;
  if (refreshHistoryBtn) refreshHistoryBtn.textContent = copy.historyRefresh;
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
    helperStatus.textContent = copy.helperUnavailable;
  }
}
async function refreshHistory() {
  if (!historyList) return;
  const copy = copyFor(uiLanguage);
  try {
    const { items } = await client.getMyTasks();
    if (items.length === 0) {
      renderHistoryNotice(copy.historyEmpty);
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
      const historyTask = task;
      const inputVal = historyTask.paper_input || "Unknown Input";
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
      const dateStr = historyTask.created_at ? new Date(historyTask.created_at).toLocaleString() : "";
      if (dateStr) {
        const timeDiv = document.createElement("div");
        timeDiv.className = "history-item-time";
        timeDiv.textContent = dateStr;
        row.appendChild(timeDiv);
      }
      historyList.appendChild(row);
    }
  } catch (error) {
    const errorPrefix = copy.historyError;
    renderHistoryNotice(`${errorPrefix}${error.message}`, "#f44336");
  }
}
async function refreshView() {
  const settings = await readSettings();
  uiLanguage = resolveUiLanguage(settings.uiLanguage, globalThis.navigator?.language);
  applyLanguage();
  await refreshBridgeStatus();
  if (elsevierApiKeyInput) elsevierApiKeyInput.value = settings.elsevierApiKey ?? "";
  if (wileyTdmTokenInput) wileyTdmTokenInput.value = settings.wileyTdmToken ?? "";
  if (springerOpenAccessApiKeyInput) springerOpenAccessApiKeyInput.value = settings.springerOpenAccessApiKey ?? "";
  if (apiBaseUrlInput) apiBaseUrlInput.value = settings.apiBaseUrl;
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
    refreshHistoryBtn.textContent = copyFor(uiLanguage).historyRefreshing;
    refreshHistory().then(() => {
      refreshHistoryBtn.textContent = copyFor(uiLanguage).historyRefresh;
    });
  });
}
openAccountButton?.addEventListener("click", () => {
  void openMdteroAccount();
});
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
