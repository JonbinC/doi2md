// src/lib/api.ts
function createApiClient(getSettings) {
  async function request(path, init) {
    const settings = await getSettings();
    const headers = new Headers(init?.headers ?? {});
    headers.set("Content-Type", "application/json");
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

// ../../packages/shared/src/api-contract.ts
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
    elsevierApiKey: current.elsevierApiKey,
    uiLanguage: resolveUiLanguage(current.uiLanguage, globalThis.navigator?.language)
  };
}
async function writeSettings(next) {
  await chrome.storage.local.set({ [SETTINGS_KEY]: next });
}

// src/options/index.ts
var COPY = {
  en: {
    title: "Mdtero Account",
    subtitle: "Connect email, check credits, and tune preferences.",
    notSignedIn: "Not signed in.",
    usagePending: "Usage available after sign-in.",
    signedIn: (email) => `Signed in as ${email}`,
    credits: (amount) => `Remaining credits: ${amount}`,
    email: "Email",
    sendCode: "Send Code",
    verifyLogin: "Verify Login",
    code: "Verification Code",
    uiLanguage: "Interface language",
    advanced: "Advanced",
    elsevierApiKey: "Elsevier API Key",
    apiUrl: "API URL",
    save: "Save",
    sent: (email) => `Verification code sent to ${email}.`,
    historyTitle: "Document History",
    historyNote: "Downloads from your history are always free.",
    historyEmpty: "No parsing or translation history found yet.",
    historyError: "Failed to load history: "
  },
  zh: {
    title: "Mdtero \u8D26\u6237",
    subtitle: "\u767B\u5F55\u90AE\u7BB1\u3001\u67E5\u770B\u989D\u5EA6\uFF0C\u5E76\u7BA1\u7406\u504F\u597D\u8BBE\u7F6E\u3002",
    notSignedIn: "\u5C1A\u672A\u767B\u5F55\u3002",
    usagePending: "\u767B\u5F55\u540E\u53EF\u67E5\u770B\u989D\u5EA6\u3002",
    signedIn: (email) => `\u5DF2\u767B\u5F55\uFF1A${email}`,
    credits: (amount) => `\u5269\u4F59\u989D\u5EA6\uFF1A${amount}`,
    email: "\u90AE\u7BB1",
    sendCode: "\u53D1\u9001\u9A8C\u8BC1\u7801",
    verifyLogin: "\u9A8C\u8BC1\u767B\u5F55",
    code: "\u9A8C\u8BC1\u7801",
    uiLanguage: "\u754C\u9762\u8BED\u8A00",
    advanced: "\u9AD8\u7EA7\u8BBE\u7F6E",
    elsevierApiKey: "Elsevier API Key",
    apiUrl: "API \u5730\u5740",
    save: "\u4FDD\u5B58",
    sent: (email) => `\u9A8C\u8BC1\u7801\u5DF2\u53D1\u9001\u5230 ${email}\u3002`,
    historyTitle: "\u5386\u53F2\u6587\u6863",
    historyNote: "\u4ECE\u5386\u53F2\u8BB0\u5F55\u4E0B\u8F7D\u5185\u5BB9\u6C38\u8FDC\u514D\u8D39\uFF0C\u4E0D\u6263\u9664\u989D\u5EA6\u3002",
    historyEmpty: "\u6682\u65E0\u89E3\u6790\u6216\u7FFB\u8BD1\u8BB0\u5F55\u3002",
    historyError: "\u52A0\u8F7D\u5386\u53F2\u6587\u6863\u5931\u8D25\uFF1A"
  }
};
var titleEl = document.querySelector("#settings-title");
var subtitleEl = document.querySelector("#settings-subtitle");
var languageToggleEl = document.querySelector("#language-toggle");
var elsevierApiKeyInput = document.querySelector("#elsevier-api-key");
var apiBaseUrlInput = document.querySelector("#api-base-url");
var emailInput = document.querySelector("#email-input");
var codeInput = document.querySelector("#code-input");
var uiLanguageSelect = document.querySelector("#ui-language");
var accountStatus = document.querySelector("#account-status");
var usageStatus = document.querySelector("#usage-status");
var saveButton = document.querySelector("#save-settings");
var sendCodeButton = document.querySelector("#send-code");
var verifyButton = document.querySelector("#verify-code");
var emailLabel = document.querySelector("#email-label");
var codeLabel = document.querySelector("#code-label");
var uiLanguageLabel = document.querySelector("#ui-language-label");
var advancedSummary = document.querySelector("#advanced-summary");
var elsevierApiKeyLabel = document.querySelector("#elsevier-api-key-label");
var apiBaseUrlLabel = document.querySelector("#api-base-url-label");
var historySection = document.querySelector("#history-section");
var historyList = document.querySelector("#history-list");
var historyTitle = document.querySelector("#history-title");
var historyNote = document.querySelector("#history-note");
var refreshHistoryBtn = document.querySelector("#refresh-history");
var client = createApiClient(readSettings);
var uiLanguage = "en";
function copyFor(language) {
  return COPY[language];
}
function toggleLanguageLabel(language) {
  return language === "en" ? "\u4E2D\u6587" : "EN";
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
  if (historyTitle) historyTitle.textContent = copy.historyTitle || "Document History";
  if (historyNote) historyNote.textContent = copy.historyNote || "Downloads from your history are always free.";
}
async function refreshHistory() {
  if (!historyList) return;
  const copy = copyFor(uiLanguage);
  try {
    const { items } = await client.getMyTasks();
    if (items.length === 0) {
      historyList.innerHTML = `<p class="meta-label">${copy.historyEmpty || "No history found."}</p>`;
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
      const rawTask = task;
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
          dlBtn.textContent = `\u2B07 ${key.replace("paper_", "").toUpperCase()}`;
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
              dlBtn.textContent = `\u2B07 ${key.replace("paper_", "").toUpperCase()}`;
            } catch (err) {
              alert("Download failed: " + err.message);
              dlBtn.textContent = `\u2B07 ${key.replace("paper_", "").toUpperCase()}`;
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
    const errorPrefix = copy.historyError || "Failed to load history: ";
    historyList.innerHTML = `<p class="meta-label" style="color: #f44336;">${errorPrefix}${error.message}</p>`;
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
    accountStatus.textContent = settings.email ? copyFor(uiLanguage).signedIn(settings.email) : copyFor(uiLanguage).notSignedIn;
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
      usageStatus.textContent = error.message;
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
      elsevierApiKey: elsevierApiKeyInput?.value.trim() || void 0,
      apiBaseUrl: apiBaseUrlInput?.value.trim() || current.apiBaseUrl,
      uiLanguage: resolveUiLanguage(uiLanguageSelect?.value, globalThis.navigator?.language)
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
    accountStatus.textContent = error.message;
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
    accountStatus.textContent = error.message;
  }
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
