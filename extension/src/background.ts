import { createApiClient } from "./lib/api";
import type { PdfEngine } from "@mdtero/shared";
import {
  type BrowserBridgeAcquireRequest,
  initializeBrowserBridge
} from "./lib/browser-bridge";
import { performBridgeAcquire } from "./lib/bridge-acquire";
import { isBridgeSupportedPage } from "./lib/bridge-wake";
import {
  buildElsevierLocalAcquireGuidance,
  fetchElsevierXml,
  requiresElsevierLocalAcquire
} from "./lib/elsevier";
import { fetchSpringerOpenAccessJats, normalizeSpringerInput } from "./lib/springer";
import {
  buildHelperBundleBlob,
  inferBrowserHelperBundleAccess,
  inferBrowserHelperBundleConnector
} from "./lib/helper-bundle";
import { readSettings, writeSettings } from "./lib/storage";

const client = createApiClient(readSettings);
const bridgeSession: { tabId?: number | null; pageTabId?: number | null } = {};
let browserBridge =
  typeof chrome !== "undefined" && chrome.runtime?.connectNative
    ? initializeBrowserBridge({
        runtime: chrome.runtime,
        alarms: chrome.alarms,
        runtimeId: chrome.runtime.id,
        acquire: handleBridgeAcquire
      })
    : null;

async function handleBridgeAcquire(request: BrowserBridgeAcquireRequest) {
  return performBridgeAcquire({
    request,
    chromeApi: chrome,
    bridgeSession
  });
}

function inferSourceDoi(input: string): string | undefined {
  const trimmed = String(input || "").trim();
  return /^10\.\S+/i.test(trimmed) ? trimmed : undefined;
}

function describeCurrentTabCaptureFailure(params: {
  failureCode?: string;
  failureMessage?: string;
}) {
  const failureCode = String(params.failureCode || "").trim().toLowerCase();
  const failureMessage = String(params.failureMessage || "").trim();

  if (failureCode === "login_required") {
    return "This page still requires institutional or account sign-in. Open the article in your browser, finish login, then retry capture.";
  }
  if (failureCode === "challenge_page_detected") {
    return "This page is still behind a browser challenge. Finish the verification in the page, wait for the article to load, then retry capture.";
  }
  if (failureCode === "article_body_missing") {
    return "No article body was detected on the current page. Open the HTML full-text page instead of a PDF or download shell, then retry capture.";
  }
  if (failureCode === "content_script_unavailable") {
    return "Browser page capture is not ready yet. Reload the paper page or reopen the extension, then try again.";
  }

  return failureMessage || "Browser page capture did not succeed on the current page.";
}

async function tryCreateCurrentTabHelperBundleTask(message: {
  input: string;
  springerOpenAccessApiKey?: string;
  pageContext?: {
    tabId?: number;
    tabUrl?: string;
  };
}) {
  const tabId = message.pageContext?.tabId;
  if (!tabId) {
    return null;
  }

  const response = await chrome.tabs.sendMessage(tabId, {
    type: "mdtero.capture_current_tab.request",
    springerOpenAccessApiKey: message.springerOpenAccessApiKey
  });
  if (response?.xml?.ok && response.xml.payloadText) {
    return client.createParseFulltextV2Task({
      fulltextFile: new Blob([response.xml.payloadText], { type: "application/xml" }),
      filename: response.xml.payloadName || "paper.xml",
      sourceDoi: inferSourceDoi(message.input) || normalizeSpringerInput(message.input, message.pageContext?.tabUrl) || undefined,
      sourceInput: message.input
    });
  }
  const capture = response?.capture;
  if (!response?.ok) {
    throw new Error(
      describeCurrentTabCaptureFailure({
        failureCode: "content_script_unavailable"
      })
    );
  }
  if (!capture?.ok || !capture.html) {
    throw new Error(
      describeCurrentTabCaptureFailure({
        failureCode: capture?.failureCode,
        failureMessage: capture?.failureMessage
      })
    );
  }

  const connector = inferBrowserHelperBundleConnector(message.input, message.pageContext?.tabUrl || capture.sourceUrl);
  const helperBundle = buildHelperBundleBlob({
    connector,
    artifactKind: "html",
    payload: capture.html,
    payloadName: capture.payloadName || "paper.html",
    sourceDoi: inferSourceDoi(message.input),
    sourceUrl: message.pageContext?.tabUrl || capture.sourceUrl || undefined,
    access: inferBrowserHelperBundleAccess(connector)
  });

  return client.createParseHelperBundleV2Task({
    helperBundleFile: helperBundle,
    filename: "helper-bundle.zip",
    sourceDoi: inferSourceDoi(message.input),
    sourceInput: message.input
  });
}

async function createLocalFileHelperBundleTask(message: {
  file: Blob;
  filename?: string;
  artifactKind?: "pdf" | "epub";
  pdfEngine?: PdfEngine;
}) {
  const filename = String(message.filename || "").trim() || "paper.bin";
  const artifactKind = message.artifactKind === "epub" ? "epub" : "pdf";
  const sourceType =
    artifactKind === "pdf"
      ? "browser_extension_local_upload_pdf"
      : "browser_extension_local_upload_epub";
  const helperBundle = buildHelperBundleBlob({
    connector: "local_file_upload",
    artifactKind,
    payload: await message.file.arrayBuffer(),
    payloadName: filename,
    sourceType,
    sourceUrl: `file://${filename}`,
    acquisitionMode: "browser_extension_local_upload",
    userPrivateRetention: true
  });

  return client.createParseHelperBundleV2Task({
    helperBundleFile: helperBundle,
    filename: "helper-bundle.zip",
    sourceInput: filename,
    pdfEngine: artifactKind === "pdf" ? message.pdfEngine : undefined
  });
}

chrome.runtime.onStartup?.addListener(() => {
  browserBridge?.ensureConnected();
});

chrome.runtime.onInstalled?.addListener(() => {
  browserBridge?.ensureConnected();
});

chrome.tabs.onUpdated?.addListener((_tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && isBridgeSupportedPage(tab?.url || "")) {
    browserBridge?.ensureConnected();
  }
});

chrome.tabs.onRemoved?.addListener((tabId) => {
  if (bridgeSession.tabId === tabId) {
    bridgeSession.tabId = null;
  }
  if (bridgeSession.pageTabId === tabId) {
    bridgeSession.pageTabId = null;
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "mdtero.bridge.page_ready") {
    const senderTabId = sender?.tab?.id;
    if (typeof senderTabId === "number") {
      bridgeSession.pageTabId = senderTabId;
    }
    browserBridge?.ensureConnected();
    sendResponse({ ok: true });
    return false;
  }

  if (message?.type === "mdtero.bridge.status") {
    sendResponse({
      ok: true,
      result: browserBridge
        ? browserBridge.getStatus()
        : {
            state: "unavailable",
            runnerState: "idle"
          }
    });
    return false;
  }

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

  if (message?.type === "mdtero.parse.request") {
    (async () => {
      const settings = await readSettings();
      if (!settings.token) {
        throw new Error("Sign in required before parsing or translating.");
      }
      if (requiresElsevierLocalAcquire(message.input)) {
        if (!message.elsevierApiKey) {
          throw new Error(buildElsevierLocalAcquireGuidance());
        }
        const uploaded = await fetchElsevierXml(message.input, message.elsevierApiKey);
        const helperBundle = buildHelperBundleBlob({
          connector: "elsevier_article_retrieval_api",
          artifactKind: "structured_xml",
          payload: await uploaded.xmlBlob.arrayBuffer(),
          payloadName: uploaded.filename,
          sourceDoi: uploaded.sourceDoi,
          access: "licensed",
          extraFiles: uploaded.bundleExtraFiles
        });
        return client.createParseHelperBundleV2Task({
          helperBundleFile: helperBundle,
          filename: "helper-bundle.zip",
          sourceDoi: uploaded.sourceDoi,
          sourceInput: uploaded.sourceInput
        });
      }
      const springerSourceDoi = normalizeSpringerInput(message.input, message.pageContext?.tabUrl);
      if (springerSourceDoi && settings.springerOpenAccessApiKey) {
        try {
          const uploaded = await fetchSpringerOpenAccessJats(
            message.input,
            settings.springerOpenAccessApiKey,
            message.pageContext?.tabUrl
          );
          return client.createParseFulltextV2Task({
            fulltextFile: uploaded.xmlBlob,
            filename: uploaded.filename,
            sourceDoi: uploaded.sourceDoi,
            sourceInput: uploaded.sourceInput
          });
        } catch {
        }
      }
      const currentTabBundleTask = await tryCreateCurrentTabHelperBundleTask({
        ...message,
        springerOpenAccessApiKey: settings.springerOpenAccessApiKey
      });
      if (currentTabBundleTask) {
        return currentTabBundleTask;
      }
      return client.createParseTask({ input: message.input });
    })()
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error: Error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  if (message?.type === "mdtero.parse.file.request") {
    (async () => {
      const settings = await readSettings();
      if (!settings.token) {
        throw new Error("Sign in required before parsing or translating.");
      }
      if (!message.file) {
        throw new Error("No local file was provided.");
      }
      return createLocalFileHelperBundleTask({
        file: message.file,
        filename: message.filename,
        artifactKind: message.artifactKind,
        pdfEngine: message.pdfEngine
      });
    })()
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error: Error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  if (message?.type === "mdtero.task.get") {
    client
      .getTask(message.taskId)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error: Error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  if (message?.type === "mdtero.translate.request") {
    (async () => {
      const settings = await readSettings();
      if (!settings.token) {
        throw new Error("Sign in required before parsing or translating.");
      }
      return client.createTranslateTask({
        source_markdown_path: message.sourceMarkdownPath,
        target_language: message.targetLanguage,
        mode: message.mode
      });
    })()
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error: Error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  return false;
});
