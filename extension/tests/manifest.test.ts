import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("extension manifest", () => {
  it("keeps only the permissions needed for the current shipping flow", () => {
    const manifest = JSON.parse(
      readFileSync(resolve("manifest.json"), "utf-8")
    ) as {
      permissions?: string[];
      host_permissions?: string[];
      content_scripts?: Array<{ matches?: string[] }>;
    };

    expect(manifest.permissions).toEqual(["storage", "downloads", "nativeMessaging", "tabs"]);
    expect(manifest.host_permissions).toEqual([
      "https://api.mdtero.com/*",
      "https://api.elsevier.com/*",
      "https://api.springernature.com/*",
      "https://doi.org/*",
      "*://*.arxiv.org/*",
      "*://*.sciencedirect.com/science/article/pii/*",
      "*://*.link.springer.com/*",
      "*://*.springer.com/*",
      "*://*.springernature.com/*",
      "*://*.onlinelibrary.wiley.com/*",
      "*://*.tandfonline.com/*"
    ]);
    expect(manifest.content_scripts?.[0]?.matches).toEqual([
      "https://mdtero.com/*",
      "https://*.mdtero.com/*"
    ]);
    expect(manifest.content_scripts?.[1]?.matches).toEqual([
      "*://*.arxiv.org/*",
      "*://*.sciencedirect.com/science/article/pii/*",
      "*://*.link.springer.com/*",
      "*://*.springer.com/*",
      "*://*.springernature.com/*",
      "*://*.onlinelibrary.wiley.com/*",
      "*://*.tandfonline.com/*"
    ]);
  });
});
