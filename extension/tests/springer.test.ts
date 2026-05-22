import { describe, expect, it } from "vitest";

import { normalizeSpringerInput } from "../src/lib/springer";

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
