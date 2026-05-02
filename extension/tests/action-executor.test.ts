import { beforeEach, describe, expect, it, vi } from "vitest";

import { executeAction } from "../src/lib/action-executor";

describe("executeAction", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("uses the user-owned Wiley TDM token locally and redacts it from helper bundle metadata", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(new Blob([new Uint8Array([0x25, 0x50, 0x44, 0x46])]), {
        status: 200,
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await executeAction(
      "fetch_wiley_tdm_pdf",
      {
        input: "10.1002/demo",
        wileyTdmToken: "wiley-secret-token",
      },
      {}
    );

    expect(result.success).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.wiley.com/onlinelibrary/tdm/v1/articles/10.1002%2Fdemo",
      expect.objectContaining({
        headers: {
          "Wiley-TDM-Client-Token": "wiley-secret-token",
        },
      })
    );

    const helperBundle = result.helperBundle;
    expect(helperBundle).toBeInstanceOf(Blob);
    const bundleText = new TextDecoder().decode(new Uint8Array(await helperBundle!.arrayBuffer()));
    expect(bundleText).toContain("\"connector\":\"wiley_tdm\"");
    expect(bundleText).toContain("\"artifact_kind\":\"pdf\"");
    expect(bundleText).toContain("\"Wiley-TDM-Client-Token\":\"<user-provided>\"");
    expect(bundleText).not.toContain("wiley-secret-token");
  });

  it("asks for a local Wiley token instead of treating the backend as globally configured", async () => {
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
      error: "Wiley TDM requires your Wiley TDM token in extension settings.",
    });
  });
});
