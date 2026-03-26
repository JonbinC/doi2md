import type {
  BrowserBridgeAcquireRequest,
  BrowserBridgeAcquireResponse
} from "./browser-bridge";

interface TabsApiLike {
  create(createProperties: { url: string; active?: boolean }): Promise<{ id?: number; url?: string }>;
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
    const response = (await sendTabMessageWithRetry(chromeApi.tabs, activeTabId, {
      type: "mdtero.capture_current_tab.request"
    })) as ContentCaptureResponse | undefined;
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
    const tabId = await openAcquisitionTab(chromeApi.tabs, targetUrl, bridgeSession);
    if (!tabId) {
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: "tab_open_failed",
        failure_message: "Browser opened the target page without a usable tab id."
      };
    }
    await waitForTabComplete(chromeApi.tabs, tabId, pageLoadMs);
    await delay(settleMs);
    const response = (await sendTabMessageWithRetry(chromeApi.tabs, tabId, {
      type: "mdtero.fetch_xml.request",
      artifactUrl: request.artifact_url,
      sourceUrl: request.source_url
    })) as ContentCaptureResponse | undefined;
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
    const tabId = await openAcquisitionTab(chromeApi.tabs, targetUrl, bridgeSession);
    if (!tabId) {
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: "tab_open_failed",
        failure_message: "Browser opened the target page without a usable tab id."
      };
    }

    await waitForTabComplete(chromeApi.tabs, tabId, pageLoadMs);
    await delay(settleMs);

    const response = (await sendTabMessageWithRetry(
      chromeApi.tabs,
      tabId,
      {
        type: "mdtero.download_epub.request",
        artifactUrl
      }
    )) as ContentCaptureResponse | undefined;

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
  const tabId = await openAcquisitionTab(chromeApi.tabs, targetUrl, bridgeSession);
  if (!tabId) {
    return {
      task_id: request.task_id,
      status: "failed",
      connector: request.connector,
      failure_code: "tab_open_failed",
      failure_message: "Browser opened the target page without a usable tab id."
    };
  }

  await waitForTabComplete(chromeApi.tabs, tabId, pageLoadMs);
  await delay(settleMs);

  const response = (await sendTabMessageWithRetry(chromeApi.tabs, tabId, {
    type: "mdtero.capture_html.request"
  })) as ContentCaptureResponse | undefined;

  if (!response?.ok || !response.capture) {
    return {
      task_id: request.task_id,
      status: "failed",
      connector: request.connector,
      failure_code: "content_script_unavailable",
      failure_message: "Capture hook did not return a usable article payload."
    };
  }

  if (!response.capture.ok) {
    return {
      task_id: request.task_id,
      status: "failed",
      connector: request.connector,
      failure_code: response.capture.failureCode || "article_body_missing",
      failure_message:
        response.capture.failureMessage || "Page loaded but article capture did not succeed."
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
) {
  const existingTabId = bridgeSession?.tabId;
  if (existingTabId && typeof tabs.update === "function") {
    try {
      const updated = await tabs.update(existingTabId, {
        url: targetUrl,
        active: false
      });
      const updatedTabId = updated.id ?? existingTabId;
      if (bridgeSession) {
        bridgeSession.tabId = updatedTabId;
      }
      return updatedTabId;
    } catch {
      if (bridgeSession) {
        bridgeSession.tabId = null;
      }
    }
  }

  const created = await tabs.create({ url: targetUrl, active: false });
  if (bridgeSession) {
    bridgeSession.tabId = created.id ?? null;
  }
  return created.id;
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
      return await tabs.sendMessage(tabId, message);
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

function isRetryableContentScriptError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error || "");
  const lowered = message.toLowerCase();
  return (
    lowered.includes("receiving end does not exist") ||
    lowered.includes("could not establish connection") ||
    lowered.includes("message port closed")
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

function waitForTabComplete(tabs: TabsApiLike, tabId: number, timeoutMs: number) {
  return new Promise<void>((resolve, reject) => {
    const timeout = globalThis.setTimeout(() => {
      tabs.onUpdated.removeListener(handleUpdate);
      reject(new Error("Timed out waiting for tab load completion."));
    }, timeoutMs);

    const handleUpdate = (updatedTabId: number, changeInfo: { status?: string }) => {
      if (updatedTabId !== tabId) {
        return;
      }
      if (changeInfo.status === "complete") {
        globalThis.clearTimeout(timeout);
        tabs.onUpdated.removeListener(handleUpdate);
        resolve();
      }
    };

    tabs.onUpdated.addListener(handleUpdate);
  });
}
