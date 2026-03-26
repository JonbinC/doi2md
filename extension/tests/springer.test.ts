import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchSpringerOpenAccessJats, normalizeSpringerInput } from "../src/lib/springer";

describe("normalizeSpringerInput", () => {
  it("extracts DOIs from Springer article urls", () => {
    expect(
      normalizeSpringerInput("https://link.springer.com/article/10.1007/s12011-024-04385-0")
    ).toBe("10.1007/s12011-024-04385-0");
  });

  it("accepts Springer-style DOI inputs directly", () => {
    expect(normalizeSpringerInput("10.1007/s12011-024-04385-0")).toBe("10.1007/s12011-024-04385-0");
  });

  it("uses the page url to validate DOI inputs from Springer pages", () => {
    expect(
      normalizeSpringerInput(
        "doi:10.1007/s12011-024-04385-0".replace(/^doi:/, ""),
        "https://link.springer.com/article/10.1007/s12011-024-04385-0"
      )
    ).toBe("10.1007/s12011-024-04385-0");
  });
});

describe("fetchSpringerOpenAccessJats", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("fetches OA JATS from the Springer Nature API", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response("<?xml version='1.0'?><response><records><article><body>Demo</body></article></records></response>", {
        status: 200,
        headers: { "Content-Type": "application/xml" }
      })
    );

    const result = await fetchSpringerOpenAccessJats(
      "https://link.springer.com/article/10.1007/s12011-024-04385-0",
      "springer-oa-key"
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.springernature.com/openaccess/jats?q=doi:10.1007%2Fs12011-024-04385-0&api_key=springer-oa-key"
    );
    expect(result.filename).toBe("paper.xml");
    expect(result.sourceDoi).toBe("10.1007/s12011-024-04385-0");
  });

  it("fails cleanly when the API does not return an article payload", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response("<response><result><total>0</total></result></response>", { status: 200 })
    );

    await expect(
      fetchSpringerOpenAccessJats("10.1007/s12011-024-04385-0", "springer-oa-key")
    ).rejects.toThrow("did not return a JATS article payload");
  });
});
