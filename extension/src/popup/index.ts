import type { TaskRecord } from "@mdtero/shared";

import { createApiClient } from "../lib/api";
import { MDTERO_ACCOUNT_URL } from "../lib/auth-bridge";
import { triggerBlobDownload } from "../lib/download";
import {
  createFileParseMessage,
  createDetectMessage,
  createSsotParseMessage,
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
  getArtifactFilename,
  getActionStatusText,
  getDownloadLabel,
  getPreflightHintText,
  getPreferredArtifactKey,
  getResultWarningText,
  getSavedResultSummary,
  getUsageStatusText,
  getTaskProcessingSummary,
  getTaskFailureText,
  buildCliHandoffCommandPlan,
  buildApiErrorCliHandoffPlan,
  buildApiErrorHandoffContext,
  buildTaskFailureCliHandoffPlan,
  buildTaskHandoffContext,
  formatCliHandoffClipboard,
  type CliHandoffContext,
  getDownloadFailureText,
  buildCliParseCommand,
  buildCliFileParseCommand,
  getCliHandoffNote,
  shouldShowCliHandoffForPreflight,
  getSecondaryArtifactKeys,
  getSourceArtifactKeys
} from "./task-view";

const COPY = {
  en: {
    title: "Mdtero",
    subtitle: "Paper parsing connected to Mdtero Account",
    guest: "Guest mode",
    signedIn: (email: string) => email,
    usageSummary: (wallet: string, parse: number, translation: number) =>
      `Balance ${wallet} · Parse ${parse} · Translation ${translation}`,
    signInHint: "Sign in through website OAuth at mdtero.com/auth, then return here to parse, translate, and download.",
    signInButton: "Open website OAuth",
    connectionPillSignedOut: "Website OAuth",
    connectionPillSignedIn: "Connected",
    workflowAuth: "Login",
    workflowParse: "Parse / Upload",
    workflowTranslate: "Translate",
    workflowDownload: "Download",
    workflowPending: "next",
    workflowActive: "active",
    workflowDone: "done",
    inputLabel: "DOI or live page",
    inputPlaceholder: "10.1016/...",
    fileIntakeTitle: "Local file intake",
    fileIntakeNote: "Use this when you already have a local PDF or EPUB. PDF uploads are parsed by the Mdtero backend automatically.",
    pickPdfButton: "Use PDF",
    pickEpubButton: "Use EPUB",
    fileNameEmpty: "No local file selected.",
    localFileParsing: (filename: string) => `Uploading ${filename}; Mdtero will create a parse task and poll it here...`,
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
    openPaper: "Reuse input",
    enterDoi: "Enter a DOI or use the detected paper page first.",
    translateFirst: "Parse a paper to Markdown first; translation uses that paper_md artifact path.",
    parseReady: (filename: string) => `Markdown ready: ${filename}. Download it or translate from the parsed Markdown.`,
    translateReady: (filename: string) => `Translation ready: ${filename}.`,
    parseFailed: "Parse failed. Please try again.",
    translationFailed: "Translation failed. Please try again.",
    detected: (kind: string) => `Detected ${kind}.`,
    noDoi: "No DOI detected. Paste one manually.",
    noActiveTab: "No active tab available.",
    downloadFailed: "Download failed. Please try again.",
    copyCliCommand: "Copy handoff",
    cliCommandCopied: "CLI handoff copied."
  },
  zh: {
    title: "Mdtero",
    subtitle: "连接 Mdtero 账户的本地论文解析",
    guest: "游客模式",
    signedIn: (email: string) => email,
    usageSummary: (wallet: string, parse: number, translation: number) =>
      `余额 ${wallet} · 解析 ${parse} · 翻译 ${translation}`,
    signInHint: "请通过 mdtero.com/auth 的网页登录授权扩展，然后回到这里解析、翻译和下载。",
    signInButton: "打开网页登录",
    connectionPillSignedOut: "网页登录",
    connectionPillSignedIn: "已连接",
    workflowAuth: "登录",
    workflowParse: "解析 / 上传",
    workflowTranslate: "翻译",
    workflowDownload: "下载",
    workflowPending: "下一步",
    workflowActive: "进行中",
    workflowDone: "完成",
    inputLabel: "DOI 或实时页面",
    inputPlaceholder: "10.1016/...",
    fileIntakeTitle: "本地文件入口",
    fileIntakeNote: "如果你手里已经有 PDF 或 EPUB，也可以继续走同一条 Markdown 解析链。PDF 会自动使用内置解析栈。",
    pickPdfButton: "选择 PDF",
    pickEpubButton: "选择 EPUB",
    fileNameEmpty: "尚未选择本地文件。",
    localFileParsing: (filename: string) => `正在上传 ${filename}，后端会创建解析任务并在这里轮询...`,
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
    enterDoi: "请先输入 DOI 或使用检测到的论文页面。",
    translateFirst: "请先成功解析论文，再进行翻译。",
    parseReady: (filename: string) => `Markdown 已就绪：${filename}。可以下载或基于该 Markdown 翻译。`,
    translateReady: (filename: string) => `译文已就绪：${filename}。`,
    parseFailed: "解析失败，请重试。",
    translationFailed: "翻译失败，请重试。",
    detected: (kind: string) => `已识别${kind}。`,
    noDoi: "未识别到 DOI，请手动粘贴。",
    noActiveTab: "当前没有可用标签页。",
    downloadFailed: "下载失败，请重试。",
    copyCliCommand: "复制交接信息",
    cliCommandCopied: "CLI 交接信息已复制。"
  }
} satisfies Record<UiLanguage, Record<string, string | ((...args: any[]) => string)>>;

const titleEl = document.querySelector<HTMLHeadingElement>("#app-title");
const subtitleEl = document.querySelector<HTMLParagraphElement>("#app-subtitle");
const languageToggleEl = document.querySelector<HTMLButtonElement>("#language-toggle");
const accountEmailEl = document.querySelector<HTMLParagraphElement>("#account-email");
const usageStatusEl = document.querySelector<HTMLParagraphElement>("#usage-status");
const connectionPillEl = document.querySelector<HTMLParagraphElement>("#connection-pill");
const workflowAuthEl = document.querySelector<HTMLSpanElement>("#workflow-auth");
const workflowParseEl = document.querySelector<HTMLSpanElement>("#workflow-parse");
const workflowTranslateEl = document.querySelector<HTMLSpanElement>("#workflow-translate");
const workflowDownloadEl = document.querySelector<HTMLSpanElement>("#workflow-download");
const inputLabelEl = document.querySelector<HTMLLabelElement>("#paper-input-label");
const inputEl = document.querySelector<HTMLInputElement>("#paper-input");
const statusEl = document.querySelector<HTMLParagraphElement>("#status");
const preflightHintEl = document.querySelector<HTMLParagraphElement>("#preflight-hint");
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
const taskSummaryEl = document.querySelector<HTMLDivElement>("#task-summary");
const taskSummaryListEl = document.querySelector<HTMLUListElement>("#task-summary-list");
const cliHandoffEl = document.querySelector<HTMLDivElement>("#cli-handoff");
const cliHandoffNoteEl = document.querySelector<HTMLParagraphElement>("#cli-handoff-note");
const cliHandoffCommandEl = document.querySelector<HTMLElement>("#cli-handoff-command");
const cliHandoffPlanEl = document.querySelector<HTMLOListElement>("#cli-handoff-plan");
const copyCliHandoffButton = document.querySelector<HTMLButtonElement>("#copy-cli-handoff");
const artifactActionsEl = document.querySelector<HTMLElement>("#artifact-actions");
const downloadButton = document.querySelector<HTMLButtonElement>("#download-link");
const secondaryDownloadsEl = document.querySelector<HTMLDivElement>("#secondary-downloads");
const sourceFilesEl = document.querySelector<HTMLDetailsElement>("#source-files");
const sourceFilesSummaryEl = document.querySelector<HTMLElement>("#source-files-summary");
const sourceDownloadsEl = document.querySelector<HTMLDivElement>("#source-downloads");
const recentTasksSummaryEl = document.querySelector<HTMLElement>("#recent-tasks-summary");
const recentTaskListEl = document.querySelector<HTMLDivElement>("#recent-task-list");

const client = createApiClient(readSettings);
type ParsedMarkdownSource = {
  path?: string | null;
  taskId?: string | null;
  artifactKey?: string | null;
  filename?: string | null;
};

let lastParsedMarkdownSource: ParsedMarkdownSource | null = null;
let currentInput: string | null = null;
let uiLanguage: UiLanguage = "en";
let isParsing = false;
let isTranslating = false;
let isSignedIn = false;
let hasParsedArtifact = false;
let hasTranslatedArtifact = false;
let hasDownloadableArtifact = false;
let detectedPageContext: { tabId: number; tabUrl?: string; detectedInput: string } | null = null;
let currentBridgeStatus: { state?: string | null; runnerState?: string | null } | null = null;
let currentCliHandoffCommands: string[] = [];
let currentCliHandoffContext: CliHandoffContext | null = null;

function copyFor(language: UiLanguage) {
  return COPY[language];
}

async function openMdteroAccount() {
  await chrome.tabs.create({ url: MDTERO_ACCOUNT_URL });
}

function setResult(message: string) {
  if (resultEl) {
    resultEl.textContent = message;
  }
}

function setTaskSummary(lines?: string[] | null) {
  if (!taskSummaryEl || !taskSummaryListEl) {
    return;
  }
  taskSummaryListEl.innerHTML = "";
  const visibleLines = (lines ?? []).map((line) => line.trim()).filter(Boolean).slice(0, 7);
  taskSummaryEl.hidden = visibleLines.length === 0;
  visibleLines.forEach((line) => {
    const item = document.createElement("li");
    item.textContent = line;
    taskSummaryListEl.appendChild(item);
  });
}

type WorkflowState = "pending" | "active" | "done";

function setWorkflowStep(element: HTMLSpanElement | null, state: WorkflowState) {
  if (!element) return;
  element.dataset.state = state;
  const copy = getCurrentCopy();
  const label = state === "done" ? copy.workflowDone : state === "active" ? copy.workflowActive : copy.workflowPending;
  element.setAttribute("aria-label", `${element.textContent || "Step"}: ${label}`);
}

function updateWorkflowState() {
  setWorkflowStep(workflowAuthEl, isSignedIn ? "done" : "active");
  setWorkflowStep(workflowParseEl, hasParsedArtifact ? "done" : isSignedIn ? "active" : "pending");
  setWorkflowStep(workflowTranslateEl, hasTranslatedArtifact ? "done" : isTranslating || hasParsedArtifact ? "active" : "pending");
  setWorkflowStep(workflowDownloadEl, hasDownloadableArtifact ? "done" : hasParsedArtifact || hasTranslatedArtifact ? "active" : "pending");
}

function setCliHandoff(
  input?: string | null,
  commandOverride?: string | null,
  planCommands?: string[] | null,
  context?: CliHandoffContext | null
) {
  const commands = normalizeHandoffCommands(planCommands);
  const command = String(commandOverride || commands[0] || "").trim() || buildCliParseCommand(input);
  const handoffCommands = command ? buildCliHandoffCommandPlan(command, commands) : [];
  if (!cliHandoffEl || !cliHandoffCommandEl || !copyCliHandoffButton || !cliHandoffNoteEl) {
    return;
  }
  cliHandoffEl.hidden = !command;
  cliHandoffNoteEl.textContent = getCliHandoffNote(command, uiLanguage);
  cliHandoffCommandEl.textContent = command;
  currentCliHandoffCommands = handoffCommands;
  currentCliHandoffContext = context ?? null;
  renderCliHandoffPlan(currentCliHandoffCommands);
  copyCliHandoffButton.textContent = getCurrentCopy().copyCliCommand;
}

function normalizeHandoffCommands(commands?: string[] | null): string[] {
  return Array.from(new Set((commands ?? []).map((value) => String(value || "").trim()).filter(Boolean)));
}

function renderCliHandoffPlan(commands: string[]) {
  if (!cliHandoffPlanEl) {
    return;
  }
  const unique = normalizeHandoffCommands(commands);
  cliHandoffPlanEl.innerHTML = "";
  cliHandoffPlanEl.hidden = unique.length <= 1;
  unique.slice(1).forEach((command) => {
    const item = document.createElement("li");
    item.textContent = command;
    cliHandoffPlanEl.appendChild(item);
  });
}

async function copyCliHandoff() {
  const command = cliHandoffCommandEl?.textContent?.trim();
  if (!command) {
    return;
  }
  await navigator.clipboard?.writeText(formatCliHandoffClipboard(command, currentCliHandoffCommands, currentCliHandoffContext));
  setResult(getCurrentCopy().cliCommandCopied);
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
  const hint = getPreflightHintText(
    {
      input,
      pageUrl,
      bridgeStatus: currentBridgeStatus,
    },
    uiLanguage
  );
  setPreflightHint(hint);
  if (shouldShowCliHandoffForPreflight(hint, input)) {
    setCliHandoff(input);
  } else if (!isParsing) {
    setCliHandoff(null);
  }
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
  } catch (error) {
    setResult(getDownloadFailureText(error, getCurrentCopy().downloadFailed, uiLanguage));
    const handoffPlan = buildApiErrorCliHandoffPlan(error, currentInput, "parse");
    if (handoffPlan.primaryCommand) {
      setCliHandoff(
        currentInput,
        handoffPlan.primaryCommand,
        handoffPlan.commands,
        buildApiErrorHandoffContext(error, "parse")
      );
    }
  }
}

function applyLanguage() {
  const copy = getCurrentCopy();
  document.documentElement.lang = uiLanguage === "zh" ? "zh-CN" : "en";
  if (titleEl) titleEl.textContent = copy.title;
  if (subtitleEl) subtitleEl.textContent = copy.subtitle;
  if (languageToggleEl) languageToggleEl.textContent = toggleLanguageLabel(uiLanguage);
  if (workflowAuthEl) workflowAuthEl.textContent = copy.workflowAuth;
  if (workflowParseEl) workflowParseEl.textContent = copy.workflowParse;
  if (workflowTranslateEl) workflowTranslateEl.textContent = copy.workflowTranslate;
  if (workflowDownloadEl) workflowDownloadEl.textContent = copy.workflowDownload;
  if (inputLabelEl) inputLabelEl.textContent = copy.inputLabel;
  if (inputEl) inputEl.placeholder = copy.inputPlaceholder;
  if (fileIntakeTitleEl) fileIntakeTitleEl.textContent = copy.fileIntakeTitle;
  if (fileIntakeNoteEl) fileIntakeNoteEl.textContent = copy.fileIntakeNote;
  if (pickPdfButton) pickPdfButton.textContent = copy.pickPdfButton;
  if (pickEpubButton) pickEpubButton.textContent = copy.pickEpubButton;
  if (localFileNameEl && !localFileNameEl.dataset.selectedName) {
    localFileNameEl.textContent = copy.fileNameEmpty;
  }
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
  if (copyCliHandoffButton) copyCliHandoffButton.textContent = copy.copyCliCommand;
  updateWorkflowState();
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
    translateButton.disabled = isTranslating || !hasParsedMarkdownSource(lastParsedMarkdownSource);
  }
}

function hasParsedMarkdownSource(source?: ParsedMarkdownSource | null): boolean {
  return Boolean(source?.path || (source?.taskId && source?.artifactKey));
}

function parsedMarkdownRef(source?: ParsedMarkdownSource | null): string {
  return String(source?.path || source?.taskId || "").trim();
}

function getArtifactDescriptor(result: TaskRecord["result"], artifactKey: string) {
  return result?.artifacts?.[artifactKey]
    ?? result?.download_artifacts?.find((artifact) => artifact.artifact === artifactKey);
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
  if (!preferredKey) {
    if (artifactActionsEl) artifactActionsEl.hidden = true;
    return;
  }

  hasDownloadableArtifact = true;
  if (preferredKey === "translated_md") {
    hasTranslatedArtifact = true;
  } else {
    hasParsedArtifact = true;
  }
  updateWorkflowState();

  if (artifactActionsEl) artifactActionsEl.hidden = false;
  if (downloadButton) {
    downloadButton.hidden = false;
    downloadButton.textContent = getDownloadLabel(preferredKey, uiLanguage);
    downloadButton.onclick = () => {
      void saveArtifact(task.task_id, preferredKey, getArtifactFilename(task.result, preferredKey));
    };
  }

  getSecondaryArtifactKeys(task.result).forEach((artifactKey) => {
    appendActionButton(
      secondaryDownloadsEl,
      task.task_id,
      artifactKey,
      getArtifactFilename(task.result, artifactKey)
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
        getArtifactFilename(task.result, artifactKey)
      );
    });
  }
}

async function persistPopupState(task: TaskRecord) {
  if (!currentInput || !task.result) {
    return;
  }

  const previous = await readPopupState();
  const preferredParseArtifact =
    task.result.preferred_artifact === "paper_bundle" ? "paper_bundle" : "paper_md";
  const preferredParseDescriptor = getArtifactDescriptor(task.result, preferredParseArtifact);
  const paperMarkdownDescriptor = getArtifactDescriptor(task.result, "paper_md");
  const translatedDescriptor = getArtifactDescriptor(task.result, "translated_md");
  const nextState = {
    input: currentInput,
    parseTaskId: preferredParseDescriptor ? task.task_id : previous?.parseTaskId,
    parseArtifactKey: preferredParseDescriptor ? preferredParseArtifact : previous?.parseArtifactKey,
    parseFilename: preferredParseDescriptor?.filename ?? previous?.parseFilename,
    parseMarkdownTaskId: paperMarkdownDescriptor ? task.task_id : previous?.parseMarkdownTaskId,
    parseMarkdownArtifactKey: paperMarkdownDescriptor ? "paper_md" : previous?.parseMarkdownArtifactKey,
    parseMarkdownFilename: paperMarkdownDescriptor?.filename ?? previous?.parseMarkdownFilename,
    parseMarkdownPath: task.result.artifacts?.paper_md?.path ?? previous?.parseMarkdownPath,
    translatedTaskId: translatedDescriptor ? task.task_id : previous?.translatedTaskId,
    translatedFilename:
      translatedDescriptor?.filename ?? previous?.translatedFilename,
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
  lastParsedMarkdownSource = {
    path: savedState.parseMarkdownPath,
    taskId: savedState.parseMarkdownTaskId,
    artifactKey: savedState.parseMarkdownArtifactKey,
    filename: savedState.parseMarkdownFilename
  };
  hasParsedArtifact = Boolean(savedState.parseTaskId || hasParsedMarkdownSource(lastParsedMarkdownSource));
  hasTranslatedArtifact = Boolean(savedState.translatedTaskId || savedState.translatedFilename);
  hasDownloadableArtifact = hasParsedArtifact || hasTranslatedArtifact;
  updateWorkflowState();
  renderActionButtons();
}

async function pollTask(taskId: string, kind: "parse" | "translate") {
  const response = await chrome.runtime.sendMessage({
    type: "mdtero.task.get",
    taskId
  });
  if (!response?.ok) {
    setResult(response?.error ?? getCurrentCopy().parseFailed);
    if (kind === "parse") {
      setCliHandoff(currentInput);
    }
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
    updateWorkflowState();
    return;
  }

  const task = response.result as TaskRecord;
  if (task.status === "failed") {
    setTaskSummary(getTaskProcessingSummary(task, uiLanguage));
    setResult(
      getTaskFailureText(
        task,
        kind === "parse" ? getCurrentCopy().parseFailed : getCurrentCopy().translationFailed,
        uiLanguage
      )
    );
    const failureHandoffPlan = buildTaskFailureCliHandoffPlan(task, currentInput, kind);
    if (failureHandoffPlan.primaryCommand) {
      setCliHandoff(
        currentInput,
        failureHandoffPlan.primaryCommand,
        failureHandoffPlan.commands,
        buildTaskHandoffContext(task, kind)
      );
    } else {
      setCliHandoff(null);
    }
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
    updateWorkflowState();
    return;
  }

  if (task.status !== "succeeded") {
    setResult(
      getActionStatusText(kind === "parse" ? "running_parse" : "running_translate", uiLanguage)
    );
    setTaskSummary(getTaskProcessingSummary(task, uiLanguage));
    window.setTimeout(() => {
      void pollTask(taskId, kind);
    }, 1500);
    updateWorkflowState();
    return;
  }

  const paperMarkdownDescriptor = getArtifactDescriptor(task.result, "paper_md");
  if (paperMarkdownDescriptor) {
    lastParsedMarkdownSource = {
      path: task.result?.artifacts?.paper_md?.path ?? lastParsedMarkdownSource?.path,
      taskId: task.task_id,
      artifactKey: "paper_md",
      filename: paperMarkdownDescriptor.filename
    };
  }
  setCliHandoff(null);
  setTaskSummary(getTaskProcessingSummary(task, uiLanguage));
  renderArtifacts(task);
  await persistPopupState(task);
  await renderRecentTasks();

  if (kind === "parse") {
    isParsing = false;
    hasParsedArtifact = true;
    hasDownloadableArtifact = true;
    const preferredArtifactKey = getPreferredArtifactKey(task.result);
    const filename = preferredArtifactKey
      ? getArtifactDescriptor(task.result, preferredArtifactKey)?.filename
      : undefined;
    const warningText = getResultWarningText(task.result, uiLanguage);
    if (filename) {
      setResult([getCurrentCopy().parseReady(filename), warningText].filter(Boolean).join(" "));
    } else if (warningText) {
      setResult(warningText);
    }
  } else {
    isTranslating = false;
    hasTranslatedArtifact = true;
    hasDownloadableArtifact = true;
    const filename = getArtifactDescriptor(task.result, "translated_md")?.filename;
    if (filename) {
      setResult(getCurrentCopy().translateReady(filename));
    }
  }
  renderActionButtons();
  updateWorkflowState();
}

async function refreshUsage() {
  const settings = await readSettings();
  isSignedIn = Boolean(settings.token);
  if (connectionPillEl) {
    connectionPillEl.textContent = settings.token
      ? getCurrentCopy().connectionPillSignedIn
      : getCurrentCopy().connectionPillSignedOut;
  }
  if (accountEmailEl) {
    accountEmailEl.textContent = settings.email
      ? getCurrentCopy().signedIn(settings.email)
      : getCurrentCopy().guest;
  }

  if (!settings.token) {
    if (usageStatusEl) {
      usageStatusEl.textContent = getCurrentCopy().signInHint;
    }
    updateWorkflowState();
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
  updateWorkflowState();
}

async function refreshBridgeStatus() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    currentBridgeStatus = { state: "unavailable", runnerState: "idle" };
    await updatePreflightHint();
    return;
  }

  try {
    await chrome.tabs.sendMessage(tab.id, createDetectMessage());
    currentBridgeStatus = { state: "connected", runnerState: "idle" };
  } catch {
    currentBridgeStatus = { state: "unavailable", runnerState: "idle" };
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
  setTaskSummary(null);
  setLocalFileName(file.name);
  isParsing = true;
  updateWorkflowState();
  renderActionButtons();
  setResult(getCurrentCopy().localFileParsing(file.name));

  const settings = await readSettings();
  if (!settings.token) {
    isParsing = false;
    updateWorkflowState();
    renderActionButtons();
    setResult(getCurrentCopy().signInHint);
    await openMdteroAccount();
    return;
  }

  const response = await chrome.runtime.sendMessage(createFileParseMessage(file, artifactKind));

  if (!response?.ok) {
    isParsing = false;
    updateWorkflowState();
    renderActionButtons();
    setResult(response?.error ?? getCurrentCopy().localFileParseFailed);
    setCliHandoff(file.name, buildCliFileParseCommand(file.name, artifactKind));
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
  setTaskSummary(null);
  isParsing = true;
  updateWorkflowState();
  renderActionButtons();
  setResult(getActionStatusText("queued_parse", uiLanguage));

  const settings = await readSettings();
  if (!settings.token) {
    isParsing = false;
    updateWorkflowState();
    renderActionButtons();
    setResult(getCurrentCopy().signInHint);
    await openMdteroAccount();
    return;
  }
  const pageContext = await resolveParsePageContext(input);
  const response = await chrome.runtime.sendMessage(
    createSsotParseMessage(input, pageContext)
  );
  if (!response?.ok) {
    isParsing = false;
    updateWorkflowState();
    renderActionButtons();
    setResult(response?.error ?? getCurrentCopy().parseFailed);
    setCliHandoff(input, response?.nextCommand);
    return;
  }

  setCliHandoff(null);

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
  if (!hasParsedMarkdownSource(lastParsedMarkdownSource)) {
    setResult(getCurrentCopy().translateFirst);
    return;
  }

  const previous = await readPopupState();
  const markdownRef = parsedMarkdownRef(lastParsedMarkdownSource);
  const reconnectableTask = getReconnectablePendingTranslationTask(
    previous,
    currentInput ?? "",
    markdownRef
  );
  if (reconnectableTask) {
    isTranslating = true;
    updateWorkflowState();
    renderActionButtons();
    setResult(getActionStatusText("running_translate", uiLanguage));
    void pollTask(reconnectableTask.taskId, "translate");
    return;
  }

  isTranslating = true;
  updateWorkflowState();
  renderActionButtons();
  setResult(getActionStatusText("queued_translate", uiLanguage));
  const response = await chrome.runtime.sendMessage(
    createTranslateMessage(
      lastParsedMarkdownSource ?? {},
      translateLanguageEl?.value ?? "zh",
      "standard"
    )
  );
  if (!response?.ok) {
    isTranslating = false;
    updateWorkflowState();
    renderActionButtons();
    setResult(response?.error ?? getCurrentCopy().translationFailed);
    return;
  }

  await writePopupState({
    ...(await readPopupState()),
    input: currentInput ?? "",
    parseMarkdownPath: lastParsedMarkdownSource?.path || undefined,
    parseMarkdownTaskId: lastParsedMarkdownSource?.taskId || undefined,
    parseMarkdownArtifactKey: lastParsedMarkdownSource?.artifactKey || undefined,
    parseMarkdownFilename: lastParsedMarkdownSource?.filename || undefined,
    pendingTaskId: response.result.task_id,
    pendingTaskKind: "translate"
  });

  void pollTask(response.result.task_id, "translate");
});

openSettingsButton?.addEventListener("click", () => {
  void chrome.runtime.openOptionsPage();
});

openSettingsLoginButton?.addEventListener("click", () => {
  void openMdteroAccount();
});

copyCliHandoffButton?.addEventListener("click", () => {
  void copyCliHandoff();
});

inputEl?.addEventListener("input", () => {
  currentInput = inputEl.value.trim() || currentInput;
  setCliHandoff(null);
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
