import { beforeEach, describe, expect, it, vi } from "vitest";

import { executeAction } from "../src/lib/action-executor";

describe("executeAction", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("keeps Wiley TDM keys out of the extension and points users to CLI or upload", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const result = await executeAction(
      "fetch_wiley_tdm_pdf",
      {
        input: "10.1002/demo",
      },
      {}
    );

    expect(result).toEqual({
      success: false,
      requiresUpload: true,
      error: "Wiley TDM requires a user token. Configure academic source keys with `mdtero config academic` in the Python CLI, use the extension on an already-open full-text page, or upload the PDF/XML/EPUB file directly.",
      nextCommand: "mdtero parse 10.1002/demo --trace --wait --json",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps Elsevier API keys out of the extension route executor", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const result = await executeAction(
      "fetch_elsevier_xml",
      {
        input: "10.1016/j.energy.2026.140192",
      },
      {}
    );

    expect(result.success).toBe(false);
    expect(result.requiresUpload).toBe(true);
    expect(result.error).toContain("mdtero config academic");
    expect(result.nextCommand).toBe("mdtero parse 10.1016/j.energy.2026.140192 --trace --wait --json");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("quotes shell-sensitive URL handoff commands when browser capture fails", async () => {
    const chromeStub = {
      tabs: {
        sendMessage: vi.fn().mockResolvedValue({
          ok: true,
          capture: {
            ok: false,
            failureCode: "challenge_page_detected",
            failureMessage: "Page loaded but did not expose article content."
          }
        })
      }
    };
    vi.stubGlobal("chrome", chromeStub);

    const result = await executeAction(
      "capture_current_tab_html",
      {
        input: "https://www.mdpi.com/2071-1050/17/5/2018?x=a b",
        tabId: 42,
      },
      {}
    );

    expect(result.success).toBe(false);
    expect(result.error).toBe("Page loaded but did not expose article content.");
    expect(result.nextCommand).toBe("mdtero parse 'https://www.mdpi.com/2071-1050/17/5/2018?x=a b' --trace --wait --json");
  });
});
