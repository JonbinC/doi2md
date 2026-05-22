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
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
