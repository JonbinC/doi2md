import type { TaskRecord } from "@mdtero/shared";

import { createApiClient } from "../lib/api";
import { triggerBlobDownload } from "../lib/download";
import { requiresElsevierLocalAcquire } from "../lib/elsevier";
import {
  createFileParseMessage,
  createDetectMessage,
  createParseMessage,
  createTranslateMessage,
  type LocalFileArtifactKind,
  type ParsePageContext
} from "../lib/runtime";
import {
  getReconnectablePendingTranslationTask,
  getPendingPopupTask,
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
  getBridgeStatusText,
  getDownloadLabel,
  getPreflightHintText,
  getPreferredArtifactKey,
  getResultWarningText,
  getSavedResultSummary,
  getUsageStatusText,
  getSecondaryArtifactKeys,
  getSourceArtifactKeys
} from "./task-view";

const COPY = {
  en: {
    title: "Mdtero",
    subtitle: "Parse papers from this computer",
    guest: "Guest mode",
    signedIn: (email: string) => email,
    usageSummary: (wallet: string, parse: number, translation: number) =>
      `Balance ${wallet} · Parse ${parse} · Translation ${translation}`,
    signInHint: "Sign in in Mdtero Account to unlock Markdown downloads, translation, and task history.",
    signInButton: "Sign in",
    freeHint: "PDF/XML free",
    supportSummary: "Keep the paper page or local file on this machine, then let Mdtero turn it into Markdown you can keep using. Prefer direct publisher APIs and TDM routes first, then fall back locally when needed.",
    supportStableTitle: "Ready on this machine",
    supportStableItems: "arXiv, PMC / Europe PMC, bioRxiv / medRxiv, PLOS, Springer Open Access, and other open sources work best.",
    supportShadowTitle: "Use your own access",
    supportShadowItems: "Publisher pages such as Elsevier and Springer work best when you can already open the full text yourself on this computer.",
    supportExperimentalTitle: "Needs browser help sometimes",
    supportExperimentalItems: "Some Wiley and Taylor & Francis pages still vary more by login and challenge flow.",
    inputLabel: "DOI or live page",
    inputPlaceholder: "10.1016/...",
    fileIntakeTitle: "Local file intake",
    fileIntakeNote: "Use this when you already have a local PDF or EPUB. PDF now uses the built-in parser stack automatically.",
    pickPdfButton: "Use PDF",
    pickEpubButton: "Use EPUB",
    fileNameEmpty: "No local file selected.",
    localFileParsing: (filename: string) => `Uploading ${filename} for on-device parsing...`,
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
    parseReady: (filename: string) => `Ready: ${filename}`,
    translateReady: (filename: string) => `Ready: ${filename}`,
    parseFailed: "Parse failed. Please try again.",
    translationFailed: "Translation failed. Please try again.",
    detected: (kind: string) => `Detected ${kind}.`,
    noDoi: "No DOI detected. Paste one manually.",
    noActiveTab: "No active tab available.",
    downloadFailed: "Download failed. Please try again.",
    campusHint: "Note: Campus network IP required for non-open access full-text.",
    elsevierKeyRequired: "ScienceDirect link detected. Please configure Elsevier API Key in settings first."
  },
  zh: {
    title: "Mdtero",
    subtitle: "在这台机器上处理论文",
    guest: "游客模式",
    signedIn: (email: string) => email,
    usageSummary: (wallet: string, parse: number, translation: number) =>
      `余额 ${wallet} · 解析 ${parse} · 翻译 ${translation}`,
    signInHint: "先去 Mdtero Account 登录，之后才能使用 Markdown 下载、翻译和任务历史。",
    signInButton: "去登录",
    freeHint: "PDF/XML 免费",
    supportSummary: "把论文页或本地文件留在这台机器上，再让 Mdtero 把它整理成可继续使用的 Markdown。优先走 publisher API / TDM，必要时再本地回退。",
    supportStableTitle: "这台机器上已经比较顺手",
    supportStableItems: "arXiv、PMC / Europe PMC、bioRxiv / medRxiv、PLOS、Springer Open Access 等开放来源最顺手。",
    supportShadowTitle: "使用你自己的访问权限",
    supportShadowItems: "Elsevier、Springer 等出版社页面，在你已经能在这台机器上打开全文时通常效果最好。",
    supportExperimentalTitle: "有时需要浏览器帮一把",
    supportExperimentalItems: "部分 Wiley 与 Taylor & Francis 页面仍更容易受登录态或挑战页影响。",
    inputLabel: "DOI 或实时页面",
    inputPlaceholder: "10.1016/...",
    fileIntakeTitle: "本地文件入口",
    fileIntakeNote: "如果你手里已经有 PDF 或 EPUB，也可以继续走同一条 Markdown 解析链。PDF 会自动使用内置解析栈。",
    pickPdfButton: "选择 PDF",
    pickEpubButton: "选择 EPUB",
    fileNameEmpty: "尚未选择本地文件。",
    localFileParsing: (filename: string) => `正在上传 ${filename}，并走本机解析链路...`,
    localFileParseFailed: "本地文件解析失败，请重试。",
    parseButton: "解析论文",
    parsingButton: "解析中...",
    settingsButton: "设置",
    translateLabel: "翻译为",
    translateButton: "翻译",
    translatingButton: "翻译中...",
    chinese: "中文",
    english: "英文",
    spanish: "西班牙文",
    french: "法文",
    german: "德文",
    japanese: "日文",
    korean: "韩文",
    russian: "俄文",
    turkish: "土耳其文",
    arabic: "阿拉伯文",
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
    downloadFailed: "下载失败，请重试。",
    campusHint: "提示：需要校园网或机构 IP 才能获取非开源全文，否则仅解析摘要。",
    elsevierKeyRequired: "检测到 ScienceDirect 链接，请先在设置中配置 Elsevier API Key。"
  }
} satisfies Record<UiLanguage, Record<string, string | ((...args: any[]) => string)>>;

const titleEl = document.querySelector<HTMLHeadingElement>("#app-title");
const subtitleEl = document.querySelector<HTMLParagraphElement>("#app-subtitle");
const languageToggleEl = document.querySelector<HTMLButtonElement>("#language-toggle");
const accountEmailEl = document.querySelector<HTMLParagraphElement>("#account-email");
const usageStatusEl = document.querySelector<HTMLParagraphElement>("#usage-status");
const helperStatusEl = document.querySelector<HTMLParagraphElement>("#helper-status");
const freeHintEl = document.querySelector<HTMLParagraphElement>("#free-hint");
const supportSummaryEl = document.querySelector<HTMLParagraphElement>("#support-summary");
const supportStableTitleEl = document.querySelector<HTMLParagraphElement>("#support-stable-title");
const supportStableItemsEl = document.querySelector<HTMLParagraphElement>("#support-stable-items");
const supportShadowTitleEl = document.querySelector<HTMLParagraphElement>("#support-shadow-title");
const supportShadowItemsEl = document.querySelector<HTMLParagraphElement>("#support-shadow-items");
const supportExperimentalTitleEl = document.querySelector<HTMLParagraphElement>("#support-experimental-title");
const supportExperimentalItemsEl = document.querySelector<HTMLParagraphElement>("#support-experimental-items");
const inputLabelEl = document.querySelector<HTMLLabelElement>("#paper-input-label");
const inputEl = document.querySelector<HTMLInputElement>("#paper-input");
const statusEl = document.querySelector<HTMLParagraphElement>("#status");
const preflightHintEl = document.querySelector<HTMLParagraphElement>("#preflight-hint");
const campusHintEl = document.querySelector<HTMLParagraphElement>("#campus-hint");
const fileIntakeTitleEl = document.querySelector<HTMLParagraphElement>("#file-intake-title");
const fileIntakeNoteEl = document.querySelector<HTMLParagraphElement>("#file-intake-note");
const pickPdfButton = document.querySelector<HTMLButtonElement>("#pick-pdf-button");
const pickEpubButton = document.querySelector<HTMLButtonElement>("#pick-epub-button");
const localFileInputEl = document.querySelector<HTMLInputElement>("#local-file-input");
const localFileNameEl = document.querySelector<HTMLParagraphElement>("#local-file-name");
const parseButton = document.querySelector<HTMLButtonElement>("#parse-button");
const openSettingsButton = document.querySelector<HTMLButtonElement>("#open-settings");
const openSettingsLoginButton = document.querySelector<HTMLButtonElement>("#open-settings-login");
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
let detectedPageContext: { tabId: number; tabUrl?: string; detectedInput: string } | null = null;
let currentBridgeStatus: { state?: string | null; runnerState?: string | null } | null = null;

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

function setPreflightHint(message: string) {
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
    parseArtifactKey: state.parseArtifactKey,
    parseFilename: state.parseFilename,
    translatedTaskId: state.translatedTaskId,
    translatedFilename: state.translatedFilename
  };
}

async function saveArtifact(taskId: string, artifactKey: string, preferredFilename?: string) {
  try {
    const artifact = await client.downloadArtifact(taskId, artifactKey, preferredFilename);
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
          case "zh": option.text = copy.chinese; break;
          case "en": option.text = copy.english; break;
          case "es": option.text = copy.spanish; break;
          case "fr": option.text = copy.french; break;
          case "de": option.text = copy.german; break;
          case "ja": option.text = copy.japanese; break;
          case "ko": option.text = copy.korean; break;
          case "ru": option.text = copy.russian; break;
          case "tr": option.text = copy.turkish; break;
          case "ar": option.text = copy.arabic; break;
        }
      }
    }
  }
  if (openSettingsButton) openSettingsButton.textContent = copy.settingsButton;
  if (openSettingsLoginButton) openSettingsLoginButton.textContent = copy.signInButton;
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

function appendActionButton(
  container: HTMLDivElement | null,
  taskId: string,
  artifactKey: string,
  preferredFilename?: string
) {
  if (!container) {
    return;
  }
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = getDownloadLabel(artifactKey, uiLanguage);
  button.addEventListener("click", () => {
    void saveArtifact(taskId, artifactKey, preferredFilename);
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
      void saveArtifact(task.task_id, preferredKey, task.result?.artifacts?.[preferredKey]?.filename);
    };
  }

  getSecondaryArtifactKeys(task.result).forEach((artifactKey) => {
    appendActionButton(
      secondaryDownloadsEl,
      task.task_id,
      artifactKey,
      task.result?.artifacts?.[artifactKey]?.filename
    );
  });

  const sourceArtifactKeys = getSourceArtifactKeys(task.result);
  if (sourceArtifactKeys.length > 0) {
    if (sourceFilesEl) {
      sourceFilesEl.hidden = false;
    }
    sourceArtifactKeys.forEach((artifactKey) => {
      appendActionButton(
        sourceDownloadsEl,
        task.task_id,
        artifactKey,
        task.result?.artifacts?.[artifactKey]?.filename
      );
    });
  }
}

async function persistPopupState(task: TaskRecord) {
  if (!currentInput || !task.result?.artifacts) {
    return;
  }

  const previous = await readPopupState();
  const preferredParseArtifact =
    task.result.preferred_artifact === "paper_bundle" ? "paper_bundle" : "paper_md";
  const preferredParseDescriptor = task.result.artifacts[preferredParseArtifact];
  const nextState = {
    input: currentInput,
    parseTaskId: preferredParseDescriptor ? task.task_id : previous?.parseTaskId,
    parseArtifactKey: preferredParseDescriptor ? preferredParseArtifact : previous?.parseArtifactKey,
    parseFilename: preferredParseDescriptor?.filename ?? previous?.parseFilename,
    parseMarkdownPath: task.result.artifacts.paper_md?.path ?? previous?.parseMarkdownPath,
    translatedTaskId: task.result.artifacts.translated_md ? task.task_id : previous?.translatedTaskId,
    translatedFilename:
      task.result.artifacts.translated_md?.filename ?? previous?.translatedFilename,
    pendingTaskId: undefined,
    pendingTaskKind: undefined
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

    if (task.parseTaskId && task.parseArtifactKey) {
      const parseButton = document.createElement("button");
      parseButton.type = "button";
      parseButton.className = "secondary-button";
      parseButton.textContent = getDownloadLabel(task.parseArtifactKey, uiLanguage);
      parseButton.addEventListener("click", () => {
        void saveArtifact(task.parseTaskId!, task.parseArtifactKey!, task.parseFilename);
      });
      actions.appendChild(parseButton);
    }

    if (task.translatedTaskId) {
      const translatedButton = document.createElement("button");
      translatedButton.type = "button";
      translatedButton.className = "secondary-button";
      translatedButton.textContent = getDownloadLabel("translated_md", uiLanguage);
      translatedButton.addEventListener("click", () => {
        void saveArtifact(task.translatedTaskId!, "translated_md", task.translatedFilename);
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

async function pollTask(taskId: string, kind: "parse" | "translate") {
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
        ...(previous ?? { input: currentInput }),
        input: currentInput,
        pendingTaskId: undefined,
        pendingTaskKind: undefined
      });
    }
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
    if (currentInput) {
      const previous = await readPopupState();
      await writePopupState({
        ...(previous ?? { input: currentInput }),
        input: currentInput,
        pendingTaskId: undefined,
        pendingTaskKind: undefined
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
    const preferredArtifactKey = getPreferredArtifactKey(task.result);
    const filename = preferredArtifactKey
      ? task.result?.artifacts?.[preferredArtifactKey]?.filename
      : undefined;
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
      usageStatusEl.textContent = getUsageStatusText(usage, uiLanguage);
    }
    if (accountEmailEl && usage.email) {
      accountEmailEl.textContent = getCurrentCopy().signedIn(usage.email);
    }
  } catch (error) {
    if (usageStatusEl) {
      usageStatusEl.textContent = getUsageStatusText(null, uiLanguage, (error as Error).message);
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
    helperStatusEl.textContent = getBridgeStatusText(undefined, uiLanguage);
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
    // Ignore content-script detection failures and fall back to manual input.
  }
  detectedPageContext = null;
  setStatus(getCurrentCopy().noDoi);
  await updatePreflightHint();
}

async function resolveParsePageContext(input: string): Promise<ParsePageContext | undefined> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    return undefined;
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

  return undefined;
}

async function initializeLanguage() {
  const settings = await readSettings();
  uiLanguage = resolveUiLanguage(settings.uiLanguage, globalThis.navigator?.language);
  applyLanguage();
}

function setLocalFileName(filename?: string) {
  if (!localFileNameEl) {
    return;
  }
  const trimmed = String(filename || "").trim();
  localFileNameEl.dataset.selectedName = trimmed;
  localFileNameEl.textContent = trimmed || getCurrentCopy().fileNameEmpty;
}

async function submitLocalFile(file: File, artifactKind: LocalFileArtifactKind) {
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

  const response = await chrome.runtime.sendMessage(createFileParseMessage(file, artifactKind));

  if (!response?.ok) {
    isParsing = false;
    renderActionButtons();
    setResult(response?.error ?? getCurrentCopy().localFileParseFailed);
    return;
  }

  await writePopupState({
    ...(await readPopupState()),
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
    setResult(getCurrentCopy().elsevierKeyRequired as string);
    setTimeout(() => {
      void chrome.runtime.openOptionsPage();
    }, 2000);
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
    ...(await readPopupState()),
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
    ...(await readPopupState()),
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

openSettingsLoginButton?.addEventListener("click", () => {
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
