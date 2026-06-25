import { beforeEach, describe, expect, it, vi } from "vitest";
import { createFileParseMessage } from "../src/lib/runtime";

const createParseTask = vi.fn();
const createUploadedParseTask = vi.fn();
const createRawUploadTask = vi.fn();
const createTranslateTask = vi.fn();
const getTask = vi.fn();
const downloadArtifact = vi.fn();
const fetchRoutePlan = vi.fn();
const readSettings = vi.fn();
const writeSettings = vi.fn();

vi.mock("../src/lib/api", () => ({
  createApiClient: vi.fn(() => ({
    createParseTask,
    createUploadedParseTask,
    createRawUploadTask,
    createTranslateTask,
    getTask,
    downloadArtifact
  })),
  createRouterSSOTClient: vi.fn(() => ({
    fetchRoutePlan
  }))
}));

vi.mock("../src/lib/storage", () => ({
  readSettings,
  writeSettings,
  SETTINGS_KEY: "mdtero_settings"
}));

function createChromeStub() {
  const messageListeners: Array<(message: unknown, sender: unknown, sendResponse: (payload: unknown) => void) => boolean | void> = [];
  return {
    runtime: {
      id: "runtime-demo",
      getManifest: vi.fn(() => ({
        content_scripts: [
          { js: ["dist/content.js"] },
        ],
      })),
      onMessage: {
        addListener(listener: (message: unknown, sender: unknown, sendResponse: (payload: unknown) => void) => boolean | void) {
          messageListeners.push(listener);
        }
      }
    },
    tabs: {
      sendMessage: vi.fn()
    },
    scripting: {
      executeScript: vi.fn().mockResolvedValue(undefined),
    },
    storage: {
      onChanged: {
        addListener: vi.fn()
      }
    },
    proxy: {
      settings: {
        clear: vi.fn(async () => undefined),
        set: vi.fn(async () => undefined)
      }
    },
    __messageListeners: messageListeners
  };
}

describe("extension background routing", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    readSettings.mockResolvedValue({
      token: "demo-token",
      email: "demo@example.com",
      proxyEnabled: false,
      requireCampusProxy: false
    });
    writeSettings.mockResolvedValue(undefined);
    createParseTask.mockResolvedValue({ task_id: "task-generic", status: "queued" });
    createUploadedParseTask.mockResolvedValue({ task_id: "task-legacy", status: "queued" });
    createRawUploadTask.mockResolvedValue({ task_id: "task-v2", status: "queued" });
    createTranslateTask.mockResolvedValue({ task_id: "task-translate", status: "queued" });
    getTask.mockResolvedValue({
      notModified: false,
      result: { task_id: "task-1", status: "queued" },
      etag: '"task-1-etag"'
    });
    downloadArtifact.mockResolvedValue({ blob: new Blob(["# Demo\n\nBody"]), filename: "demo.md" });
    fetchRoutePlan.mockReset();
  });

  it("persists website OAuth tokens from the trusted auth bridge", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    readSettings.mockResolvedValue({
      apiBaseUrl: "https://api.mdtero.com",
      token: "old-token",
      email: "old@example.com",
      uiLanguage: "zh",
    });

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    expect(listener).toBeTypeOf("function");
    listener?.(
      {
        type: "mdtero.auth.save_token",
        token: "web-token",
        email: "reader@example.com",
      },
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(writeSettings).toHaveBeenCalledWith({
        apiBaseUrl: "https://api.mdtero.com",
        token: "web-token",
        email: "reader@example.com",
        uiLanguage: "zh",
      });
      expect(sendResponse).toHaveBeenCalledWith({ ok: true });
    });
  });

  it("does not expose the retired pre-SSOT parse message", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    expect(listener).toBeTypeOf("function");
    const handled = listener?.(
      {
        type: "mdtero.parse.request",
        input: "10.1016/j.energy.2026.140192",
      },
      {},
      sendResponse
    );

    expect(handled).toBe(false);
    expect(createParseTask).not.toHaveBeenCalled();
    expect(createRawUploadTask).not.toHaveBeenCalled();
    expect(createUploadedParseTask).not.toHaveBeenCalled();
    expect(sendResponse).not.toHaveBeenCalled();
  });

  it("routes local PDF uploads through the v1 upload endpoint", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);

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
      expect(createRawUploadTask).not.toHaveBeenCalled();
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-legacy", status: "queued" }
      });
    });
  });

  it("routes local EPUB uploads through the v1 upload endpoint", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);

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
          sourceInput: "demo.epub",
          artifactKind: "epub"
        })
      );
      expect(createRawUploadTask).not.toHaveBeenCalled();
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-legacy", status: "queued" }
      });
    });
  });

  it("routes local HTML uploads through the v1 upload endpoint", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      createFileParseMessage(new File(["<html><article>Full text</article></html>"], "paper.html", { type: "text/html" }), "html"),
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(createUploadedParseTask).toHaveBeenCalledWith(
        expect.objectContaining({
          paperFile: expect.any(Blob),
          filename: "paper.html",
          sourceInput: "paper.html",
          artifactKind: "html"
        })
      );
      expect(createRawUploadTask).not.toHaveBeenCalled();
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-legacy", status: "queued" }
      });
    });
  });

  it("captures the current page through the dedicated HTML upload path", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    chromeStub.tabs.sendMessage.mockResolvedValue({
      ok: true,
      capture: {
        ok: true,
        html: "<html><body><article>Captured browser full text</article></body></html>",
        payloadName: "paper.html",
        sourceUrl: "https://example.org/fulltext",
        pageTitle: "Captured browser full text",
      },
    });

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.parse.current_html.request",
        input: "10.1000/current-html",
        pageContext: {
          tabId: 42,
          tabUrl: "https://example.org/fulltext",
        },
      },
      {},
      sendResponse
    );

    await vi.waitFor(async () => {
      expect(fetchRoutePlan).not.toHaveBeenCalled();
      expect(chromeStub.tabs.sendMessage).toHaveBeenCalledWith(42, {
        type: "mdtero.capture_html.request",
      });
      expect(createRawUploadTask).toHaveBeenCalledWith(
        expect.objectContaining({
          rawFile: expect.any(Blob),
          filename: "paper.html",
          sourceDoi: "10.1000/current-html",
          sourceInput: "10.1000/current-html",
          artifactKind: "html",
        })
      );
      const rawArtifact = createRawUploadTask.mock.calls[0]?.[0]?.rawFile as Blob;
      await expect(rawArtifact.text()).resolves.toContain("Captured browser full text");
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-v2", status: "queued" },
      });
    });
  });

  it("injects the content script before dedicated HTML capture on unsupported active tabs", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    chromeStub.tabs.sendMessage
      .mockRejectedValueOnce(new Error("Could not establish connection. Receiving end does not exist."))
      .mockResolvedValueOnce({
        ok: true,
        capture: {
          ok: true,
          html: "<html><body><article>Dynamically injected capture</article></body></html>",
          payloadName: "paper.html",
          sourceUrl: "https://publisher.example/fulltext",
          pageTitle: "Injected capture",
        },
      });

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.parse.current_html.request",
        input: "https://publisher.example/fulltext",
        pageContext: {
          tabId: 77,
          tabUrl: "https://publisher.example/fulltext",
        },
      },
      {},
      sendResponse
    );

    await vi.waitFor(async () => {
      expect(chromeStub.scripting.executeScript).toHaveBeenCalledWith({
        target: { tabId: 77 },
        files: ["dist/content.js"],
      });
      expect(chromeStub.tabs.sendMessage).toHaveBeenCalledTimes(2);
      expect(createRawUploadTask).toHaveBeenCalledWith(
        expect.objectContaining({
          rawFile: expect.any(Blob),
          filename: "paper.html",
          sourceInput: "https://publisher.example/fulltext",
          artifactKind: "html",
        })
      );
      const rawArtifact = createRawUploadTask.mock.calls[0]?.[0]?.rawFile as Blob;
      await expect(rawArtifact.text()).resolves.toContain("Dynamically injected capture");
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-v2", status: "queued" },
      });
    });
  });

  it("translates by server markdown path when legacy artifacts expose one", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.translate.request",
        sourceMarkdownPath: "/app/tasks/parse-1/paper.md",
        targetLanguage: "zh",
        mode: "standard"
      },
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(downloadArtifact).not.toHaveBeenCalled();
      expect(createTranslateTask).toHaveBeenCalledWith({
        source_markdown_path: "/app/tasks/parse-1/paper.md",
        target_language: "zh",
        mode: "standard"
      });
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-translate", status: "queued" }
      });
    });
  });

  it("translates v1-only markdown artifacts by downloading text first", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.translate.request",
        sourceTaskId: "task-parse",
        sourceArtifactKey: "paper_md",
        sourceFilename: "vaswani2017attention.md",
        targetLanguage: "zh",
        mode: "standard"
      },
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(downloadArtifact).toHaveBeenCalledWith("task-parse", "paper_md", "vaswani2017attention.md");
      expect(createTranslateTask).toHaveBeenCalledWith({
        source_markdown_path: "",
        source_markdown_text: "# Demo\n\nBody",
        source_markdown_filename: "demo.md",
        target_language: "zh",
        mode: "standard"
      });
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-translate", status: "queued" }
      });
    });
  });

  it("returns a CLI file handoff when local upload submission fails", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    createUploadedParseTask.mockRejectedValueOnce(new Error("upload timed out"));

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.parse.file.request",
        file: new File(["pdf"], "My Paper's Draft.pdf", { type: "application/pdf" }),
        filename: "My Paper's Draft.pdf",
        mediaType: "application/pdf",
        artifactKind: "pdf"
      },
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(sendResponse).toHaveBeenCalledWith({
        ok: false,
        error: "upload timed out",
        nextCommand: "mdtero parse --file 'My Paper'\"'\"'s Draft.pdf' --trace --wait --timeout 600 --json"
      });
    });
  });

  it("returns an XML-aware CLI handoff when raw local upload submission fails", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    createUploadedParseTask.mockRejectedValueOnce(new Error("upload timed out"));

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.parse.file.request",
        file: new File(["<article />"], "fulltext.xml", { type: "application/xml" }),
        filename: "fulltext.xml",
        mediaType: "application/xml",
        artifactKind: "xml"
      },
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(sendResponse).toHaveBeenCalledWith({
        ok: false,
        error: "upload timed out",
        nextCommand: "mdtero parse --file fulltext.xml --trace --wait --timeout 600 --json"
      });
    });
  });

  it("executes SSOT source-first routes through raw artifact upload", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    fetchRoutePlan.mockResolvedValue({
      input_kind: "doi",
      input_value: "10.1000/demo",
      top_connector: "wiley_tdm",
      route_kind: "browser_capture_required",
      acquisition_mode: "browser_extension",
      requires_browser_capture: true,
      allows_current_tab: true,
      action_sequence: ["fetch_browser_source"],
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
          format: "html",
          html_url: "https://onlinelibrary.wiley.com/doi/full/10.1000/demo"
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
        type: "mdtero.fetch_html.request",
        candidateUrls: ["https://onlinelibrary.wiley.com/doi/full/10.1000/demo"],
      });
      expect(chromeStub.tabs.sendMessage).toHaveBeenCalledWith(42, {
        type: "mdtero.capture_current_tab.request",
      });
      expect(createRawUploadTask).toHaveBeenCalledWith(
        expect.objectContaining({
          rawFile: expect.any(Blob),
          filename: "paper.html",
          sourceInput: "10.1000/demo",
          artifactKind: "html"
        })
      );
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-v2", status: "queued" }
      });
    });

    const rawArtifact = createRawUploadTask.mock.calls[0]?.[0]?.rawFile as Blob;
    await expect(rawArtifact.text()).resolves.toContain("Captured paper");
  });

  it("uses v1 server parse when the route planner is unavailable", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    fetchRoutePlan.mockResolvedValue({
      input_kind: "unknown",
      input_value: "",
      top_connector: "server_parse",
      route_kind: "server",
      acquisition_mode: "server_parse",
      requires_browser_capture: false,
      allows_current_tab: false,
      action_sequence: ["server_parse"],
      acceptance_rules: {},
      fail_closed: true,
      matched_connectors: ["server_parse"],
      route_planner_fallback: true,
      server_entrypoint: "/api/v1/tasks/parse",
      upload_entrypoint: "/api/v1/tasks/upload"
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
      expect(createParseTask).toHaveBeenCalledWith({ input: "10.1000/demo" });
      expect(createRawUploadTask).not.toHaveBeenCalled();
      expect(chromeStub.tabs.sendMessage).not.toHaveBeenCalled();
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-generic", status: "queued" }
      });
    });
  });

  it("parses CNKI current-page PDFs through browser-session download without route planning", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    chromeStub.tabs.sendMessage.mockResolvedValue({
      ok: true,
      download: {
        ok: true,
        payloadBase64: "JVBERi0xLjc=",
        payloadName: "paper.pdf",
        sourceUrl: "https://kns.cnki.net/kcms2/article/download?filename=paper.pdf"
      }
    });

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.parse.ssot.request",
        input: "https://kns.cnki.net/kcms2/article/abstract?v=demo",
        pageContext: {
          tabId: 42,
          tabUrl: "https://kns.cnki.net/kcms2/article/abstract?v=demo",
          tabTitle: "CNKI Paper"
        }
      },
      {},
      sendResponse
    );

    await vi.waitFor(async () => {
      expect(fetchRoutePlan).not.toHaveBeenCalled();
      expect(chromeStub.tabs.sendMessage).toHaveBeenCalledWith(42, {
        type: "mdtero.download_current_page_pdf.request",
      });
      expect(createRawUploadTask).toHaveBeenCalledWith(
        expect.objectContaining({
          rawFile: expect.any(Blob),
          filename: "paper.pdf",
          sourceInput: "https://kns.cnki.net/kcms2/article/abstract?v=demo",
          artifactKind: "pdf"
        })
      );
      const rawArtifact = createRawUploadTask.mock.calls[0]?.[0]?.rawFile as Blob;
      expect(rawArtifact.type).toBe("application/pdf");
      expect(new TextDecoder().decode(new Uint8Array(await rawArtifact.arrayBuffer()))).toBe("%PDF-1.7");
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-v2", status: "queued" }
      });
    });
  });

  it("parses IEEE current-page PDFs through browser-session download before route planning", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    chromeStub.tabs.sendMessage.mockResolvedValue({
      ok: true,
      download: {
        ok: true,
        payloadBase64: "JVBERi0xLjc=",
        payloadName: "paper.pdf",
        sourceUrl: "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=9919149"
      }
    });

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.parse.ssot.request",
        input: "10.1109/demo",
        pageContext: {
          tabId: 42,
          tabUrl: "https://ieeexplore.ieee.org/document/9919149",
          tabTitle: "IEEE Paper"
        }
      },
      {},
      sendResponse
    );

    await vi.waitFor(async () => {
      expect(fetchRoutePlan).not.toHaveBeenCalled();
      expect(chromeStub.tabs.sendMessage).toHaveBeenCalledWith(42, {
        type: "mdtero.download_current_page_pdf.request",
      });
      expect(createRawUploadTask).toHaveBeenCalledWith(
        expect.objectContaining({
          rawFile: expect.any(Blob),
          filename: "paper.pdf",
          sourceDoi: "10.1109/demo",
          sourceInput: "10.1109/demo",
          artifactKind: "pdf"
        })
      );
      const rawArtifact = createRawUploadTask.mock.calls[0]?.[0]?.rawFile as Blob;
      expect(rawArtifact.type).toBe("application/pdf");
      expect(new TextDecoder().decode(new Uint8Array(await rawArtifact.arrayBuffer()))).toBe("%PDF-1.7");
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-v2", status: "queued" }
      });
    });
  });

  it("executes SSOT EPUB routes through browser download and raw artifact upload", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    fetchRoutePlan.mockResolvedValue({
      input_kind: "doi",
      input_value: "10.1080/26395940.2021.1947159",
      top_connector: "taylor_francis_oa_epub",
      route_kind: "epub_first",
      acquisition_mode: "browser_extension",
      requires_browser_capture: true,
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
      expect(createRawUploadTask).toHaveBeenCalledWith(
        expect.objectContaining({
          rawFile: expect.any(Blob),
          filename: "paper.epub",
          sourceDoi: "10.1080/26395940.2021.1947159",
          sourceInput: "10.1080/26395940.2021.1947159",
          artifactKind: "epub"
        })
      );
      const rawArtifact = createRawUploadTask.mock.calls[0]?.[0]?.rawFile as Blob;
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

  it("executes SSOT PDF handoff routes through browser download and raw artifact upload", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    fetchRoutePlan.mockResolvedValue({
      input_kind: "doi",
      input_value: "10.1109/demo",
      top_connector: "publisher_pdf_guess",
      route_kind: "browser_capture_required",
      acquisition_mode: "browser_extension",
      requires_browser_capture: true,
      allows_current_tab: true,
      action_sequence: ["fallback_pdf_parse"],
      acceptance_rules: {},
      fail_closed: true,
      user_message: "Use browser session for the publisher PDF gateway.",
      matched_connectors: ["publisher_pdf_guess"],
      acquisition_candidates: [],
      client_handoff_candidates: [
        {
          transport: "browser_extension",
          capture_mode: "download_artifact",
          artifact_kind: "pdf",
          connector: "publisher_pdf_guess",
          source: "publisher_pdf_guess:ieee_stamp_gateway",
          artifact_url: "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=9919149",
          requires_user_rights: true,
        }
      ],
      publisher_capabilities: {
        access_mode: "institution_browser",
        browser_extension_useful: true,
      }
    });
    chromeStub.tabs.sendMessage.mockResolvedValue({
      ok: true,
      download: {
        ok: true,
        payloadBase64: "JVBERi0xLjc=",
        payloadName: "paper.pdf",
        sourceUrl: "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=9919149"
      }
    });

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.parse.ssot.request",
        input: "10.1109/demo",
        pageContext: {
          tabId: 42,
          tabUrl: "https://doi.org/10.1109/demo",
          tabTitle: "IEEE Paper"
        }
      },
      {},
      sendResponse
    );

    await vi.waitFor(async () => {
      expect(chromeStub.tabs.sendMessage).toHaveBeenCalledWith(42, {
        type: "mdtero.download_pdf.request",
        artifactUrl: "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=9919149"
      });
      expect(createRawUploadTask).toHaveBeenCalledWith(
        expect.objectContaining({
          rawFile: expect.any(Blob),
          filename: "paper.pdf",
          sourceDoi: "10.1109/demo",
          sourceInput: "10.1109/demo",
          artifactKind: "pdf"
        })
      );
      const rawArtifact = createRawUploadTask.mock.calls[0]?.[0]?.rawFile as Blob;
      expect(rawArtifact.type).toBe("application/pdf");
      const text = new TextDecoder().decode(new Uint8Array(await rawArtifact.arrayBuffer()));
      expect(text).toBe("%PDF-1.7");
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-v2", status: "queued" }
      });
    });
  });

  it("returns browser-capture guidance when an SSOT page route cannot use the current tab", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    fetchRoutePlan.mockResolvedValue({
      input_kind: "doi",
      input_value: "10.1000/demo",
      top_connector: "wiley_tdm",
      route_kind: "browser_capture_required",
      acquisition_mode: "browser_extension",
      requires_browser_capture: true,
      allows_current_tab: true,
      action_sequence: ["fetch_browser_source"],
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
      expect(createRawUploadTask).not.toHaveBeenCalled();
      expect(sendResponse).toHaveBeenCalledWith({
        ok: false,
        error: "This source requires browser capture. Open the article page and retry.",
        nextCommand: "mdtero parse 10.1000/demo --trace --wait --timeout 300 --json"
      });
    });
  });

  it("executes SSOT OA repository routes through direct HTML fetch and raw artifact upload", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    fetchRoutePlan.mockResolvedValue({
      input_kind: "doi",
      input_value: "10.9999/demo-open",
      top_connector: "best_oa_location_html",
      route_kind: "browser_capture_required",
      acquisition_mode: "native_source_adapter",
      requires_browser_capture: false,
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
        expect(createRawUploadTask).toHaveBeenCalledWith(
          expect.objectContaining({
            rawFile: expect.any(Blob),
            filename: "paper.html",
            sourceDoi: "10.9999/demo-open",
            sourceInput: "10.9999/demo-open",
            artifactKind: "html"
          })
        );
        const rawArtifact = createRawUploadTask.mock.calls[0]?.[0]?.rawFile as Blob;
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
    fetchRoutePlan.mockResolvedValue({
      input_kind: "doi",
      input_value: "10.9999/demo-open",
      top_connector: "best_oa_location_html",
      route_kind: "browser_capture_required",
      acquisition_mode: "native_source_adapter",
      requires_browser_capture: false,
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
        expect(createRawUploadTask).toHaveBeenCalledWith(
          expect.objectContaining({
            rawFile: expect.any(Blob),
            filename: "paper.html",
            sourceDoi: "10.9999/demo-open",
            sourceInput: "10.9999/demo-open",
            artifactKind: "html"
          })
        );
        const rawArtifact = createRawUploadTask.mock.calls[0]?.[0]?.rawFile as Blob;
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

  it("prefers current-tab XML over HTML capture when SSOT capture returns structured XML", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    fetchRoutePlan.mockResolvedValue({
      input_kind: "url",
      input_value: "https://link.springer.com/article/10.1007/s12011-024-04385-0",
      top_connector: "springer_openaccess_api",
      route_kind: "browser_capture_required",
      acquisition_mode: "browser_extension",
      requires_browser_capture: true,
      allows_current_tab: true,
      action_sequence: ["capture_current_tab_html"],
      acceptance_rules: {},
      fail_closed: true,
      user_message: "Capture the current Springer page.",
      matched_connectors: ["springer_openaccess_api"],
      acquisition_candidates: []
    });
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
        type: "mdtero.parse.ssot.request",
        input: "https://link.springer.com/article/10.1007/s12011-024-04385-0",
        pageContext: {
          tabId: 42,
          tabUrl: "https://link.springer.com/article/10.1007/s12011-024-04385-0",
          tabTitle: "Captured paper"
        }
      },
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(chromeStub.tabs.sendMessage).toHaveBeenCalledWith(42, {
        type: "mdtero.capture_current_tab.request",
      });
      expect(createRawUploadTask).toHaveBeenCalledWith(
        expect.objectContaining({
          rawFile: expect.any(Blob),
          filename: "paper.xml",
          sourceInput: "https://link.springer.com/article/10.1007/s12011-024-04385-0",
          artifactKind: "xml"
        })
      );
      expect(sendResponse).toHaveBeenCalledWith({
        ok: true,
        result: { task_id: "task-v2", status: "queued" }
      });
    });
  });

  it("returns actionable access-shell guidance when SSOT capture sees institutional access", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    fetchRoutePlan.mockResolvedValue({
      input_kind: "url",
      input_value: "https://example.com/paper",
      top_connector: "browser_capture",
      route_kind: "browser_capture_required",
      acquisition_mode: "browser_extension",
      requires_browser_capture: true,
      allows_current_tab: true,
      action_sequence: ["capture_current_tab_html"],
      acceptance_rules: {},
      fail_closed: true,
      user_message: "Capture the current page.",
      matched_connectors: ["browser_capture"],
      acquisition_candidates: []
    });
    chromeStub.tabs.sendMessage.mockResolvedValue({
      ok: true,
      capture: {
        ok: false,
        failureCode: "login_required",
        failureMessage: "The tab is open, but Mdtero received a login, access, or subscription page instead of the article. Open the full-text or PDF view in this browser session, or upload the PDF/XML/EPUB."
      }
    });

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.parse.ssot.request",
        input: "https://example.com/paper",
        pageContext: {
          tabId: 42,
          tabUrl: "https://example.com/paper",
          tabTitle: "Paper"
        }
      },
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(createParseTask).not.toHaveBeenCalled();
      expect(sendResponse).toHaveBeenCalledWith({
        ok: false,
        error: "The tab is open, but Mdtero received a login, access, or subscription page instead of the article. Open the full-text or PDF view in this browser session, or upload the PDF/XML/EPUB.",
        nextCommand: "mdtero parse https://example.com/paper --trace --wait --timeout 300 --json"
      });
    });
  });

  it("returns actionable full-text guidance when SSOT capture sees only a shell page", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);
    fetchRoutePlan.mockResolvedValue({
      input_kind: "url",
      input_value: "https://example.com/paper",
      top_connector: "browser_capture",
      route_kind: "browser_capture_required",
      acquisition_mode: "browser_extension",
      requires_browser_capture: true,
      allows_current_tab: true,
      action_sequence: ["capture_current_tab_html"],
      acceptance_rules: {},
      fail_closed: true,
      user_message: "Capture the current page.",
      matched_connectors: ["browser_capture"],
      acquisition_candidates: []
    });
    chromeStub.tabs.sendMessage.mockResolvedValue({
      ok: true,
      capture: {
        ok: false,
        failureCode: "article_body_missing",
        failureMessage: "The tab is open, but Mdtero could not find a parsable article body in the captured page. Open the full-text/PDF view or upload the PDF/XML/EPUB."
      }
    });

    await import("../src/background");

    const listener = chromeStub.__messageListeners[0];
    const sendResponse = vi.fn();

    listener?.(
      {
        type: "mdtero.parse.ssot.request",
        input: "https://example.com/paper",
        pageContext: {
          tabId: 42,
          tabUrl: "https://example.com/paper",
          tabTitle: "Paper"
        }
      },
      {},
      sendResponse
    );

    await vi.waitFor(() => {
      expect(createParseTask).not.toHaveBeenCalled();
      expect(sendResponse).toHaveBeenCalledWith({
        ok: false,
        error: "The tab is open, but Mdtero could not find a parsable article body in the captured page. Open the full-text/PDF view or upload the PDF/XML/EPUB.",
        nextCommand: "mdtero parse https://example.com/paper --trace --wait --timeout 300 --json"
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
