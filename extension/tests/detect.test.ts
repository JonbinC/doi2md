import { describe, expect, it } from "vitest";

import { detectPaperInput } from "../src/lib/detect";

describe("detectPaperInput", () => {
  it("detects DOI from current URL", () => {
    expect(
      detectPaperInput({
        url: "https://doi.org/10.1016/j.conbuildmat.2026.145877",
        html: "<html></html>"
      })
    ).toEqual({ kind: "doi", value: "10.1016/j.conbuildmat.2026.145877" });
  });

  it("detects DOI from ScienceDirect pages", () => {
    expect(
      detectPaperInput({
        url: "https://www.sciencedirect.com/science/article/pii/S0000000000000012",
        html: '<meta name="citation_doi" content="10.1016/j.ijthermalsci.2023.108851">'
      })
    ).toEqual({ kind: "doi", value: "10.1016/j.ijthermalsci.2023.108851" });
  });
});
