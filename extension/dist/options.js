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
var ONE_COMMAND_RAG_BOOTSTRAP = 'mdtero rag query "What are the strongest findings?" --build-if-needed --json';
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
    cliHandoffGuideNote: "Use the extension for browser context, current-page parse, PDF/EPUB upload, translation, and downloads. When a publisher challenge, campus login, or saved file blocks capture, continue in the Python CLI; `mdtero setup --json` returns the onboarding checklist for agents. After one parse succeeds, use one-command RAG bootstrap instead of hand-copying a server project id.",
    cliHandoffGuideBoundary: "The extension does not install Python dependencies, run native helpers, or store Elsevier/Wiley/Semantic Scholar keys; those stay in `mdtero config academic` on the local CLI.",
    copyCliHandoffGuide: "Copy handoff",
    cliHandoffGuideCopied: "CLI handoff copied.",
    mcpServerConfigTitle: "Agent MCP server",
    mcpServerConfigNote: "After `mdtero setup`, start `mdtero mcp serve` from a local project and paste this stdio server config into Codex, Claude, Gemini, Hermes, or OpenCode.",
    mcpServerConfigMeta: "FastMCP \xB7 stdio \xB7 local project root",
    copyMcpServerConfig: "Copy MCP config",
    mcpServerConfigCopied: "MCP config copied.",
    cliOnboardingTitle: "CLI setup checklist",
    cliOnboardingNote: "The Python client handles local acquisition, project queues, Zotero, backend Voyage RAG, MCP, and agent skills.",
    cliOnboardingPill: "Python / uv",
    inputRouteTitle: "Input routes",
    inputRouteNote: "Choose the shortest path to a Markdown artifact. The extension covers browser context; the CLI continues local files, RAG, MCP, and agent handoff.",
    inputRoutePill: "Extension + CLI",
    inputRouteCopy: "Copy",
    inputRouteCopied: "Route copied.",
    serverApiContractTitle: "Server API contract",
    serverApiContractNote: "The same /api/v1 routes back extension capture, CLI upload, task polling, downloads, project import, and backend Voyage RAG.",
    copyServerApiContract: "Copy API contract",
    serverApiContractCopied: "API contract copied.",
    serverApiContract: [
      ["route", "/api/v1/route"],
      ["parse", "/api/v1/tasks/parse"],
      ["upload", "/api/v1/tasks/upload"],
      ["status", "/api/v1/tasks/{task_id}"],
      ["download", "/api/v1/tasks/{task_id}/download/{artifact}"],
      ["project_import", "/api/v1/projects/{project_id}/tasks/{task_id}/import"],
      ["rag_build", "/api/v1/projects/{project_id}/rag/build"],
      ["rag_query", "/api/v1/projects/{project_id}/rag/query"]
    ],
    inputRoutes: [
      ["DOI or URL", "fast smoke", "Use the CLI for DOI, arXiv, EuropePMC XML, or an open URL the backend route can recognize.", "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json"],
      ["PDF / EPUB file", "upload", "Use direct file upload for local PDF, EPUB, XML, or HTML. PDFs go through the backend MinerU-first path.", "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json"],
      ["Browser extension", "manual capture", "Use the extension when OAuth, campus network, cookies, or a selected PDF/EPUB matter, then hand off saved inputs to the CLI.", "mdtero parse <doi-or-current-page-url> --trace --wait --timeout 300 --json\nmdtero parse --file <saved-browser-artifact.pdf|epub|html|xml> --trace --wait --timeout 600 --json"],
      ["RAG / MCP", "after parse", "Build backend Voyage RAG from completed Markdown and expose the same project to local agents through FastMCP. The bootstrap query creates or reuses the server project, binds it locally, imports Markdown, builds RAG, and queries without asking you to copy a server project id.", `${ONE_COMMAND_RAG_BOOTSTRAP}
mdtero mcp briefing --json
mdtero mcp serve`]
    ],
    cliOnboardingItems: [
      ["Install", "uv tool install git+https://github.com/JonbinC/doi2md.git", "Install the public Python client; the extension never installs Python dependencies."],
      ["Authenticate", "mdtero setup", "Use website OAuth on a workstation, or API-key setup on a trusted headless server."],
      ["Checklist", "mdtero setup --json", "Return the same secret-safe onboarding checklist used by local agents."],
      ["Academic keys", "mdtero config academic", "Optional academic resource keys stay in local CLI config."],
      ["Discover", 'mdtero discover "<topic>" --limit 5 --interactive', "Use local Semantic Scholar when configured; otherwise use server OpenAlex."],
      ["Parse", "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json", "Preserve route, client_acquisition, reason_code, action_hint, and artifacts."],
      ["File upload", "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 300 --json", "Continue from browser-saved files or challenged publisher pages."],
      ["RAG", ONE_COMMAND_RAG_BOOTSTRAP, "Backend Voyage RAG is driven by the CLI project. This one command can create or bind the server project, import succeeded Markdown, build Voyage RAG, and query with citations; citation_contract requires final answers to preserve citations and source_nodes."],
      ["MCP briefing", "mdtero mcp briefing --json", "Expose account, project, extension_handoff, RAG readiness, and citation_contract to local agents."],
      ["MCP server", "mdtero mcp serve", "Run the FastMCP stdio server from the local project root for agent context tools."],
      ["Agent skills", "mdtero agent install --interactive", "Detect Codex, Claude, Gemini, Hermes, or OpenCode and select workspaces with Space."]
    ],
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
    cliHandoffGuideNote: "\u6269\u5C55\u8D1F\u8D23\u6D4F\u89C8\u5668\u4E0A\u4E0B\u6587\u3001\u5F53\u524D\u9875\u89E3\u6790\u3001PDF/EPUB \u4E0A\u4F20\u3001\u7FFB\u8BD1\u548C\u4E0B\u8F7D\u3002\u9047\u5230 publisher challenge\u3001\u6821\u56ED\u7F51\u767B\u5F55\u6001\u6216\u7528\u6237\u5DF2\u4FDD\u5B58\u6587\u4EF6\u65F6\uFF0C\u4EA4\u7ED9 Python CLI \u7EE7\u7EED\uFF1B`mdtero setup --json` \u4F1A\u8FD4\u56DE\u7ED9 agent \u4F7F\u7528\u7684 onboarding checklist\u3002\u5DF2\u6709\u4E00\u6B21\u6210\u529F\u89E3\u6790\u540E\uFF0C\u7528\u4E00\u6761\u547D\u4EE4 RAG bootstrap\uFF0C\u4E0D\u8981\u624B\u5DE5\u590D\u5236 server project id\u3002",
    cliHandoffGuideBoundary: "\u6269\u5C55\u4E0D\u5B89\u88C5 Python \u4F9D\u8D56\u3001\u4E0D\u8FD0\u884C\u672C\u5730 helper\uFF0C\u4E5F\u4E0D\u4FDD\u5B58 Elsevier/Wiley/Semantic Scholar key\uFF1B\u8FD9\u4E9B\u53EA\u7559\u5728\u672C\u5730 CLI \u7684 `mdtero config academic`\u3002",
    copyCliHandoffGuide: "\u590D\u5236\u4EA4\u63A5",
    cliHandoffGuideCopied: "CLI \u4EA4\u63A5\u5DF2\u590D\u5236\u3002",
    mcpServerConfigTitle: "Agent MCP \u670D\u52A1",
    mcpServerConfigNote: "\u8FD0\u884C `mdtero setup` \u540E\uFF0C\u5728\u672C\u5730\u9879\u76EE\u76EE\u5F55\u542F\u52A8 `mdtero mcp serve`\uFF0C\u518D\u628A\u8FD9\u6BB5 stdio server \u914D\u7F6E\u7C98\u8D34\u5230 Codex\u3001Claude\u3001Gemini\u3001Hermes \u6216 OpenCode\u3002",
    mcpServerConfigMeta: "FastMCP \xB7 stdio \xB7 \u672C\u5730\u9879\u76EE\u6839\u76EE\u5F55",
    copyMcpServerConfig: "\u590D\u5236 MCP \u914D\u7F6E",
    mcpServerConfigCopied: "MCP \u914D\u7F6E\u5DF2\u590D\u5236\u3002",
    cliOnboardingTitle: "CLI \u914D\u7F6E\u6E05\u5355",
    cliOnboardingNote: "Python \u5BA2\u6237\u7AEF\u8D1F\u8D23\u672C\u5730\u6293\u53D6\u3001\u9879\u76EE\u961F\u5217\u3001Zotero\u3001\u540E\u7AEF Voyage RAG\u3001MCP \u548C agent skill\u3002",
    cliOnboardingPill: "Python / uv",
    inputRouteTitle: "\u8F93\u5165\u8DEF\u5F84",
    inputRouteNote: "\u6309\u8F93\u5165\u7C7B\u578B\u9009\u62E9\u6700\u77ED Markdown \u8DEF\u5F84\u3002\u6269\u5C55\u8D1F\u8D23\u6D4F\u89C8\u5668\u4E0A\u4E0B\u6587\uFF1BCLI \u7EE7\u7EED\u5904\u7406\u672C\u5730\u6587\u4EF6\u3001RAG\u3001MCP \u548C agent \u4EA4\u63A5\u3002",
    inputRoutePill: "\u6269\u5C55 + CLI",
    inputRouteCopy: "\u590D\u5236",
    inputRouteCopied: "\u8DEF\u5F84\u5DF2\u590D\u5236\u3002",
    serverApiContractTitle: "\u670D\u52A1\u7AEF API \u5951\u7EA6",
    serverApiContractNote: "\u6269\u5C55\u6293\u53D6\u3001CLI \u4E0A\u4F20\u3001\u4EFB\u52A1\u8F6E\u8BE2\u3001\u4E0B\u8F7D\u3001\u9879\u76EE\u5BFC\u5165\u548C\u540E\u7AEF Voyage RAG \u90FD\u843D\u5230\u540C\u4E00\u7EC4 /api/v1 \u8DEF\u7531\u3002",
    copyServerApiContract: "\u590D\u5236 API \u5951\u7EA6",
    serverApiContractCopied: "API \u5951\u7EA6\u5DF2\u590D\u5236\u3002",
    serverApiContract: [
      ["route", "/api/v1/route"],
      ["parse", "/api/v1/tasks/parse"],
      ["upload", "/api/v1/tasks/upload"],
      ["status", "/api/v1/tasks/{task_id}"],
      ["download", "/api/v1/tasks/{task_id}/download/{artifact}"],
      ["project_import", "/api/v1/projects/{project_id}/tasks/{task_id}/import"],
      ["rag_build", "/api/v1/projects/{project_id}/rag/build"],
      ["rag_query", "/api/v1/projects/{project_id}/rag/query"]
    ],
    inputRoutes: [
      ["DOI \u6216 URL", "\u5FEB\u901F\u5192\u70DF", "DOI\u3001arXiv\u3001EuropePMC XML\uFF0C\u6216\u540E\u7AEF route \u80FD\u8BC6\u522B\u7684\u5F00\u653E URL\uFF0C\u4F18\u5148\u8D70 CLI\u3002", "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json"],
      ["PDF / EPUB \u6587\u4EF6", "\u4E0A\u4F20", "\u672C\u5730 PDF\u3001EPUB\u3001XML \u6216 HTML \u8D70\u76F4\u63A5\u4E0A\u4F20\u3002PDF \u9ED8\u8BA4\u8FDB\u5165\u540E\u7AEF MinerU-first \u8DEF\u5F84\u3002", "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json"],
      ["\u6D4F\u89C8\u5668\u6269\u5C55", "\u4EBA\u5DE5\u6293\u53D6", "\u9047\u5230 OAuth\u3001\u6821\u56ED\u7F51\u3001cookie \u6216\u4EBA\u5DE5\u9009\u62E9 PDF/EPUB \u65F6\u7528\u6269\u5C55\uFF0C\u518D\u628A\u5DF2\u4FDD\u5B58\u8F93\u5165\u4EA4\u7ED9 CLI\u3002", "mdtero parse <doi-or-current-page-url> --trace --wait --timeout 300 --json\nmdtero parse --file <saved-browser-artifact.pdf|epub|html|xml> --trace --wait --timeout 600 --json"],
      ["RAG / MCP", "\u89E3\u6790\u540E", "\u57FA\u4E8E\u5B8C\u6210\u7684 Markdown \u6784\u5EFA\u540E\u7AEF Voyage RAG\uFF0C\u5E76\u901A\u8FC7 FastMCP \u4EA4\u7ED9\u672C\u5730 agent\u3002Bootstrap \u67E5\u8BE2\u4F1A\u521B\u5EFA\u6216\u590D\u7528\u670D\u52A1\u7AEF\u9879\u76EE\u3001\u5199\u5165\u672C\u5730\u7ED1\u5B9A\u3001\u5BFC\u5165 Markdown\u3001\u6784\u5EFA RAG \u5E76\u67E5\u8BE2\uFF0C\u4E0D\u9700\u8981\u4F60\u624B\u5DE5\u590D\u5236 server project id\u3002", `${ONE_COMMAND_RAG_BOOTSTRAP}
mdtero mcp briefing --json
mdtero mcp serve`]
    ],
    cliOnboardingItems: [
      ["\u5B89\u88C5", "uv tool install git+https://github.com/JonbinC/doi2md.git", "\u5B89\u88C5\u516C\u5F00 Python \u5BA2\u6237\u7AEF\uFF1B\u6269\u5C55\u4E0D\u4F1A\u5B89\u88C5 Python \u4F9D\u8D56\u3002"],
      ["\u9274\u6743", "mdtero setup", "\u5DE5\u4F5C\u7AD9\u8D70\u7F51\u9875\u767B\u5F55 OAuth\uFF1B\u53EF\u4FE1\u65E0\u5934\u670D\u52A1\u5668\u53EF\u8D70 API-key setup\u3002"],
      ["\u68C0\u67E5\u6E05\u5355", "mdtero setup --json", "\u8FD4\u56DE\u7ED9\u672C\u5730 agent \u4F7F\u7528\u7684\u540C\u4E00\u4EFD secret-safe onboarding checklist\u3002"],
      ["\u5B66\u672F key", "mdtero config academic", "\u5B66\u672F\u8D44\u6E90 key \u90FD\u662F\u53EF\u9009\u589E\u5F3A\uFF0C\u53EA\u5B58\u5728\u672C\u5730 CLI \u914D\u7F6E\u3002"],
      ["\u53D1\u73B0", 'mdtero discover "<topic>" --limit 5 --interactive', "\u6709 Semantic Scholar \u65F6\u8D70\u672C\u5730\uFF1B\u5426\u5219\u8D70\u670D\u52A1\u7AEF OpenAlex\u3002"],
      ["\u89E3\u6790", "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json", "\u4FDD\u7559 route\u3001client_acquisition\u3001reason_code\u3001action_hint \u548C artifacts\u3002"],
      ["\u6587\u4EF6\u4E0A\u4F20", "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 300 --json", "\u6D4F\u89C8\u5668\u4FDD\u5B58\u7684\u6587\u4EF6\u6216 publisher challenge \u9875\u9762\u4EA4\u7ED9 CLI \u7EE7\u7EED\u3002"],
      ["RAG", ONE_COMMAND_RAG_BOOTSTRAP, "\u540E\u7AEF Voyage RAG \u7531 CLI \u9879\u76EE\u9A71\u52A8\u3002\u8FD9\u4E00\u6761\u547D\u4EE4\u53EF\u4EE5\u521B\u5EFA\u6216\u7ED1\u5B9A\u670D\u52A1\u7AEF\u9879\u76EE\u3001\u5BFC\u5165\u6210\u529F Markdown\u3001\u6784\u5EFA Voyage RAG\uFF0C\u5E76\u5E26\u5F15\u7528\u67E5\u8BE2\uFF1Bcitation_contract \u8981\u6C42\u6700\u7EC8\u56DE\u7B54\u4FDD\u7559 citations \u548C source_nodes\u3002"],
      ["MCP briefing", "mdtero mcp briefing --json", "\u628A\u8D26\u6237\u3001\u9879\u76EE\u3001extension_handoff\u3001RAG readiness \u548C citation_contract \u66B4\u9732\u7ED9\u672C\u5730 agent\u3002"],
      ["MCP \u670D\u52A1", "mdtero mcp serve", "\u5728\u672C\u5730\u9879\u76EE\u6839\u76EE\u5F55\u8FD0\u884C FastMCP stdio server\uFF0C\u7ED9 agent \u63D0\u4F9B\u4E0A\u4E0B\u6587\u5DE5\u5177\u3002"],
      ["Agent skill", "mdtero agent install --interactive", "\u52A8\u6001\u68C0\u6D4B Codex\u3001Claude\u3001Gemini\u3001Hermes\u3001OpenCode\uFF0C\u5E76\u7528\u7A7A\u683C\u591A\u9009\u5B89\u88C5\u3002"]
    ],
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
var mcpServerConfigTitleEl = document.querySelector("#mcp-server-config-title");
var mcpServerConfigNoteEl = document.querySelector("#mcp-server-config-note");
var mcpServerConfigMetaEl = document.querySelector("#mcp-server-config-meta");
var mcpServerConfigCommandEl = document.querySelector("#mcp-server-config-command");
var copyMcpServerConfigButton = document.querySelector("#copy-mcp-server-config");
var cliOnboardingTitleEl = document.querySelector("#cli-onboarding-title");
var cliOnboardingNoteEl = document.querySelector("#cli-onboarding-note");
var cliOnboardingPillEl = document.querySelector("#cli-onboarding-pill");
var cliOnboardingListEl = document.querySelector("#cli-onboarding-list");
var inputRouteTitleEl = document.querySelector("#input-route-title");
var inputRouteNoteEl = document.querySelector("#input-route-note");
var inputRoutePillEl = document.querySelector("#input-route-pill");
var inputRouteListEl = document.querySelector("#input-route-list");
var serverApiContractTitleEl = document.querySelector("#server-api-contract-title");
var serverApiContractNoteEl = document.querySelector("#server-api-contract-note");
var serverApiContractListEl = document.querySelector("#server-api-contract-list");
var copyServerApiContractButton = document.querySelector("#copy-server-api-contract");
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
  ONE_COMMAND_RAG_BOOTSTRAP,
  "mdtero rag build --json",
  "mdtero rag status --json",
  'mdtero rag query "<question>" --build-if-needed --json',
  "# Preserve citation_contract.required_for_final_answer: final RAG answers keep citations and source_nodes.",
  "mdtero mcp briefing --json",
  "mdtero mcp serve"
].join("\n");
var MCP_SERVER_CONFIG = JSON.stringify(
  {
    mcpServers: {
      mdtero: {
        command: "mdtero",
        args: ["mcp", "serve"],
        cwd: "<local-mdtero-project-root>"
      }
    }
  },
  null,
  2
);
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
  if (mcpServerConfigTitleEl) mcpServerConfigTitleEl.textContent = copy.mcpServerConfigTitle;
  if (mcpServerConfigNoteEl) mcpServerConfigNoteEl.textContent = copy.mcpServerConfigNote;
  if (mcpServerConfigMetaEl) mcpServerConfigMetaEl.textContent = copy.mcpServerConfigMeta;
  if (mcpServerConfigCommandEl) mcpServerConfigCommandEl.textContent = MCP_SERVER_CONFIG;
  if (copyMcpServerConfigButton) copyMcpServerConfigButton.textContent = copy.copyMcpServerConfig;
  if (cliOnboardingTitleEl) cliOnboardingTitleEl.textContent = copy.cliOnboardingTitle;
  if (cliOnboardingNoteEl) cliOnboardingNoteEl.textContent = copy.cliOnboardingNote;
  if (cliOnboardingPillEl) cliOnboardingPillEl.textContent = copy.cliOnboardingPill;
  if (inputRouteTitleEl) inputRouteTitleEl.textContent = copy.inputRouteTitle;
  if (inputRouteNoteEl) inputRouteNoteEl.textContent = copy.inputRouteNote;
  if (inputRoutePillEl) inputRoutePillEl.textContent = copy.inputRoutePill;
  if (serverApiContractTitleEl) serverApiContractTitleEl.textContent = copy.serverApiContractTitle;
  if (serverApiContractNoteEl) serverApiContractNoteEl.textContent = copy.serverApiContractNote;
  if (copyServerApiContractButton) copyServerApiContractButton.textContent = copy.copyServerApiContract;
  renderInputRouteList();
  renderServerApiContractList();
  renderCliOnboardingList();
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
function renderServerApiContractList() {
  if (!serverApiContractListEl) return;
  const copy = copyFor(uiLanguage);
  serverApiContractListEl.textContent = "";
  copy.serverApiContract.forEach(([label, value]) => {
    const item = document.createElement("div");
    item.className = "server-api-contract-item";
    const labelEl = document.createElement("span");
    labelEl.className = "server-api-label";
    labelEl.textContent = label;
    const valueEl = document.createElement("code");
    valueEl.className = "server-api-value";
    valueEl.textContent = value;
    item.appendChild(labelEl);
    item.appendChild(valueEl);
    serverApiContractListEl.appendChild(item);
  });
}
function renderInputRouteList() {
  if (!inputRouteListEl) return;
  const copy = copyFor(uiLanguage);
  inputRouteListEl.textContent = "";
  copy.inputRoutes.forEach(([title, status, detail, command]) => {
    const row = document.createElement("div");
    row.className = "input-route-item";
    const header = document.createElement("div");
    header.className = "input-route-header";
    const titleEl2 = document.createElement("p");
    titleEl2.className = "onboarding-title";
    titleEl2.textContent = title;
    const statusEl = document.createElement("span");
    statusEl.className = "meta-pill input-route-status";
    statusEl.textContent = status;
    header.appendChild(titleEl2);
    header.appendChild(statusEl);
    const detailEl = document.createElement("p");
    detailEl.className = "meta-label";
    detailEl.textContent = detail;
    const commandEl = document.createElement("code");
    commandEl.className = "onboarding-command";
    commandEl.textContent = command;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ghost-chip input-route-copy";
    button.textContent = copy.inputRouteCopy;
    button.addEventListener("click", async () => {
      await navigator.clipboard?.writeText(command);
      button.textContent = copyFor(uiLanguage).inputRouteCopied;
    });
    row.appendChild(header);
    row.appendChild(detailEl);
    row.appendChild(commandEl);
    row.appendChild(button);
    inputRouteListEl.appendChild(row);
  });
}
function renderCliOnboardingList() {
  if (!cliOnboardingListEl) return;
  const copy = copyFor(uiLanguage);
  cliOnboardingListEl.textContent = "";
  copy.cliOnboardingItems.forEach(([title, command, detail], index) => {
    const row = document.createElement("div");
    row.className = "onboarding-item";
    const icon = document.createElement("span");
    icon.className = "guide-index";
    icon.textContent = String(index + 1);
    const body = document.createElement("div");
    body.className = "onboarding-body";
    const heading = document.createElement("p");
    heading.className = "onboarding-title";
    heading.textContent = title;
    const commandEl = document.createElement("code");
    commandEl.className = "onboarding-command";
    commandEl.textContent = command;
    const detailEl = document.createElement("p");
    detailEl.className = "meta-label";
    detailEl.textContent = detail;
    body.appendChild(heading);
    body.appendChild(commandEl);
    body.appendChild(detailEl);
    row.appendChild(icon);
    row.appendChild(body);
    cliOnboardingListEl.appendChild(row);
  });
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
copyMcpServerConfigButton?.addEventListener("click", async () => {
  await navigator.clipboard?.writeText(MCP_SERVER_CONFIG);
  copyMcpServerConfigButton.textContent = copyFor(uiLanguage).mcpServerConfigCopied;
});
copyServerApiContractButton?.addEventListener("click", async () => {
  const contract = copyFor(uiLanguage).serverApiContract.map(([label, value]) => `${label}: ${value}`).join("\n");
  await navigator.clipboard?.writeText(contract);
  copyServerApiContractButton.textContent = copyFor(uiLanguage).serverApiContractCopied;
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
