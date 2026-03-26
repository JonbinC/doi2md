import { describe, expect, it, vi } from "vitest";

import { triggerBlobDownload } from "../src/lib/download";

describe("triggerBlobDownload", () => {
  it("downloads blobs with the provided stable filename", () => {
    const click = vi.fn();
    const revokeObjectURL = vi.fn();
    const anchor = {
      href: "",
      download: "",
      click,
      remove: vi.fn()
    };

    triggerBlobDownload(new Blob(["zip-data"]), "zhou2025performance.zip", {
      createObjectURL: () => "blob:chrome-extension://demo/6fbf3978-4cae-4ed1-865a-f23f7b328d75",
      revokeObjectURL,
      createAnchor: () => anchor
    });

    expect(anchor.href).toBe("blob:chrome-extension://demo/6fbf3978-4cae-4ed1-865a-f23f7b328d75");
    expect(anchor.download).toBe("zhou2025performance.zip");
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith(
      "blob:chrome-extension://demo/6fbf3978-4cae-4ed1-865a-f23f7b328d75"
    );
  });
});
