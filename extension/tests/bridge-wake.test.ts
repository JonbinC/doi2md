import { describe, expect, it } from "vitest";

import { isBridgeSupportedPage } from "../src/lib/bridge-wake";

describe("isBridgeSupportedPage", () => {
  it("ignores non-supported pages", () => {
    expect(isBridgeSupportedPage("https://example.com")).toBe(false);
  });

  it("recognizes common publisher HTML pages used by live bridge capture", () => {
    expect(isBridgeSupportedPage("https://dl.acm.org/doi/10.1145/3131726.3131736")).toBe(true);
    expect(isBridgeSupportedPage("https://www.nature.com/articles/d41586-023-02980-0")).toBe(true);
    expect(isBridgeSupportedPage("https://pubs.rsc.org/en/content/articlehtml/2020/ta/d0ta03080e")).toBe(true);
    expect(isBridgeSupportedPage("https://pubs.acs.org/doi/10.1021/acs.jpclett.5b02686")).toBe(true);
    expect(isBridgeSupportedPage("https://ieeexplore.ieee.org/document/1234567")).toBe(true);
    expect(isBridgeSupportedPage("https://www.mdpi.com/1996-1073/17/23/5965")).toBe(true);
    expect(isBridgeSupportedPage("https://www.techrxiv.org/users/123/articles/456-demo")).toBe(true);
  });
});
