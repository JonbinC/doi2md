import { beforeEach, describe, expect, it, vi } from "vitest";

import { executeAction } from "../src/lib/action-executor";

describe("executeAction", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("rejects retired publisher PDF/API actions instead of direct keyed fetches", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const result = await executeAction(
      "fetch_wiley_tdm_pdf",
      {
        input: "10.1002/demo",
      },
      {}
    );

    expect(result).toEqual({
      success: false,
      error: "Unknown action: fetch_wiley_tdm_pdf",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not keep stale publisher API action compatibility in the extension runtime", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const chromeStub = {
      tabs: {
        sendMessage: vi.fn().mockResolvedValue({
          ok: true,
          capture: {
            ok: true,
            html: "<html><article>Captured publisher page</article></html>",
            payloadName: "paper.html",
          },
        }),
      },
    };
    vi.stubGlobal("chrome", chromeStub);

    const result = await executeAction(
      "fetch_elsevier_xml",
      {
        input: "10.1016/j.energy.2026.140192",
        tabId: 12,
      },
      {}
    );

    expect(result).toEqual({ success: false, error: "Unknown action: fetch_elsevier_xml" });
    expect(chromeStub.tabs.sendMessage).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("downloads EPUB assets through the active browser action", async () => {
    const chromeStub = {
      tabs: {
        sendMessage: vi.fn().mockResolvedValue({
          ok: true,
          download: {
            ok: true,
            payloadBase64: "UEsDBGJlbW8tZXB1Yg==",
            payloadName: "paper.epub",
          },
        }),
      },
    };
    vi.stubGlobal("chrome", chromeStub);

    const result = await executeAction(
      "fetch_epub_asset",
      {
        input: "10.1080/26395940.2021.1947159",
        tabId: 42,
      },
      {
        top_connector: "taylor_francis_oa_epub",
        acquisition_candidates: [
          {
            connector: "taylor_francis_oa_epub",
            epub_url: "https://www.tandfonline.com/doi/epub/10.1080/26395940.2021.1947159?needAccess=true",
          },
        ],
      }
    );

    expect(result.success).toBe(true);
    expect(result.filename).toBe("paper.epub");
    expect(chromeStub.tabs.sendMessage).toHaveBeenCalledWith(42, {
      type: "mdtero.download_epub.request",
      artifactUrl: "https://www.tandfonline.com/doi/epub/10.1080/26395940.2021.1947159?needAccess=true",
    });
  });

  it("quotes shell-sensitive URL handoff commands when browser capture fails", async () => {
    const chromeStub = {
      tabs: {
        sendMessage: vi.fn().mockResolvedValue({
          ok: true,
          capture: {
            ok: false,
            failureCode: "challenge_page_detected",
            failureMessage: "Page loaded but did not expose article content."
          }
        })
      }
    };
    vi.stubGlobal("chrome", chromeStub);

    const result = await executeAction(
      "capture_current_tab_html",
      {
        input: "https://www.mdpi.com/2071-1050/17/5/2018?x=a b",
        tabId: 42,
      },
      {}
    );

    expect(result.success).toBe(false);
    expect(result.error).toBe("Page loaded but did not expose article content.");
    expect(result.nextCommand).toBe("mdtero parse 'https://www.mdpi.com/2071-1050/17/5/2018?x=a b' --trace --wait --timeout 300 --json");
  });
});
