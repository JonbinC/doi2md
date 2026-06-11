import type { TaskRecord } from "@mdtero/shared";

import { createApiClient } from "../lib/api";
import { MDTERO_ACCOUNT_URL } from "../lib/auth-bridge";
import { triggerBlobDownload } from "../lib/download";
import {
  mergeSettings,
  readSettings,
  resolveUiLanguage,
  writeSettings,
  type UiLanguage
} from "../lib/storage";

const COPY = {
  en: {
    title: "Mdtero Extension",
    subtitle: "Sign in, check quota, and configure browser-side paper capture.",
    permissionsTitle: "Why Mdtero asks for these permissions",
    permissionsTabs: "`tabs` lets the extension read the current paper page and open website OAuth when you sign in.",
    permissionsDownloads: "`downloads` saves Markdown files, translations, ZIP bundles, and uploaded-source results back to your machine.",
    permissionsCapture: "Browser capture reuses the active tab only when you ask Mdtero to parse the current paper page.",
    permissionsHosts: "Host permissions stay limited to Mdtero Auth, supported scholarly pages, and files you choose to upload.",
    notSignedIn: "Not signed in with website OAuth.",
    usagePending: "Balance and quota appear after sign-in.",
    signedIn: (email: string) => `Signed in as ${email}`,
    usageSummary: (wallet: string, parse: number, translation: number) =>
      `Balance ${wallet} · Parse ${parse} · Translation ${translation}`,
    openAccount: "Open website OAuth",
    websiteAuthTitle: "Website sign-in",
    websiteAuthNote: "The extension opens mdtero.com/auth for OAuth sign-in. Complete login on the website, and the trusted auth bridge will hand the token back to this extension.",
    guideTitle: "Connection guide",
    setupStepAuth: "OAuth",
    setupStepParse: "Parse / Upload",
    setupStepTranslate: "Translate",
    setupStepDownload: "Download",
    guideSignedOut: [
      "Open website OAuth and complete sign-in at mdtero.com/auth.",
      "Return to this popup after the trusted auth bridge connects your account.",
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
    elsevierSettingsTitle: "Elsevier access",
    elsevierSettingsNote: "Add your own Elsevier API key to let the extension fetch Article Retrieval XML directly from supported ScienceDirect pages.",
    elsevierConfigured: "Configured",
    elsevierNotConfigured: "Not configured",
    elsevierKeyVisible: "Hide",
    elsevierKeyHidden: "Show",
    elsevierKeySaved: "Elsevier key saved in this browser.",
    elsevierKeyCleared: "Elsevier key cleared.",
    clearElsevierKey: "Clear key",
    elsevierApiKey: "Elsevier API key",
    elsevierApiKeyPlaceholder: "Paste your Elsevier API key",
    elsevierApiKeyNote: "Stored only in this browser. Used for Elsevier XML capture before backend fallback.",
    save: "Save settings",
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
      paper_epub: "EPUB",
      paper_html: "HTML",
      paper_xml: "XML"
    },
    historyRefresh: "Refresh",
    historyRefreshing: "Refreshing..."
  },
  zh: {
    title: "Mdtero 扩展",
    subtitle: "使用网页登录授权扩展，并管理浏览器抓取、上传、翻译和下载设置。",
    permissionsTitle: "为什么 Mdtero 需要这些权限",
    permissionsTabs: "`tabs` 用来读取当前论文页，并在登录时打开网页登录页。",
    permissionsDownloads: "`downloads` 用来把 Markdown、译文、ZIP 包和上传文件的解析结果保存回你的电脑。",
    permissionsCapture: "浏览器补抓取只会在你主动解析当前论文页时复用当前标签页。",
    permissionsHosts: "站点权限只覆盖 Mdtero 登录页、受支持的学术页面，以及你主动选择上传的文件。",
    notSignedIn: "尚未通过网页登录授权扩展。",
    usagePending: "请在 mdtero.com/auth 登录以同步余额、额度和历史。",
    signedIn: (email: string) => `已登录：${email}`,
    usageSummary: (wallet: string, parse: number, translation: number) =>
      `余额 ${wallet} · 解析 ${parse} · 翻译 ${translation}`,
    openAccount: "打开网页登录",
    websiteAuthTitle: "官网登录",
    websiteAuthNote: "扩展统一打开 mdtero.com/auth 登录。请在官网完成登录，受信任 auth bridge 会把 token 交回扩展。",
    guideTitle: "连接引导",
    setupStepAuth: "网页登录",
    setupStepParse: "解析 / 上传",
    setupStepTranslate: "翻译",
    setupStepDownload: "下载",
    guideSignedOut: [
      "打开网页登录，并在 mdtero.com/auth 完成授权。",
      "受信任 auth bridge 连接账户后，回到扩展弹窗继续。",
      "在弹窗解析当前论文页、粘贴 DOI，或上传本地 PDF/EPUB。",
      "任务完成后下载 Markdown、ZIP、源文件或译文。"
    ],
    guideSignedIn: [
      "网页登录已连接。",
      "在弹窗解析当前页面、粘贴 DOI，或上传 PDF/EPUB。",
      "当 paper_md 产物就绪后，可直接从弹窗请求翻译。",
      "下方历史记录可免费下载已生成产物。"
    ],
    uiLanguage: "界面语言",
    advanced: "高级设置",
    apiUrl: "API 地址",
    elsevierSettingsTitle: "Elsevier 访问",
    elsevierSettingsNote: "添加你自己的 Elsevier API key，让扩展可以直接从支持的 ScienceDirect 页面获取 Article Retrieval XML。",
    elsevierConfigured: "已配置",
    elsevierNotConfigured: "未配置",
    elsevierKeyVisible: "隐藏",
    elsevierKeyHidden: "显示",
    elsevierKeySaved: "Elsevier key 已保存在本浏览器。",
    elsevierKeyCleared: "Elsevier key 已清除。",
    clearElsevierKey: "清除 key",
    elsevierApiKey: "Elsevier API key",
    elsevierApiKeyPlaceholder: "粘贴你的 Elsevier API key",
    elsevierApiKeyNote: "只保存在本浏览器。用于 Elsevier XML 抓取，失败时再回退后端解析。",
    save: "保存设置",
    historyTitle: "账户历史",
    historyNote: "从历史记录下载内容永远免费，不扣除额度。",
    historyEmpty: "暂无解析或翻译记录。",
    historyError: "加载历史文档失败：",
    downloadFailed: "下载失败：",
    download: "下载",
    artifactLabels: {
      paper_md: "Markdown",
      paper_bundle: "压缩包",
      translated_md: "译文",
      paper_pdf: "PDF",
      paper_epub: "EPUB",
      paper_html: "HTML",
      paper_xml: "XML"
    },
    historyRefresh: "刷新",
    historyRefreshing: "刷新中..."
  }
} as const;

const titleEl = document.querySelector<HTMLHeadingElement>("#settings-title");
const subtitleEl = document.querySelector<HTMLParagraphElement>("#settings-subtitle");
const permissionsTitleEl = document.querySelector<HTMLHeadingElement>("#permissions-title");
const permissionsTabsEl = document.querySelector<HTMLParagraphElement>("#permissions-tabs");
const permissionsDownloadsEl = document.querySelector<HTMLParagraphElement>("#permissions-downloads");
const permissionsCaptureEl = document.querySelector<HTMLParagraphElement>("#permissions-capture");
const permissionsHostsEl = document.querySelector<HTMLParagraphElement>("#permissions-hosts");
const languageToggleEl = document.querySelector<HTMLButtonElement>("#language-toggle");
const apiBaseUrlInput = document.querySelector<HTMLInputElement>("#api-base-url");
const uiLanguageSelect = document.querySelector<HTMLSelectElement>("#ui-language");
const accountStatus = document.querySelector<HTMLParagraphElement>("#account-status");
const usageStatus = document.querySelector<HTMLParagraphElement>("#usage-status");
const saveButton = document.querySelector<HTMLButtonElement>("#save-settings");
const openAccountButton = document.querySelector<HTMLButtonElement>("#open-account");
const websiteAuthTitleEl = document.querySelector<HTMLHeadingElement>("#website-auth-title");
const websiteAuthNoteEl = document.querySelector<HTMLParagraphElement>("#website-auth-note");
const connectionGuideTitleEl = document.querySelector<HTMLHeadingElement>("#connection-guide-title");
const connectionGuideListEl = document.querySelector<HTMLDivElement>("#connection-guide-list");
const setupStepAuthEl = document.querySelector<HTMLSpanElement>("#setup-step-auth");
const setupStepParseEl = document.querySelector<HTMLSpanElement>("#setup-step-parse");
const setupStepTranslateEl = document.querySelector<HTMLSpanElement>("#setup-step-translate");
const setupStepDownloadEl = document.querySelector<HTMLSpanElement>("#setup-step-download");
const uiLanguageLabel = document.querySelector<HTMLLabelElement>("#ui-language-label");
const advancedSummary = document.querySelector<HTMLElement>("#advanced-summary");
const apiBaseUrlLabel = document.querySelector<HTMLLabelElement>("#api-base-url-label");
const elsevierSettingsTitleEl = document.querySelector<HTMLHeadingElement>("#elsevier-settings-title");
const elsevierSettingsNoteEl = document.querySelector<HTMLParagraphElement>("#elsevier-settings-note");
const elsevierKeyStatusEl = document.querySelector<HTMLSpanElement>("#elsevier-key-status");
const elsevierApiKeyInput = document.querySelector<HTMLInputElement>("#elsevier-api-key");
const elsevierApiKeyLabel = document.querySelector<HTMLLabelElement>("#elsevier-api-key-label");
const elsevierApiKeyNote = document.querySelector<HTMLParagraphElement>("#elsevier-api-key-note");
const toggleElsevierKeyButton = document.querySelector<HTMLButtonElement>("#toggle-elsevier-key");
const clearElsevierKeyButton = document.querySelector<HTMLButtonElement>("#clear-elsevier-key");
const elsevierApiKeyFeedback = document.querySelector<HTMLParagraphElement>("#elsevier-api-key-feedback");
const historySection = document.querySelector<HTMLElement>("#history-section");
const historyList = document.querySelector<HTMLDivElement>("#history-list");
const historyTitle = document.querySelector<HTMLHeadingElement>("#history-title");
const historyNote = document.querySelector<HTMLParagraphElement>("#history-note");
const refreshHistoryBtn = document.querySelector<HTMLButtonElement>("#refresh-history");

type HistoryTaskRecord = TaskRecord & { paper_input?: string };

const client = createApiClient(readSettings);
let uiLanguage: UiLanguage = "en";

function renderHistoryNotice(message: string, color?: string) {
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

function copyFor(language: UiLanguage) {
  return COPY[language];
}

function toggleLanguageLabel(language: UiLanguage) {
  return language === "en" ? "中文" : "EN";
}

async function openMdteroAccount() {
  await chrome.tabs.create({ url: MDTERO_ACCOUNT_URL });
}

function formatUsageSummary(usage: {
  wallet_balance_display?: string;
  parse_quota_remaining?: number;
  translation_quota_remaining?: number;
}): string {
  const wallet = usage.wallet_balance_display?.trim() || (uiLanguage === "zh" ? "¥0.00" : "$0.00");
  const parse = Number.isFinite(usage.parse_quota_remaining) ? Number(usage.parse_quota_remaining) : 0;
  const translation = Number.isFinite(usage.translation_quota_remaining)
    ? Number(usage.translation_quota_remaining)
    : 0;
  return copyFor(uiLanguage).usageSummary(wallet, parse, translation);
}

function formatArtifactActionLabel(artifactKey: string): string {
  const copy = copyFor(uiLanguage);
  const labels = copy.artifactLabels as Record<string, string>;
  const label = labels[artifactKey] || artifactKey.replace(/^paper_/, "").replace(/_/g, " ").toUpperCase();
  return `${copy.download} ${label}`;
}

function renderElsevierKeyState(hasKey: boolean) {
  if (!elsevierKeyStatusEl) return;
  const copy = copyFor(uiLanguage);
  elsevierKeyStatusEl.textContent = hasKey ? copy.elsevierConfigured : copy.elsevierNotConfigured;
  elsevierKeyStatusEl.dataset.state = hasKey ? "configured" : "empty";
}

function setElsevierFeedback(message?: string) {
  if (!elsevierApiKeyFeedback) return;
  elsevierApiKeyFeedback.textContent = message || "";
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
  if (elsevierSettingsTitleEl) elsevierSettingsTitleEl.textContent = copy.elsevierSettingsTitle;
  if (elsevierSettingsNoteEl) elsevierSettingsNoteEl.textContent = copy.elsevierSettingsNote;
  if (elsevierApiKeyLabel) elsevierApiKeyLabel.textContent = copy.elsevierApiKey;
  if (elsevierApiKeyInput) elsevierApiKeyInput.placeholder = copy.elsevierApiKeyPlaceholder;
  if (elsevierApiKeyNote) elsevierApiKeyNote.textContent = copy.elsevierApiKeyNote;
  if (toggleElsevierKeyButton) {
    toggleElsevierKeyButton.textContent = elsevierApiKeyInput?.type === "text" ? copy.elsevierKeyVisible : copy.elsevierKeyHidden;
  }
  if (clearElsevierKeyButton) clearElsevierKeyButton.textContent = copy.clearElsevierKey;
  if (openAccountButton) openAccountButton.textContent = copy.openAccount;
  if (websiteAuthTitleEl) websiteAuthTitleEl.textContent = copy.websiteAuthTitle;
  if (websiteAuthNoteEl) websiteAuthNoteEl.textContent = copy.websiteAuthNote;
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

function setStepText(element: HTMLSpanElement | null, index: string, label: string) {
  if (!element) return;
  element.textContent = "";
  const icon = document.createElement("span");
  icon.className = "support-icon";
  icon.textContent = index;
  element.appendChild(icon);
  element.append(label);
}

function renderConnectionGuide(isSignedIn: boolean) {
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
      const historyTask = task as HistoryTaskRecord;
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

      const artifactEntries = task.result
        ? task.result.artifacts
          ? Object.entries(task.result.artifacts).map(([key, desc]) => [key, desc.filename] as const)
          : (task.result.download_artifacts ?? []).map((desc) => [desc.artifact, desc.filename] as const)
        : [];

      if (task.status === "succeeded" && artifactEntries.length > 0) {
        const artifactsRow = document.createElement("div");
        artifactsRow.className = "history-actions";
        
        for (const [key, filename] of artifactEntries) {
          const dlBtn = document.createElement("button");
          dlBtn.className = "ghost-chip history-download-button";
          dlBtn.textContent = formatArtifactActionLabel(key);
          dlBtn.addEventListener("click", async () => {
            try {
              dlBtn.textContent = uiLanguage === "zh" ? "下载中..." : "Downloading...";
              const result = await client.downloadArtifact(task.task_id, key, filename);
              triggerBlobDownload(result.blob, result.filename);
              dlBtn.textContent = formatArtifactActionLabel(key);
            } catch (err) {
              renderHistoryNotice(`${copyFor(uiLanguage).downloadFailed} ${(err as Error).message}`, "#b91c1c");
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
    renderHistoryNotice(`${errorPrefix}${(error as Error).message}`, "#f44336");
  }
}

async function refreshView() {
  const settings = await readSettings();
  uiLanguage = resolveUiLanguage(settings.uiLanguage, globalThis.navigator?.language);
  applyLanguage();

  if (apiBaseUrlInput) apiBaseUrlInput.value = settings.apiBaseUrl;
  if (elsevierApiKeyInput) elsevierApiKeyInput.value = settings.elsevierApiKey || "";
  renderElsevierKeyState(Boolean(settings.elsevierApiKey));
  if (uiLanguageSelect) uiLanguageSelect.value = uiLanguage;
  if (accountStatus) {
    accountStatus.textContent = settings.email
      ? copyFor(uiLanguage).signedIn(settings.email)
      : copyFor(uiLanguage).notSignedIn;
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
      usageStatus.textContent = (error as Error).message;
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
        apiBaseUrl: apiBaseUrlInput?.value.trim() || current.apiBaseUrl,
        uiLanguage: resolveUiLanguage(uiLanguageSelect?.value as UiLanguage | undefined, globalThis.navigator?.language),
        elsevierApiKey: elsevierApiKeyInput?.value.trim() || undefined,
    })
  );
  setElsevierFeedback(copyFor(uiLanguage).elsevierKeySaved);
  await refreshView();
});

toggleElsevierKeyButton?.addEventListener("click", () => {
  if (!elsevierApiKeyInput || !toggleElsevierKeyButton) return;
  const copy = copyFor(uiLanguage);
  const shouldShow = elsevierApiKeyInput.type === "password";
  elsevierApiKeyInput.type = shouldShow ? "text" : "password";
  toggleElsevierKeyButton.textContent = shouldShow ? copy.elsevierKeyVisible : copy.elsevierKeyHidden;
});

clearElsevierKeyButton?.addEventListener("click", async () => {
  const current = await readSettings();
  await writeSettings(
    mergeSettings(current, {
      elsevierApiKey: undefined
    })
  );
  if (elsevierApiKeyInput) elsevierApiKeyInput.value = "";
  renderElsevierKeyState(false);
  setElsevierFeedback(copyFor(uiLanguage).elsevierKeyCleared);
});

uiLanguageSelect?.addEventListener("change", async () => {
  uiLanguage = resolveUiLanguage(uiLanguageSelect.value as UiLanguage, globalThis.navigator?.language);
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
