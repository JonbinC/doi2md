import { beforeEach, describe, expect, it, vi } from "vitest";
import { createFileParseMessage } from "../src/lib/runtime";

const createParseTask = vi.fn();
const createUploadedParseTask = vi.fn();
const createParseFulltextV2Task = vi.fn();
const createTranslateTask = vi.fn();
const getTask = vi.fn();
const fetchRoutePlan = vi.fn();
const readSettings = vi.fn();
const writeSettings = vi.fn();
const requiresElsevierLocalAcquire = vi.fn();
const buildElsevierLocalAcquireGuidance = vi.fn(() => "Use local acquisition.");
const normalizeSpringerInput = vi.fn();

vi.mock("../src/lib/api", () => ({
  createApiClient: vi.fn(() => ({
    createParseTask,
    createUploadedParseTask,
    createParseFulltextV2Task,
    createTranslateTask,
    getTask
  })),
  createRouterSSOTClient: vi.fn(() => ({
    fetchRoutePlan
  }))
}));

vi.mock("../src/lib/storage", () => ({
  readSettings,
  writeSettings
}));

vi.mock("../src/lib/elsevier", () => ({
  requiresElsevierLocalAcquire,
  buildElsevierLocalAcquireGuidance
}));

vi.mock("../src/lib/springer", () => ({
  normalizeSpringerInput,
}));

function createChromeStub() {
  const messageListeners: Array<(message: unknown, sender: unknown, sendResponse: (payload: unknown) => void) => boolean | void> = [];
  return {
    runtime: {
      id: "runtime-demo",
      onMessage: {
        addListener(listener: (message: unknown, sender: unknown, sendResponse: (payload: unknown) => void) => boolean | void) {
          messageListeners.push(listener);
        }
      }
    },
    tabs: {
      sendMessage: vi.fn()
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
    createTranslateTask.mockResolvedValue({ task_id: "task-translate", status: "queued" });
    getTask.mockResolvedValue({ task_id: "task-1", status: "queued" });
    fetchRoutePlan.mockReset();
    normalizeSpringerInput.mockReturnValue(null);
  });

  it("does not accept direct Elsevier API keys in extension parse messages", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    requiresElsevierLocalAcquire.mockReturnValue(true);
    buildElsevierLocalAcquireGuidance.mockReturnValue("Use CLI academic keys or upload the PDF/XML.");

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
      expect(createParseFulltextV2Task).not.toHaveBeenCalled();
      expect(createUploadedParseTask).not.toHaveBeenCalled();
      expect(sendResponse).toHaveBeenCalledWith({
        ok: false,
        error: "Use CLI academic keys or upload the PDF/XML."
      });
    });
  });

  it("routes current-tab browser capture through raw fulltext upload before falling back to direct parse", async () => {
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
      expect(createParseFulltextV2Task).toHaveBeenCalledWith(
        expect.objectContaining({
          fulltextFile: expect.any(Blob),
          filename: "paper.html",
          sourceInput: "https://example.com/paper"
        })
      );
      expect(createParseTask).not.toHaveBeenCalled();
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-v2", status: "queued" }
      });
    });

    const rawArtifact = createParseFulltextV2Task.mock.calls[0]?.[0]?.fulltextFile as Blob;
    expect(rawArtifact.type).toBe("text/html");
    await expect(rawArtifact.text()).resolves.toContain("Captured paper");
  });

  it("skips current-tab raw upload for arxiv abs inputs and falls back to native parse", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    requiresElsevierLocalAcquire.mockReturnValue(false);

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.parse.request",
        input: "https://arxiv.org/abs/2507.01903",
        pageContext: {
          tabId: 42,
          tabUrl: "https://arxiv.org/abs/2507.01903"
        }
      },
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(chromeStub.tabs.sendMessage).not.toHaveBeenCalled();
      expect(createParseTask).toHaveBeenCalledWith({ input: "https://arxiv.org/abs/2507.01903" });
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-generic", status: "queued" }
      });
    });
  });

  it("captures current-tab arxiv html pages through raw fulltext upload", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    requiresElsevierLocalAcquire.mockReturnValue(false);
    chromeStub.tabs.sendMessage.mockResolvedValue({
      ok: true,
      capture: {
        ok: true,
        html: "<html><body><article class='ltx_document'><section class='ltx_abstract'></section><section class='ltx_section'></section></article></body></html>",
        payloadName: "paper.html",
        sourceUrl: "https://arxiv.org/html/2401.00001",
        pageTitle: "arXiv HTML Demo"
      }
    });

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.parse.request",
        input: "https://arxiv.org/html/2401.00001",
        pageContext: {
          tabId: 42,
          tabUrl: "https://arxiv.org/html/2401.00001"
        }
      },
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(chromeStub.tabs.sendMessage).toHaveBeenCalledWith(42, {
        type: "mdtero.capture_current_tab.request"
      });
      expect(createParseFulltextV2Task).toHaveBeenCalledWith(
        expect.objectContaining({
          fulltextFile: expect.any(Blob),
          filename: "paper.html",
          sourceInput: "https://arxiv.org/html/2401.00001"
        })
      );
      expect(createParseTask).not.toHaveBeenCalled();
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-v2", status: "queued" }
      });
    });

    const rawArtifact = createParseFulltextV2Task.mock.calls[0]?.[0]?.fulltextFile as Blob;
    await expect(rawArtifact.text()).resolves.toContain("ltx_document");
  });

  it("routes local PDF uploads through the v1 upload endpoint", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    requiresElsevierLocalAcquire.mockReturnValue(false);

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      createFileParseMessage(new File(["pdf"], "demo.pdf", { type: "application/pdf" }), "pdf"),
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(createUploadedParseTask).toHaveBeenCalledWith(
        expect.objectContaining({
          paperFile: expect.any(Blob),
          filename: "demo.pdf",
          sourceInput: "demo.pdf"
        })
      );
      expect(createParseFulltextV2Task).not.toHaveBeenCalled();
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-legacy", status: "queued" }
      });
    });
  });

  it("routes local EPUB uploads through the v1 upload endpoint", async () => {
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
      expect(createUploadedParseTask).toHaveBeenCalledWith(
        expect.objectContaining({
          paperFile: expect.any(Blob),
          filename: "demo.epub",
          sourceInput: "demo.epub"
        })
      );
      expect(createParseFulltextV2Task).not.toHaveBeenCalled();
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-legacy", status: "queued" }
      });
    });
  });

  it("executes SSOT helper-source routes through raw fulltext upload", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    requiresElsevierLocalAcquire.mockReturnValue(false);
    fetchRoutePlan.mockResolvedValue({
      input_kind: "doi",
      input_value: "10.1000/demo",
      top_connector: "wiley_tdm",
      route_kind: "html_helper_first",
      acquisition_mode: "browser_extension",
      requires_helper: true,
      allows_current_tab: true,
      action_sequence: ["fetch_helper_source"],
      acceptance_rules: {},
      fail_closed: true,
      user_message: "Open the article page and retry.",
      matched_connectors: ["wiley_tdm"],
      best_oa_url: undefined,
      acquisition_candidates: [
        {
          connector: "wiley_tdm",
          priority: 1,
          access: "licensed",
          format: "html"
        }
      ]
    });
    chromeStub.tabs.sendMessage.mockResolvedValue({
      ok: true,
      capture: {
        ok: true,
        html: "<html><body><article><h1>Captured paper</h1></article></body></html>",
        payloadName: "paper.html",
        sourceUrl: "https://onlinelibrary.wiley.com/doi/full/10.1000/demo",
        pageTitle: "Captured paper"
      }
    });

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.parse.ssot.request",
        input: "10.1000/demo",
        pageContext: {
          tabId: 42,
          tabUrl: "https://onlinelibrary.wiley.com/doi/full/10.1000/demo",
          tabTitle: "Captured paper"
        }
      },
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(fetchRoutePlan).toHaveBeenCalledWith({
        input: "10.1000/demo",
        page_url: "https://onlinelibrary.wiley.com/doi/full/10.1000/demo",
        page_title: "Captured paper"
      });
      expect(chromeStub.tabs.sendMessage).toHaveBeenCalledWith(42, {
        type: "mdtero.capture_current_tab.request",
      });
      expect(createParseFulltextV2Task).toHaveBeenCalledWith(
        expect.objectContaining({
          fulltextFile: expect.any(Blob),
          filename: "paper.html",
          sourceInput: "10.1000/demo"
        })
      );
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-v2", status: "queued" }
      });
    });

    const rawArtifact = createParseFulltextV2Task.mock.calls[0]?.[0]?.fulltextFile as Blob;
    await expect(rawArtifact.text()).resolves.toContain("Captured paper");
  });

  it("executes SSOT EPUB routes through browser download and raw fulltext upload", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    requiresElsevierLocalAcquire.mockReturnValue(false);
    fetchRoutePlan.mockResolvedValue({
      input_kind: "doi",
      input_value: "10.1080/26395940.2021.1947159",
      top_connector: "taylor_francis_oa_epub",
      route_kind: "epub_first",
      acquisition_mode: "browser_extension",
      requires_helper: true,
      allows_current_tab: true,
      action_sequence: ["fetch_epub_asset"],
      acceptance_rules: {},
      fail_closed: true,
      user_message: "Open the article page and retry.",
      matched_connectors: ["taylor_francis_oa_epub", "taylor_francis_tdm"],
      acquisition_candidates: [
        {
          connector: "taylor_francis_oa_epub",
          priority: 1,
          access: "open",
          epub_url: "https://www.tandfonline.com/doi/epub/10.1080/26395940.2021.1947159?needAccess=true"
        }
      ]
    });
    chromeStub.tabs.sendMessage.mockResolvedValue({
      ok: true,
      download: {
        ok: true,
        payloadBase64: "UEsDBGJlbW8tZXB1Yg==",
        payloadName: "paper.epub",
        sourceUrl: "https://www.tandfonline.com/doi/epub/10.1080/26395940.2021.1947159?needAccess=true"
      }
    });

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.parse.ssot.request",
        input: "10.1080/26395940.2021.1947159",
        pageContext: {
          tabId: 42,
          tabUrl: "https://www.tandfonline.com/doi/full/10.1080/26395940.2021.1947159",
          tabTitle: "T&F OA Paper"
        }
      },
      {},
      sendResponse
    );

    await vi.waitFor(async () => {
      expect(chromeStub.tabs.sendMessage).toHaveBeenCalledWith(42, {
        type: "mdtero.download_epub.request",
        artifactUrl: "https://www.tandfonline.com/doi/epub/10.1080/26395940.2021.1947159?needAccess=true"
      });
      expect(createParseFulltextV2Task).toHaveBeenCalledWith(
        expect.objectContaining({
          fulltextFile: expect.any(Blob),
          filename: "paper.epub",
          sourceDoi: "10.1080/26395940.2021.1947159",
          sourceInput: "10.1080/26395940.2021.1947159"
        })
      );
      const rawArtifact = createParseFulltextV2Task.mock.calls[0]?.[0]?.fulltextFile as Blob;
      expect(rawArtifact.type).toBe("application/epub+zip");
      const text = new TextDecoder().decode(new Uint8Array(await rawArtifact.arrayBuffer()));
      expect(text).toContain("PK");
      expect(text).toContain("bemo-epub");
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-v2", status: "queued" }
      });
    });
  });

  it("returns browser-capture guidance when an SSOT page route cannot use the current tab", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    requiresElsevierLocalAcquire.mockReturnValue(false);
    fetchRoutePlan.mockResolvedValue({
      input_kind: "doi",
      input_value: "10.1000/demo",
      top_connector: "wiley_tdm",
      route_kind: "html_helper_first",
      acquisition_mode: "browser_extension",
      requires_helper: true,
      allows_current_tab: true,
      action_sequence: ["fetch_helper_source"],
      acceptance_rules: {},
      fail_closed: true,
      user_message: "Open the article page and retry.",
      matched_connectors: ["wiley_tdm"],
      acquisition_candidates: []
    });

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.parse.ssot.request",
        input: "10.1000/demo"
      },
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(createParseFulltextV2Task).not.toHaveBeenCalled();
      expect(sendResponse).toHaveBeenCalledWith({
        ok: false,
        error: "This source requires browser capture. Open the article page and retry.",
        nextCommand: "mdtero parse 10.1000/demo --trace --wait --timeout 300 --json"
      });
    });
  });

  it("executes SSOT OA repository routes through direct HTML fetch and raw fulltext upload", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    requiresElsevierLocalAcquire.mockReturnValue(false);
    fetchRoutePlan.mockResolvedValue({
      input_kind: "doi",
      input_value: "10.9999/demo-open",
      top_connector: "best_oa_location_html",
      route_kind: "html_helper_first",
      acquisition_mode: "native_source_adapter",
      requires_helper: false,
      allows_current_tab: false,
      action_sequence: ["fetch_oa_repository"],
      acceptance_rules: {},
      fail_closed: true,
      user_message: "Using open access repository.",
      matched_connectors: ["best_oa_location_html"],
      best_oa_url: "https://example.org/articles/demo-open",
      acquisition_candidates: [
        {
          connector: "best_oa_location_html",
          priority: 1,
          access: "open",
          html_url: "https://example.org/articles/demo-open"
        }
      ]
    });

    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      url: "https://example.org/articles/demo-open",
      text: async () => "<html><body><article><h1>OA Demo</h1></article></body></html>"
    }) as Response) as typeof fetch;

    try {
      await import("../src/background");

      const listener = chromeStub.__messageListeners[0];
      const sendResponse = vi.fn();

      listener?.(
        {
          type: "mdtero.parse.ssot.request",
          input: "10.9999/demo-open"
        },
        {},
        sendResponse
      );

      await vi.waitFor(async () => {
        expect(chromeStub.tabs.sendMessage).not.toHaveBeenCalled();
        expect(globalThis.fetch).toHaveBeenCalledWith("https://example.org/articles/demo-open", { credentials: "include" });
        expect(createParseFulltextV2Task).toHaveBeenCalledWith(
          expect.objectContaining({
            fulltextFile: expect.any(Blob),
            filename: "paper.html",
            sourceDoi: "10.9999/demo-open",
            sourceInput: "10.9999/demo-open"
          })
        );
        const rawArtifact = createParseFulltextV2Task.mock.calls[0]?.[0]?.fulltextFile as Blob;
        const text = await rawArtifact.text();
        expect(text).toContain("OA Demo");
        expect(sendResponse).toHaveBeenCalledWith({
          ok: true,
          result: { task_id: "task-v2", status: "queued" }
        });
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("prefers current-tab capture before OA repository fetch when SSOT enables it", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    requiresElsevierLocalAcquire.mockReturnValue(false);
    fetchRoutePlan.mockResolvedValue({
      input_kind: "doi",
      input_value: "10.9999/demo-open",
      top_connector: "best_oa_location_html",
      route_kind: "html_helper_first",
      acquisition_mode: "native_source_adapter",
      requires_helper: false,
      allows_current_tab: true,
      action_sequence: ["capture_current_tab_html", "fetch_oa_repository"],
      acceptance_rules: {},
      fail_closed: true,
      user_message: "Prefer current tab capture.",
      matched_connectors: ["best_oa_location_html"],
      best_oa_url: "https://example.org/articles/demo-open",
      acquisition_candidates: [
        {
          connector: "best_oa_location_html",
          priority: 1,
          access: "open",
          html_url: "https://example.org/articles/demo-open"
        }
      ]
    });
    chromeStub.tabs.sendMessage.mockResolvedValue({
      ok: true,
      capture: {
        ok: true,
        html: "<html><body><article><h1>Browser DOM Demo</h1><img src=\"fig1.png\" /></article></body></html>",
        payloadName: "paper.html",
        sourceUrl: "https://example.org/articles/demo-open",
        pageTitle: "Browser DOM Demo"
      }
    });

    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      url: "https://example.org/articles/demo-open",
      text: async () => "<html><body><article><h1>Fallback Demo</h1></article></body></html>"
    }) as Response) as typeof fetch;

    try {
      await import("../src/background");

      const listener = chromeStub.__messageListeners[0];
      const sendResponse = vi.fn();

      listener?.(
        {
          type: "mdtero.parse.ssot.request",
          input: "10.9999/demo-open",
          pageContext: {
            tabId: 42,
            tabUrl: "https://example.org/articles/demo-open",
            tabTitle: "Browser DOM Demo"
          }
        },
        {},
        sendResponse
      );

      await vi.waitFor(async () => {
        expect(chromeStub.tabs.sendMessage).toHaveBeenCalledWith(
          42,
          expect.objectContaining({
            type: "mdtero.capture_current_tab.request"
          })
        );
        expect(globalThis.fetch).not.toHaveBeenCalled();
        expect(createParseFulltextV2Task).toHaveBeenCalledWith(
          expect.objectContaining({
            fulltextFile: expect.any(Blob),
            filename: "paper.html",
            sourceDoi: "10.9999/demo-open",
            sourceInput: "10.9999/demo-open"
          })
        );
        const rawArtifact = createParseFulltextV2Task.mock.calls[0]?.[0]?.fulltextFile as Blob;
        const text = await rawArtifact.text();
        expect(text).toContain("Browser DOM Demo");
        expect(sendResponse).toHaveBeenCalledWith({
          ok: true,
          result: { task_id: "task-v2", status: "queued" }
        });
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("prefers current-tab XML over HTML capture when the page context returns structured XML", async () => {
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
      });
      expect(createParseFulltextV2Task).toHaveBeenCalledWith(
        expect.objectContaining({
          fulltextFile: expect.any(Blob),
          filename: "paper.xml",
          sourceDoi: "10.1007/s12011-024-04385-0"
        })
      );
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

  it("does not expose the retired native helper diagnostics", async () => {
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

    expect(sendResponse).not.toHaveBeenCalled();
  });

  it("does not expose retired source connectivity helper observations", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    expect(listener).toBeTypeOf("function");
    listener?.(
      {
        type: "mdtero.source_connectivity.observation"
      },
      {},
      sendResponse
    );

    expect(sendResponse).not.toHaveBeenCalled();
  });
});
