import type { TaskRecord } from "@mdtero/shared";

import { createApiClient } from "../lib/api";
import { createDetectMessage, createParseMessage, createTranslateMessage } from "../lib/runtime";
import {
  readPopupState,
  readRecentTasks,
  readSettings,
  resolveUiLanguage,
  upsertRecentTasks,
  writePopupState,
  writeRecentTasks,
  writeSettings,
  type RecentTaskSummary,
  type UiLanguage
} from "../lib/storage";
import {
  getActionStatusText,
  getDownloadLabel,
  getPreferredArtifactKey,
  getSavedResultSummary,
  getSecondaryArtifactKeys,
  getSourceArtifactKeys
} from "./task-view";

const COPY = {
  en: {
    title: "Mdtero",
    subtitle: "Markdown-first paper workflow",
    guest: "Guest mode",
    signedIn: (email: string) => email,
    credits: (amount: number) => `Credits: ${amount}`,
    signInHint: "Sign in to unlock parse bundles and translation.",
    freeHint: "PDF/XML free",
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
    sourceFiles: "Source files",
    recentTasks: "Recent items",
    noRecentTasks: "No recent papers yet.",
    openPaper: "Use DOI",
    enterDoi: "Enter a DOI first.",
    translateFirst: "Parse a paper successfully before translating.",
    parseReady: (filename: string) => `Ready: ${filename}`,
    translateReady: (filename: string) => `Ready: ${filename}`,
    parseFailed: "Parse failed. Please try again.",
    translationFailed: "Translation failed. Please try again.",
    detected: (kind: string) => `Detected ${kind}.`,
    noDoi: "No DOI detected. Paste one manually.",
    noActiveTab: "No active tab available.",
    downloadFailed: "Download failed. Please try again."
  },
  zh: {
    title: "Mdtero",
    subtitle: "面向 Markdown 的论文工作流",
    guest: "游客模式",
    signedIn: (email: string) => email,
    credits: (amount: number) => `额度：${amount}`,
    signInHint: "登录后可使用压缩包解析和翻译。",
    freeHint: "PDF/XML 免费",
    inputLabel: "DOI 或当前页面",
    inputPlaceholder: "10.1016/...",
    parseButton: "解析论文",
    parsingButton: "解析中...",
    settingsButton: "设置",
    translateLabel: "翻译为",
    translateButton: "翻译",
    translatingButton: "翻译中...",
    chinese: "中文",
    english: "英文",
    sourceFiles: "源文件",
    recentTasks: "最近处理",
    noRecentTasks: "还没有最近论文。",
    openPaper: "填入 DOI",
    enterDoi: "请先输入 DOI。",
    translateFirst: "请先成功解析论文，再进行翻译。",
    parseReady: (filename: string) => `已就绪：${filename}`,
    translateReady: (filename: string) => `已就绪：${filename}`,
    parseFailed: "解析失败，请重试。",
    translationFailed: "翻译失败，请重试。",
    detected: (kind: string) => `已识别${kind}。`,
    noDoi: "未识别到 DOI，请手动粘贴。",
    noActiveTab: "当前没有可用标签页。",
    downloadFailed: "下载失败，请重试。"
  }
} satisfies Record<UiLanguage, Record<string, string | ((...args: any[]) => string)>>;

const titleEl = document.querySelector<HTMLHeadingElement>("#app-title");
const subtitleEl = document.querySelector<HTMLParagraphElement>("#app-subtitle");
const languageToggleEl = document.querySelector<HTMLButtonElement>("#language-toggle");
const accountEmailEl = document.querySelector<HTMLParagraphElement>("#account-email");
const usageStatusEl = document.querySelector<HTMLParagraphElement>("#usage-status");
const freeHintEl = document.querySelector<HTMLParagraphElement>("#free-hint");
const inputLabelEl = document.querySelector<HTMLLabelElement>("#paper-input-label");
const inputEl = document.querySelector<HTMLInputElement>("#paper-input");
const statusEl = document.querySelector<HTMLParagraphElement>("#status");
const parseButton = document.querySelector<HTMLButtonElement>("#parse-button");
const openSettingsButton = document.querySelector<HTMLButtonElement>("#open-settings");
const translateLanguageLabelEl = document.querySelector<HTMLLabelElement>("#translate-language-label");
const translateButton = document.querySelector<HTMLButtonElement>("#translate-button");
const translateLanguageEl = document.querySelector<HTMLSelectElement>("#translate-language");
const resultEl = document.querySelector<HTMLParagraphElement>("#result");
const artifactActionsEl = document.querySelector<HTMLElement>("#artifact-actions");
const downloadButton = document.querySelector<HTMLButtonElement>("#download-link");
const secondaryDownloadsEl = document.querySelector<HTMLDivElement>("#secondary-downloads");
const sourceFilesEl = document.querySelector<HTMLDetailsElement>("#source-files");
const sourceFilesSummaryEl = document.querySelector<HTMLElement>("#source-files-summary");
const sourceDownloadsEl = document.querySelector<HTMLDivElement>("#source-downloads");
const recentTasksEl = document.querySelector<HTMLDetailsElement>("#recent-tasks");
const recentTasksSummaryEl = document.querySelector<HTMLElement>("#recent-tasks-summary");
const recentTaskListEl = document.querySelector<HTMLDivElement>("#recent-task-list");

const client = createApiClient(readSettings);
let lastParsedMarkdownPath: string | null = null;
let currentInput: string | null = null;
let uiLanguage: UiLanguage = "en";
let isParsing = false;
let isTranslating = false;

function copyFor(language: UiLanguage) {
  return COPY[language];
}

function setResult(message: string) {
  if (resultEl) {
    resultEl.textContent = message;
  }
}

function setStatus(message: string) {
  if (statusEl) {
    statusEl.textContent = message;
  }
}

function getCurrentCopy() {
  return copyFor(uiLanguage);
}

function toggleLanguageLabel(language: UiLanguage) {
  return language === "en" ? "中文" : "EN";
}

function stripArtifactSuffix(filename?: string): string {
  if (!filename) {
    return "paper";
  }
  return filename
    .replace(/\.zip$/i, "")
    .replace(/\.pdf$/i, "")
    .replace(/\.xml$/i, "")
    .replace(/\.(zh|en)\.md$/i, "")
    .replace(/\.md$/i, "");
}

function createRecentTaskSummary(state: Awaited<ReturnType<typeof readPopupState>>): RecentTaskSummary | null {
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

async function saveArtifact(taskId: string, artifactKey: string) {
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
  if (inputLabelEl) inputLabelEl.textContent = copy.inputLabel;
  if (inputEl) inputEl.placeholder = copy.inputPlaceholder;
  if (translateLanguageLabelEl) translateLanguageLabelEl.textContent = copy.translateLabel;
  if (sourceFilesSummaryEl) sourceFilesSummaryEl.textContent = copy.sourceFiles;
  if (recentTasksSummaryEl) recentTasksSummaryEl.textContent = copy.recentTasks;
  if (translateLanguageEl?.options[0]) translateLanguageEl.options[0].text = copy.chinese;
  if (translateLanguageEl?.options[1]) translateLanguageEl.options[1].text = copy.english;
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

function appendActionButton(container: HTMLDivElement | null, taskId: string, artifactKey: string) {
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

function renderArtifacts(task: TaskRecord) {
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

async function persistPopupState(task: TaskRecord) {
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
    translatedFilename:
      task.result.artifacts.translated_md?.filename ?? previous?.translatedFilename
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
        void saveArtifact(task.parseTaskId!, "paper_bundle");
      });
      actions.appendChild(zipButton);
    }

    if (task.translatedTaskId) {
      const translatedButton = document.createElement("button");
      translatedButton.type = "button";
      translatedButton.className = "secondary-button";
      translatedButton.textContent = getDownloadLabel("translated_md", uiLanguage);
      translatedButton.addEventListener("click", () => {
        void saveArtifact(task.translatedTaskId!, "translated_md");
      });
      actions.appendChild(translatedButton);
    }

    item.appendChild(actions);
    recentTaskListEl.appendChild(item);
  });
}

async function hydrateSavedState(detectedInput: string) {
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

async function pollTask(taskId: string, kind: "parse" | "translate") {
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

  const task = response.result as TaskRecord;
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
    accountEmailEl.textContent = settings.email
      ? getCurrentCopy().signedIn(settings.email)
      : getCurrentCopy().guest;
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
    // Ignore content-script detection failures and fall back to manual input.
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
