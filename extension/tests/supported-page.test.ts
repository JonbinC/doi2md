import { describe, expect, it } from "vitest";

import { isSupportedPaperPage } from "../src/lib/supported-page";

describe("isSupportedPaperPage", () => {
  it("ignores non-supported pages", () => {
    expect(isSupportedPaperPage("https://example.com")).toBe(false);
  });

  it("recognizes common publisher HTML pages that extension capture can inspect", () => {
    expect(isSupportedPaperPage("https://dl.acm.org/doi/10.1145/3131726.3131736")).toBe(true);
    expect(isSupportedPaperPage("https://kns.cnki.net/kcms2/article/abstract?v=demo")).toBe(true);
    expect(isSupportedPaperPage("https://www.nature.com/articles/d41586-023-02980-0")).toBe(true);
    expect(isSupportedPaperPage("https://pubs.rsc.org/en/content/articlehtml/2020/ta/d0ta03080e")).toBe(true);
    expect(isSupportedPaperPage("https://pubs.acs.org/doi/10.1021/acs.jpclett.5b02686")).toBe(true);
    expect(isSupportedPaperPage("https://ieeexplore.ieee.org/document/1234567")).toBe(true);
    expect(isSupportedPaperPage("https://www.mdpi.com/1996-1073/17/23/5965")).toBe(true);
    expect(isSupportedPaperPage("https://www.techrxiv.org/users/123/articles/456-demo")).toBe(true);
  });
});
