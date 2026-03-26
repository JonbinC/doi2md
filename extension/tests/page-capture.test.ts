import { describe, expect, it } from "vitest";
import { vi } from "vitest";

import {
  buildPageCaptureResult,
  extractXmlCandidateUrls,
  fetchXmlArtifact,
  downloadEpubArtifact,
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
    }
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
  it("extracts Springer XML candidates from article metadata and injects the OA key", () => {
    expect(
      extractXmlCandidateUrls({
        pageUrl: "https://link.springer.com/article/10.1007/s12011-024-04385-0",
        springerOpenAccessApiKey: "springer-key",
        html: `
          <meta name="citation_doi" content="10.1007/s12011-024-04385-0" />
          <meta name="citation_springer_api_url" content="http://api.springer.com/xmldata/jats?q=doi:10.1007/s12011-024-04385-0&amp;api_key=" />
        `
      })
    ).toEqual([
      "https://api.springernature.com/openaccess/jats?q=doi:10.1007%2Fs12011-024-04385-0&api_key=springer-key",
      "https://api.springer.com/xmldata/jats?q=doi%3A10.1007%2Fs12011-024-04385-0&api_key=springer-key"
    ]);
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

  it("reads DOI metadata from colon-style prism and dc meta names", () => {
    const candidates = extractXmlCandidateUrls({
      pageUrl: "https://link.springer.com/article/10.1007/s12011-024-04385-0",
      springerOpenAccessApiKey: "springer-key",
      html: `
        <meta name="prism:doi" content="10.1007/s12011-024-04385-0" />
        <meta name="citation_springer_api_url" content="https://api.springer.com/xmldata/jats?q=doi:10.1007/s12011-024-04385-0&amp;api_key=" />
      `
    });

    expect(candidates[0]).toBe(
      "https://api.springernature.com/openaccess/jats?q=doi:10.1007%2Fs12011-024-04385-0&api_key=springer-key"
    );
  });
});
