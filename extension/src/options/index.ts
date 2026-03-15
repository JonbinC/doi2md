import { createApiClient } from "../lib/api";
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
    subtitle: "Connect email, check credits, and tune preferences.",
    notSignedIn: "Not signed in.",
    usagePending: "Usage available after sign-in.",
    signedIn: (email: string) => `Signed in as ${email}`,
    credits: (amount: number) => `Remaining credits: ${amount}`,
    email: "Email",
    sendCode: "Send Code",
    verifyLogin: "Verify Login",
    code: "Verification Code",
    uiLanguage: "Interface language",
    advanced: "Advanced",
    elsevierApiKey: "Elsevier API Key",
    apiUrl: "API URL",
    save: "Save",
    sent: (email: string) => `Verification code sent to ${email}.`,
    historyTitle: "Document History",
    historyNote: "Downloads from your history are always free.",
    historyEmpty: "No parsing or translation history found yet.",
    historyError: "Failed to load history: "
  },
  zh: {
    title: "Mdtero 账户",
    subtitle: "登录邮箱、查看额度，并管理偏好设置。",
    notSignedIn: "尚未登录。",
    usagePending: "登录后可查看额度。",
    signedIn: (email: string) => `已登录：${email}`,
    credits: (amount: number) => `剩余额度：${amount}`,
    email: "邮箱",
    sendCode: "发送验证码",
    verifyLogin: "验证登录",
    code: "验证码",
    uiLanguage: "界面语言",
    advanced: "高级设置",
    elsevierApiKey: "Elsevier API Key",
    apiUrl: "API 地址",
    save: "保存",
    sent: (email: string) => `验证码已发送到 ${email}。`,
    historyTitle: "历史文档",
    historyNote: "从历史记录下载内容永远免费，不扣除额度。",
    historyEmpty: "暂无解析或翻译记录。",
    historyError: "加载历史文档失败："
  }
} as const;

const titleEl = document.querySelector<HTMLHeadingElement>("#settings-title");
const subtitleEl = document.querySelector<HTMLParagraphElement>("#settings-subtitle");
const languageToggleEl = document.querySelector<HTMLButtonElement>("#language-toggle");
const elsevierApiKeyInput = document.querySelector<HTMLInputElement>("#elsevier-api-key");
const apiBaseUrlInput = document.querySelector<HTMLInputElement>("#api-base-url");
const emailInput = document.querySelector<HTMLInputElement>("#email-input");
const codeInput = document.querySelector<HTMLInputElement>("#code-input");
const uiLanguageSelect = document.querySelector<HTMLSelectElement>("#ui-language");
const accountStatus = document.querySelector<HTMLParagraphElement>("#account-status");
const usageStatus = document.querySelector<HTMLParagraphElement>("#usage-status");
const saveButton = document.querySelector<HTMLButtonElement>("#save-settings");
const sendCodeButton = document.querySelector<HTMLButtonElement>("#send-code");
const verifyButton = document.querySelector<HTMLButtonElement>("#verify-code");
const emailLabel = document.querySelector<HTMLLabelElement>("#email-label");
const codeLabel = document.querySelector<HTMLLabelElement>("#code-label");
const uiLanguageLabel = document.querySelector<HTMLLabelElement>("#ui-language-label");
const advancedSummary = document.querySelector<HTMLElement>("#advanced-summary");
const elsevierApiKeyLabel = document.querySelector<HTMLLabelElement>("#elsevier-api-key-label");
const apiBaseUrlLabel = document.querySelector<HTMLLabelElement>("#api-base-url-label");
const historySection = document.querySelector<HTMLElement>("#history-section");
const historyList = document.querySelector<HTMLDivElement>("#history-list");
const historyTitle = document.querySelector<HTMLHeadingElement>("#history-title");
const historyNote = document.querySelector<HTMLParagraphElement>("#history-note");
const refreshHistoryBtn = document.querySelector<HTMLButtonElement>("#refresh-history");

const client = createApiClient(readSettings);
let uiLanguage: UiLanguage = "en";

function copyFor(language: UiLanguage) {
  return COPY[language] as any;
}

function toggleLanguageLabel(language: UiLanguage) {
  return language === "en" ? "中文" : "EN";
}

function applyLanguage() {
  const copy = copyFor(uiLanguage);
  document.documentElement.lang = uiLanguage === "zh" ? "zh-CN" : "en";
  if (titleEl) titleEl.textContent = copy.title;
  if (subtitleEl) subtitleEl.textContent = copy.subtitle;
  if (languageToggleEl) languageToggleEl.textContent = toggleLanguageLabel(uiLanguage);
  if (emailLabel) emailLabel.textContent = copy.email;
  if (sendCodeButton) sendCodeButton.textContent = copy.sendCode;
  if (verifyButton) verifyButton.textContent = copy.verifyLogin;
  if (codeLabel) codeLabel.textContent = copy.code;
  if (uiLanguageLabel) uiLanguageLabel.textContent = copy.uiLanguage;
  if (advancedSummary) advancedSummary.textContent = copy.advanced;
  if (elsevierApiKeyLabel) elsevierApiKeyLabel.textContent = copy.elsevierApiKey;
  if (apiBaseUrlLabel) apiBaseUrlLabel.textContent = copy.apiUrl;
  if (saveButton) saveButton.textContent = copy.save;
  if (historyTitle) historyTitle.textContent = (copy as any).historyTitle || "Document History";
  if (historyNote) historyNote.textContent = (copy as any).historyNote || "Downloads from your history are always free.";
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
              const url = URL.createObjectURL(result.blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = result.filename;
              a.click();
              URL.revokeObjectURL(url);
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

  if (elsevierApiKeyInput) elsevierApiKeyInput.value = settings.elsevierApiKey ?? "";
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
    if (historySection) historySection.style.display = "none";
    return;
  }

  if (historySection) historySection.style.display = "block";

  try {
    const usage = await client.getUsage();
    if (usageStatus) {
      usageStatus.textContent = copyFor(uiLanguage).credits(usage.credit_balance);
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
    refreshHistoryBtn.textContent = "...";
    refreshHistory().then(() => {
      refreshHistoryBtn.textContent = "Refresh";
    });
  });
}

saveButton?.addEventListener("click", async () => {
  const current = await readSettings();
  await writeSettings(
    mergeSettings(current, {
      elsevierApiKey: elsevierApiKeyInput?.value.trim() || undefined,
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
