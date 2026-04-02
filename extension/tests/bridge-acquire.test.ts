import { describe, expect, it, vi } from "vitest";

import {
  performBridgeAcquire
} from "../src/lib/bridge-acquire";

function createChromeTabsMock() {
  const onUpdatedListeners: Array<(tabId: number, changeInfo: { status?: string }) => void> = [];
  return {
    create: vi.fn(async ({ url }: { url: string }) => ({ id: 11, url })),
    get: vi.fn(async (tabId: number) => ({ id: tabId, status: "loading" })),
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

  it("forwards article-body diagnostics from the content script when helper capture fails", async () => {
    const tabs = createChromeTabsMock();
    tabs.sendMessage.mockResolvedValue({
      ok: true,
      capture: {
        ok: false,
        failureCode: "article_body_missing",
        failureMessage: "Page loaded but no article body markers were detected.",
        failureContext: {
          sourceUrl: "https://www.nature.com/articles/d41586-023-02980-0",
          title: "AI and science: what 1,600 researchers think",
          hasMetadataSignals: true,
          hasBodySignals: false,
          isPdfEmbedShell: false
        }
      }
    });

    const promise = performBridgeAcquire({
      request: {
        task_id: "task-diagnostics",
        action: "open_and_capture_html",
        connector: "nature_html",
        input: "https://www.nature.com/articles/d41586-023-02980-0"
      },
      chromeApi: {
        tabs
      } as never
    });

    await flushBridgeSetup();
    tabs.onUpdated.emit(11, "complete");
    const response = await promise;

    expect(response.status).toBe("failed");
    expect(response.failure_code).toBe("article_body_missing");
    expect(response.failure_context).toEqual(
      expect.objectContaining({
        sourceUrl: "https://www.nature.com/articles/d41586-023-02980-0",
        hasMetadataSignals: true,
        hasBodySignals: false
      })
    );
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

  it("opens a fresh acquisition tab when the next request targets a different page", async () => {
    const tabs = createChromeTabsMock();
    const currentTab = {
      id: 17,
      status: "loading",
      url: "https://link.springer.com/article/10.1007/old"
    };
    tabs.get.mockImplementation(async () => ({ ...currentTab }));
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
    await new Promise((resolve) => setTimeout(resolve, 25));
    tabs.onUpdated.emit(11, "complete");
    const response = await promise;

    expect(tabs.update).not.toHaveBeenCalled();
    expect(tabs.create).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "https://doi.org/10.1007/s12011-024-04385-0",
        active: false
      })
    );
    expect(bridgeSession.tabId).toBe(11);
    expect(response.status).toBe("succeeded");
  });

  it("includes the final tab URL when the content script never becomes available", async () => {
    const tabs = createChromeTabsMock();
    tabs.get.mockResolvedValue({
      id: 11,
      status: "complete",
      url: "https://dl.acm.org/doi/10.1145/3131726.3131736"
    });
    tabs.sendMessage.mockRejectedValue(
      new Error("Could not establish connection. Receiving end does not exist.")
    );

    const promise = performBridgeAcquire({
      request: {
        task_id: "task-unavailable",
        action: "open_and_capture_html",
        connector: "best_oa_location_html",
        input: "10.1145/3131726.3131736"
      },
      chromeApi: {
        tabs
      } as never
    });

    await flushBridgeSetup();
    tabs.onUpdated.emit(11, "complete");
    const response = await promise;

    expect(response.status).toBe("failed");
    expect(response.failure_code).toBe("content_script_unavailable");
    expect(response.failure_message).toContain("Final tab URL: https://dl.acm.org/doi/10.1145/3131726.3131736");
  });

  it("fails cleanly when the content script message hangs without resolving", async () => {
    vi.useFakeTimers();
    const tabs = createChromeTabsMock();
    tabs.get.mockResolvedValue({
      id: 11,
      status: "complete",
      url: "https://www.nature.com/articles/d41586-023-02980-0"
    });
    tabs.sendMessage.mockImplementation(() => new Promise(() => {}));

    try {
      const promise = performBridgeAcquire({
        request: {
          task_id: "task-hung-message",
          action: "open_and_capture_html",
          connector: "nature_html",
          input: "https://www.nature.com/articles/d41586-023-02980-0"
        },
        chromeApi: {
          tabs
        } as never
      });

      await vi.advanceTimersByTimeAsync(12000);
      const response = await promise;

      expect(response.status).toBe("failed");
      expect(response.failure_code).toBe("content_script_unavailable");
      expect(response.failure_message).toContain("Final tab URL: https://www.nature.com/articles/d41586-023-02980-0");
    } finally {
      vi.useRealTimers();
    }
  });

  it("accepts an already-complete newly opened tab without waiting for another update event", async () => {
    const tabs = createChromeTabsMock();
    tabs.get.mockResolvedValue({
      id: 11,
      status: "complete",
      url: "https://link.springer.com/article/10.1007/s10735-026-10774-7"
    });
    tabs.sendMessage.mockResolvedValue({
      ok: true,
      capture: {
        ok: true,
        html: "<html><body><article>Fast complete</article></body></html>",
        payloadName: "paper.html",
        sourceUrl: "https://link.springer.com/article/10.1007/s10735-026-10774-7",
        pageTitle: "Fast complete"
      }
    });

    await expect(
      performBridgeAcquire({
        request: {
          task_id: "task-fast-complete",
          action: "open_and_capture_html",
          connector: "springer_subscription_connector",
          input: "10.1007/s10735-026-10774-7",
          timeouts: {
            page_load_ms: 5
          }
        } as never,
        chromeApi: {
          tabs
        } as never
      } as never)
    ).resolves.toMatchObject({
      status: "succeeded",
      artifact_kind: "html"
    });

    expect(tabs.create).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "https://doi.org/10.1007/s10735-026-10774-7",
        active: false
      })
    );
    expect(tabs.get).toHaveBeenCalledWith(11);
  });

  it("opens a fresh acquisition tab even when the previous bridge tab already points at the same target URL", async () => {
    const tabs = createChromeTabsMock();
    tabs.get.mockResolvedValue({
      id: 17,
      status: "complete",
      url: "https://www.nature.com/articles/d41586-023-02980-0"
    });
    tabs.sendMessage.mockResolvedValue({
      ok: true,
      capture: {
        ok: true,
        html: "<html><body><article>Fresh same-url page</article></body></html>",
        payloadName: "paper.html",
        sourceUrl: "https://www.nature.com/articles/d41586-023-02980-0",
        pageTitle: "AI and science"
      }
    });

    const bridgeSession = { tabId: 17 };
    const promise = performBridgeAcquire({
      request: {
        task_id: "task-same-url",
        action: "open_and_capture_html",
        connector: "nature_html",
        input: "https://www.nature.com/articles/d41586-023-02980-0"
      },
      chromeApi: {
        tabs
      } as never,
      bridgeSession
    } as never);

    await flushBridgeSetup();
    tabs.onUpdated.emit(11, "complete");
    const response = await promise;

    expect(tabs.update).not.toHaveBeenCalled();
    expect(tabs.create).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "https://www.nature.com/articles/d41586-023-02980-0",
        active: false
      })
    );
    expect(bridgeSession.tabId).toBe(11);
    expect(response.status).toBe("succeeded");
    expect(response.payload_text).toContain("Fresh same-url page");
  });

  it("ignores stale completion events from the previous bridge tab after opening a fresh acquisition tab", async () => {
    const tabs = createChromeTabsMock();
    const nextTab = {
      id: 11,
      status: "loading",
      url: "https://pubs.rsc.org/en/content/articlehtml/2020/ta/d0ta03080e"
    };
    tabs.get.mockImplementation(async (tabId: number) => {
      if (tabId === 17) {
        return {
          id: 17,
          status: "complete",
          url: "https://dl.acm.org/doi/10.1145/3131726.3131736"
        };
      }
      return { ...nextTab };
    });
    tabs.sendMessage.mockResolvedValue({
      ok: true,
      capture: {
        ok: true,
        html: "<html><body><article>Fresh page</article></body></html>",
        payloadName: "paper.html",
        sourceUrl: "https://pubs.rsc.org/en/content/articlehtml/2020/ta/d0ta03080e",
        pageTitle: "RSC Article"
      }
    });

    const promise = performBridgeAcquire({
      request: {
        task_id: "task-refresh",
        action: "open_and_capture_html",
        connector: "rsc_html",
        input: "https://pubs.rsc.org/en/content/articlehtml/2020/ta/d0ta03080e"
      },
      chromeApi: {
        tabs
      } as never,
      bridgeSession: {
        tabId: 17
      }
    } as never);

    await flushBridgeSetup();
    tabs.onUpdated.emit(17, "complete");
    await new Promise((resolve) => setTimeout(resolve, 25));
    expect(tabs.sendMessage).not.toHaveBeenCalled();

    nextTab.status = "complete";
    tabs.onUpdated.emit(11, "complete");
    await new Promise((resolve) => setTimeout(resolve, 25));
    expect(tabs.sendMessage).toHaveBeenCalledTimes(1);
    const response = await promise;

    expect(tabs.update).not.toHaveBeenCalled();
    expect(tabs.create).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "https://pubs.rsc.org/en/content/articlehtml/2020/ta/d0ta03080e",
        active: false
      })
    );
    expect(tabs.sendMessage).toHaveBeenCalledTimes(1);
    expect(response.status).toBe("succeeded");
    expect(response.payload_text).toContain("Fresh page");
  });

  it("includes the final tab URL when tab load completion times out", async () => {
    const tabs = createChromeTabsMock();
    tabs.get.mockResolvedValue({
      id: 11,
      status: "loading",
      url: "https://www.nature.com/articles/d41586-023-02980-0"
    });

    const responsePromise = performBridgeAcquire({
      request: {
        task_id: "task-load-timeout",
        action: "open_and_capture_html",
        connector: "nature_html",
        input: "https://www.nature.com/articles/d41586-023-02980-0",
        timeouts: {
          page_load_ms: 5
        }
      },
      chromeApi: {
        tabs
      } as never
    });

    await expect(responsePromise).resolves.toMatchObject({
      status: "failed",
      failure_code: "tab_load_timeout"
    });
    await expect(responsePromise).resolves.toMatchObject({
      failure_message: expect.stringContaining(
        "Final tab URL: https://www.nature.com/articles/d41586-023-02980-0"
      )
    });
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
