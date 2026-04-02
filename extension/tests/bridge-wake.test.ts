import { describe, expect, it, vi } from "vitest";

import { announceBridgePageReady, isBridgeSupportedPage } from "../src/lib/bridge-wake";

describe("announceBridgePageReady", () => {
  it("sends a lightweight wake ping for supported pages", () => {
    const sendMessage = vi.fn().mockResolvedValue({ ok: true });

    announceBridgePageReady(
      {
        sendMessage
      } as never,
      "https://www.tandfonline.com/doi/full/10.1080/26395940.2021.1947159"
    );

    expect(sendMessage).toHaveBeenCalledWith({
      type: "mdtero.bridge.page_ready",
      url: "https://www.tandfonline.com/doi/full/10.1080/26395940.2021.1947159"
    });
  });

  it("fails soft when the runtime is unavailable", async () => {
    const sendMessage = vi.fn().mockRejectedValue(new Error("background unavailable"));

    expect(() =>
      announceBridgePageReady(
        {
          sendMessage
        } as never,
        "https://arxiv.org/abs/2401.00001"
      )
    ).not.toThrow();

    await Promise.resolve();
  });

  it("ignores non-supported pages", () => {
    const sendMessage = vi.fn().mockResolvedValue({ ok: true });

    expect(isBridgeSupportedPage("https://example.com")).toBe(false);

    announceBridgePageReady(
      {
        sendMessage
      } as never,
      "https://example.com"
    );

    expect(sendMessage).not.toHaveBeenCalled();
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
