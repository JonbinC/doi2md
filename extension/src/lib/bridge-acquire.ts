import type {
  BrowserBridgeAcquireRequest,
  BrowserBridgeAcquireResponse
} from "./browser-bridge";
import type { PageCaptureFailureContext } from "./page-capture";

interface TabsApiLike {
  create(createProperties: { url: string; active?: boolean }): Promise<{ id?: number; url?: string }>;
  get?(tabId: number): Promise<{ id?: number; status?: string; url?: string }>;
  update?(
    tabId: number,
    updateProperties: { url?: string; active?: boolean }
  ): Promise<{ id?: number; url?: string }>;
  sendMessage(tabId: number, message: unknown): Promise<unknown>;
  onUpdated: {
    addListener(listener: (tabId: number, changeInfo: { status?: string }) => void): void;
    removeListener(listener: (tabId: number, changeInfo: { status?: string }) => void): void;
  };
}

interface ChromeApiLike {
  tabs: TabsApiLike;
}

interface PerformBridgeAcquireOptions {
  request: BrowserBridgeAcquireRequest;
  chromeApi: ChromeApiLike;
  bridgeSession?: {
    tabId?: number | null;
    pageTabId?: number | null;
  };
}

interface ContentCaptureResponse {
  ok: boolean;
  capture?: {
    ok: boolean;
    html?: string;
    payloadName?: string;
    sourceUrl?: string;
    pageTitle?: string;
    failureCode?: string;
    failureMessage?: string;
    failureContext?: PageCaptureFailureContext;
  };
  download?: {
    ok: boolean;
    payloadBase64?: string;
    payloadName?: string;
    sourceUrl?: string;
    failureCode?: string;
    failureMessage?: string;
  };
  xml?: {
    ok: boolean;
    payloadText?: string;
    payloadName?: string;
    sourceUrl?: string;
    failureCode?: string;
    failureMessage?: string;
  };
}

interface OpenAcquisitionTabResult {
  tabId: number | null | undefined;
  acceptAlreadyComplete: boolean;
  previousUrl?: string;
}

const CONTENT_SCRIPT_MESSAGE_TIMEOUT_MS = 2000;

export async function performBridgeAcquire(
  options: PerformBridgeAcquireOptions
): Promise<BrowserBridgeAcquireResponse> {
  const { request, chromeApi, bridgeSession } = options;
  const pageLoadMs = getBridgeTimeoutMs(request.timeouts?.page_load_ms, 30000);
  const settleMs = getBridgeTimeoutMs(request.timeouts?.settle_ms, 0);
  if (request.action === "capture_current_tab") {
    const activeTabId = bridgeSession?.pageTabId ?? bridgeSession?.tabId;
    if (!activeTabId) {
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: "tab_open_failed",
        failure_message: "No active bridge tab is available for current-tab capture."
      };
    }
    let response: ContentCaptureResponse | undefined;
    try {
      response = (await sendTabMessageWithRetry(chromeApi.tabs, activeTabId, {
        type: "mdtero.capture_current_tab.request"
      })) as ContentCaptureResponse | undefined;
    } catch {
      const finalTabUrl = await getTabUrl(chromeApi.tabs, activeTabId);
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: "content_script_unavailable",
        failure_message: buildUnavailableContentScriptMessage({
          baseMessage: "Current-tab capture did not succeed.",
          finalTabUrl
        })
      };
    }
    if (!response?.ok || !response.capture?.ok) {
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: response?.capture?.failureCode || "content_script_unavailable",
        failure_message: response?.capture?.failureMessage || "Current-tab capture did not succeed."
      };
    }
    return {
      task_id: request.task_id,
      status: "succeeded",
      connector: request.connector,
      artifact_kind: "html",
      payload_name: response.capture.payloadName || "paper.html",
      payload_text: response.capture.html || "",
      source_url: response.capture.sourceUrl,
      page_title: response.capture.pageTitle
    };
  }

  if (request.action === "open_and_fetch_xml") {
    const targetUrl = resolveTargetUrl(request.input, request.source_url);
    const opened = await openAcquisitionTab(chromeApi.tabs, targetUrl, bridgeSession);
    const tabId = opened.tabId;
    if (!tabId) {
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: "tab_open_failed",
        failure_message: "Browser opened the target page without a usable tab id."
      };
    }
    const xmlTabLoadResult = await waitForTabComplete(chromeApi.tabs, tabId, pageLoadMs, {
      acceptAlreadyComplete: opened.acceptAlreadyComplete,
      previousUrl: opened.previousUrl
    });
    if (!xmlTabLoadResult.ok) {
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: "tab_load_timeout",
        failure_message: buildUnavailableContentScriptMessage({
          baseMessage: xmlTabLoadResult.errorMessage,
          finalTabUrl: xmlTabLoadResult.finalTabUrl
        })
      };
    }
    await delay(settleMs);
    let response: ContentCaptureResponse | undefined;
    try {
      response = (await sendTabMessageWithRetry(chromeApi.tabs, tabId, {
        type: "mdtero.fetch_xml.request",
        artifactUrl: request.artifact_url,
        sourceUrl: request.source_url
      })) as ContentCaptureResponse | undefined;
    } catch {
      const finalTabUrl = await getTabUrl(chromeApi.tabs, tabId);
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: "content_script_unavailable",
        failure_message: buildUnavailableContentScriptMessage({
          baseMessage: "Page hook did not return a usable XML payload.",
          finalTabUrl
        })
      };
    }
    if (!response?.ok || !response.xml) {
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: "content_script_unavailable",
        failure_message: "Page hook did not return a usable XML payload."
      };
    }
    if (!response.xml.ok || !response.xml.payloadText) {
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: response.xml.failureCode || "artifact_download_missing",
        failure_message: response.xml.failureMessage || "Browser page context could not download the XML artifact."
      };
    }
    return {
      task_id: request.task_id,
      status: "succeeded",
      connector: request.connector,
      artifact_kind: "structured_xml",
      payload_name: response.xml.payloadName || "paper.xml",
      payload_text: response.xml.payloadText,
      source_url: response.xml.sourceUrl || targetUrl
    };
  }

  if (request.action === "open_and_download_epub") {
    const artifactUrl = resolveArtifactUrl(request);
    const targetUrl = resolveEpubTargetUrl(request);
    const opened = await openAcquisitionTab(chromeApi.tabs, targetUrl, bridgeSession);
    const tabId = opened.tabId;
    if (!tabId) {
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: "tab_open_failed",
        failure_message: "Browser opened the target page without a usable tab id."
      };
    }

    const epubTabLoadResult = await waitForTabComplete(chromeApi.tabs, tabId, pageLoadMs, {
      acceptAlreadyComplete: opened.acceptAlreadyComplete,
      previousUrl: opened.previousUrl
    });
    if (!epubTabLoadResult.ok) {
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: "tab_load_timeout",
        failure_message: buildUnavailableContentScriptMessage({
          baseMessage: epubTabLoadResult.errorMessage,
          finalTabUrl: epubTabLoadResult.finalTabUrl
        })
      };
    }
    await delay(settleMs);

    let response: ContentCaptureResponse | undefined;
    try {
      response = (await sendTabMessageWithRetry(
        chromeApi.tabs,
        tabId,
        {
          type: "mdtero.download_epub.request",
          artifactUrl
        }
      )) as ContentCaptureResponse | undefined;
    } catch {
      const finalTabUrl = await getTabUrl(chromeApi.tabs, tabId);
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: "content_script_unavailable",
        failure_message: buildUnavailableContentScriptMessage({
          baseMessage: "Page hook did not return a usable EPUB payload.",
          finalTabUrl
        })
      };
    }

    if (!response?.ok || !response.download) {
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: "content_script_unavailable",
        failure_message: "Page hook did not return a usable EPUB payload."
      };
    }

    if (!response.download.ok || !response.download.payloadBase64) {
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: response.download.failureCode || "artifact_download_missing",
        failure_message:
          response.download.failureMessage || "Browser page context could not download the EPUB artifact."
      };
    }

    return {
      task_id: request.task_id,
      status: "succeeded",
      connector: request.connector,
      artifact_kind: "epub",
      payload_name: response.download.payloadName || "paper.epub",
      payload_base64: response.download.payloadBase64,
      source_url: response.download.sourceUrl || artifactUrl
    };
  }

  if (request.action !== "open_and_capture_html") {
    throw new Error(`Unsupported bridge action: ${request.action}`);
  }

  const targetUrl = resolveTargetUrl(request.input, request.source_url);
  const opened = await openAcquisitionTab(chromeApi.tabs, targetUrl, bridgeSession);
  const tabId = opened.tabId;
  if (!tabId) {
    return {
      task_id: request.task_id,
      status: "failed",
      connector: request.connector,
      failure_code: "tab_open_failed",
      failure_message: "Browser opened the target page without a usable tab id."
    };
  }

  const htmlTabLoadResult = await waitForTabComplete(chromeApi.tabs, tabId, pageLoadMs, {
    acceptAlreadyComplete: opened.acceptAlreadyComplete,
    previousUrl: opened.previousUrl
  });
  if (!htmlTabLoadResult.ok) {
    return {
      task_id: request.task_id,
      status: "failed",
      connector: request.connector,
      failure_code: "tab_load_timeout",
      failure_message: buildUnavailableContentScriptMessage({
        baseMessage: htmlTabLoadResult.errorMessage,
        finalTabUrl: htmlTabLoadResult.finalTabUrl
      })
    };
  }
  await delay(settleMs);

  let response: ContentCaptureResponse | undefined;
  try {
    response = (await sendTabMessageWithRetry(chromeApi.tabs, tabId, {
      type: "mdtero.capture_html.request"
    })) as ContentCaptureResponse | undefined;
  } catch {
    response = undefined;
  }

  if (!response?.ok || !response.capture) {
    const finalTabUrl = await getTabUrl(chromeApi.tabs, tabId);
    return {
      task_id: request.task_id,
      status: "failed",
      connector: request.connector,
      failure_code: "content_script_unavailable",
      failure_message: buildUnavailableContentScriptMessage({
        baseMessage: "Capture hook did not return a usable article payload.",
        finalTabUrl
      })
    };
  }

  if (!response.capture.ok) {
    return {
      task_id: request.task_id,
      status: "failed",
      connector: request.connector,
      failure_code: response.capture.failureCode || "article_body_missing",
      failure_message:
        response.capture.failureMessage || "Page loaded but article capture did not succeed.",
      failure_context: response.capture.failureContext
    };
  }

  return {
    task_id: request.task_id,
    status: "succeeded",
    connector: request.connector,
    artifact_kind: "html",
    payload_name: response.capture.payloadName || "paper.html",
    payload_text: response.capture.html || "",
    source_url: response.capture.sourceUrl,
    page_title: response.capture.pageTitle
  };
}

async function openAcquisitionTab(
  tabs: TabsApiLike,
  targetUrl: string,
  bridgeSession?: { tabId?: number | null; pageTabId?: number | null }
): Promise<OpenAcquisitionTabResult> {
  const created = await tabs.create({ url: targetUrl, active: false });
  if (bridgeSession) {
    bridgeSession.tabId = created.id ?? null;
  }
  return {
    tabId: created.id,
    acceptAlreadyComplete: true
  };
}

async function sendTabMessageWithRetry(
  tabs: TabsApiLike,
  tabId: number,
  message: unknown,
  maxAttempts = 4
) {
  let lastError: unknown = null;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    try {
      return await sendTabMessageWithTimeout(tabs, tabId, message, CONTENT_SCRIPT_MESSAGE_TIMEOUT_MS);
    } catch (error) {
      lastError = error;
      if (!isRetryableContentScriptError(error) || attempt === maxAttempts - 1) {
        break;
      }
      await delay(250 * (attempt + 1));
    }
  }
  throw lastError instanceof Error ? lastError : new Error("Content script did not become available.");
}

async function sendTabMessageWithTimeout(
  tabs: TabsApiLike,
  tabId: number,
  message: unknown,
  timeoutMs: number
) {
  let timeoutHandle: ReturnType<typeof globalThis.setTimeout> | null = null;
  try {
    return await Promise.race([
      tabs.sendMessage(tabId, message),
      new Promise<never>((_, reject) => {
        timeoutHandle = globalThis.setTimeout(() => {
          reject(new Error("Content script response timed out."));
        }, timeoutMs);
      })
    ]);
  } finally {
    if (timeoutHandle !== null) {
      globalThis.clearTimeout(timeoutHandle);
    }
  }
}

async function getTabUrl(tabs: TabsApiLike, tabId: number) {
  if (typeof tabs.get !== "function") {
    return "";
  }
  try {
    return String((await tabs.get(tabId))?.url || "").trim();
  } catch {
    return "";
  }
}

function buildUnavailableContentScriptMessage(options: {
  baseMessage: string;
  finalTabUrl?: string;
}) {
  const baseMessage = String(options.baseMessage || "").trim() || "Content script did not become available.";
  const finalTabUrl = String(options.finalTabUrl || "").trim();
  if (!finalTabUrl) {
    return baseMessage;
  }
  return `${baseMessage} Final tab URL: ${finalTabUrl}`;
}

function isRetryableContentScriptError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error || "");
  const lowered = message.toLowerCase();
  return (
    lowered.includes("receiving end does not exist") ||
    lowered.includes("could not establish connection") ||
    lowered.includes("message port closed") ||
    lowered.includes("response timed out")
  );
}

function delay(ms: number) {
  return new Promise<void>((resolve) => {
    globalThis.setTimeout(resolve, ms);
  });
}

function getBridgeTimeoutMs(value: unknown, fallbackMs: number) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 0) {
    return fallbackMs;
  }
  return Math.floor(numeric);
}

function resolveArtifactUrl(request: BrowserBridgeAcquireRequest): string {
  const artifactUrl = String(request.artifact_url || "").trim();
  if (artifactUrl) {
    return artifactUrl;
  }
  throw new Error("Bridge download request is missing an artifact URL.");
}

function resolveTargetUrl(input?: string, sourceUrl?: string | null): string {
  const trimmedSource = String(sourceUrl || "").trim();
  if (trimmedSource) {
    return trimmedSource;
  }
  const trimmedInput = String(input || "").trim();
  if (!trimmedInput) {
    throw new Error("Bridge acquisition request is missing an input URL or DOI.");
  }
  if (/^https?:\/\//i.test(trimmedInput)) {
    return trimmedInput;
  }
  return `https://doi.org/${trimmedInput}`;
}

function resolveEpubTargetUrl(request: BrowserBridgeAcquireRequest): string {
  const sourceUrl = String(request.source_url || "").trim();
  if (sourceUrl) {
    return sourceUrl;
  }

  const artifactUrl = String(request.artifact_url || "").trim();
  if (artifactUrl.includes("/doi/epub/")) {
    return artifactUrl.replace("/doi/epub/", "/doi/full/").replace(/[?].*$/, "");
  }

  if (artifactUrl) {
    return artifactUrl;
  }

  return resolveTargetUrl(request.input, request.source_url);
}

function waitForTabComplete(
  tabs: TabsApiLike,
  tabId: number,
  timeoutMs: number,
  options?: {
    acceptAlreadyComplete?: boolean;
    previousUrl?: string;
  }
) {
  return new Promise<{ ok: true } | { ok: false; errorMessage: string; finalTabUrl?: string }>((resolve) => {
    const timeout = globalThis.setTimeout(() => {
      void getTabUrl(tabs, tabId).then((finalTabUrl) => {
        resolveIfPending({
          ok: false,
          errorMessage: "Timed out waiting for tab load completion.",
          finalTabUrl
        });
      });
    }, timeoutMs);

    let settled = false;

    const resolveIfPending = (result: { ok: true } | { ok: false; errorMessage: string; finalTabUrl?: string }) => {
      if (settled) {
        return;
      }
      settled = true;
      globalThis.clearTimeout(timeout);
      tabs.onUpdated.removeListener(handleUpdate);
      resolve(result);
    };

    const handleUpdate = (updatedTabId: number, changeInfo: { status?: string }) => {
      if (updatedTabId !== tabId) {
        return;
      }
      if (changeInfo.status === "complete") {
        if (!options?.previousUrl) {
          resolveIfPending({ ok: true });
          return;
        }
        void maybeResolveCompletedState();
      }
    };

    tabs.onUpdated.addListener(handleUpdate);

    if (options?.acceptAlreadyComplete !== false) {
      void maybeResolveCompletedState();
    }

    async function maybeResolveCompletedState() {
      const tab = await getTabDetails(tabs, tabId);
      if (tab?.status !== "complete") {
        return;
      }
      const currentUrl = String(tab.url || "").trim();
      const previousUrl = String(options?.previousUrl || "").trim();
      if (previousUrl && currentUrl === previousUrl) {
        return;
      }
      resolveIfPending({ ok: true });
    }
  });
}

async function isTabAlreadyComplete(tabs: TabsApiLike, tabId: number) {
  if (typeof tabs.get !== "function") {
    return false;
  }
  try {
    const tab = await tabs.get(tabId);
    return tab?.status === "complete";
  } catch {
    return false;
  }
}

async function getTabDetails(tabs: TabsApiLike, tabId: number) {
  if (typeof tabs.get !== "function") {
    return null;
  }
  try {
    return await tabs.get(tabId);
  } catch {
    return null;
  }
}
