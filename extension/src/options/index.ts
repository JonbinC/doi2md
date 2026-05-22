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
    title: "Mdtero Account",
    subtitle: "Use the website account for sign-in, check balance and quota, and tune publisher API, TDM, and on-device fallback preferences.",
    connectorKeysTitle: "Connector keys",
    connectorKeysNote:
      "Only fill the keys you actually need. Everything stays on your own machine.",
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
    signedIn: (email: string) => `Signed in as ${email}`,
    usageSummary: (wallet: string, parse: number, translation: number) =>
      `Balance ${wallet} · Parse ${parse} · Translation ${translation}`,
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
    title: "Mdtero 账户",
    subtitle: "使用官网登录授权扩展，同时把本地 publisher 访问与下载保留在这台电脑上。",
    connectorKeysTitle: "Connector keys",
    connectorKeysNote: "只填写你实际需要的 key；这些信息都保留在你自己的机器上。",
    permissionsTitle: "为什么 Mdtero 需要这些权限",
    permissionsTabs: "`tabs` 用来复用或打开受支持的论文页面，以便在本机完成抓取。",
    permissionsDownloads: "`downloads` 用来把 Markdown、译文、兜底压缩包和源文件保存回你的电脑。",
    permissionsNative: "`nativeMessaging` 用来把扩展连接到你本地的 Mdtero 运行时，在直连 publisher API 或 TDM 不可用时回退到设备侧获取链路。",
    permissionsHosts: "站点权限只覆盖已支持的学术站点，以及产品已经使用的 Mdtero / 出版商 API。",
    helperReady: "本地运行时已就绪，可在需要时处理设备侧回退与浏览器抓取。",
    helperBusy: "本地运行时已连接，正在处理设备侧获取任务。",
    helperUnavailable: "暂未检测到本地运行时。请安装或重启 mdtero 以启用设备侧回退链路。",
    helperDisconnected: "本地运行时已断开。请重启 mdtero 或重载扩展后再试。",
    helperUnknown: "本地运行时状态未知。",
    notSignedIn: "尚未登录。请打开 Mdtero Account 授权扩展。",
    usagePending: "请在 mdtero.com/account 登录以同步余额、额度和历史。",
    signedIn: (email: string) => `已登录：${email}`,
    usageSummary: (wallet: string, parse: number, translation: number) =>
      `余额 ${wallet} · 解析 ${parse} · 翻译 ${translation}`,
    openAccount: "打开 Mdtero Account",
    websiteAuthTitle: "官网登录",
    websiteAuthNote: "扩展统一使用 Mdtero Account 登录。请打开官网完成登录，受信任 auth bridge 会把 token 交回扩展。",
    uiLanguage: "界面语言",
    advanced: "高级设置",
    elsevierApiKey: "Elsevier API Key",
    wileyTdmToken: "Wiley TDM Token",
    springerOpenAccessApiKey: "Springer OA API Key",
    apiUrl: "API 地址",
    save: "保存",
    historyTitle: "账户历史",
    historyNote: "从历史记录下载内容永远免费，不扣除额度。",
    historyEmpty: "暂无解析或翻译记录。",
    historyError: "加载历史文档失败：",
    downloadFailed: "下载失败：",
    historyRefresh: "刷新",
    historyRefreshing: "刷新中..."
  }
} as const;

const titleEl = document.querySelector<HTMLHeadingElement>("#settings-title");
const subtitleEl = document.querySelector<HTMLParagraphElement>("#settings-subtitle");
const connectorKeysTitleEl = document.querySelector<HTMLHeadingElement>("#connector-keys-title");
const connectorKeysNoteEl = document.querySelector<HTMLParagraphElement>("#connector-keys-note");
const permissionsTitleEl = document.querySelector<HTMLHeadingElement>("#permissions-title");
const permissionsTabsEl = document.querySelector<HTMLParagraphElement>("#permissions-tabs");
const permissionsDownloadsEl = document.querySelector<HTMLParagraphElement>("#permissions-downloads");
const permissionsNativeEl = document.querySelector<HTMLParagraphElement>("#permissions-native");
const permissionsHostsEl = document.querySelector<HTMLParagraphElement>("#permissions-hosts");
const languageToggleEl = document.querySelector<HTMLButtonElement>("#language-toggle");
const elsevierApiKeyInput = document.querySelector<HTMLInputElement>("#elsevier-api-key");
const wileyTdmTokenInput = document.querySelector<HTMLInputElement>("#wiley-tdm-token");
const springerOpenAccessApiKeyInput = document.querySelector<HTMLInputElement>("#springer-oa-api-key");
const apiBaseUrlInput = document.querySelector<HTMLInputElement>("#api-base-url");
const uiLanguageSelect = document.querySelector<HTMLSelectElement>("#ui-language");
const accountStatus = document.querySelector<HTMLParagraphElement>("#account-status");
const usageStatus = document.querySelector<HTMLParagraphElement>("#usage-status");
const helperStatus = document.querySelector<HTMLParagraphElement>("#helper-status");
const saveButton = document.querySelector<HTMLButtonElement>("#save-settings");
const openAccountButton = document.querySelector<HTMLButtonElement>("#open-account");
const websiteAuthTitleEl = document.querySelector<HTMLHeadingElement>("#website-auth-title");
const websiteAuthNoteEl = document.querySelector<HTMLParagraphElement>("#website-auth-note");
const uiLanguageLabel = document.querySelector<HTMLLabelElement>("#ui-language-label");
const advancedSummary = document.querySelector<HTMLElement>("#advanced-summary");
const elsevierApiKeyLabel = document.querySelector<HTMLLabelElement>("#elsevier-api-key-label");
const wileyTdmTokenLabel = document.querySelector<HTMLLabelElement>("#wiley-tdm-token-label");
const springerOpenAccessApiKeyLabel = document.querySelector<HTMLLabelElement>("#springer-oa-api-key-label");
const apiBaseUrlLabel = document.querySelector<HTMLLabelElement>("#api-base-url-label");
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

      if (task.status === "succeeded" && task.result?.artifacts) {
        const artifactsRow = document.createElement("div");
        artifactsRow.className = "history-actions";
        
        for (const [key, desc] of Object.entries(task.result.artifacts)) {
          const dlBtn = document.createElement("button");
          dlBtn.className = "ghost-chip history-download-button";
          dlBtn.textContent = `${copyFor(uiLanguage).historyRefresh === "刷新" ? "下载" : "Download"} ${key.replace("paper_", "").toUpperCase()}`;
          dlBtn.addEventListener("click", async () => {
            try {
              dlBtn.textContent = uiLanguage === "zh" ? "下载中..." : "Downloading...";
              const result = await client.downloadArtifact(task.task_id, key, desc.filename);
              triggerBlobDownload(result.blob, result.filename);
              dlBtn.textContent = `${copyFor(uiLanguage).historyRefresh === "刷新" ? "下载" : "Download"} ${key.replace("paper_", "").toUpperCase()}`;
            } catch (err) {
              renderHistoryNotice(`${copyFor(uiLanguage).downloadFailed} ${(err as Error).message}`, "#b91c1c");
              dlBtn.textContent = `${copyFor(uiLanguage).historyRefresh === "刷新" ? "下载" : "Download"} ${key.replace("paper_", "").toUpperCase()}`;
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
  await refreshBridgeStatus();

  if (elsevierApiKeyInput) elsevierApiKeyInput.value = settings.elsevierApiKey ?? "";
  if (wileyTdmTokenInput) wileyTdmTokenInput.value = settings.wileyTdmToken ?? "";
  if (springerOpenAccessApiKeyInput) springerOpenAccessApiKeyInput.value = settings.springerOpenAccessApiKey ?? "";
  if (apiBaseUrlInput) apiBaseUrlInput.value = settings.apiBaseUrl;
  if (uiLanguageSelect) uiLanguageSelect.value = uiLanguage;
  if (accountStatus) {
    accountStatus.textContent = settings.email
      ? copyFor(uiLanguage).signedIn(settings.email)
      : copyFor(uiLanguage).notSignedIn;
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
        elsevierApiKey: elsevierApiKeyInput?.value.trim() || undefined,
        wileyTdmToken: wileyTdmTokenInput?.value.trim() || undefined,
        springerOpenAccessApiKey: springerOpenAccessApiKeyInput?.value.trim() || undefined,
        apiBaseUrl: apiBaseUrlInput?.value.trim() || current.apiBaseUrl,
        uiLanguage: resolveUiLanguage(uiLanguageSelect?.value as UiLanguage | undefined, globalThis.navigator?.language)
    })
  );
  await refreshView();
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
