// src/lib/api.ts
function buildHelperFirstParseBody(params) {
  const body = new FormData();
  body.set(params.fileField, params.file, params.filename);
  if (params.sourceDoi) {
    body.set("source_doi", params.sourceDoi);
  }
  if (params.sourceInput) {
    body.set("source_input", params.sourceInput);
  }
  return body;
}
function fallbackArtifactFilename(artifact) {
  if (artifact === "paper_bundle") return "paper_bundle.zip";
  if (artifact === "paper_md") return "paper.md";
  if (artifact === "paper_pdf") return "paper.pdf";
  if (artifact === "paper_xml") return "paper.xml";
  if (artifact === "translated_md") return "translated.md";
  return `${artifact}.bin`;
}
function createApiClient(getSettings) {
  async function requireSignedInSettings() {
    const settings = await getSettings();
    if (!settings.token) {
      throw new Error("Sign in required before parsing or translating.");
    }
    return settings;
  }
  function getRuntimeVersion() {
    const runtimeVersion = globalThis.chrome?.runtime?.getManifest?.().version;
    return runtimeVersion ? `extension-${runtimeVersion}` : "extension-dev";
  }
  async function request(path, init, options) {
    const settings = options?.requireAuth ? await requireSignedInSettings() : await getSettings();
    const headers = new Headers(init?.headers ?? {});
    if (!(init?.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (settings.token) {
      headers.set("Authorization", `Bearer ${settings.token}`);
    }
    headers.set("X-Client-Channel", "extension");
    headers.set("X-Client-Version", getRuntimeVersion());
    const response = await fetch(`${settings.apiBaseUrl}${path}`, {
      ...init,
      headers
    });
    if (!response.ok) {
      const detail = await response.clone().json().then((payload) => {
        if (payload && typeof payload.detail === "string" && payload.detail.trim()) {
          return payload.detail.trim();
        }
        return "";
      }).catch(() => "");
      throw new Error(detail || `API request failed: ${response.status}`);
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
    loginWithPassword(payload) {
      return request("/auth/password/login", {
        method: "POST",
        body: JSON.stringify(payload)
      }).then((response) => response.json());
    },
    getUsage() {
      return request("/me/usage", void 0, { requireAuth: true }).then((response) => response.json());
    },
    getParserV2ShadowDiagnostics() {
      return request("/diagnostics/parser-v2/shadow", void 0, { requireAuth: true }).then(
        (response) => response.json()
      );
    },
    getClientConfig() {
      return request("/client-config").then((response) => response.json());
    },
    getMyTasks() {
      return request("/me/tasks", void 0, { requireAuth: true }).then((response) => response.json());
    },
    createParseTask(payload) {
      return request("/tasks/parse", {
        method: "POST",
        body: JSON.stringify(payload)
      }, { requireAuth: true }).then((response) => response.json());
    },
    createUploadedParseTask(payload) {
      const body = new FormData();
      body.set("xml_file", payload.xmlFile, payload.filename ?? "paper.xml");
      if (payload.sourceDoi) {
        body.set("source_doi", payload.sourceDoi);
      }
      if (payload.sourceInput) {
        body.set("source_input", payload.sourceInput);
      }
      return request("/tasks/parse-upload", {
        method: "POST",
        body
      }, { requireAuth: true }).then((response) => response.json());
    },
    createParseFulltextV2Task(payload) {
      const body = buildHelperFirstParseBody({
        fileField: "fulltext_file",
        file: payload.fulltextFile,
        filename: payload.filename ?? "paper.fulltext",
        sourceDoi: payload.sourceDoi,
        sourceInput: payload.sourceInput
      });
      return request("/tasks/parse-fulltext-v2", {
        method: "POST",
        body
      }, { requireAuth: true }).then((response) => response.json());
    },
    createParseHelperBundleV2Task(payload) {
      const body = buildHelperFirstParseBody({
        fileField: "helper_bundle",
        file: payload.helperBundleFile,
        filename: payload.filename ?? "helper-bundle.zip",
        sourceDoi: payload.sourceDoi,
        sourceInput: payload.sourceInput
      });
      if (payload.pdfEngine) {
        body.set("pdf_engine", payload.pdfEngine);
      }
      return request("/tasks/parse-helper-bundle-v2", {
        method: "POST",
        body
      }, { requireAuth: true }).then((response) => response.json());
    },
    createTranslateTask(payload) {
      return request("/tasks/translate", {
        method: "POST",
        body: JSON.stringify(payload)
      }, { requireAuth: true }).then((response) => response.json());
    },
    getTask(taskId) {
      return request(`/tasks/${taskId}`, void 0, { requireAuth: true }).then((response) => response.json());
    },
    downloadArtifact(taskId, artifact) {
      return request(`/tasks/${taskId}/download/${artifact}`, void 0, { requireAuth: true }).then(async (response) => ({
        blob: await response.blob(),
        filename: extractFilename(response.headers.get("Content-Disposition"), fallbackArtifactFilename(artifact)),
        mediaType: response.headers.get("Content-Type") ?? "application/octet-stream"
      }));
    }
  };
}

// src/lib/browser-bridge.ts
var BRIDGE_NATIVE_HOST = "com.mdtero.browser_bridge";
var BRIDGE_HEARTBEAT_ALARM = "mdtero-browser-bridge-heartbeat";
var BRIDGE_HEARTBEAT_PERIOD_MINUTES = 0.5;
var BRIDGE_IDLE_POLL_DELAY_MS = 5e3;
var BRIDGE_POST_TASK_POLL_DELAY_MS = 250;
function isAcquireEnvelope(payload) {
  return Boolean(
    payload && typeof payload === "object" && payload.type === "mdtero.bridge.acquire" && payload.request && typeof payload.request === "object"
  );
}
function toBridgeFailure(request, error) {
  return {
    task_id: request.task_id,
    status: "failed",
    connector: request.connector,
    failure_code: "unsupported_route",
    failure_message: error instanceof Error ? error.message : "Browser acquisition failed."
  };
}
function initializeBrowserBridge(options) {
  let port = null;
  let runnerState = "idle";
  let bridgeState = "disconnected";
  let idlePollTimer = null;
  const clearIdlePoll = () => {
    if (idlePollTimer !== null) {
      globalThis.clearTimeout(idlePollTimer);
      idlePollTimer = null;
    }
  };
  const announceHello = (targetPort) => {
    targetPort.postMessage({
      type: "mdtero.bridge.hello",
      runtime_id: options.runtimeId,
      runner_state: runnerState,
      capabilities: ["open_and_capture_html", "open_and_download_epub", "open_and_fetch_xml", "capture_current_tab"]
    });
  };
  const scheduleIdlePoll = (delayMs = BRIDGE_IDLE_POLL_DELAY_MS) => {
    clearIdlePoll();
    if (runnerState !== "idle") {
      return;
    }
    idlePollTimer = globalThis.setTimeout(() => {
      idlePollTimer = null;
      if (runnerState === "idle") {
        ensureConnected();
      }
    }, delayMs);
  };
  const connect = () => {
    if (port) {
      return port;
    }
    try {
      port = options.runtime.connectNative(BRIDGE_NATIVE_HOST);
    } catch {
      bridgeState = "unavailable";
      if (options.runtimeId) {
        console.warn("[mdtero-bridge] native host unavailable", options.runtimeId);
      }
      return null;
    }
    bridgeState = "connected";
    const connectedPort = port;
    connectedPort.onMessage.addListener((payload) => {
      if (!isAcquireEnvelope(payload)) {
        return;
      }
      runnerState = "busy";
      clearIdlePoll();
      Promise.resolve(options.acquire(payload.request)).then((response) => {
        connectedPort.postMessage(response);
      }).catch((error) => {
        connectedPort.postMessage(toBridgeFailure(payload.request, error));
      }).finally(() => {
        runnerState = "idle";
        scheduleIdlePoll(BRIDGE_POST_TASK_POLL_DELAY_MS);
      });
    });
    connectedPort.onDisconnect.addListener(() => {
      if (port === connectedPort) {
        port = null;
      }
      runnerState = "idle";
      bridgeState = "disconnected";
      clearIdlePoll();
    });
    announceHello(connectedPort);
    scheduleIdlePoll();
    return connectedPort;
  };
  const ensureConnected = () => {
    const activePort = connect();
    if (activePort) {
      announceHello(activePort);
      scheduleIdlePoll();
    }
  };
  if (options.alarms) {
    options.alarms.create(BRIDGE_HEARTBEAT_ALARM, {
      periodInMinutes: BRIDGE_HEARTBEAT_PERIOD_MINUTES
    });
    options.alarms.onAlarm.addListener((alarm) => {
      if (alarm?.name === BRIDGE_HEARTBEAT_ALARM) {
        ensureConnected();
      }
    });
  }
  connect();
  return {
    ensureConnected,
    getStatus() {
      return {
        state: bridgeState,
        runnerState
      };
    }
  };
}

// src/lib/bridge-acquire.ts
async function performBridgeAcquire(options) {
  const { request, chromeApi, bridgeSession: bridgeSession2 } = options;
  const pageLoadMs = getBridgeTimeoutMs(request.timeouts?.page_load_ms, 3e4);
  const settleMs = getBridgeTimeoutMs(request.timeouts?.settle_ms, 0);
  if (request.action === "capture_current_tab") {
    const activeTabId = bridgeSession2?.pageTabId ?? bridgeSession2?.tabId;
    if (!activeTabId) {
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: "tab_open_failed",
        failure_message: "No active bridge tab is available for current-tab capture."
      };
    }
    const response2 = await sendTabMessageWithRetry(chromeApi.tabs, activeTabId, {
      type: "mdtero.capture_current_tab.request"
    });
    if (!response2?.ok || !response2.capture?.ok) {
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: response2?.capture?.failureCode || "content_script_unavailable",
        failure_message: response2?.capture?.failureMessage || "Current-tab capture did not succeed."
      };
    }
    return {
      task_id: request.task_id,
      status: "succeeded",
      connector: request.connector,
      artifact_kind: "html",
      payload_name: response2.capture.payloadName || "paper.html",
      payload_text: response2.capture.html || "",
      source_url: response2.capture.sourceUrl,
      page_title: response2.capture.pageTitle
    };
  }
  if (request.action === "open_and_fetch_xml") {
    const targetUrl2 = resolveTargetUrl(request.input, request.source_url);
    const tabId2 = await openAcquisitionTab(chromeApi.tabs, targetUrl2, bridgeSession2);
    if (!tabId2) {
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: "tab_open_failed",
        failure_message: "Browser opened the target page without a usable tab id."
      };
    }
    await waitForTabComplete(chromeApi.tabs, tabId2, pageLoadMs);
    await delay(settleMs);
    const response2 = await sendTabMessageWithRetry(chromeApi.tabs, tabId2, {
      type: "mdtero.fetch_xml.request",
      artifactUrl: request.artifact_url,
      sourceUrl: request.source_url
    });
    if (!response2?.ok || !response2.xml) {
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: "content_script_unavailable",
        failure_message: "Page hook did not return a usable XML payload."
      };
    }
    if (!response2.xml.ok || !response2.xml.payloadText) {
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: response2.xml.failureCode || "artifact_download_missing",
        failure_message: response2.xml.failureMessage || "Browser page context could not download the XML artifact."
      };
    }
    return {
      task_id: request.task_id,
      status: "succeeded",
      connector: request.connector,
      artifact_kind: "structured_xml",
      payload_name: response2.xml.payloadName || "paper.xml",
      payload_text: response2.xml.payloadText,
      source_url: response2.xml.sourceUrl || targetUrl2
    };
  }
  if (request.action === "open_and_download_epub") {
    const artifactUrl = resolveArtifactUrl(request);
    const targetUrl2 = resolveEpubTargetUrl(request);
    const tabId2 = await openAcquisitionTab(chromeApi.tabs, targetUrl2, bridgeSession2);
    if (!tabId2) {
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: "tab_open_failed",
        failure_message: "Browser opened the target page without a usable tab id."
      };
    }
    await waitForTabComplete(chromeApi.tabs, tabId2, pageLoadMs);
    await delay(settleMs);
    const response2 = await sendTabMessageWithRetry(
      chromeApi.tabs,
      tabId2,
      {
        type: "mdtero.download_epub.request",
        artifactUrl
      }
    );
    if (!response2?.ok || !response2.download) {
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: "content_script_unavailable",
        failure_message: "Page hook did not return a usable EPUB payload."
      };
    }
    if (!response2.download.ok || !response2.download.payloadBase64) {
      return {
        task_id: request.task_id,
        status: "failed",
        connector: request.connector,
        failure_code: response2.download.failureCode || "artifact_download_missing",
        failure_message: response2.download.failureMessage || "Browser page context could not download the EPUB artifact."
      };
    }
    return {
      task_id: request.task_id,
      status: "succeeded",
      connector: request.connector,
      artifact_kind: "epub",
      payload_name: response2.download.payloadName || "paper.epub",
      payload_base64: response2.download.payloadBase64,
      source_url: response2.download.sourceUrl || artifactUrl
    };
  }
  if (request.action !== "open_and_capture_html") {
    throw new Error(`Unsupported bridge action: ${request.action}`);
  }
  const targetUrl = resolveTargetUrl(request.input, request.source_url);
  const tabId = await openAcquisitionTab(chromeApi.tabs, targetUrl, bridgeSession2);
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
  const response = await sendTabMessageWithRetry(chromeApi.tabs, tabId, {
    type: "mdtero.capture_html.request"
  });
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
      failure_message: response.capture.failureMessage || "Page loaded but article capture did not succeed."
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
async function openAcquisitionTab(tabs, targetUrl, bridgeSession2) {
  const existingTabId = bridgeSession2?.tabId;
  if (existingTabId && typeof tabs.update === "function") {
    try {
      const updated = await tabs.update(existingTabId, {
        url: targetUrl,
        active: false
      });
      const updatedTabId = updated.id ?? existingTabId;
      if (bridgeSession2) {
        bridgeSession2.tabId = updatedTabId;
      }
      return updatedTabId;
    } catch {
      if (bridgeSession2) {
        bridgeSession2.tabId = null;
      }
    }
  }
  const created = await tabs.create({ url: targetUrl, active: false });
  if (bridgeSession2) {
    bridgeSession2.tabId = created.id ?? null;
  }
  return created.id;
}
async function sendTabMessageWithRetry(tabs, tabId, message, maxAttempts = 4) {
  let lastError = null;
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
function isRetryableContentScriptError(error) {
  const message = error instanceof Error ? error.message : String(error || "");
  const lowered = message.toLowerCase();
  return lowered.includes("receiving end does not exist") || lowered.includes("could not establish connection") || lowered.includes("message port closed");
}
function delay(ms) {
  return new Promise((resolve) => {
    globalThis.setTimeout(resolve, ms);
  });
}
function getBridgeTimeoutMs(value, fallbackMs) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 0) {
    return fallbackMs;
  }
  return Math.floor(numeric);
}
function resolveArtifactUrl(request) {
  const artifactUrl = String(request.artifact_url || "").trim();
  if (artifactUrl) {
    return artifactUrl;
  }
  throw new Error("Bridge download request is missing an artifact URL.");
}
function resolveTargetUrl(input, sourceUrl) {
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
function resolveEpubTargetUrl(request) {
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
function waitForTabComplete(tabs, tabId, timeoutMs) {
  return new Promise((resolve, reject) => {
    const timeout = globalThis.setTimeout(() => {
      tabs.onUpdated.removeListener(handleUpdate);
      reject(new Error("Timed out waiting for tab load completion."));
    }, timeoutMs);
    const handleUpdate = (updatedTabId, changeInfo) => {
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

// src/lib/bridge-wake.ts
var BRIDGE_SUPPORTED_URL_PATTERNS = [
  "arxiv.org",
  "sciencedirect.com/science/article/pii/",
  "link.springer.com",
  "springer.com",
  "springernature.com",
  "onlinelibrary.wiley.com",
  "tandfonline.com"
];
function isBridgeSupportedPage(url) {
  const normalized = String(url || "").trim().toLowerCase();
  return BRIDGE_SUPPORTED_URL_PATTERNS.some((pattern) => normalized.includes(pattern));
}

// src/lib/elsevier.ts
var LOCAL_XML_DOI_PREFIXES = ["10.1016/"];
var DOI_URL_PATTERN = /^https?:\/\/(?:dx\.)?doi\.org\/(10\.\d{4,9}\/.+)$/i;
var PII_PATTERN = /^S[0-9A-Z]{16,}$/i;
var SCIENCEDIRECT_PII_PATTERN = /sciencedirect\.com\/science\/article\/pii\/(S[0-9A-Z]{16,})/i;
function usesLocalXmlAcquire(doi) {
  const lowered = doi.toLowerCase();
  return LOCAL_XML_DOI_PREFIXES.some((prefix) => lowered.startsWith(prefix));
}
function normalizeElsevierInput(input) {
  const trimmed = input.trim();
  const doiUrlMatch = trimmed.match(DOI_URL_PATTERN);
  if (doiUrlMatch && usesLocalXmlAcquire(doiUrlMatch[1])) {
    return { kind: "doi", value: doiUrlMatch[1] };
  }
  if (usesLocalXmlAcquire(trimmed)) {
    return { kind: "doi", value: trimmed };
  }
  const piiUrlMatch = trimmed.match(SCIENCEDIRECT_PII_PATTERN);
  if (piiUrlMatch) {
    return { kind: "pii", value: piiUrlMatch[1] };
  }
  if (PII_PATTERN.test(trimmed)) {
    return { kind: "pii", value: trimmed };
  }
  return null;
}
function requiresElsevierLocalAcquire(input) {
  return normalizeElsevierInput(input) !== null;
}
function buildElsevierLocalAcquireGuidance() {
  return [
    "This Elsevier or ScienceDirect paper needs local acquisition in your browser first.",
    "Add your Elsevier API key in Mdtero extension settings, then retry.",
    "If Elsevier only returns the abstract, check whether this machine is on a campus or institutional network IP."
  ].join(" ");
}
async function fetchElsevierXml(input, apiKey) {
  const identifier = normalizeElsevierInput(input);
  if (!identifier) {
    throw new Error("Input is not recognized as an Elsevier DOI or ScienceDirect article.");
  }
  const endpointBase = identifier.kind === "doi" ? `https://api.elsevier.com/content/article/doi/${identifier.value}` : `https://api.elsevier.com/content/article/pii/${identifier.value}`;
  const response = await fetch(
    `${endpointBase}?APIKey=${encodeURIComponent(apiKey)}&httpAccept=text/xml`
  );
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      throw new Error("Elsevier API request failed. Please verify your Elsevier API key and network entitlement.");
    }
    throw new Error(`Elsevier XML fetch failed: ${response.status}`);
  }
  return {
    xmlBlob: await response.blob(),
    sourceDoi: identifier.kind === "doi" ? identifier.value : void 0,
    sourceInput: input,
    filename: "paper.xml"
  };
}

// src/lib/springer.ts
var DOI_PATTERN = /(10\.\d{4,9}\/[-._;()/:A-Z0-9]+)/i;
var DOI_URL_PATTERN2 = /^https?:\/\/(?:dx\.)?doi\.org\/(10\.\d{4,9}\/.+)$/i;
var SPRINGER_HOST_PATTERN = /(link\.springer\.com|springer\.com|springernature\.com)/i;
function normalizeSpringerInput(input, pageUrl) {
  const trimmed = String(input || "").trim();
  const doiUrlMatch = trimmed.match(DOI_URL_PATTERN2);
  if (doiUrlMatch) {
    return doiUrlMatch[1];
  }
  if (SPRINGER_HOST_PATTERN.test(trimmed)) {
    const doiMatch = trimmed.match(DOI_PATTERN);
    if (doiMatch) {
      return doiMatch[1];
    }
  }
  if (/^10\.1007\//i.test(trimmed)) {
    return trimmed;
  }
  if (SPRINGER_HOST_PATTERN.test(String(pageUrl || ""))) {
    const doiMatch = trimmed.match(DOI_PATTERN);
    if (doiMatch) {
      return doiMatch[1];
    }
  }
  return null;
}
async function fetchSpringerOpenAccessJats(input, apiKey, pageUrl) {
  const sourceDoi = normalizeSpringerInput(input, pageUrl);
  if (!sourceDoi) {
    throw new Error("Input is not recognized as a Springer DOI or Springer article page.");
  }
  const response = await fetch(
    `https://api.springernature.com/openaccess/jats?q=doi:${encodeURIComponent(sourceDoi)}&api_key=${encodeURIComponent(apiKey)}`
  );
  if (!response.ok) {
    throw new Error(`Springer OA JATS fetch failed: ${response.status}`);
  }
  const text = await response.text();
  if (!/<article[\s>]/i.test(text)) {
    throw new Error("Springer OA API did not return a JATS article payload.");
  }
  return {
    xmlBlob: new Blob([text], { type: "application/xml" }),
    filename: "paper.xml",
    sourceDoi,
    sourceInput: input
  };
}

// src/lib/helper-bundle.ts
var encoder = new TextEncoder();
var CONNECTOR_PRESETS = {
  local_file_upload: {
    access: "unknown",
    sourceName: "local_file_upload",
    userPrivateRetention: true
  },
  elsevier_article_retrieval_api: {
    access: "licensed",
    sourceName: "elsevier_article_retrieval_api",
    userPrivateRetention: true
  },
  wiley_tdm: {
    access: "licensed",
    sourceName: "wiley_tdm",
    userPrivateRetention: true
  },
  springer_subscription_connector: {
    access: "licensed",
    sourceName: "springer_subscription_connector",
    userPrivateRetention: true
  },
  taylor_francis_tdm: {
    access: "licensed",
    sourceName: "taylor_francis_tdm",
    userPrivateRetention: true
  },
  arxiv_native: {
    access: "open",
    sourceName: "arxiv_native"
  }
};
function buildHelperBundleBlob(options) {
  const payloadBytes = toUint8Array(options.payload);
  const manifest = {
    connector: options.connector,
    artifact_kind: options.artifactKind,
    acquisition_mode: options.acquisitionMode || "browser_extension",
    source_name: CONNECTOR_PRESETS[options.connector]?.sourceName || options.connector,
    source_type: options.sourceType || defaultSourceType(options.artifactKind),
    source_id: options.sourceId || null,
    source_url: options.sourceUrl || null,
    source_doi: options.sourceDoi || null,
    license_name: options.licenseName || null,
    rights_confidence: "high",
    access: options.access || CONNECTOR_PRESETS[options.connector]?.access || "unknown",
    explicit_open_license: false,
    user_private_retention: Boolean(
      options.userPrivateRetention ?? CONNECTOR_PRESETS[options.connector]?.userPrivateRetention ?? false
    ),
    payload_name: options.payloadName,
    extra_files: []
  };
  const archive = buildStoredZip([
    {
      name: "manifest.json",
      bytes: encoder.encode(JSON.stringify(manifest))
    },
    {
      name: options.payloadName,
      bytes: payloadBytes
    }
  ]);
  return new Blob([archive], { type: "application/zip" });
}
function inferBrowserHelperBundleConnector(input, pageUrl) {
  const haystack = `${String(input || "").toLowerCase()} ${String(pageUrl || "").toLowerCase()}`;
  if (haystack.includes("arxiv.org") || haystack.includes("arxiv:")) {
    return "arxiv_native";
  }
  if (haystack.includes("link.springer.com") || haystack.includes("springernature.com") || haystack.includes("springer.com")) {
    return "springer_subscription_connector";
  }
  if (haystack.includes("onlinelibrary.wiley.com") || haystack.includes("10.1002/")) {
    return "wiley_tdm";
  }
  if (haystack.includes("tandfonline.com") || haystack.includes("10.1080/")) {
    return "taylor_francis_tdm";
  }
  if (haystack.includes("sciencedirect.com") || haystack.includes("elsevier.com") || haystack.includes("10.1016/")) {
    return "elsevier_article_retrieval_api";
  }
  return "browser_extension_html_capture";
}
function inferBrowserHelperBundleAccess(connector) {
  return CONNECTOR_PRESETS[connector]?.access || "unknown";
}
function defaultSourceType(artifactKind) {
  if (artifactKind === "html") {
    return "browser_extension_html";
  }
  if (artifactKind === "epub") {
    return "browser_extension_epub";
  }
  if (artifactKind === "pdf") {
    return "browser_extension_pdf";
  }
  if (artifactKind === "jats_xml") {
    return "browser_extension_jats";
  }
  return "browser_extension_xml";
}
function toUint8Array(payload) {
  if (typeof payload === "string") {
    return encoder.encode(payload);
  }
  if (payload instanceof Uint8Array) {
    return payload;
  }
  return new Uint8Array(payload);
}
function buildStoredZip(entries) {
  const localParts = [];
  const centralParts = [];
  let offset = 0;
  for (const entry of entries) {
    const nameBytes = encoder.encode(entry.name);
    const crc = crc32(entry.bytes);
    const localHeader = new Uint8Array(30 + nameBytes.length);
    const localView = new DataView(localHeader.buffer);
    localView.setUint32(0, 67324752, true);
    localView.setUint16(4, 20, true);
    localView.setUint16(6, 0, true);
    localView.setUint16(8, 0, true);
    localView.setUint16(10, 0, true);
    localView.setUint16(12, 0, true);
    localView.setUint32(14, crc, true);
    localView.setUint32(18, entry.bytes.length, true);
    localView.setUint32(22, entry.bytes.length, true);
    localView.setUint16(26, nameBytes.length, true);
    localView.setUint16(28, 0, true);
    localHeader.set(nameBytes, 30);
    localParts.push(localHeader, entry.bytes);
    const centralHeader = new Uint8Array(46 + nameBytes.length);
    const centralView = new DataView(centralHeader.buffer);
    centralView.setUint32(0, 33639248, true);
    centralView.setUint16(4, 20, true);
    centralView.setUint16(6, 20, true);
    centralView.setUint16(8, 0, true);
    centralView.setUint16(10, 0, true);
    centralView.setUint16(12, 0, true);
    centralView.setUint16(14, 0, true);
    centralView.setUint32(16, crc, true);
    centralView.setUint32(20, entry.bytes.length, true);
    centralView.setUint32(24, entry.bytes.length, true);
    centralView.setUint16(28, nameBytes.length, true);
    centralView.setUint16(30, 0, true);
    centralView.setUint16(32, 0, true);
    centralView.setUint16(34, 0, true);
    centralView.setUint16(36, 0, true);
    centralView.setUint32(38, 0, true);
    centralView.setUint32(42, offset, true);
    centralHeader.set(nameBytes, 46);
    centralParts.push(centralHeader);
    offset += localHeader.length + entry.bytes.length;
  }
  const centralDirectoryOffset = offset;
  let centralDirectorySize = 0;
  for (const part of centralParts) {
    centralDirectorySize += part.length;
  }
  const endRecord = new Uint8Array(22);
  const endView = new DataView(endRecord.buffer);
  endView.setUint32(0, 101010256, true);
  endView.setUint16(4, 0, true);
  endView.setUint16(6, 0, true);
  endView.setUint16(8, entries.length, true);
  endView.setUint16(10, entries.length, true);
  endView.setUint32(12, centralDirectorySize, true);
  endView.setUint32(16, centralDirectoryOffset, true);
  endView.setUint16(20, 0, true);
  const totalLength = localParts.reduce((sum, part) => sum + part.length, 0) + centralDirectorySize + endRecord.length;
  const archive = new Uint8Array(totalLength);
  let cursor = 0;
  for (const part of localParts) {
    archive.set(part, cursor);
    cursor += part.length;
  }
  for (const part of centralParts) {
    archive.set(part, cursor);
    cursor += part.length;
  }
  archive.set(endRecord, cursor);
  return archive;
}
var CRC32_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let index = 0; index < 256; index += 1) {
    let value = index;
    for (let bit = 0; bit < 8; bit += 1) {
      value = (value & 1) === 1 ? (3988292384 ^ value >>> 1) >>> 0 : value >>> 1;
    }
    table[index] = value >>> 0;
  }
  return table;
})();
function crc32(bytes) {
  let value = 4294967295;
  for (const item of bytes) {
    value = CRC32_TABLE[(value ^ item) & 255] ^ value >>> 8;
  }
  return (value ^ 4294967295) >>> 0;
}

// ../../packages/shared/src/api-contract.ts
var DEFAULT_API_BASE_URL = "https://api.mdtero.com";

// ../../packages/shared/src/publisher-capability-matrix.ts
function link(href, en, zh) {
  return {
    href,
    label: { en, zh }
  };
}
var PUBLISHER_CAPABILITY_MATRIX = [
  {
    id: "arxiv",
    label: { en: "arXiv", zh: "arXiv" },
    variantOf: "arxiv",
    accessVariant: "open_repository",
    presentationGroup: "helper_only",
    rightsMode: "open",
    acquisitionMode: "direct_open_fulltext",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: false,
    mayNeedInstitutionAccess: false,
    whatYouNeed: {
      en: "Install the local helper.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\u3002"
    },
    howMdteroGetsIt: {
      en: "Direct open full-text retrieval from arXiv.",
      zh: "\u76F4\u63A5\u4ECE arXiv \u83B7\u53D6\u5F00\u653E\u5168\u6587\u3002"
    },
    configureTarget: "none",
    status: "stable",
    fallbacks: ["pdf"],
    validationRef: "acceptance:task-arxiv-html-live-1",
    links: []
  },
  {
    id: "pmc_europe_pmc",
    label: { en: "PMC / Europe PMC", zh: "PMC / Europe PMC" },
    variantOf: "pmc",
    accessVariant: "open_access",
    presentationGroup: "helper_only",
    rightsMode: "open",
    acquisitionMode: "direct_open_fulltext",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: false,
    mayNeedInstitutionAccess: false,
    whatYouNeed: {
      en: "Install the local helper.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\u3002"
    },
    howMdteroGetsIt: {
      en: "Structured open-access full text from PMC routes.",
      zh: "\u901A\u8FC7 PMC \u8DEF\u7EBF\u83B7\u53D6\u7ED3\u6784\u5316\u5F00\u653E\u5168\u6587\u3002"
    },
    configureTarget: "none",
    status: "stable",
    fallbacks: ["pdf"],
    validationRef: "checklist:pmc-open-access",
    links: []
  },
  {
    id: "plos",
    label: { en: "PLOS", zh: "PLOS" },
    variantOf: "plos",
    accessVariant: "open_access",
    presentationGroup: "helper_only",
    rightsMode: "open",
    acquisitionMode: "direct_open_fulltext",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: false,
    mayNeedInstitutionAccess: false,
    whatYouNeed: {
      en: "Install the local helper.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\u3002"
    },
    howMdteroGetsIt: {
      en: "Structured open-access full text from PLOS.",
      zh: "\u4ECE PLOS \u83B7\u53D6\u7ED3\u6784\u5316\u5F00\u653E\u5168\u6587\u3002"
    },
    configureTarget: "none",
    status: "stable",
    fallbacks: ["pdf"],
    validationRef: "checklist:plos-open-access",
    links: []
  },
  {
    id: "biorxiv_medrxiv",
    label: { en: "bioRxiv / medRxiv", zh: "bioRxiv / medRxiv" },
    variantOf: "biorxiv_medrxiv",
    accessVariant: "preprint_server",
    presentationGroup: "helper_only",
    rightsMode: "open",
    acquisitionMode: "direct_open_fulltext",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: false,
    mayNeedInstitutionAccess: false,
    whatYouNeed: {
      en: "Install the local helper.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\u3002"
    },
    howMdteroGetsIt: {
      en: "Preprint full text from the source site.",
      zh: "\u4ECE\u9884\u5370\u672C\u6E90\u7AD9\u83B7\u53D6\u5168\u6587\u3002"
    },
    configureTarget: "none",
    status: "stable",
    fallbacks: ["pdf"],
    validationRef: "checklist:biorxiv-medrxiv-open",
    links: []
  },
  {
    id: "chemrxiv",
    label: { en: "ChemRxiv", zh: "ChemRxiv" },
    variantOf: "chemrxiv",
    accessVariant: "preprint_server",
    presentationGroup: "helper_only",
    rightsMode: "open",
    acquisitionMode: "direct_open_fulltext",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: false,
    mayNeedInstitutionAccess: false,
    whatYouNeed: {
      en: "Install the local helper.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\u3002"
    },
    howMdteroGetsIt: {
      en: "Preprint full text from ChemRxiv when available.",
      zh: "\u5728\u53EF\u7528\u65F6\u4ECE ChemRxiv \u83B7\u53D6\u9884\u5370\u672C\u5168\u6587\u3002"
    },
    configureTarget: "none",
    status: "demo",
    fallbacks: ["pdf"],
    validationRef: "checklist:chemrxiv-demo",
    links: []
  },
  {
    id: "mdpi",
    label: { en: "MDPI", zh: "MDPI" },
    variantOf: "mdpi",
    accessVariant: "publisher_open_page",
    presentationGroup: "helper_only",
    rightsMode: "open",
    acquisitionMode: "direct_open_fulltext",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: false,
    mayNeedInstitutionAccess: false,
    whatYouNeed: {
      en: "Install the local helper.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\u3002"
    },
    howMdteroGetsIt: {
      en: "Open publisher full text from MDPI pages.",
      zh: "\u4ECE MDPI \u9875\u9762\u83B7\u53D6\u5F00\u653E\u5168\u6587\u3002"
    },
    configureTarget: "none",
    status: "demo",
    fallbacks: ["pdf"],
    validationRef: "checklist:mdpi-demo",
    links: []
  },
  {
    id: "elsevier",
    label: { en: "Elsevier", zh: "Elsevier" },
    variantOf: "elsevier",
    accessVariant: "api",
    presentationGroup: "api_key",
    rightsMode: "licensed",
    acquisitionMode: "official_api",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: true,
    mayNeedInstitutionAccess: true,
    whatYouNeed: {
      en: "Install the local helper and add your Elsevier API key. Some papers may still require institutional access.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\uFF0C\u5E76\u586B\u5199 Elsevier API key\u3002\u90E8\u5206\u8BBA\u6587\u4ECD\u53EF\u80FD\u9700\u8981\u673A\u6784\u6743\u9650\u3002"
    },
    howMdteroGetsIt: {
      en: "Official full-text API for structured publisher retrieval.",
      zh: "\u901A\u8FC7\u5B98\u65B9\u5168\u6587 API \u83B7\u53D6\u7ED3\u6784\u5316\u51FA\u7248\u793E\u5185\u5BB9\u3002"
    },
    configureTarget: "connector_keys",
    status: "stable",
    fallbacks: ["pdf"],
    validationRef: "acceptance:elsevier-local-api",
    links: [
      link("https://dev.elsevier.com/", "Get Elsevier API key", "\u7533\u8BF7 Elsevier API key")
    ]
  },
  {
    id: "springer_oa",
    label: { en: "Springer Open Access", zh: "Springer Open Access" },
    variantOf: "springer",
    accessVariant: "open_access",
    presentationGroup: "api_key",
    rightsMode: "open",
    acquisitionMode: "hybrid",
    requiresHelper: true,
    requiresBrowser: false,
    requiresApiKey: true,
    mayNeedInstitutionAccess: false,
    whatYouNeed: {
      en: "Install the local helper. Add your Springer OA API key for the best XML path.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\u3002\u586B\u5199 Springer OA API key \u53EF\u4F18\u5148\u8D70 XML \u8DEF\u5F84\u3002"
    },
    howMdteroGetsIt: {
      en: "Springer OA XML when available, otherwise open full text.",
      zh: "\u4F18\u5148\u83B7\u53D6 Springer OA XML\uFF0C\u5426\u5219\u8D70\u5F00\u653E\u5168\u6587\u3002"
    },
    configureTarget: "connector_keys",
    status: "stable",
    fallbacks: ["browser_page_capture", "pdf"],
    validationRef: "acceptance:task-springer-s12011-04820-w",
    links: [
      link("https://dev.springernature.com/", "Get Springer Nature API key", "\u7533\u8BF7 Springer Nature API key")
    ]
  },
  {
    id: "springer_subscription",
    label: { en: "Springer subscription pages", zh: "Springer \u8BA2\u9605\u9875\u9762" },
    variantOf: "springer",
    accessVariant: "subscription_page",
    presentationGroup: "browser_assisted",
    rightsMode: "licensed",
    acquisitionMode: "browser_page_capture",
    requiresHelper: true,
    requiresBrowser: true,
    requiresApiKey: false,
    mayNeedInstitutionAccess: true,
    whatYouNeed: {
      en: "Install the local helper and keep the article page open in your browser. Institutional sign-in may be required.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\uFF0C\u5E76\u5728\u6D4F\u89C8\u5668\u4E2D\u4FDD\u6301\u6587\u7AE0\u9875\u9762\u6253\u5F00\u3002\u53EF\u80FD\u9700\u8981\u673A\u6784\u767B\u5F55\u3002"
    },
    howMdteroGetsIt: {
      en: "Browser-assisted page capture from the live article page.",
      zh: "\u901A\u8FC7\u5B9E\u65F6\u6587\u7AE0\u9875\u8FDB\u884C\u6D4F\u89C8\u5668\u8F85\u52A9\u6293\u53D6\u3002"
    },
    configureTarget: "browser_assisted_sources",
    status: "demo",
    fallbacks: ["pdf"],
    validationRef: "acceptance:task-springer-s12011-04820-w",
    links: []
  },
  {
    id: "wiley",
    label: { en: "Wiley", zh: "Wiley" },
    variantOf: "wiley",
    accessVariant: "publisher_page",
    presentationGroup: "browser_assisted",
    rightsMode: "licensed",
    acquisitionMode: "browser_page_capture",
    requiresHelper: true,
    requiresBrowser: true,
    requiresApiKey: false,
    mayNeedInstitutionAccess: true,
    whatYouNeed: {
      en: "Install the local helper and keep the article page open in your browser. Institutional sign-in may be required.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\uFF0C\u5E76\u5728\u6D4F\u89C8\u5668\u4E2D\u4FDD\u6301\u6587\u7AE0\u9875\u9762\u6253\u5F00\u3002\u53EF\u80FD\u9700\u8981\u673A\u6784\u767B\u5F55\u3002"
    },
    howMdteroGetsIt: {
      en: "Browser-assisted page capture from Wiley article pages.",
      zh: "\u901A\u8FC7 Wiley \u6587\u7AE0\u9875\u8FDB\u884C\u6D4F\u89C8\u5668\u8F85\u52A9\u6293\u53D6\u3002"
    },
    configureTarget: "browser_assisted_sources",
    status: "experimental",
    fallbacks: ["pdf"],
    validationRef: "acceptance:task-wiley-validation-1",
    links: []
  },
  {
    id: "taylor_francis",
    label: { en: "Taylor & Francis", zh: "Taylor & Francis" },
    variantOf: "taylor_francis",
    accessVariant: "publisher_page",
    presentationGroup: "browser_assisted",
    rightsMode: "licensed",
    acquisitionMode: "browser_page_capture",
    requiresHelper: true,
    requiresBrowser: true,
    requiresApiKey: false,
    mayNeedInstitutionAccess: true,
    whatYouNeed: {
      en: "Install the local helper and keep the article page open in your browser. Institutional sign-in may be required.",
      zh: "\u5B89\u88C5\u672C\u5730 helper\uFF0C\u5E76\u5728\u6D4F\u89C8\u5668\u4E2D\u4FDD\u6301\u6587\u7AE0\u9875\u9762\u6253\u5F00\u3002\u53EF\u80FD\u9700\u8981\u673A\u6784\u767B\u5F55\u3002"
    },
    howMdteroGetsIt: {
      en: "Browser-assisted page capture from Taylor & Francis pages.",
      zh: "\u901A\u8FC7 Taylor & Francis \u9875\u9762\u8FDB\u884C\u6D4F\u89C8\u5668\u8F85\u52A9\u6293\u53D6\u3002"
    },
    configureTarget: "browser_assisted_sources",
    status: "experimental",
    fallbacks: ["pdf"],
    validationRef: "acceptance:task-tf-html-live-3",
    links: []
  }
];

// src/lib/storage.ts
var SETTINGS_KEY = "mdtero_settings";
function resolveUiLanguage(preferred, browserLanguage) {
  if (preferred === "en" || preferred === "zh") {
    return preferred;
  }
  return browserLanguage?.toLowerCase().startsWith("zh") ? "zh" : "en";
}
async function readSettings() {
  const stored = await chrome.storage.local.get(SETTINGS_KEY);
  const current = stored[SETTINGS_KEY] ?? { apiBaseUrl: DEFAULT_API_BASE_URL };
  return {
    apiBaseUrl: current.apiBaseUrl ?? DEFAULT_API_BASE_URL,
    token: current.token,
    email: current.email,
    elsevierApiKey: current.elsevierApiKey,
    springerOpenAccessApiKey: current.springerOpenAccessApiKey,
    uiLanguage: resolveUiLanguage(current.uiLanguage, globalThis.navigator?.language)
  };
}
async function writeSettings(next) {
  await chrome.storage.local.set({ [SETTINGS_KEY]: next });
}

// src/background.ts
var client = createApiClient(readSettings);
var bridgeSession = {};
var browserBridge = typeof chrome !== "undefined" && chrome.runtime?.connectNative ? initializeBrowserBridge({
  runtime: chrome.runtime,
  alarms: chrome.alarms,
  runtimeId: chrome.runtime.id,
  acquire: handleBridgeAcquire
}) : null;
async function handleBridgeAcquire(request) {
  return performBridgeAcquire({
    request,
    chromeApi: chrome,
    bridgeSession
  });
}
function inferSourceDoi(input) {
  const trimmed = String(input || "").trim();
  return /^10\.\S+/i.test(trimmed) ? trimmed : void 0;
}
function describeCurrentTabCaptureFailure(params) {
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
async function tryCreateCurrentTabHelperBundleTask(message) {
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
      sourceDoi: inferSourceDoi(message.input) || normalizeSpringerInput(message.input, message.pageContext?.tabUrl) || void 0,
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
    sourceUrl: message.pageContext?.tabUrl || capture.sourceUrl || void 0,
    access: inferBrowserHelperBundleAccess(connector)
  });
  return client.createParseHelperBundleV2Task({
    helperBundleFile: helperBundle,
    filename: "helper-bundle.zip",
    sourceDoi: inferSourceDoi(message.input),
    sourceInput: message.input
  });
}
async function createLocalFileHelperBundleTask(message) {
  const filename = String(message.filename || "").trim() || "paper.bin";
  const artifactKind = message.artifactKind === "epub" ? "epub" : "pdf";
  const sourceType = artifactKind === "pdf" ? "browser_extension_local_upload_pdf" : "browser_extension_local_upload_epub";
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
    pdfEngine: artifactKind === "pdf" ? message.pdfEngine : void 0
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
      result: browserBridge ? browserBridge.getStatus() : {
        state: "unavailable",
        runnerState: "idle"
      }
    });
    return false;
  }
  if (message?.type === "mdtero.auth.save_token") {
    readSettings().then((settings) => {
      return writeSettings({
        ...settings,
        token: message.token,
        email: message.email
      });
    }).then(() => sendResponse({ ok: true })).catch((error) => sendResponse({ ok: false, error: error.message }));
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
        return client.createParseFulltextV2Task({
          fulltextFile: uploaded.xmlBlob,
          filename: uploaded.filename,
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
    })().then((result) => sendResponse({ ok: true, result })).catch((error) => sendResponse({ ok: false, error: error.message }));
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
    })().then((result) => sendResponse({ ok: true, result })).catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type === "mdtero.task.get") {
    client.getTask(message.taskId).then((result) => sendResponse({ ok: true, result })).catch((error) => sendResponse({ ok: false, error: error.message }));
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
    })().then((result) => sendResponse({ ok: true, result })).catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  return false;
});
//# sourceMappingURL=background.js.map
