import { createApiClient, createRouterSSOTClient } from "./lib/api";
import { buildCliFileParseCommand } from "./lib/cli-handoff";
import { PROXY_FEATURES_ENABLED } from "./lib/features";
import { runBrowserFileParseRequest } from "./lib/file-upload";
import type { LocalFileArtifactKind } from "./lib/runtime";
import { executeSsotActionSequence, fetchRoutePlanFromSsot } from "./lib/ssot-route";
import { readSettings, SETTINGS_KEY, writeSettings } from "./lib/storage";
import { sendTabMessageWithInjection } from "./lib/tab-messaging";

const client = createApiClient(readSettings);
const routerSSOT = createRouterSSOTClient(readSettings);

async function ensureNetworkPolicy(settings?: Awaited<ReturnType<typeof readSettings>>) {
  if (!PROXY_FEATURES_ENABLED) {
    return;
  }
  const { applyProxySettings, assertCampusProxyIfRequired } = await import("./lib/proxy-sync");
  const resolved = settings ?? await readSettings();
  await applyProxySettings(resolved);
  await assertCampusProxyIfRequired(resolved);
}

if (PROXY_FEATURES_ENABLED) {
  void import("./lib/proxy-sync").then(({ applyProxySettings }) =>
    readSettings().then((settings) => applyProxySettings(settings))
  );

  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName !== "local" || !changes[SETTINGS_KEY]) {
      return;
    }
    void import("./lib/proxy-sync").then(({ applyProxySettings }) =>
      readSettings().then((settings) => applyProxySettings(settings))
    );
  });
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "mdtero.auth.save_token") {
    readSettings().then(settings => {
      return writeSettings({
        ...settings,
        token: message.token,
        email: message.email
      });
    }).then(() => sendResponse({ ok: true }))
      .catch((error: Error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  // Router SSOT: new canonical routing via backend
  if (message?.type === "mdtero.parse.ssot.request") {
    (async () => {
      const settings = await readSettings();
      await ensureNetworkPolicy(settings);
      if (!settings.token) {
        throw new Error("Sign in required before parsing or translating.");
      }

      if (shouldTryCurrentPagePdf(message.input, message.pageContext?.tabUrl)) {
        const currentPagePdfResult = await tryCurrentPagePdfParse(message.input, message.pageContext);
        if (currentPagePdfResult) {
          return currentPagePdfResult;
        }
      }

      // Fetch canonical route plan from backend SSOT
      const routePlan = await fetchRoutePlanFromSsot(
        routerSSOT,
        message.input,
        message.pageContext?.tabUrl ? {
          tabUrl: message.pageContext.tabUrl,
          tabTitle: message.pageContext.tabTitle,
        } : undefined
      );

      const result = await executeSsotActionSequence(
        client,
        routePlan,
        {
          tabId: message.pageContext?.tabId,
          tabUrl: message.pageContext?.tabUrl,
          tabTitle: message.pageContext?.tabTitle,
          input: message.input,
          elsevierApiKey: settings.elsevierApiKey,
        }
      );

      if (result.success && result.taskId) {
        return result.task ?? { task_id: result.taskId };
      }

      return {
        ok: false,
        error: formatSsotFailure(result),
        nextCommand: result.nextCommand,
      };
    })()
    .then((result) => {
      if (result && typeof result === "object" && "ok" in result && result.ok === false) {
        sendResponse(result);
        return;
      }
      sendResponse({ ok: true, result });
    })
    .catch((error: Error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  if (message?.type === "mdtero.parse.file.request") {
    (async () => {
      const settings = await readSettings();
      await ensureNetworkPolicy(settings);
      if (!settings.token) {
        throw new Error("Sign in required before parsing or translating.");
      }
      if (!message.file) {
        throw new Error("No local file was provided.");
      }
      return runBrowserFileParseRequest(client, {
        file: message.file,
        filename: message.filename,
        artifactKind: message.artifactKind
      });
    })()
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error: Error) =>
        sendResponse({
          ok: false,
          error: error.message,
          nextCommand: buildFileParseCommand(message.filename, message.artifactKind),
        })
      );
    return true;
  }

  if (message?.type === "mdtero.parse.current_html.request") {
    (async () => {
      const settings = await readSettings();
      await ensureNetworkPolicy(settings);
      if (!settings.token) {
        throw new Error("Sign in required before parsing or translating.");
      }
      const tabId = message.pageContext?.tabId;
      if (!tabId) {
        throw new Error("Open the full-text article page in the current tab before HTML capture.");
      }
      const response = await sendTabMessageWithInjection(tabId, {
        type: "mdtero.capture_html.request",
      });
      const capture = response?.capture;
      if (!response?.ok || !capture?.ok || !capture.html) {
        throw new Error(capture?.failureMessage || "Current-page HTML capture failed.");
      }
      return client.createRawUploadTask({
        rawFile: new Blob([capture.html], { type: "text/html" }),
        filename: capture.payloadName || "paper.html",
        sourceDoi: inferSourceDoi(message.input),
        sourceInput: message.input || capture.sourceUrl || message.pageContext?.tabUrl,
        artifactKind: "html",
      });
    })()
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error: Error) =>
        sendResponse({
          ok: false,
          error: error.message,
          nextCommand: buildCliFileParseCommand("paper.html", "html"),
        })
      );
    return true;
  }

  if (message?.type === "mdtero.task.get") {
    client
      .getTask(message.taskId, { etag: message.etag })
      .then((result) => sendResponse({ ok: true, ...result }))
      .catch((error: Error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  if (message?.type === "mdtero.translate.request") {
    (async () => {
      const settings = await readSettings();
      await ensureNetworkPolicy(settings);
      if (!settings.token) {
        throw new Error("Sign in required before parsing or translating.");
      }
      if (message.sourceMarkdownPath) {
        return client.createTranslateTask({
          source_markdown_path: message.sourceMarkdownPath,
          target_language: message.targetLanguage,
          mode: message.mode
        });
      }
      if (!message.sourceTaskId || !message.sourceArtifactKey) {
        throw new Error("Parse a paper to Markdown first; no source Markdown artifact is available for translation.");
      }
      const artifact = await client.downloadArtifact(
        message.sourceTaskId,
        message.sourceArtifactKey,
        message.sourceFilename
      );
      const sourceMarkdownText = await artifact.blob.text();
      if (!sourceMarkdownText.trim()) {
        throw new Error("The Markdown artifact is empty and cannot be translated.");
      }
      return client.createTranslateTask({
        source_markdown_path: "",
        source_markdown_text: sourceMarkdownText,
        source_markdown_filename: artifact.filename || message.sourceFilename || "paper.md",
        target_language: message.targetLanguage,
        mode: message.mode
      });
    })()
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error: Error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  if (PROXY_FEATURES_ENABLED && message?.type === "mdtero.proxy.test.request") {
    (async () => {
      const { applyProxySettings, verifyCampusProxyOutlet } = await import("./lib/proxy-sync");
      const settings = await readSettings();
      await applyProxySettings(settings);
      return verifyCampusProxyOutlet();
    })()
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error: Error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  return false;
});

function formatSsotFailure(result: {
  error?: string;
  nextCommand?: string;
  requiresBrowserCapture?: boolean;
  requiresUpload?: boolean;
}) {
  if (result.requiresBrowserCapture) {
    return result.error || "Open the article page in this browser, make sure the full text is loaded, then retry current-page parse or upload the PDF/EPUB directly.";
  }
  if (result.requiresUpload) {
    return result.error || "Upload the PDF/EPUB/XML/HTML file directly so Mdtero can parse it.";
  }
  return result.error || "Action sequence failed";
}

function buildFileParseCommand(filename?: string, artifactKind?: LocalFileArtifactKind) {
  return buildCliFileParseCommand(filename, artifactKind);
}

function inferSourceDoi(input?: string): string | undefined {
  const trimmed = String(input || "").trim();
  return /^10\.\S+/i.test(trimmed) ? trimmed : undefined;
}

function shouldTryCurrentPagePdf(input?: string, tabUrl?: string): boolean {
  return isCnkiArticleUrl(input) || isCnkiArticleUrl(tabUrl) || isIeeeArticleUrl(input) || isIeeeArticleUrl(tabUrl);
}

function isCnkiArticleUrl(value?: string): boolean {
  try {
    const parsed = new URL(String(value || ""));
    return parsed.hostname.endsWith("cnki.net") && /\/kcms2\/article\/(?:abstract|detail)/i.test(parsed.pathname);
  } catch {
    return false;
  }
}

function isIeeeArticleUrl(value?: string): boolean {
  try {
    const parsed = new URL(String(value || ""));
    return parsed.hostname.endsWith("ieeexplore.ieee.org") && /\/(?:abstract\/)?document\/\d+|\/stamp\/stamp\.jsp|\/stampPDF\/getPDF\.jsp/i.test(parsed.pathname);
  } catch {
    return false;
  }
}

async function tryCurrentPagePdfParse(
  input: string,
  pageContext?: { tabId?: number; tabUrl?: string }
) {
  const tabId = pageContext?.tabId;
  if (!tabId) {
    return null;
  }
  const response = await sendTabMessageWithInjection(tabId, {
    type: "mdtero.download_current_page_pdf.request",
  });
  const download = response?.download;
  if (!response?.ok || !download?.ok || !download.payloadBase64) {
    return null;
  }
  return client.createRawUploadTask({
    rawFile: new Blob([base64ToBytes(download.payloadBase64)], { type: "application/pdf" }),
    filename: download.payloadName || "paper.pdf",
    sourceDoi: inferSourceDoi(input),
    sourceInput: input || download.sourceUrl || pageContext?.tabUrl,
    artifactKind: "pdf",
  });
}

function base64ToBytes(payloadBase64: string): Uint8Array {
  const decoded = globalThis.atob(payloadBase64);
  const bytes = new Uint8Array(decoded.length);
  for (let index = 0; index < decoded.length; index += 1) {
    bytes[index] = decoded.charCodeAt(index);
  }
  return bytes;
}
