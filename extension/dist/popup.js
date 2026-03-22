// src/lib/api.ts
function createApiClient(getSettings) {
  async function request(path, init) {
    const settings = await getSettings();
    const headers = new Headers(init?.headers ?? {});
    if (!(init?.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (settings.token) {
      headers.set("Authorization", `Bearer ${settings.token}`);
    }
    const response = await fetch(`${settings.apiBaseUrl}${path}`, {
      ...init,
      headers
    });
    if (!response.ok) {
      throw new Error(`API request failed: ${response.status}`);
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
    getUsage() {
      return request("/me/usage").then((response) => response.json());
    },
    getMyTasks() {
      return request("/me/tasks").then((response) => response.json());
    },
    createParseTask(payload) {
      return request("/tasks/parse", {
        method: "POST",
        body: JSON.stringify(payload)
      }).then((response) => response.json());
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
      }).then((response) => response.json());
    },
    createTranslateTask(payload) {
      return request("/tasks/translate", {
        method: "POST",
        body: JSON.stringify(payload)
      }).then((response) => response.json());
    },
    getTask(taskId) {
      return request(`/tasks/${taskId}`).then((response) => response.json());
    },
    downloadArtifact(taskId, artifact) {
      return request(`/tasks/${taskId}/download/${artifact}`).then(async (response) => ({
        blob: await response.blob(),
        filename: extractFilename(response.headers.get("Content-Disposition"), `${artifact}.bin`),
        mediaType: response.headers.get("Content-Type") ?? "application/octet-stream"
      }));
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

// src/lib/runtime.ts
function createParseMessage(input, elsevierApiKey) {
  return {
    type: "mdtero.parse.request",
    input,
    elsevierApiKey
  };
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
function getSavedResultSummary(state, language = "en") {
  const filename = state?.translatedFilename ?? state?.parseFilename;
  if (!filename) {
    return "";
  }
  return language === "zh" ? `\u5DF2\u5C31\u7EEA\uFF1A${filename}` : `Ready: ${filename}`;
}

// src/popup/index.ts
var COPY = {
  en: {
    title: "Mdtero",
    subtitle: "Markdown-first paper workflow",
    guest: "Guest mode",
    signedIn: (email) => email,
    credits: (amount) => `Credits: ${amount}`,
    signInHint: "Sign in to unlock parse bundles and translation.",
    freeHint: "PDF/XML free",
    supportSummary: "One extension flow for publisher pages, preprints, and Markdown-ready outputs.",
    inputLabel: "DOI or supported page",
    inputPlaceholder: "10.1016/...",
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
    subtitle: "\u9762\u5411 Markdown \u7684\u8BBA\u6587\u5DE5\u4F5C\u6D41",
    guest: "\u6E38\u5BA2\u6A21\u5F0F",
    signedIn: (email) => email,
    credits: (amount) => `\u989D\u5EA6\uFF1A${amount}`,
    signInHint: "\u767B\u5F55\u540E\u53EF\u4F7F\u7528\u538B\u7F29\u5305\u89E3\u6790\u548C\u7FFB\u8BD1\u3002",
    freeHint: "PDF/XML \u514D\u8D39",
    supportSummary: "\u4E00\u4E2A\u6269\u5C55\u754C\u9762\uFF0C\u540C\u65F6\u8986\u76D6\u51FA\u7248\u793E\u9875\u9762\u3001\u9884\u5370\u672C\u4E0E Markdown \u5C31\u7EEA\u4EA7\u7269\u3002",
    inputLabel: "DOI \u6216\u5F53\u524D\u9875\u9762",
    inputPlaceholder: "10.1016/...",
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
var freeHintEl = document.querySelector("#free-hint");
var supportSummaryEl = document.querySelector("#support-summary");
var inputLabelEl = document.querySelector("#paper-input-label");
var inputEl = document.querySelector("#paper-input");
var statusEl = document.querySelector("#status");
var campusHintEl = document.querySelector("#campus-hint");
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
function getCurrentCopy() {
  return copyFor(uiLanguage);
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
    const objectUrl = URL.createObjectURL(artifact.blob);
    chrome.downloads.download({
      url: objectUrl,
      filename: artifact.filename,
      saveAs: true
    });
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
  if (inputLabelEl) inputLabelEl.textContent = copy.inputLabel;
  if (inputEl) inputEl.placeholder = copy.inputPlaceholder;
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
    translatedFilename: task.result.artifacts.translated_md?.filename ?? previous?.translatedFilename
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
    if (filename) {
      setResult(getCurrentCopy().parseReady(filename));
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
      usageStatusEl.textContent = getCurrentCopy().credits(usage.credit_balance);
    }
    if (accountEmailEl && usage.email) {
      accountEmailEl.textContent = getCurrentCopy().signedIn(usage.email);
    }
  } catch {
    if (usageStatusEl) {
      usageStatusEl.textContent = getCurrentCopy().signInHint;
    }
  }
}
async function detectCurrentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    setStatus(getCurrentCopy().noActiveTab);
    return;
  }
  try {
    setStatus(getActionStatusText("detecting", uiLanguage));
    const response = await chrome.tabs.sendMessage(tab.id, createDetectMessage());
    if (response?.detected?.value && inputEl) {
      inputEl.value = response.detected.value;
      currentInput = response.detected.value;
      setStatus(getCurrentCopy().detected(response.detected.kind));
      await hydrateSavedState(response.detected.value);
      return;
    }
  } catch {
  }
  setStatus(getCurrentCopy().noDoi);
}
async function initializeLanguage() {
  const settings = await readSettings();
  uiLanguage = resolveUiLanguage(settings.uiLanguage, globalThis.navigator?.language);
  applyLanguage();
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
  if (requiresElsevierLocalAcquire(input) && !settings.elsevierApiKey) {
    isParsing = false;
    renderActionButtons();
    setResult(getCurrentCopy().elsevierKeyRequired);
    setTimeout(() => {
      void chrome.runtime.openOptionsPage();
    }, 2e3);
    return;
  }
  const response = await chrome.runtime.sendMessage(createParseMessage(input, settings.elsevierApiKey));
  if (!response?.ok) {
    isParsing = false;
    renderActionButtons();
    setResult(response?.error ?? getCurrentCopy().parseFailed);
    return;
  }
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
  void pollTask(response.result.task_id, "translate");
});
openSettingsButton?.addEventListener("click", () => {
  void chrome.runtime.openOptionsPage();
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
  await renderRecentTasks();
  const savedState = await readPopupState();
  const summary = getSavedResultSummary(savedState, uiLanguage);
  if (summary) {
    setResult(summary);
  }
  if (!currentInput) {
    await detectCurrentTab();
  }
});
void (async () => {
  await initializeLanguage();
  await refreshUsage();
  await renderRecentTasks();
  renderActionButtons();
  await detectCurrentTab();
})();
//# sourceMappingURL=popup.js.map
