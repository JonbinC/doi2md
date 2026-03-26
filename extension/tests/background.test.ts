import { beforeEach, describe, expect, it, vi } from "vitest";

const createParseTask = vi.fn();
const createUploadedParseTask = vi.fn();
const createParseFulltextV2Task = vi.fn();
const createParseHelperBundleV2Task = vi.fn();
const createTranslateTask = vi.fn();
const getTask = vi.fn();
const readSettings = vi.fn();
const writeSettings = vi.fn();
const requiresElsevierLocalAcquire = vi.fn();
const fetchElsevierXml = vi.fn();
const buildElsevierLocalAcquireGuidance = vi.fn(() => "Use local acquisition.");
const normalizeSpringerInput = vi.fn();
const fetchSpringerOpenAccessJats = vi.fn();

vi.mock("../src/lib/api", () => ({
    createApiClient: vi.fn(() => ({
      createParseTask,
      createUploadedParseTask,
      createParseFulltextV2Task,
      createParseHelperBundleV2Task,
      createTranslateTask,
      getTask
    }))
}));

vi.mock("../src/lib/storage", () => ({
  readSettings,
  writeSettings
}));

vi.mock("../src/lib/elsevier", () => ({
  requiresElsevierLocalAcquire,
  fetchElsevierXml,
  buildElsevierLocalAcquireGuidance
}));

vi.mock("../src/lib/springer", () => ({
  normalizeSpringerInput,
  fetchSpringerOpenAccessJats
}));

vi.mock("../src/lib/browser-bridge", () => ({
  initializeBrowserBridge: vi.fn(() => ({
    ensureConnected: vi.fn(),
    getStatus: vi.fn(() => ({
      state: "connected",
      runnerState: "idle"
    }))
  }))
}));

vi.mock("../src/lib/bridge-acquire", () => ({
  performBridgeAcquire: vi.fn()
}));

vi.mock("../src/lib/bridge-wake", () => ({
  isBridgeSupportedPage: vi.fn(() => false)
}));

function createChromeStub() {
  const messageListeners: Array<(message: unknown, sender: unknown, sendResponse: (payload: unknown) => void) => boolean | void> = [];
  return {
    runtime: {
      id: "runtime-demo",
      connectNative: vi.fn(),
      onStartup: {
        addListener: vi.fn()
      },
      onInstalled: {
        addListener: vi.fn()
      },
      onMessage: {
        addListener(listener: (message: unknown, sender: unknown, sendResponse: (payload: unknown) => void) => boolean | void) {
          messageListeners.push(listener);
        }
      }
    },
    tabs: {
      sendMessage: vi.fn(),
      onUpdated: {
        addListener: vi.fn()
      },
      onRemoved: {
        addListener: vi.fn()
      }
    },
    __messageListeners: messageListeners
  };
}

describe("extension background Elsevier routing", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    readSettings.mockResolvedValue({ token: "demo-token", email: "demo@example.com" });
    writeSettings.mockResolvedValue(undefined);
    createParseTask.mockResolvedValue({ task_id: "task-generic", status: "queued" });
    createUploadedParseTask.mockResolvedValue({ task_id: "task-legacy", status: "queued" });
    createParseFulltextV2Task.mockResolvedValue({ task_id: "task-v2", status: "queued" });
    createParseHelperBundleV2Task.mockResolvedValue({ task_id: "task-bundle", status: "queued" });
    createTranslateTask.mockResolvedValue({ task_id: "task-translate", status: "queued" });
    getTask.mockResolvedValue({ task_id: "task-1", status: "queued" });
    normalizeSpringerInput.mockReturnValue(null);
    fetchSpringerOpenAccessJats.mockReset();
  });

  it("routes Elsevier local XML acquisition through parse-fulltext-v2 instead of the legacy upload endpoint", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    requiresElsevierLocalAcquire.mockReturnValue(true);
    fetchElsevierXml.mockResolvedValue({
      xmlBlob: new Blob(["<article/>"], { type: "application/xml" }),
      filename: "paper.xml",
      sourceDoi: "10.1016/j.energy.2026.140192",
      sourceInput: "10.1016/j.energy.2026.140192"
    });

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    expect(listener).toBeTypeOf("function");
    listener?.(
      {
        type: "mdtero.parse.request",
        input: "10.1016/j.energy.2026.140192",
        elsevierApiKey: "elsevier-key"
      },
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(createParseFulltextV2Task).toHaveBeenCalledWith(
        expect.objectContaining({
          fulltextFile: expect.any(Blob),
          filename: "paper.xml",
          sourceDoi: "10.1016/j.energy.2026.140192",
          sourceInput: "10.1016/j.energy.2026.140192"
        })
      );
      expect(createUploadedParseTask).not.toHaveBeenCalled();
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-v2", status: "queued" }
      });
    });
  });

  it("routes current-tab browser capture through parse-helper-bundle-v2 before falling back to direct parse", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    requiresElsevierLocalAcquire.mockReturnValue(false);
    chromeStub.tabs.sendMessage.mockResolvedValue({
      ok: true,
      capture: {
        ok: true,
        html: "<html><body><article><h1>Captured paper</h1></article></body></html>",
        payloadName: "paper.html",
        sourceUrl: "https://example.com/paper",
        pageTitle: "Captured paper"
      }
    });

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    expect(listener).toBeTypeOf("function");
    listener?.(
      {
        type: "mdtero.parse.request",
        input: "https://example.com/paper",
        pageContext: {
          tabId: 42,
          tabUrl: "https://example.com/paper"
        }
      },
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(chromeStub.tabs.sendMessage).toHaveBeenCalledWith(42, {
        type: "mdtero.capture_current_tab.request"
      });
      expect(createParseHelperBundleV2Task).toHaveBeenCalledWith(
        expect.objectContaining({
          helperBundleFile: expect.any(Blob),
          filename: "helper-bundle.zip",
          sourceInput: "https://example.com/paper"
        })
      );
      expect(createParseFulltextV2Task).not.toHaveBeenCalled();
      expect(createParseTask).not.toHaveBeenCalled();
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-bundle", status: "queued" }
      });
    });
  });

  it("routes local PDF uploads through parse-helper-bundle-v2 with the chosen PDF engine", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    requiresElsevierLocalAcquire.mockReturnValue(false);

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.parse.file.request",
        file: new File(["pdf"], "demo.pdf", { type: "application/pdf" }),
        filename: "demo.pdf",
        mediaType: "application/pdf",
        artifactKind: "pdf",
        pdfEngine: "docling"
      },
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(createParseHelperBundleV2Task).toHaveBeenCalledWith(
        expect.objectContaining({
          helperBundleFile: expect.any(Blob),
          filename: "helper-bundle.zip",
          sourceInput: "demo.pdf",
          pdfEngine: "docling"
        })
      );
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-bundle", status: "queued" }
      });
    });
  });

  it("routes local EPUB uploads through parse-helper-bundle-v2 without a PDF engine", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    requiresElsevierLocalAcquire.mockReturnValue(false);

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.parse.file.request",
        file: new File(["epub"], "demo.epub", { type: "application/epub+zip" }),
        filename: "demo.epub",
        mediaType: "application/epub+zip",
        artifactKind: "epub"
      },
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(createParseHelperBundleV2Task).toHaveBeenCalledWith(
        expect.objectContaining({
          helperBundleFile: expect.any(Blob),
          filename: "helper-bundle.zip",
          sourceInput: "demo.epub"
        })
      );
      const call = createParseHelperBundleV2Task.mock.calls.at(-1)?.[0];
      expect(call?.pdfEngine).toBeUndefined();
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-bundle", status: "queued" }
      });
    });
  });

  it("prefers current-tab XML over HTML helper bundles when the page context returns structured XML", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    requiresElsevierLocalAcquire.mockReturnValue(false);
    normalizeSpringerInput.mockReturnValue("10.1007/s12011-024-04385-0");
    chromeStub.tabs.sendMessage.mockResolvedValue({
      ok: true,
      xml: {
        ok: true,
        payloadText: "<article><body>Springer XML</body></article>",
        payloadName: "paper.xml",
        sourceUrl: "https://api.springernature.com/openaccess/jats?q=doi:10.1007%2Fs12011-024-04385-0"
      },
      capture: {
        ok: true,
        html: "<html><body><article>Captured paper</article></body></html>",
        payloadName: "paper.html",
        sourceUrl: "https://link.springer.com/article/10.1007/s12011-024-04385-0",
        pageTitle: "Captured paper"
      }
    });

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.parse.request",
        input: "https://link.springer.com/article/10.1007/s12011-024-04385-0",
        pageContext: {
          tabId: 42,
          tabUrl: "https://link.springer.com/article/10.1007/s12011-024-04385-0"
        }
      },
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(chromeStub.tabs.sendMessage).toHaveBeenCalledWith(42, {
        type: "mdtero.capture_current_tab.request",
        springerOpenAccessApiKey: undefined
      });
      expect(createParseFulltextV2Task).toHaveBeenCalledWith(
        expect.objectContaining({
          fulltextFile: expect.any(Blob),
          filename: "paper.xml",
          sourceDoi: "10.1007/s12011-024-04385-0"
        })
      );
      expect(createParseHelperBundleV2Task).not.toHaveBeenCalled();
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-v2", status: "queued" }
      });
    });
  });

  it("prefers local Springer OA JATS when a Springer OA key is available", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    readSettings.mockResolvedValue({
      token: "demo-token",
      email: "demo@example.com",
      springerOpenAccessApiKey: "springer-oa-key"
    });
    requiresElsevierLocalAcquire.mockReturnValue(false);
    normalizeSpringerInput.mockReturnValue("10.1007/s12011-024-04385-0");
    fetchSpringerOpenAccessJats.mockResolvedValue({
      xmlBlob: new Blob(["<article/>"], { type: "application/xml" }),
      filename: "paper.xml",
      sourceDoi: "10.1007/s12011-024-04385-0",
      sourceInput: "https://link.springer.com/article/10.1007/s12011-024-04385-0"
    });

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.parse.request",
        input: "https://link.springer.com/article/10.1007/s12011-024-04385-0",
        pageContext: {
          tabId: 42,
          tabUrl: "https://link.springer.com/article/10.1007/s12011-024-04385-0"
        }
      },
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(fetchSpringerOpenAccessJats).toHaveBeenCalledWith(
        "https://link.springer.com/article/10.1007/s12011-024-04385-0",
        "springer-oa-key",
        "https://link.springer.com/article/10.1007/s12011-024-04385-0"
      );
      expect(createParseFulltextV2Task).toHaveBeenCalledWith(
        expect.objectContaining({
          fulltextFile: expect.any(Blob),
          filename: "paper.xml",
          sourceDoi: "10.1007/s12011-024-04385-0"
        })
      );
      expect(createParseHelperBundleV2Task).not.toHaveBeenCalled();
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-v2", status: "queued" }
      });
    });
  });

  it("returns actionable sign-in guidance when the live page is still behind institutional access", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    requiresElsevierLocalAcquire.mockReturnValue(false);
    chromeStub.tabs.sendMessage.mockResolvedValue({
      ok: true,
      capture: {
        ok: false,
        failureCode: "login_required",
        failureMessage: "Page loaded but still requires user sign-in or institutional access."
      }
    });

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.parse.request",
        input: "https://example.com/paper",
        pageContext: {
          tabId: 42,
          tabUrl: "https://example.com/paper"
        }
      },
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(createParseTask).not.toHaveBeenCalled();
      expect(sendResponse).toHaveBeenCalledWith({
        ok: false,
        error: "This page still requires institutional or account sign-in. Open the article in your browser, finish login, then retry capture."
      });
    });
  });

  it("returns actionable full-text guidance when the live page is only a PDF or download shell", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    requiresElsevierLocalAcquire.mockReturnValue(false);
    chromeStub.tabs.sendMessage.mockResolvedValue({
      ok: true,
      capture: {
        ok: false,
        failureCode: "article_body_missing",
        failureMessage: "Page loaded but no article body markers were detected."
      }
    });

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.parse.request",
        input: "https://example.com/paper",
        pageContext: {
          tabId: 42,
          tabUrl: "https://example.com/paper"
        }
      },
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(createParseTask).not.toHaveBeenCalled();
      expect(sendResponse).toHaveBeenCalledWith({
        ok: false,
        error: "No article body was detected on the current page. Open the HTML full-text page instead of a PDF or download shell, then retry capture."
      });
    });
  });

  it("exposes bridge readiness status for helper diagnostics", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    expect(listener).toBeTypeOf("function");
    listener?.(
      {
        type: "mdtero.bridge.status"
      },
      {},
      sendResponse
    );

    expect(sendResponse).toHaveBeenCalledWith({
      ok: true,
      result: {
        state: "connected",
        runnerState: "idle"
      }
    });
  });
});
