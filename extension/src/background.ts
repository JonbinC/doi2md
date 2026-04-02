import { createApiClient, createRouterSSOTClient } from "./lib/api";
import {
  type BrowserBridgeAcquireRequest,
  initializeBrowserBridge
} from "./lib/browser-bridge";
import { performBridgeAcquire } from "./lib/bridge-acquire";
import { isBridgeSupportedPage } from "./lib/bridge-wake";
import {
  runLegacyFileParseRequest,
  runLegacyParseRequest,
} from "./lib/legacy-parse";
import { buildSourceConnectivityObservation } from "./lib/source-connectivity-observation";
import { executeSsotActionSequence, fetchRoutePlanFromSsot } from "./lib/ssot-route";
import { readSettings, writeSettings } from "./lib/storage";

const client = createApiClient(readSettings);
const routerSSOT = createRouterSSOTClient(readSettings);
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
    const status = browserBridge
      ? browserBridge.getStatus()
      : {
          state: "unavailable",
          runnerState: "idle"
        };
    sendResponse({
      ok: true,
      result: status
    });
    return false;
  }

  if (message?.type === "mdtero.source_connectivity.observation") {
    const status = browserBridge
      ? browserBridge.getStatus()
      : {
          state: "unavailable",
          runnerState: "idle"
        };
    sendResponse({
      ok: true,
      result: buildSourceConnectivityObservation(status)
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

  // Router SSOT: new canonical routing via backend
  if (message?.type === "mdtero.parse.ssot.request") {
    (async () => {
      const settings = await readSettings();
      if (!settings.token) {
        throw new Error("Sign in required before parsing or translating.");
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
          springerOpenAccessApiKey: settings.springerOpenAccessApiKey,
          elsevierApiKey: settings.elsevierApiKey,
        }
      );

      if (result.success && result.taskId) {
        return { task_id: result.taskId };
      }

      throw new Error(result.error || "Action sequence failed");
    })()
    .then((result) => sendResponse({ ok: true, result }))
    .catch((error: Error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  // Legacy routing with optional SSOT fallback
  if (message?.type === "mdtero.parse.request") {
    (async () => {
      const settings = await readSettings();
      if (!settings.token) {
        throw new Error("Sign in required before parsing or translating.");
      }
      return runLegacyParseRequest(client, {
        input: message.input,
        elsevierApiKey: message.elsevierApiKey,
        springerOpenAccessApiKey: settings.springerOpenAccessApiKey,
        pageContext: message.pageContext,
      });
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
      return runLegacyFileParseRequest(client, {
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
