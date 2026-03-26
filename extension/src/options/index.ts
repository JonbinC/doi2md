import { createApiClient } from "../lib/api";
import { triggerBlobDownload } from "../lib/download";
import {
  mergeSettings,
  readSettings,
  resolveUiLanguage,
  writeSettings,
  type UiLanguage
} from "../lib/storage";
import { summarizeParserV2ShadowDiagnostics } from "@mdtero/shared";

const COPY = {
  en: {
    title: "Mdtero Account",
    subtitle: "Sign in faster, check balance and quota, and tune preferences.",
    supportSummary: "Configure the helper-first browser surface for publisher-page capture, preprints, and account-linked downloads.",
    supportStableTitle: "Stable mainline",
    supportStableItems: "arXiv, PMC / Europe PMC, bioRxiv / medRxiv, PLOS, Springer Open Access, and Elsevier with your own local entitlement.",
    supportShadowTitle: "Bridge-assisted",
    supportShadowItems: "Springer subscription pages already use helper + browser capture when a live HTML page is available.",
    supportExperimentalTitle: "Experimental",
    supportExperimentalItems: "Wiley and Taylor & Francis can run through helper + browser capture, but challenge and login variance is still higher.",
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
    supportSummary: "在这里配置 helper-first 流程里的浏览器侧入口，用于出版社页面抓取、预印本和与你账户关联的下载内容。",
    supportStableTitle: "稳定主线",
    supportStableItems: "arXiv、PMC / Europe PMC、bioRxiv / medRxiv、PLOS、Springer Open Access，以及带有你本地权限的 Elsevier。",
    supportShadowTitle: "浏览器协同",
    supportShadowItems: "Springer 订阅页已经可以在实时 HTML 页面条件下走 helper + 浏览器抓取。",
    supportExperimentalTitle: "实验支持",
    supportExperimentalItems: "Wiley 与 Taylor & Francis 已可通过 helper + 浏览器抓取，但被 challenge 或登录页拦住的波动仍更高。",
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
const supportStableTitleEl = document.querySelector<HTMLParagraphElement>("#settings-support-stable-title");
const supportStableItemsEl = document.querySelector<HTMLParagraphElement>("#settings-support-stable-items");
const supportShadowTitleEl = document.querySelector<HTMLParagraphElement>("#settings-support-shadow-title");
const supportShadowItemsEl = document.querySelector<HTMLParagraphElement>("#settings-support-shadow-items");
const supportExperimentalTitleEl = document.querySelector<HTMLParagraphElement>("#settings-support-experimental-title");
const supportExperimentalItemsEl = document.querySelector<HTMLParagraphElement>("#settings-support-experimental-items");
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

function applyLanguage() {
  const copy = copyFor(uiLanguage);
  document.documentElement.lang = uiLanguage === "zh" ? "zh-CN" : "en";
  if (titleEl) titleEl.textContent = copy.title;
  if (subtitleEl) subtitleEl.textContent = copy.subtitle;
  if (supportSummaryEl) supportSummaryEl.textContent = copy.supportSummary;
  if (supportStableTitleEl) supportStableTitleEl.textContent = copy.supportStableTitle;
  if (supportStableItemsEl) supportStableItemsEl.textContent = copy.supportStableItems;
  if (supportShadowTitleEl) supportShadowTitleEl.textContent = copy.supportShadowTitle;
  if (supportShadowItemsEl) supportShadowItemsEl.textContent = copy.supportShadowItems;
  if (supportExperimentalTitleEl) supportExperimentalTitleEl.textContent = copy.supportExperimentalTitle;
  if (supportExperimentalItemsEl) supportExperimentalItemsEl.textContent = copy.supportExperimentalItems;
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
    helperStatus.textContent = copy.helperUnknown;
  }
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
