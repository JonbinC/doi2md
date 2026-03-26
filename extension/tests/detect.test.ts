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

  it("detects arxiv pages directly from the current url", () => {
    expect(
      detectPaperInput({
        url: "https://arxiv.org/abs/2401.00001",
        html: "<html></html>"
      })
    ).toEqual({ kind: "arxiv", value: "https://arxiv.org/abs/2401.00001" });
  });

  it("detects DOI from single-quoted meta tags and prism metadata", () => {
    expect(
      detectPaperInput({
        url: "https://publisher.example/paper",
        html: "<meta name='prism.doi' content='10.1002/er.7490'>"
      })
    ).toEqual({ kind: "doi", value: "10.1002/er.7490" });
  });

  it("detects arxiv pdf urls as arxiv inputs", () => {
    expect(
      detectPaperInput({
        url: "https://arxiv.org/pdf/2401.00001.pdf",
        html: "<html></html>"
      })
    ).toEqual({ kind: "arxiv", value: "https://arxiv.org/pdf/2401.00001.pdf" });
  });
});
