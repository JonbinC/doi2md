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

  it("fetches Elsevier XML with the user's extension API key", async () => {
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValue(
      new Response("<full-text-retrieval-response><originalText /></full-text-retrieval-response>", {
        status: 200,
        headers: { "Content-Type": "text/xml" },
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await executeAction(
      "fetch_elsevier_xml",
      {
        input: "10.1016/j.energy.2026.140192",
        elsevierApiKey: "user-elsevier-key",
      },
      {}
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.elsevier.com/content/article/doi/10.1016/j.energy.2026.140192?httpAccept=text%2Fxml&view=FULL",
      {
        headers: {
          Accept: "text/xml",
          "X-ELS-APIKey": "user-elsevier-key",
        },
      }
    );
    expect(result.success).toBe(true);
    expect(result.filename).toBe("paper.xml");
    expect(result.artifactKind).toBe("xml");
    expect(result.sourceDoi).toBe("10.1016/j.energy.2026.140192");
    await expect(result.rawArtifact?.text()).resolves.toContain("full-text-retrieval-response");
  });

  it("surfaces missing Elsevier extension key so SSOT can fall back to backend parse", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const result = await executeAction(
      "fetch_elsevier_xml",
      {
        input: "10.1016/j.energy.2026.140192",
      },
      {}
    );

    expect(result).toEqual({
      success: false,
      error: "Elsevier API key is not configured in the extension.",
      nextCommand: "mdtero parse 10.1016/j.energy.2026.140192 --trace --wait --timeout 300 --json",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("downloads arXiv PDF as a raw upload artifact", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(Uint8Array.from([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x37]), {
        status: 200,
        headers: { "Content-Type": "application/pdf" },
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await executeAction("native_arxiv_parse", { input: "10.48550/arXiv.1706.03762" }, {});

    expect(fetchMock).toHaveBeenCalledWith("https://arxiv.org/pdf/1706.03762.pdf", {
      credentials: "include",
      headers: { Accept: "application/pdf" },
    });
    expect(result.success).toBe(true);
    expect(result.filename).toBe("arxiv.pdf");
    expect(result.artifactKind).toBe("pdf");
    await expect(result.rawArtifact?.arrayBuffer()).resolves.toHaveProperty("byteLength", 8);
  });

  it("downloads open PDF candidates before asking for manual upload", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(Uint8Array.from([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31]), {
        status: 200,
        headers: { "Content-Type": "application/pdf" },
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await executeAction(
      "fallback_pdf_parse",
      { input: "10.1000/demo" },
      {
        acquisition_candidates: [
          {
            connector: "semantic_scholar_open_access_pdf",
            format: "pdf",
            pdf_url: "https://archive.example/paper.pdf",
          },
        ],
      }
    );

    expect(fetchMock).toHaveBeenCalledWith("https://archive.example/paper.pdf", {
      credentials: "include",
      headers: { Accept: "application/pdf" },
    });
    expect(result.success).toBe(true);
    expect(result.filename).toBe("paper.pdf");
    expect(result.artifactKind).toBe("pdf");
  });

  it("downloads OA repository PDFs instead of forcing manual upload", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(Uint8Array.from([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31]), {
        status: 200,
        headers: { "Content-Type": "application/pdf" },
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await executeAction(
      "fetch_oa_repository",
      { input: "10.1000/demo" },
      { best_oa_url: "https://repository.example/fulltext.pdf" }
    );

    expect(fetchMock).toHaveBeenCalledWith("https://repository.example/fulltext.pdf", {
      credentials: "include",
      headers: { Accept: "application/pdf" },
    });
    expect(result.success).toBe(true);
    expect(result.filename).toBe("paper.pdf");
    expect(result.artifactKind).toBe("pdf");
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

  it("surfaces browser-session PDF handoff candidates for fallback PDF routes", async () => {
    const result = await executeAction(
      "fallback_pdf_parse",
      {
        input: "10.1109/demo",
      },
      {
        user_message: "Server-side PDF acquisition failed.",
        client_handoff_candidates: [
          {
            transport: "browser_extension",
            capture_mode: "download_artifact",
            artifact_kind: "pdf",
            connector: "publisher_pdf_guess",
            source: "publisher_pdf_guess:ieee_stamp_gateway",
            artifact_url: "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=9919149",
            requires_user_rights: true,
            reason: "IEEE PDF gateways often require browser state; use the extension to download the PDF and upload the artifact.",
          },
        ],
        publisher_capabilities: {
          access_mode: "institution_browser",
        },
      }
    );

    expect(result.success).toBe(false);
    expect(result.requiresBrowserCapture).toBe(true);
    expect(result.requiresUpload).toBe(false);
    expect(result.error).toContain("IEEE PDF gateways often require browser state");
    expect(result.error).toContain("publisher_pdf_guess:ieee_stamp_gateway");
    expect(result.error).toContain("institution_browser");
    expect(result.error).toContain("https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=9919149");
    expect(result.nextCommand).toBe("mdtero parse 10.1109/demo --trace --wait --timeout 300 --json");
  });

  it("downloads PDF handoff candidates through the active browser action", async () => {
    const chromeStub = {
      tabs: {
        sendMessage: vi.fn().mockResolvedValue({
          ok: true,
          download: {
            ok: true,
            payloadBase64: "JVBERi0xLjc=",
            payloadName: "paper.pdf",
          },
        }),
      },
    };
    vi.stubGlobal("chrome", chromeStub);

    const result = await executeAction(
      "fallback_pdf_parse",
      {
        input: "10.1109/demo",
        tabId: 42,
      },
      {
        client_handoff_candidates: [
          {
            transport: "browser_extension",
            capture_mode: "download_artifact",
            artifact_kind: "pdf",
            artifact_url: "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=9919149",
            requires_user_rights: true,
          },
        ],
      }
    );

    expect(result.success).toBe(true);
    expect(result.filename).toBe("paper.pdf");
    expect(result.rawArtifact?.type).toBe("application/pdf");
    expect(chromeStub.tabs.sendMessage).toHaveBeenCalledWith(42, {
      type: "mdtero.download_pdf.request",
      artifactUrl: "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=9919149",
    });
  });

  it("fetches planned HTML candidates before falling back to current-tab capture", async () => {
    const chromeStub = {
      tabs: {
        sendMessage: vi.fn().mockResolvedValue({
          ok: true,
          html: {
            ok: true,
            payloadText: "<html><article>Fetched full text</article></html>",
            payloadName: "paper.html",
            sourceUrl: "https://example.org/full",
          },
        }),
      },
    };
    vi.stubGlobal("chrome", chromeStub);

    const result = await executeAction(
      "fetch_browser_source",
      {
        input: "10.1000/demo",
        tabId: 42,
      },
      {
        top_connector: "publisher_html",
        acquisition_candidates: [
          {
            connector: "publisher_html",
            html_url: "https://example.org/full",
          },
        ],
      }
    );

    expect(result.success).toBe(true);
    expect(result.filename).toBe("paper.html");
    expect(chromeStub.tabs.sendMessage).toHaveBeenCalledWith(42, {
      type: "mdtero.fetch_html.request",
      candidateUrls: ["https://example.org/full"],
    });
    await expect(result.rawArtifact?.text()).resolves.toContain("Fetched full text");
  });

  it("injects the content script before current-tab HTML capture when the tab is not connected", async () => {
    const chromeStub = {
      runtime: {
        getManifest: vi.fn(() => ({
          content_scripts: [{ js: ["dist/content.js"] }],
        })),
      },
      tabs: {
        sendMessage: vi.fn()
          .mockRejectedValueOnce(new Error("Could not establish connection. Receiving end does not exist."))
          .mockResolvedValueOnce({
            ok: true,
            capture: {
              ok: true,
              html: "<html><article>Injected full text</article></html>",
              payloadName: "paper.html",
            },
          }),
      },
      scripting: {
        executeScript: vi.fn().mockResolvedValue(undefined),
      },
    };
    vi.stubGlobal("chrome", chromeStub);

    const result = await executeAction(
      "capture_current_tab_html",
      {
        input: "10.1000/demo",
        tabId: 42,
      },
      {}
    );

    expect(result.success).toBe(true);
    expect(result.filename).toBe("paper.html");
    expect(chromeStub.scripting.executeScript).toHaveBeenCalledWith({
      target: { tabId: 42 },
      files: ["dist/content.js"],
    });
    expect(chromeStub.tabs.sendMessage).toHaveBeenCalledTimes(2);
    expect(chromeStub.tabs.sendMessage).toHaveBeenLastCalledWith(42, {
      type: "mdtero.capture_current_tab.request",
    });
    await expect(result.rawArtifact?.text()).resolves.toContain("Injected full text");
  });

  it("quotes shell-sensitive URL handoff commands when browser capture fails", async () => {
    const chromeStub = {
      tabs: {
        sendMessage: vi.fn().mockResolvedValue({
          ok: true,
          capture: {
            ok: false,
            failureCode: "challenge_page_detected",
            failureMessage: "The tab is open, but Mdtero received a challenge or blocked page instead of article content."
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
    expect(result.error).toBe("The tab is open, but Mdtero received a challenge or blocked page instead of article content.");
    expect(result.nextCommand).toBe("mdtero parse 'https://www.mdpi.com/2071-1050/17/5/2018?x=a b' --trace --wait --timeout 300 --json");
  });
});
