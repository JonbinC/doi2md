import { describe, expect, it } from "vitest";
import { vi } from "vitest";

import {
  buildPageCaptureResult,
  extractXmlCandidateUrls,
  fetchHtmlArtifact,
  fetchXmlArtifact,
  downloadEpubArtifact,
  downloadCurrentPagePdfArtifact,
  downloadPdfArtifact,
  inferCurrentPagePdfCandidateUrls,
  isLikelyChallengeOrLoginShell
} from "../src/lib/page-capture";
import {
  HTML_CAPTURE_FIXTURES,
  XML_CAPTURE_FIXTURES
} from "./page-capture-fixtures";

describe("isLikelyChallengeOrLoginShell", () => {
  it("flags common challenge shells", () => {
    expect(isLikelyChallengeOrLoginShell("<html><title>Just a moment...</title></html>")).toBe(true);
    expect(isLikelyChallengeOrLoginShell("<html><body>Access Denied</body></html>")).toBe(true);
    expect(isLikelyChallengeOrLoginShell("<html><body><form><input type='password'></form>Sign in</body></html>")).toBe(true);
  });

  it("does not flag normal article pages", () => {
    expect(
      isLikelyChallengeOrLoginShell("<html><head><meta name='citation_title' content='Demo'></head><body><main><article>Paper</article></main></body></html>")
    ).toBe(false);
  });
});

describe("buildPageCaptureResult", () => {
  it.each(HTML_CAPTURE_FIXTURES)("classifies $name", (fixture) => {
    const result = buildPageCaptureResult({
      url: fixture.url,
      title: fixture.title,
      html: fixture.html
    });

    expect(result.ok).toBe(fixture.expected.ok);

    if (fixture.expected.ok) {
      if (!result.ok) {
        throw new Error("expected ok result");
      }
      expect(result.payloadName).toBe("paper.html");
      expect(result.sourceUrl).toBe(fixture.url);
    } else {
      expect(result).toMatchObject({
        ok: false,
        failureCode: fixture.expected.failureCode
      });
      if (!result.ok && result.failureCode === "article_body_missing") {
        expect(result.failureContext).toEqual(
          expect.objectContaining({
            sourceUrl: fixture.url,
            title: fixture.title,
            hasMetadataSignals: expect.any(Boolean),
            hasBodySignals: expect.any(Boolean),
            isPdfEmbedShell: expect.any(Boolean)
          })
        );
      }
    }
  });

  it("strips obvious injected overlays, scripts, styles, and hidden extension nodes from captured html", () => {
    const result = buildPageCaptureResult({
      url: "https://www.nature.com/articles/d41586-023-02980-0",
      title: "AI and science: what 1,600 researchers think",
      html: `
        <html>
          <head>
            <meta name="citation_doi" content="10.1038/d41586-023-02980-0" />
            <style>.glarity--summary { display: block; }</style>
            <script>window.__tracker = true;</script>
          </head>
          <body>
            <shadow-host></shadow-host>
            <main>
              <article class="c-article-body">
                <h1>AI and science: what 1,600 researchers think</h1>
                <section class="c-article-section">Body text</section>
              </article>
            </main>
            <div id="shadowLL"><link rel="stylesheet" href="chrome-extension://demo/sciteFont.css" /></div>
            <div class="glarity--summary notranslate">Injected overlay</div>
            <div class="tp-extension">Injected widget</div>
            <div id="tcb-extension-uk-wrapper">Injected wrapper</div>
            <textarea aria-hidden="true" style="visibility:hidden !important;">shadow node</textarea>
            <iframe name="__tcfapiLocator" style="display:none;"></iframe>
          </body>
        </html>
      `
    });

    expect(result.ok).toBe(true);
    if (!result.ok) {
      throw new Error("expected ok result");
    }
    expect(result.html).toContain("<article");
    expect(result.html).not.toContain("window.__tracker");
    expect(result.html).not.toContain(".glarity--summary");
    expect(result.html).not.toContain("Injected overlay");
    expect(result.html).not.toContain("tp-extension");
    expect(result.html).not.toContain("tcb-extension-uk-wrapper");
    expect(result.html).not.toContain("__tcfapiLocator");
    expect(result.html).not.toContain("shadow-host");
    expect(result.html).not.toContain("shadowLL");
    expect(result.html).not.toContain("chrome-extension://");
    expect(result.html).not.toContain("visibility:hidden !important");
  });
});

describe("downloadEpubArtifact", () => {
  it("downloads epub bytes through the page context with credentials", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (_input, init) => {
      expect(init?.credentials).toBe("include");
      return {
        ok: true,
        arrayBuffer: async () => Uint8Array.from([0x50, 0x4b, 0x03, 0x04, 0x64, 0x65, 0x6d, 0x6f]).buffer
      } as Response;
    }) as typeof fetch;

    try {
      const result = await downloadEpubArtifact("https://www.tandfonline.com/doi/epub/10.1080/26395940.2021.1947159?needAccess=true");
      expect(result).toEqual({
        ok: true,
        payloadBase64: "UEsDBGRlbW8=",
        payloadName: "paper.epub",
        sourceUrl: "https://www.tandfonline.com/doi/epub/10.1080/26395940.2021.1947159?needAccess=true"
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("surfaces a clean failure when the page-context fetch is blocked", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async () => ({ ok: false, status: 403 }) as Response) as typeof fetch;

    try {
      const result = await downloadEpubArtifact("https://www.tandfonline.com/doi/epub/10.1080/26395940.2021.1947159?needAccess=true");
      expect(result).toEqual({
        ok: false,
        failureCode: "artifact_download_missing",
        failureMessage: "Browser page context could not download the EPUB artifact (403)."
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

describe("downloadPdfArtifact", () => {
  it("downloads and validates PDF bytes through the page context with credentials", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (_input, init) => {
      expect(init?.credentials).toBe("include");
      expect(new Headers(init?.headers).get("Accept")).toContain("application/pdf");
      return {
        ok: true,
        arrayBuffer: async () => Uint8Array.from([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x37]).buffer
      } as Response;
    }) as typeof fetch;

    try {
      const result = await downloadPdfArtifact("https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=9919149");
      expect(result).toEqual({
        ok: true,
        payloadBase64: "JVBERi0xLjc=",
        payloadName: "paper.pdf",
        sourceUrl: "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=9919149"
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("rejects HTML shells returned from PDF gateways", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      arrayBuffer: async () => new TextEncoder().encode("<html>Access denied</html>").buffer
    }) as Response) as typeof fetch;

    try {
      const result = await downloadPdfArtifact("https://publisher.example/pdf");
      expect(result).toEqual({
        ok: false,
        failureCode: "artifact_download_missing",
        failureMessage: "Browser page context downloaded a response that was not a valid PDF artifact."
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("follows IEEE stamp gateway iframe shells to the real PDF endpoint", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (input) => {
      if (String(input).includes("/stamp/stamp.jsp")) {
        return {
          ok: true,
          url: String(input),
          arrayBuffer: async () => new TextEncoder().encode(`<html><body><iframe src="/stampPDF/getPDF.jsp?tp=&arnumber=9919149&ref="></iframe></body></html>`).buffer
        } as Response;
      }
      expect(String(input)).toBe("https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=9919149&ref=");
      return {
        ok: true,
        url: String(input),
        arrayBuffer: async () => Uint8Array.from([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x37]).buffer
      } as Response;
    }) as typeof fetch;

    try {
      const result = await downloadPdfArtifact("https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=9919149");
      expect(result).toEqual({
        ok: true,
        payloadBase64: "JVBERi0xLjc=",
        payloadName: "paper.pdf",
        sourceUrl: "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=9919149&ref="
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

describe("inferCurrentPagePdfCandidateUrls", () => {
  it("infers IEEE stampPDF URLs from document pages", () => {
    expect(
      inferCurrentPagePdfCandidateUrls({
        pageUrl: "https://ieeexplore.ieee.org/document/9919149",
        html: "<html></html>"
      })
    ).toContain("https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=9919149&ref=");
  });

  it("extracts IEEE citation PDF and iframe candidates from browser pages", () => {
    const candidates = inferCurrentPagePdfCandidateUrls({
      pageUrl: "https://ieeexplore.ieee.org/document/9919149",
      html: `<html><head><meta name="citation_pdf_url" content="https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&amp;arnumber=9919149"></head><body><iframe src="/stampPDF/getPDF.jsp?tp=&arnumber=9919149&ref="></iframe></body></html>`
    });
    expect(candidates).toContain("https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=9919149");
    expect(candidates).toContain("https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=9919149&ref=");
  });

  it("infers ScienceDirect pdfft URLs from PII pages", () => {
    expect(
      inferCurrentPagePdfCandidateUrls({
        pageUrl: "https://www.sciencedirect.com/science/article/pii/S0016236126004512",
        html: "<html></html>"
      })
    ).toContain("https://www.sciencedirect.com/science/article/pii/S0016236126004512/pdfft?isDTMRedir=true&download=true");
  });

  it("extracts CNKI PDF download links from authorized detail pages", () => {
    expect(
      inferCurrentPagePdfCandidateUrls({
        pageUrl: "https://kns.cnki.net/kcms2/article/abstract?v=demo",
        html: `<html><body><a id="pdfDown" href="/kcms2/article/download?filename=paper.pdf">PDF</a></body></html>`
      })
    ).toContain("https://kns.cnki.net/kcms2/article/download?filename=paper.pdf");
  });
});

describe("downloadCurrentPagePdfArtifact", () => {
  it("downloads an inferred browser-session PDF candidate", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (input, init) => {
      expect(String(input)).toBe("https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=9919149&ref=");
      expect(init?.credentials).toBe("include");
      return {
        ok: true,
        arrayBuffer: async () => Uint8Array.from([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31]).buffer
      } as Response;
    }) as typeof fetch;

    try {
      const result = await downloadCurrentPagePdfArtifact({
        pageUrl: "https://ieeexplore.ieee.org/document/9919149",
        html: "<html></html>"
      });
      expect(result).toEqual({
        ok: true,
        payloadBase64: "JVBERi0x",
        payloadName: "paper.pdf",
        sourceUrl: "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=9919149&ref="
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

describe("fetchHtmlArtifact", () => {
  it("downloads and validates full-text HTML through the page context", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (_input, init) => {
      expect(init?.credentials).toBe("include");
      return {
        ok: true,
        url: "https://publisher.example/full",
        text: async () => `
          <html>
            <head><meta name="citation_doi" content="10.1000/demo" /></head>
            <body><main><article class="article-body">Full text</article></main></body>
          </html>
        `
      } as Response;
    }) as typeof fetch;

    try {
      const result = await fetchHtmlArtifact(["https://publisher.example/full"]);
      expect(result).toMatchObject({
        ok: true,
        payloadName: "paper.html",
        sourceUrl: "https://publisher.example/full"
      });
      if (result.ok) {
        expect(result.payloadText).toContain("Full text");
      }
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("rejects abstract-only or challenge HTML payloads", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      url: "https://publisher.example/challenge",
      text: async () => "<html><title>Just a moment...</title><body>Checking if the site connection is secure</body></html>"
    }) as Response) as typeof fetch;

    try {
      const result = await fetchHtmlArtifact(["https://publisher.example/challenge"]);
      expect(result).toEqual({
        ok: false,
        failureCode: "artifact_download_missing",
        failureMessage: "The tab is open, but Mdtero received a challenge or blocked page instead of article content."
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

describe("fetchXmlArtifact", () => {
  it.each(XML_CAPTURE_FIXTURES)("classifies $name", async (fixture) => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (input) => {
      const url = String(input);
      const match = fixture.responses.find((item) => item.url === url);
      if (match?.ok) {
        return {
          ok: true,
          text: async () => match.text ?? ""
        } as Response;
      }
      return { ok: false, status: match?.status ?? 404 } as Response;
    }) as typeof fetch;

    try {
      const result = await fetchXmlArtifact(fixture.responses.map((item) => item.url));
      expect(result.ok).toBe(fixture.expected.ok);
      if (fixture.expected.ok) {
        expect(result).toMatchObject({
          ok: true,
          payloadName: "paper.xml",
          sourceUrl: fixture.expected.sourceUrl
        });
      }
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

describe("extractXmlCandidateUrls", () => {
  it("extracts usable XML candidates from article metadata without injecting publisher keys", () => {
    expect(
      extractXmlCandidateUrls({
        pageUrl: "https://link.springer.com/article/10.1007/s12011-024-04385-0",
        html: `
          <meta name="citation_doi" content="10.1007/s12011-024-04385-0" />
          <meta name="citation_xml_url" content="http://example.org/paper.xml" />
        `
      })
    ).toEqual(["https://example.org/paper.xml"]);
  });

  it("drops unusable legacy Springer XML candidates when no key is available", () => {
    expect(
      extractXmlCandidateUrls({
        pageUrl: "https://link.springer.com/article/10.1007/s12011-024-04385-0",
        html: `
          <meta name="citation_doi" content="10.1007/s12011-024-04385-0" />
          <meta name="citation_springer_api_url" content="http://api.springer.com/xmldata/jats?q=doi:10.1007/s12011-024-04385-0&amp;api_key=" />
        `
      })
    ).toEqual([]);
  });

  it("does not synthesize Springer API URLs from DOI metadata", () => {
    const candidates = extractXmlCandidateUrls({
      pageUrl: "https://link.springer.com/article/10.1007/s12011-024-04385-0",
      html: `
        <meta name="prism:doi" content="10.1007/s12011-024-04385-0" />
      `
    });

    expect(candidates).toEqual([]);
  });
});
