import { describe, expect, it, vi } from "vitest";

import {
  performBridgeAcquire
} from "../src/lib/bridge-acquire";

function createChromeTabsMock() {
  const onUpdatedListeners: Array<(tabId: number, changeInfo: { status?: string }) => void> = [];
  return {
    create: vi.fn(async ({ url }: { url: string }) => ({ id: 11, url })),
    update: vi.fn(async (tabId: number, { url }: { url: string }) => ({ id: tabId, url })),
    sendMessage: vi.fn(),
    onUpdated: {
      addListener(listener: (tabId: number, changeInfo: { status?: string }) => void) {
        onUpdatedListeners.push(listener);
      },
      removeListener(listener: (tabId: number, changeInfo: { status?: string }) => void) {
        const index = onUpdatedListeners.indexOf(listener);
        if (index >= 0) onUpdatedListeners.splice(index, 1);
      },
      emit(tabId: number, status = "complete") {
        onUpdatedListeners.forEach((listener) => listener(tabId, { status }));
      }
    }
  };
}

describe("performBridgeAcquire", () => {
  async function flushBridgeSetup() {
    await Promise.resolve();
    await Promise.resolve();
  }

  it("opens a DOI URL and returns an inline html artifact response", async () => {
    const tabs = createChromeTabsMock();
    tabs.sendMessage.mockResolvedValue({
      ok: true,
      capture: {
        ok: true,
        html: "<html><body><main><article>Demo</article></main></body></html>",
        payloadName: "paper.html",
        sourceUrl: "https://link.springer.com/article/10.1000/demo",
        pageTitle: "Demo Article"
      }
    });

    const promise = performBridgeAcquire({
      request: {
        task_id: "task-1",
        action: "open_and_capture_html",
        connector: "springer_subscription_connector",
        input: "10.1000/demo"
      },
      chromeApi: {
        tabs
      } as never
    });

    await flushBridgeSetup();
    tabs.onUpdated.emit(11, "complete");
    const response = await promise;

    expect(tabs.create).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "https://doi.org/10.1000/demo",
        active: false
      })
    );
    expect(response.status).toBe("succeeded");
    expect(response.artifact_kind).toBe("html");
    expect(response.payload_name).toBe("paper.html");
    expect(response.payload_text).toContain("<article>Demo</article>");
  });

  it("returns challenge failure when the capture hook reports a challenge shell", async () => {
    const tabs = createChromeTabsMock();
    tabs.sendMessage.mockResolvedValue({
      ok: true,
      capture: {
        ok: false,
        failureCode: "challenge_page_detected",
        failureMessage: "Page loaded but did not expose article content."
      }
    });

    const promise = performBridgeAcquire({
      request: {
        task_id: "task-2",
        action: "open_and_capture_html",
        connector: "wiley_tdm",
        input: "https://onlinelibrary.wiley.com/doi/10.1000/demo"
      },
      chromeApi: {
        tabs
      } as never
    });

    await flushBridgeSetup();
    tabs.onUpdated.emit(11, "complete");
    const response = await promise;

    expect(response.status).toBe("failed");
    expect(response.failure_code).toBe("challenge_page_detected");
  });

  it("downloads epub artifacts and returns a base64 payload", async () => {
    const tabs = createChromeTabsMock();
    tabs.sendMessage.mockResolvedValue({
      ok: true,
      download: {
        ok: true,
        payloadBase64: "UEsDBGRlbW8=",
        payloadName: "paper.epub",
        sourceUrl: "https://www.tandfonline.com/doi/epub/10.1080/26395940.2021.1947159?needAccess=true"
      }
    });

    const promise = performBridgeAcquire({
      request: {
        task_id: "task-3",
        action: "open_and_download_epub",
        connector: "taylor_francis_oa_epub",
        input: "10.1080/26395940.2021.1947159",
        source_url: "https://www.tandfonline.com/doi/full/10.1080/26395940.2021.1947159",
        artifact_url: "https://www.tandfonline.com/doi/epub/10.1080/26395940.2021.1947159?needAccess=true"
      } as never,
      chromeApi: {
        tabs
      } as never
    });

    await flushBridgeSetup();
    tabs.onUpdated.emit(11, "complete");
    const response = await promise;

    expect(tabs.create).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "https://www.tandfonline.com/doi/full/10.1080/26395940.2021.1947159",
        active: false
      })
    );
    expect(tabs.sendMessage).toHaveBeenCalledWith(
      11,
      expect.objectContaining({
        type: "mdtero.download_epub.request",
        artifactUrl: "https://www.tandfonline.com/doi/epub/10.1080/26395940.2021.1947159?needAccess=true"
      })
    );
    expect(response.status).toBe("succeeded");
    expect(response.artifact_kind).toBe("epub");
    expect(response.payload_name).toBe("paper.epub");
    expect(response.payload_base64).toBe("UEsDBGRlbW8=");
  });

  it("fetches structured XML through the page context when requested", async () => {
    const tabs = createChromeTabsMock();
    tabs.sendMessage.mockResolvedValue({
      ok: true,
      xml: {
        ok: true,
        payloadText: "<article><body>Licensed XML</body></article>",
        payloadName: "paper.xml",
        sourceUrl: "https://api.example.org/paper.xml"
      }
    });

    const promise = performBridgeAcquire({
      request: {
        task_id: "task-xml",
        action: "open_and_fetch_xml",
        connector: "springer_subscription_connector",
        input: "10.1000/demo",
        source_url: "https://link.springer.com/article/10.1000/demo",
        artifact_url: "https://api.example.org/paper.xml"
      } as never,
      chromeApi: {
        tabs
      } as never
    });

    await flushBridgeSetup();
    tabs.onUpdated.emit(11, "complete");
    const response = await promise;

    expect(tabs.sendMessage).toHaveBeenCalledWith(
      11,
      expect.objectContaining({
        type: "mdtero.fetch_xml.request",
        artifactUrl: "https://api.example.org/paper.xml",
        sourceUrl: "https://link.springer.com/article/10.1000/demo"
      })
    );
    expect(response.status).toBe("succeeded");
    expect(response.artifact_kind).toBe("structured_xml");
    expect(response.payload_text).toContain("Licensed XML");
  });

  it("retries capture hook delivery until the content script is ready", async () => {
    const tabs = createChromeTabsMock();
    tabs.sendMessage
      .mockRejectedValueOnce(new Error("Could not establish connection. Receiving end does not exist."))
      .mockResolvedValueOnce({
        ok: true,
        capture: {
          ok: true,
          html: "<html><body><article>Retry success</article></body></html>",
          payloadName: "paper.html",
          sourceUrl: "https://www.tandfonline.com/doi/full/10.1080/03085147.2021.1900653",
          pageTitle: "Economy and society in COVID times"
        }
      });

    const promise = performBridgeAcquire({
      request: {
        task_id: "task-retry",
        action: "open_and_capture_html",
        connector: "taylor_francis_tdm",
        input: "https://www.tandfonline.com/doi/full/10.1080/03085147.2021.1900653"
      },
      chromeApi: {
        tabs
      } as never
    });

    await flushBridgeSetup();
    tabs.onUpdated.emit(11, "complete");
    const response = await promise;

    expect(tabs.sendMessage).toHaveBeenCalledTimes(2);
    expect(response.status).toBe("succeeded");
    expect(response.payload_text).toContain("Retry success");
  });

  it("reuses the existing bridge tab for the next acquisition when available", async () => {
    const tabs = createChromeTabsMock();
    tabs.sendMessage.mockResolvedValue({
      ok: true,
      capture: {
        ok: true,
        html: "<html><body><article>Bridge tab reuse</article></body></html>",
        payloadName: "paper.html",
        sourceUrl: "https://link.springer.com/article/10.1007/s12011-024-04385-0",
        pageTitle:
          "Synergistic Effects of Hydroxychloride and Organic Zinc on Performance, Carcass Characteristics, Liver and Tibia Mineral Profiles of Broiler Chickens"
      }
    });

    const bridgeSession = { tabId: 17 };
    const promise = performBridgeAcquire({
      request: {
        task_id: "task-reuse",
        action: "open_and_capture_html",
        connector: "springer_subscription_connector",
        input: "10.1007/s12011-024-04385-0"
      },
      chromeApi: {
        tabs
      } as never,
      bridgeSession
    } as never);

    await flushBridgeSetup();
    tabs.onUpdated.emit(17, "complete");
    const response = await promise;

    expect(tabs.create).not.toHaveBeenCalled();
    expect(tabs.update).toHaveBeenCalledWith(
      17,
      expect.objectContaining({
        url: "https://doi.org/10.1007/s12011-024-04385-0",
        active: false
      })
    );
    expect(response.status).toBe("succeeded");
  });

  it("prefers the last real page tab for current-tab capture instead of the recycled bridge tab", async () => {
    const tabs = createChromeTabsMock();
    tabs.sendMessage.mockResolvedValue({
      ok: true,
      capture: {
        ok: true,
        html: "<html><body><article>Live page</article></body></html>",
        payloadName: "paper.html",
        sourceUrl: "https://onlinelibrary.wiley.com/doi/full/10.1002/demo",
        pageTitle: "Live page"
      }
    });

    const response = await performBridgeAcquire({
      request: {
        task_id: "task-current-tab",
        action: "capture_current_tab",
        connector: "wiley_tdm"
      } as never,
      chromeApi: {
        tabs
      } as never,
      bridgeSession: {
        tabId: 17,
        pageTabId: 23
      }
    } as never);

    expect(tabs.sendMessage).toHaveBeenCalledWith(
      23,
      expect.objectContaining({
        type: "mdtero.capture_current_tab.request"
      })
    );
    expect(response.status).toBe("succeeded");
    expect(response.payload_text).toContain("Live page");
  });
});
