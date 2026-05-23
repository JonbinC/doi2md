// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://mdtero.com/auth?source=extension"}
import { beforeEach, describe, expect, it, vi } from "vitest";

function createChromeStub() {
  const messageListeners: Array<(message: unknown, sender: unknown, sendResponse: (payload: unknown) => void) => boolean | void> = [];
  return {
    runtime: {
      onMessage: {
        addListener(listener: (message: unknown, sender: unknown, sendResponse: (payload: unknown) => void) => boolean | void) {
          messageListeners.push(listener);
        }
      },
      sendMessage: vi.fn(async () => ({ ok: true })),
    },
    __messageListeners: messageListeners,
  };
}

describe("content auth bridge", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    document.documentElement.innerHTML = "<html><head><title>Mdtero</title></head><body></body></html>";
  });

  it("forwards trusted website OAuth tokens to the background script", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);

    await import("../src/content");

    window.dispatchEvent(
      new MessageEvent("message", {
        source: window,
        origin: "https://mdtero.com",
        data: {
          type: "mdtero.auth.token",
          token: "web-token",
          email: "reader@example.com",
        },
      })
    );

    await vi.waitFor(() => {
      expect(chromeStub.runtime.sendMessage).toHaveBeenCalledWith({
        type: "mdtero.auth.save_token",
        token: "web-token",
        email: "reader@example.com",
      });
    });
  });

  it("rejects publisher-origin auth-shaped messages", async () => {
    const chromeStub = createChromeStub();
    vi.stubGlobal("chrome", chromeStub);

    await import("../src/content");

    window.dispatchEvent(
      new MessageEvent("message", {
        source: window,
        origin: "https://www.sciencedirect.com",
        data: {
          type: "mdtero.auth.token",
          token: "publisher-token",
          email: "reader@example.com",
        },
      })
    );

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(chromeStub.runtime.sendMessage).not.toHaveBeenCalled();
  });
});
