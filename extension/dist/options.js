// src/lib/cli-handoff.ts
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
    return "";
  }
  const detail = payload.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }
  if (!detail || typeof detail !== "object") {
    return "";
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
  return redactSensitiveText(parts.join(" "));
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
    uiLanguage: resolveUiLanguage(current.uiLanguage, globalThis.navigator?.language)
  };
}
async function writeSettings(next) {
  await chrome.storage.local.set({ [SETTINGS_KEY]: next });
}

// src/options/index.ts
var COPY = {
  en: {
    title: "Mdtero Extension",
    subtitle: "Use website OAuth for sign-in, check balance and quota, and manage browser capture, upload, translation, and download settings.",
    permissionsTitle: "Why Mdtero asks for these permissions",
    permissionsTabs: "`tabs` lets the extension read the current paper page and open website OAuth when you sign in.",
    permissionsDownloads: "`downloads` saves Markdown files, translations, ZIP bundles, and uploaded-source results back to your machine.",
    permissionsCapture: "Browser capture reuses the active tab only when you ask Mdtero to parse the current paper page.",
    permissionsHosts: "Host permissions stay limited to Mdtero Auth, supported scholarly pages, and files you choose to upload.",
    notSignedIn: "Not signed in with website OAuth.",
    usagePending: "Balance and quota appear after sign-in.",
    signedIn: (email) => `Signed in as ${email}`,
    usageSummary: (wallet, parse, translation) => `Balance ${wallet} \xB7 Parse ${parse} \xB7 Translation ${translation}`,
    openAccount: "Open website OAuth",
    websiteAuthTitle: "Website sign-in",
    websiteAuthNote: "The extension opens mdtero.com/auth for OAuth sign-in. Complete login on the website, and the trusted auth bridge will hand the token back to this extension.",
    cliHandoffGuideTitle: "Extension + CLI handoff",
    cliHandoffGuideNote: "Use the extension for browser context, current-page parse, PDF/EPUB upload, translation, and downloads. When a publisher challenge, campus login, or saved file blocks capture, continue in the Python CLI; `mdtero setup --json` returns the onboarding checklist for agents.",
    cliHandoffGuideBoundary: "The extension does not install Python dependencies, run native helpers, or store Elsevier/Wiley/Semantic Scholar keys; those stay in `mdtero config academic` on the local CLI.",
    copyCliHandoffGuide: "Copy handoff",
    cliHandoffGuideCopied: "CLI handoff copied.",
    guideTitle: "Connection guide",
    setupStepAuth: "OAuth",
    setupStepParse: "Parse / Upload",
    setupStepTranslate: "Translate",
    setupStepDownload: "Download",
    guideSignedOut: [
      "Open website OAuth and complete sign-in at mdtero.com/auth.",
      "Return to this popup after the trusted auth bridge connects your account.",
      "Optionally install the Python CLI with `uv tool install git+https://github.com/JonbinC/doi2md.git`, then run `mdtero setup` for workstation OAuth.",
      "Parse the current paper page or upload a local PDF/EPUB from the popup.",
      "Download Markdown, ZIP bundles, source files, or translations when tasks finish."
    ],
    guideSignedIn: [
      "Website OAuth is connected.",
      "Use the popup to parse the current page, paste a DOI, or upload PDF/EPUB.",
      "Translate parsed Markdown from the popup when a paper_md artifact is ready.",
      "Open history below to download previous artifacts without spending quota."
    ],
    uiLanguage: "Interface language",
    advanced: "Advanced",
    apiUrl: "API URL",
    save: "Save",
    historyTitle: "Account history",
    historyNote: "Downloads from your history are always free.",
    historyEmpty: "No parsing or translation history found yet.",
    historyError: "Failed to load history: ",
    downloadFailed: "Download failed:",
    download: "Download",
    artifactLabels: {
      paper_md: "Markdown",
      paper_bundle: "ZIP",
      translated_md: "Translation",
      paper_pdf: "PDF",
      paper_xml: "XML"
    },
    historyRefresh: "Refresh",
    historyRefreshing: "Refreshing..."
  },
  zh: {
    title: "Mdtero \u6269\u5C55",
    subtitle: "\u4F7F\u7528\u7F51\u9875\u767B\u5F55\u6388\u6743\u6269\u5C55\uFF0C\u5E76\u7BA1\u7406\u6D4F\u89C8\u5668\u6293\u53D6\u3001\u4E0A\u4F20\u3001\u7FFB\u8BD1\u548C\u4E0B\u8F7D\u8BBE\u7F6E\u3002",
    permissionsTitle: "\u4E3A\u4EC0\u4E48 Mdtero \u9700\u8981\u8FD9\u4E9B\u6743\u9650",
    permissionsTabs: "`tabs` \u7528\u6765\u8BFB\u53D6\u5F53\u524D\u8BBA\u6587\u9875\uFF0C\u5E76\u5728\u767B\u5F55\u65F6\u6253\u5F00\u7F51\u9875\u767B\u5F55\u9875\u3002",
    permissionsDownloads: "`downloads` \u7528\u6765\u628A Markdown\u3001\u8BD1\u6587\u3001ZIP \u5305\u548C\u4E0A\u4F20\u6587\u4EF6\u7684\u89E3\u6790\u7ED3\u679C\u4FDD\u5B58\u56DE\u4F60\u7684\u7535\u8111\u3002",
    permissionsCapture: "\u6D4F\u89C8\u5668\u8865\u6293\u53D6\u53EA\u4F1A\u5728\u4F60\u4E3B\u52A8\u89E3\u6790\u5F53\u524D\u8BBA\u6587\u9875\u65F6\u590D\u7528\u5F53\u524D\u6807\u7B7E\u9875\u3002",
    permissionsHosts: "\u7AD9\u70B9\u6743\u9650\u53EA\u8986\u76D6 Mdtero \u767B\u5F55\u9875\u3001\u53D7\u652F\u6301\u7684\u5B66\u672F\u9875\u9762\uFF0C\u4EE5\u53CA\u4F60\u4E3B\u52A8\u9009\u62E9\u4E0A\u4F20\u7684\u6587\u4EF6\u3002",
    notSignedIn: "\u5C1A\u672A\u901A\u8FC7\u7F51\u9875\u767B\u5F55\u6388\u6743\u6269\u5C55\u3002",
    usagePending: "\u8BF7\u5728 mdtero.com/auth \u767B\u5F55\u4EE5\u540C\u6B65\u4F59\u989D\u3001\u989D\u5EA6\u548C\u5386\u53F2\u3002",
    signedIn: (email) => `\u5DF2\u767B\u5F55\uFF1A${email}`,
    usageSummary: (wallet, parse, translation) => `\u4F59\u989D ${wallet} \xB7 \u89E3\u6790 ${parse} \xB7 \u7FFB\u8BD1 ${translation}`,
    openAccount: "\u6253\u5F00\u7F51\u9875\u767B\u5F55",
    websiteAuthTitle: "\u5B98\u7F51\u767B\u5F55",
    websiteAuthNote: "\u6269\u5C55\u7EDF\u4E00\u6253\u5F00 mdtero.com/auth \u767B\u5F55\u3002\u8BF7\u5728\u5B98\u7F51\u5B8C\u6210\u767B\u5F55\uFF0C\u53D7\u4FE1\u4EFB auth bridge \u4F1A\u628A token \u4EA4\u56DE\u6269\u5C55\u3002",
    cliHandoffGuideTitle: "\u6269\u5C55 + CLI \u4EA4\u63A5",
    cliHandoffGuideNote: "\u6269\u5C55\u8D1F\u8D23\u6D4F\u89C8\u5668\u4E0A\u4E0B\u6587\u3001\u5F53\u524D\u9875\u89E3\u6790\u3001PDF/EPUB \u4E0A\u4F20\u3001\u7FFB\u8BD1\u548C\u4E0B\u8F7D\u3002\u9047\u5230 publisher challenge\u3001\u6821\u56ED\u7F51\u767B\u5F55\u6001\u6216\u7528\u6237\u5DF2\u4FDD\u5B58\u6587\u4EF6\u65F6\uFF0C\u4EA4\u7ED9 Python CLI \u7EE7\u7EED\uFF1B`mdtero setup --json` \u4F1A\u8FD4\u56DE\u7ED9 agent \u4F7F\u7528\u7684 onboarding checklist\u3002",
    cliHandoffGuideBoundary: "\u6269\u5C55\u4E0D\u5B89\u88C5 Python \u4F9D\u8D56\u3001\u4E0D\u8FD0\u884C\u672C\u5730 helper\uFF0C\u4E5F\u4E0D\u4FDD\u5B58 Elsevier/Wiley/Semantic Scholar key\uFF1B\u8FD9\u4E9B\u53EA\u7559\u5728\u672C\u5730 CLI \u7684 `mdtero config academic`\u3002",
    copyCliHandoffGuide: "\u590D\u5236\u4EA4\u63A5",
    cliHandoffGuideCopied: "CLI \u4EA4\u63A5\u5DF2\u590D\u5236\u3002",
    guideTitle: "\u8FDE\u63A5\u5F15\u5BFC",
    setupStepAuth: "\u7F51\u9875\u767B\u5F55",
    setupStepParse: "\u89E3\u6790 / \u4E0A\u4F20",
    setupStepTranslate: "\u7FFB\u8BD1",
    setupStepDownload: "\u4E0B\u8F7D",
    guideSignedOut: [
      "\u6253\u5F00\u7F51\u9875\u767B\u5F55\uFF0C\u5E76\u5728 mdtero.com/auth \u5B8C\u6210\u6388\u6743\u3002",
      "\u53D7\u4FE1\u4EFB auth bridge \u8FDE\u63A5\u8D26\u6237\u540E\uFF0C\u56DE\u5230\u6269\u5C55\u5F39\u7A97\u7EE7\u7EED\u3002",
      "\u53EF\u9009\u5B89\u88C5 Python CLI\uFF1A`uv tool install git+https://github.com/JonbinC/doi2md.git`\uFF0C\u518D\u8FD0\u884C `mdtero setup` \u8D70\u5DE5\u4F5C\u7AD9 OAuth\u3002",
      "\u5728\u5F39\u7A97\u89E3\u6790\u5F53\u524D\u8BBA\u6587\u9875\u3001\u7C98\u8D34 DOI\uFF0C\u6216\u4E0A\u4F20\u672C\u5730 PDF/EPUB\u3002",
      "\u4EFB\u52A1\u5B8C\u6210\u540E\u4E0B\u8F7D Markdown\u3001ZIP\u3001\u6E90\u6587\u4EF6\u6216\u8BD1\u6587\u3002"
    ],
    guideSignedIn: [
      "\u7F51\u9875\u767B\u5F55\u5DF2\u8FDE\u63A5\u3002",
      "\u5728\u5F39\u7A97\u89E3\u6790\u5F53\u524D\u9875\u9762\u3001\u7C98\u8D34 DOI\uFF0C\u6216\u4E0A\u4F20 PDF/EPUB\u3002",
      "\u5F53 paper_md \u4EA7\u7269\u5C31\u7EEA\u540E\uFF0C\u53EF\u76F4\u63A5\u4ECE\u5F39\u7A97\u8BF7\u6C42\u7FFB\u8BD1\u3002",
      "\u4E0B\u65B9\u5386\u53F2\u8BB0\u5F55\u53EF\u514D\u8D39\u4E0B\u8F7D\u5DF2\u751F\u6210\u4EA7\u7269\u3002"
    ],
    uiLanguage: "\u754C\u9762\u8BED\u8A00",
    advanced: "\u9AD8\u7EA7\u8BBE\u7F6E",
    apiUrl: "API \u5730\u5740",
    save: "\u4FDD\u5B58",
    historyTitle: "\u8D26\u6237\u5386\u53F2",
    historyNote: "\u4ECE\u5386\u53F2\u8BB0\u5F55\u4E0B\u8F7D\u5185\u5BB9\u6C38\u8FDC\u514D\u8D39\uFF0C\u4E0D\u6263\u9664\u989D\u5EA6\u3002",
    historyEmpty: "\u6682\u65E0\u89E3\u6790\u6216\u7FFB\u8BD1\u8BB0\u5F55\u3002",
    historyError: "\u52A0\u8F7D\u5386\u53F2\u6587\u6863\u5931\u8D25\uFF1A",
    downloadFailed: "\u4E0B\u8F7D\u5931\u8D25\uFF1A",
    download: "\u4E0B\u8F7D",
    artifactLabels: {
      paper_md: "Markdown",
      paper_bundle: "\u538B\u7F29\u5305",
      translated_md: "\u8BD1\u6587",
      paper_pdf: "PDF",
      paper_xml: "XML"
    },
    historyRefresh: "\u5237\u65B0",
    historyRefreshing: "\u5237\u65B0\u4E2D..."
  }
};
var titleEl = document.querySelector("#settings-title");
var subtitleEl = document.querySelector("#settings-subtitle");
var permissionsTitleEl = document.querySelector("#permissions-title");
var permissionsTabsEl = document.querySelector("#permissions-tabs");
var permissionsDownloadsEl = document.querySelector("#permissions-downloads");
var permissionsCaptureEl = document.querySelector("#permissions-capture");
var permissionsHostsEl = document.querySelector("#permissions-hosts");
var languageToggleEl = document.querySelector("#language-toggle");
var apiBaseUrlInput = document.querySelector("#api-base-url");
var uiLanguageSelect = document.querySelector("#ui-language");
var accountStatus = document.querySelector("#account-status");
var usageStatus = document.querySelector("#usage-status");
var saveButton = document.querySelector("#save-settings");
var openAccountButton = document.querySelector("#open-account");
var websiteAuthTitleEl = document.querySelector("#website-auth-title");
var websiteAuthNoteEl = document.querySelector("#website-auth-note");
var cliHandoffGuideTitleEl = document.querySelector("#cli-handoff-guide-title");
var cliHandoffGuideNoteEl = document.querySelector("#cli-handoff-guide-note");
var cliHandoffGuideBoundaryEl = document.querySelector("#cli-handoff-guide-boundary");
var cliHandoffGuideCommandEl = document.querySelector("#cli-handoff-guide-command");
var copyCliHandoffGuideButton = document.querySelector("#copy-cli-handoff-guide");
var connectionGuideTitleEl = document.querySelector("#connection-guide-title");
var connectionGuideListEl = document.querySelector("#connection-guide-list");
var setupStepAuthEl = document.querySelector("#setup-step-auth");
var setupStepParseEl = document.querySelector("#setup-step-parse");
var setupStepTranslateEl = document.querySelector("#setup-step-translate");
var setupStepDownloadEl = document.querySelector("#setup-step-download");
var uiLanguageLabel = document.querySelector("#ui-language-label");
var advancedSummary = document.querySelector("#advanced-summary");
var apiBaseUrlLabel = document.querySelector("#api-base-url-label");
var historySection = document.querySelector("#history-section");
var historyList = document.querySelector("#history-list");
var historyTitle = document.querySelector("#history-title");
var historyNote = document.querySelector("#history-note");
var refreshHistoryBtn = document.querySelector("#refresh-history");
var client = createApiClient(readSettings);
var uiLanguage = "en";
var CLI_HANDOFF_GUIDE_COMMAND = [
  "uv tool install git+https://github.com/JonbinC/doi2md.git",
  "mdtero setup",
  "mdtero setup --json",
  "mdtero doctor --json",
  "mdtero config academic",
  'mdtero discover "<topic>" --limit 5 --interactive',
  'mdtero discover "<topic>" --limit 5 --add --select 1,3 --json',
  "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
  "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 300 --json",
  "mdtero status <task-id> --wait --timeout 300 --json",
  "mdtero download <task-id> paper_md --output-dir ./mdtero-output --json",
  "mdtero project ingest --json",
  "mdtero project parse --wait --timeout 300 --json",
  "mdtero project refresh --wait --timeout 300 --json",
  "mdtero rag build --json",
  "mdtero rag status --json",
  'mdtero rag query "<question>" --build-if-needed --json',
  "mdtero mcp briefing --json"
].join("\n");
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
function formatArtifactActionLabel(artifactKey) {
  const copy = copyFor(uiLanguage);
  const labels = copy.artifactLabels;
  const label = labels[artifactKey] || artifactKey.replace(/^paper_/, "").replace(/_/g, " ").toUpperCase();
  return `${copy.download} ${label}`;
}
function applyLanguage() {
  const copy = copyFor(uiLanguage);
  document.documentElement.lang = uiLanguage === "zh" ? "zh-CN" : "en";
  if (titleEl) titleEl.textContent = copy.title;
  if (subtitleEl) subtitleEl.textContent = copy.subtitle;
  if (permissionsTitleEl) permissionsTitleEl.textContent = copy.permissionsTitle;
  if (permissionsTabsEl) permissionsTabsEl.textContent = copy.permissionsTabs;
  if (permissionsDownloadsEl) permissionsDownloadsEl.textContent = copy.permissionsDownloads;
  if (permissionsCaptureEl) permissionsCaptureEl.textContent = copy.permissionsCapture;
  if (permissionsHostsEl) permissionsHostsEl.textContent = copy.permissionsHosts;
  if (languageToggleEl) languageToggleEl.textContent = toggleLanguageLabel(uiLanguage);
  if (uiLanguageLabel) uiLanguageLabel.textContent = copy.uiLanguage;
  if (advancedSummary) advancedSummary.textContent = copy.advanced;
  if (apiBaseUrlLabel) apiBaseUrlLabel.textContent = copy.apiUrl;
  if (openAccountButton) openAccountButton.textContent = copy.openAccount;
  if (websiteAuthTitleEl) websiteAuthTitleEl.textContent = copy.websiteAuthTitle;
  if (websiteAuthNoteEl) websiteAuthNoteEl.textContent = copy.websiteAuthNote;
  if (cliHandoffGuideTitleEl) cliHandoffGuideTitleEl.textContent = copy.cliHandoffGuideTitle;
  if (cliHandoffGuideNoteEl) cliHandoffGuideNoteEl.textContent = copy.cliHandoffGuideNote;
  if (cliHandoffGuideBoundaryEl) cliHandoffGuideBoundaryEl.textContent = copy.cliHandoffGuideBoundary;
  if (cliHandoffGuideCommandEl) cliHandoffGuideCommandEl.textContent = CLI_HANDOFF_GUIDE_COMMAND;
  if (copyCliHandoffGuideButton) copyCliHandoffGuideButton.textContent = copy.copyCliHandoffGuide;
  if (connectionGuideTitleEl) connectionGuideTitleEl.textContent = copy.guideTitle;
  setStepText(setupStepAuthEl, "1", copy.setupStepAuth);
  setStepText(setupStepParseEl, "2", copy.setupStepParse);
  setStepText(setupStepTranslateEl, "3", copy.setupStepTranslate);
  setStepText(setupStepDownloadEl, "4", copy.setupStepDownload);
  if (saveButton) saveButton.textContent = copy.save;
  if (historyTitle) historyTitle.textContent = copy.historyTitle;
  if (historyNote) historyNote.textContent = copy.historyNote;
  if (refreshHistoryBtn) refreshHistoryBtn.textContent = copy.historyRefresh;
}
function setStepText(element, index, label) {
  if (!element) return;
  element.textContent = "";
  const icon = document.createElement("span");
  icon.className = "support-icon";
  icon.textContent = index;
  element.appendChild(icon);
  element.append(label);
}
function renderConnectionGuide(isSignedIn) {
  if (!connectionGuideListEl) return;
  const copy = copyFor(uiLanguage);
  const items = isSignedIn ? copy.guideSignedIn : copy.guideSignedOut;
  connectionGuideListEl.textContent = "";
  items.forEach((item, index) => {
    const row = document.createElement("div");
    row.className = "guide-item";
    const icon = document.createElement("span");
    icon.className = "guide-index";
    icon.textContent = String(index + 1);
    const text = document.createElement("p");
    text.className = "meta-label";
    text.textContent = item;
    row.appendChild(icon);
    row.appendChild(text);
    connectionGuideListEl.appendChild(row);
  });
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
      const artifactEntries = task.result ? task.result.artifacts ? Object.entries(task.result.artifacts).map(([key, desc]) => [key, desc.filename]) : (task.result.download_artifacts ?? []).map((desc) => [desc.artifact, desc.filename]) : [];
      if (task.status === "succeeded" && artifactEntries.length > 0) {
        const artifactsRow = document.createElement("div");
        artifactsRow.className = "history-actions";
        for (const [key, filename] of artifactEntries) {
          const dlBtn = document.createElement("button");
          dlBtn.className = "ghost-chip history-download-button";
          dlBtn.textContent = formatArtifactActionLabel(key);
          dlBtn.addEventListener("click", async () => {
            try {
              dlBtn.textContent = uiLanguage === "zh" ? "\u4E0B\u8F7D\u4E2D..." : "Downloading...";
              const result = await client.downloadArtifact(task.task_id, key, filename);
              triggerBlobDownload(result.blob, result.filename);
              dlBtn.textContent = formatArtifactActionLabel(key);
            } catch (err) {
              renderHistoryNotice(`${copyFor(uiLanguage).downloadFailed} ${err.message}`, "#b91c1c");
              dlBtn.textContent = formatArtifactActionLabel(key);
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
  if (apiBaseUrlInput) apiBaseUrlInput.value = settings.apiBaseUrl;
  if (uiLanguageSelect) uiLanguageSelect.value = uiLanguage;
  if (accountStatus) {
    accountStatus.textContent = settings.email ? copyFor(uiLanguage).signedIn(settings.email) : copyFor(uiLanguage).notSignedIn;
  }
  renderConnectionGuide(Boolean(settings.token));
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
copyCliHandoffGuideButton?.addEventListener("click", async () => {
  await navigator.clipboard?.writeText(CLI_HANDOFF_GUIDE_COMMAND);
  copyCliHandoffGuideButton.textContent = copyFor(uiLanguage).cliHandoffGuideCopied;
});
saveButton?.addEventListener("click", async () => {
  const current = await readSettings();
  await writeSettings(
    mergeSettings(current, {
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
