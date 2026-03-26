import { createApiClient } from "../lib/api";
import { triggerBlobDownload } from "../lib/download";
import {
  getPublisherCapabilityGroups,
  type PublisherCapabilityLanguage
} from "@mdtero/shared";
import {
  mergeSettings,
  readSettings,
  resolveUiLanguage,
  writeSettings,
  type UiLanguage
} from "../lib/storage";
import { summarizeParserV2ShadowDiagnostics } from "@mdtero/shared";
import {
  describeCapabilityReadiness,
  formatCapabilityFallbacks,
  formatCapabilityStatusLabel,
  resolveCapabilityReadiness,
  type CapabilityHelperState
} from "../lib/publisher-capability-view";

const COPY = {
  en: {
    title: "Mdtero Account",
    subtitle: "Sign in faster, check balance and quota, and tune preferences.",
    supportSummary: "Keep browser capture on your own machine and see which sources are ready with your current setup.",
    browserAssistedNote:
      "If a source needs browser help, just keep the article page open locally and Mdtero will guide the rest.",
    connectorKeysTitle: "Connector keys",
    connectorKeysNote:
      "Only fill the keys you actually need. Everything stays on your own machine.",
    capabilityNeed: "What you need",
    capabilityRoute: "How Mdtero gets it",
    capabilityFallback: "Fallback",
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
    signedIn: (email: string) => `Signed in as ${email}`,
    usageSummary: (wallet: string, parse: number, translation: number) =>
      `Balance ${wallet} · Parse ${parse} · Translation ${translation}`,
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
    sent: (email: string) => `Verification code sent to ${email}.`,
    passwordLoginFailed: "Password login failed.",
    historyTitle: "Document History",
    historyNote: "Downloads from your history are always free.",
    historyEmpty: "No parsing or translation history found yet.",
    historyError: "Failed to load history: ",
    historyRefresh: "Refresh",
    historyRefreshing: "Refreshing..."
  },
  zh: {
    title: "Mdtero 账户",
    subtitle: "优先用密码登录，再查看余额、额度与偏好设置。",
    supportSummary: "把浏览器抓取留在你自己的设备上，并查看当前这套配置已经适合哪些来源。",
    browserAssistedNote:
      "如果某个来源需要浏览器辅助，只要在本地保持文章页面打开，剩下的交给 Mdtero 引导即可。",
    connectorKeysTitle: "Connector keys",
    connectorKeysNote: "只填写你实际需要的 key；这些信息都保留在你自己的机器上。",
    capabilityNeed: "你需要准备什么",
    capabilityRoute: "Mdtero 怎么获取",
    capabilityFallback: "兜底方式",
    permissionsTitle: "为什么 Mdtero 需要这些权限",
    permissionsTabs: "`tabs` 用来复用或打开受支持的论文页面，以便在本机完成抓取。",
    permissionsDownloads: "`downloads` 用来把 Markdown 压缩包、译文和源文件保存回你的电脑。",
    permissionsNative: "`nativeMessaging` 用来把扩展连接到你本地的 Mdtero helper，完成浏览器协同抓取。",
    permissionsHosts: "站点权限只覆盖已支持的学术站点，以及产品已经使用的 Mdtero / 出版商 API。",
    helperReady: "本地 helper 已就绪，可处理浏览器协同抓取。",
    helperBusy: "本地 helper 已连接，正在处理浏览器任务。",
    helperUnavailable: "暂未检测到本地 helper。请安装或重启 mdtero-local 以启用浏览器协同抓取。",
    helperDisconnected: "本地 helper 已断开。请重启 mdtero-local 或重载扩展后再试。",
    helperUnknown: "本地 helper 状态未知。",
    shadowSignedOut: "登录后可查看实验 connector shadow 状态。",
    shadowUnavailable: "暂时无法获取实验 connector shadow 状态。",
    notSignedIn: "尚未登录。",
    usagePending: "登录后可查看余额与额度。",
    signedIn: (email: string) => `已登录：${email}`,
    usageSummary: (wallet: string, parse: number, translation: number) =>
      `余额 ${wallet} · 解析 ${parse} · 翻译 ${translation}`,
    email: "邮箱",
    password: "密码",
    passwordMode: "密码登录",
    codeMode: "邮箱验证码",
    signIn: "登录",
    useEmailCode: "改用验证码",
    sendCode: "发送验证码",
    verifyLogin: "验证登录",
    code: "验证码",
    uiLanguage: "界面语言",
    advanced: "高级设置",
    elsevierApiKey: "Elsevier API Key",
    springerOpenAccessApiKey: "Springer OA API Key",
    apiUrl: "API 地址",
    save: "保存",
    sent: (email: string) => `验证码已发送到 ${email}。`,
    passwordLoginFailed: "密码登录失败。",
    historyTitle: "历史文档",
    historyNote: "从历史记录下载内容永远免费，不扣除额度。",
    historyEmpty: "暂无解析或翻译记录。",
    historyError: "加载历史文档失败：",
    historyRefresh: "刷新",
    historyRefreshing: "刷新中..."
  }
} as const;

const titleEl = document.querySelector<HTMLHeadingElement>("#settings-title");
const subtitleEl = document.querySelector<HTMLParagraphElement>("#settings-subtitle");
const supportSummaryEl = document.querySelector<HTMLParagraphElement>("#support-summary");
const browserAssistedNoteEl = document.querySelector<HTMLParagraphElement>("#browser-assisted-note");
const publisherCapabilityGroupsEl = document.querySelector<HTMLDivElement>("#publisher-capability-groups");
const connectorKeysTitleEl = document.querySelector<HTMLHeadingElement>("#connector-keys-title");
const connectorKeysNoteEl = document.querySelector<HTMLParagraphElement>("#connector-keys-note");
const permissionsTitleEl = document.querySelector<HTMLHeadingElement>("#permissions-title");
const permissionsTabsEl = document.querySelector<HTMLParagraphElement>("#permissions-tabs");
const permissionsDownloadsEl = document.querySelector<HTMLParagraphElement>("#permissions-downloads");
const permissionsNativeEl = document.querySelector<HTMLParagraphElement>("#permissions-native");
const permissionsHostsEl = document.querySelector<HTMLParagraphElement>("#permissions-hosts");
const languageToggleEl = document.querySelector<HTMLButtonElement>("#language-toggle");
const elsevierApiKeyInput = document.querySelector<HTMLInputElement>("#elsevier-api-key");
const springerOpenAccessApiKeyInput = document.querySelector<HTMLInputElement>("#springer-oa-api-key");
const apiBaseUrlInput = document.querySelector<HTMLInputElement>("#api-base-url");
const emailInput = document.querySelector<HTMLInputElement>("#email-input");
const passwordInput = document.querySelector<HTMLInputElement>("#password-input");
const codeInput = document.querySelector<HTMLInputElement>("#code-input");
const uiLanguageSelect = document.querySelector<HTMLSelectElement>("#ui-language");
const accountStatus = document.querySelector<HTMLParagraphElement>("#account-status");
const usageStatus = document.querySelector<HTMLParagraphElement>("#usage-status");
const helperStatus = document.querySelector<HTMLParagraphElement>("#helper-status");
const shadowStatus = document.querySelector<HTMLParagraphElement>("#shadow-status");
const saveButton = document.querySelector<HTMLButtonElement>("#save-settings");
const sendCodeButton = document.querySelector<HTMLButtonElement>("#send-code");
const verifyButton = document.querySelector<HTMLButtonElement>("#verify-code");
const passwordLoginButton = document.querySelector<HTMLButtonElement>("#password-login");
const passwordUseCodeButton = document.querySelector<HTMLButtonElement>("#password-use-code");
const authModePasswordButton = document.querySelector<HTMLButtonElement>("#auth-mode-password");
const authModeCodeButton = document.querySelector<HTMLButtonElement>("#auth-mode-code");
const emailLabel = document.querySelector<HTMLLabelElement>("#email-label");
const passwordLabel = document.querySelector<HTMLLabelElement>("#password-label");
const codeLabel = document.querySelector<HTMLLabelElement>("#code-label");
const uiLanguageLabel = document.querySelector<HTMLLabelElement>("#ui-language-label");
const advancedSummary = document.querySelector<HTMLElement>("#advanced-summary");
const elsevierApiKeyLabel = document.querySelector<HTMLLabelElement>("#elsevier-api-key-label");
const springerOpenAccessApiKeyLabel = document.querySelector<HTMLLabelElement>("#springer-oa-api-key-label");
const apiBaseUrlLabel = document.querySelector<HTMLLabelElement>("#api-base-url-label");
const historySection = document.querySelector<HTMLElement>("#history-section");
const historyList = document.querySelector<HTMLDivElement>("#history-list");
const historyTitle = document.querySelector<HTMLHeadingElement>("#history-title");
const historyNote = document.querySelector<HTMLParagraphElement>("#history-note");
const refreshHistoryBtn = document.querySelector<HTMLButtonElement>("#refresh-history");
const passwordAuthPanel = document.querySelector<HTMLElement>("#password-auth-panel");
const codeAuthPanel = document.querySelector<HTMLElement>("#code-auth-panel");

const client = createApiClient(readSettings);
let uiLanguage: UiLanguage = "en";
let authMode: "password" | "code" = "password";
let currentHelperState: CapabilityHelperState = "unavailable";

function copyFor(language: UiLanguage) {
  return COPY[language] as any;
}

function toggleLanguageLabel(language: UiLanguage) {
  return language === "en" ? "中文" : "EN";
}

function applyAuthMode() {
  const passwordActive = authMode === "password";
  if (passwordAuthPanel) passwordAuthPanel.hidden = !passwordActive;
  if (codeAuthPanel) codeAuthPanel.hidden = passwordActive;
  authModePasswordButton?.classList.toggle("active-chip", passwordActive);
  authModeCodeButton?.classList.toggle("active-chip", !passwordActive);
}

function formatUsageSummary(usage: {
  wallet_balance_display?: string;
  parse_quota_remaining?: number;
  translation_quota_remaining?: number;
}) {
  const wallet = usage.wallet_balance_display?.trim() || (uiLanguage === "zh" ? "¥0.00" : "$0.00");
  const parse = Number.isFinite(usage.parse_quota_remaining) ? Number(usage.parse_quota_remaining) : 0;
  const translation = Number.isFinite(usage.translation_quota_remaining)
    ? Number(usage.translation_quota_remaining)
    : 0;
  return copyFor(uiLanguage).usageSummary(wallet, parse, translation);
}

function renderPublisherCapabilityMatrix() {
  if (!publisherCapabilityGroupsEl) {
    return;
  }

  const copy = copyFor(uiLanguage);
  const groups = getPublisherCapabilityGroups(uiLanguage as PublisherCapabilityLanguage);
  const settingsSnapshot = {
    helperState: currentHelperState,
    hasElsevierApiKey: Boolean(elsevierApiKeyInput?.value.trim()),
    hasSpringerOpenAccessApiKey: Boolean(springerOpenAccessApiKeyInput?.value.trim())
  };

  publisherCapabilityGroupsEl.innerHTML = "";

  for (const group of groups) {
    const section = document.createElement("section");
    section.className = "capability-group-card";

    const head = document.createElement("div");
    head.className = "capability-group-head";

    const title = document.createElement("h3");
    title.className = "capability-group-title";
    title.textContent = group.label;

    const description = document.createElement("p");
    description.className = "meta-label";
    description.textContent = group.description;

    head.appendChild(title);
    head.appendChild(description);
    section.appendChild(head);

    const list = document.createElement("div");
    list.className = "capability-entry-list";

    for (const entry of group.entries) {
      const readiness = resolveCapabilityReadiness(entry, settingsSnapshot);

      const card = document.createElement("article");
      card.className = "capability-entry-card";

      const row = document.createElement("div");
      row.className = "capability-entry-top";

      const label = document.createElement("h4");
      label.className = "capability-entry-title";
      label.textContent = entry.label;

      const badges = document.createElement("div");
      badges.className = "capability-badges";

      const statusBadge = document.createElement("span");
      statusBadge.className = `capability-badge capability-badge-${entry.status}`;
      statusBadge.textContent = formatCapabilityStatusLabel(entry.status, uiLanguage as PublisherCapabilityLanguage);

      const readinessBadge = document.createElement("span");
      readinessBadge.className = `capability-badge capability-badge-${readiness}`;
      readinessBadge.textContent = describeCapabilityReadiness(readiness, uiLanguage as PublisherCapabilityLanguage);

      badges.appendChild(statusBadge);
      badges.appendChild(readinessBadge);
      row.appendChild(label);
      row.appendChild(badges);
      card.appendChild(row);

      const need = document.createElement("p");
      need.className = "capability-copy";
      need.innerHTML = `<strong>${copy.capabilityNeed}:</strong> ${entry.whatYouNeed}`;
      card.appendChild(need);

      const route = document.createElement("p");
      route.className = "capability-copy";
      route.innerHTML = `<strong>${copy.capabilityRoute}:</strong> ${entry.howMdteroGetsIt}`;
      card.appendChild(route);

      const fallback = document.createElement("p");
      fallback.className = "capability-copy capability-copy-muted";
      fallback.innerHTML = `<strong>${copy.capabilityFallback}:</strong> ${formatCapabilityFallbacks(
        entry.fallbacks,
        uiLanguage as PublisherCapabilityLanguage
      )}`;
      card.appendChild(fallback);

      if (entry.links.length > 0) {
        const links = document.createElement("div");
        links.className = "capability-links";
        for (const item of entry.links) {
          const anchor = document.createElement("a");
          anchor.href = item.href;
          anchor.target = "_blank";
          anchor.rel = "noopener noreferrer";
          anchor.className = "guide-doc-link capability-link";
          anchor.textContent = item.label;
          links.appendChild(anchor);
        }
        card.appendChild(links);
      }

      list.appendChild(card);
    }

    section.appendChild(list);
    publisherCapabilityGroupsEl.appendChild(section);
  }
}

function applyLanguage() {
  const copy = copyFor(uiLanguage);
  document.documentElement.lang = uiLanguage === "zh" ? "zh-CN" : "en";
  if (titleEl) titleEl.textContent = copy.title;
  if (subtitleEl) subtitleEl.textContent = copy.subtitle;
  if (supportSummaryEl) supportSummaryEl.textContent = copy.supportSummary;
  if (browserAssistedNoteEl) browserAssistedNoteEl.textContent = copy.browserAssistedNote;
  if (connectorKeysTitleEl) connectorKeysTitleEl.textContent = copy.connectorKeysTitle;
  if (connectorKeysNoteEl) connectorKeysNoteEl.textContent = copy.connectorKeysNote;
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
  if (historyTitle) historyTitle.textContent = (copy as any).historyTitle || "Document History";
  if (historyNote) historyNote.textContent = (copy as any).historyNote || "Downloads from your history are always free.";
  if (refreshHistoryBtn) refreshHistoryBtn.textContent = (copy as any).historyRefresh || "Refresh";
  applyAuthMode();
  renderPublisherCapabilityMatrix();
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
      currentHelperState = "busy";
      helperStatus.textContent = copy.helperBusy;
      renderPublisherCapabilityMatrix();
      return;
    }
    if (state === "connected") {
      currentHelperState = "connected";
      helperStatus.textContent = copy.helperReady;
      renderPublisherCapabilityMatrix();
      return;
    }
    if (state === "disconnected") {
      currentHelperState = "disconnected";
      helperStatus.textContent = copy.helperDisconnected;
      renderPublisherCapabilityMatrix();
      return;
    }
    currentHelperState = "unavailable";
    helperStatus.textContent = copy.helperUnavailable;
  } catch {
    currentHelperState = "unavailable";
    helperStatus.textContent = copy.helperUnknown;
  }
  renderPublisherCapabilityMatrix();
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
      historyList.innerHTML = `<p class="meta-label">${(copy as any).historyEmpty || "No history found."}</p>`;
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
      const rawTask = task as any; 
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
          dlBtn.textContent = `⬇ ${key.replace("paper_", "").toUpperCase()}`;
          dlBtn.addEventListener("click", async () => {
            try {
              dlBtn.textContent = "Downloading...";
              const result = await client.downloadArtifact(task.task_id, key);
              triggerBlobDownload(result.blob, result.filename);
              dlBtn.textContent = `⬇ ${key.replace("paper_", "").toUpperCase()}`;
            } catch (err) {
              alert("Download failed: " + (err as Error).message);
              dlBtn.textContent = `⬇ ${key.replace("paper_", "").toUpperCase()}`;
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
    const errorPrefix = (copy as any).historyError || "Failed to load history: ";
    historyList.innerHTML = `<p class="meta-label" style="color: #f44336;">${errorPrefix}${(error as Error).message}</p>`;
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
  renderPublisherCapabilityMatrix();
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
    refreshHistoryBtn.textContent = (copyFor(uiLanguage) as any).historyRefreshing || "...";
    refreshHistory().then(() => {
      refreshHistoryBtn.textContent = (copyFor(uiLanguage) as any).historyRefresh || "Refresh";
    });
  });
}

saveButton?.addEventListener("click", async () => {
  const current = await readSettings();
  await writeSettings(
    mergeSettings(current, {
      elsevierApiKey: elsevierApiKeyInput?.value.trim() || undefined,
      springerOpenAccessApiKey: springerOpenAccessApiKeyInput?.value.trim() || undefined,
      apiBaseUrl: apiBaseUrlInput?.value.trim() || current.apiBaseUrl,
      uiLanguage: resolveUiLanguage(uiLanguageSelect?.value as UiLanguage | undefined, globalThis.navigator?.language)
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
    accountStatus.textContent = (error as Error).message;
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
    accountStatus.textContent = (error as Error).message || copyFor(uiLanguage).passwordLoginFailed;
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
    accountStatus.textContent = (error as Error).message;
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
