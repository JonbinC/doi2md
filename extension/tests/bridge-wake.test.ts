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
});
