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
      background?: { service_worker?: string };
      action?: { default_popup?: string; default_icon?: Record<string, string> };
      options_page?: string;
      icons?: Record<string, string>;
      content_scripts?: Array<{ matches?: string[]; js?: string[] }>;
    };

    expect(manifest.permissions).toEqual(["storage", "downloads", "nativeMessaging", "tabs"]);
    expect(manifest.host_permissions).toEqual([
      "https://api.mdtero.com/*",
      "https://api.elsevier.com/*",
      "https://api.wiley.com/*",
      "https://api.springernature.com/*",
      "https://doi.org/*",
      "*://*.arxiv.org/*",
      "*://*.dl.acm.org/*",
      "*://*.ieeexplore.ieee.org/*",
      "*://*.nature.com/*",
      "*://*.pubs.acs.org/*",
      "*://*.pubs.rsc.org/*",
      "*://*.sciencedirect.com/science/article/pii/*",
      "*://*.techrxiv.org/*",
      "*://*.link.springer.com/*",
      "*://*.mdpi.com/*",
      "*://*.springer.com/*",
      "*://*.springernature.com/*",
      "*://*.onlinelibrary.wiley.com/*",
      "*://*.tandfonline.com/*"
    ]);
    expect(manifest.content_scripts?.[0]?.matches).toEqual([
      "https://mdtero.com/*",
      "https://*.mdtero.com/*"
    ]);
    expect(manifest.content_scripts?.[0]?.js).toEqual(["dist/content.js"]);
    expect(manifest.content_scripts?.[1]?.matches).toEqual([
      "*://*.arxiv.org/*",
      "*://*.dl.acm.org/*",
      "*://*.ieeexplore.ieee.org/*",
      "*://*.nature.com/*",
      "*://*.pubs.acs.org/*",
      "*://*.pubs.rsc.org/*",
      "*://*.sciencedirect.com/science/article/pii/*",
      "*://*.techrxiv.org/*",
      "*://*.link.springer.com/*",
      "*://*.mdpi.com/*",
      "*://*.springer.com/*",
      "*://*.springernature.com/*",
      "*://*.onlinelibrary.wiley.com/*",
      "*://*.tandfonline.com/*"
    ]);
    expect(manifest.content_scripts?.[1]?.js).toEqual(["dist/content.js"]);
    expect(manifest.background?.service_worker).toBe("dist/background.js");
    expect(manifest.action?.default_popup).toBe("dist/popup.html");
    expect(manifest.options_page).toBe("dist/options.html");
    expect(manifest.icons).toEqual({
      "16": "dist/assets/icon-16.png",
      "32": "dist/assets/icon-32.png",
      "48": "dist/assets/icon-48.png",
      "128": "dist/assets/icon-128.png"
    });
    expect(manifest.action?.default_icon).toEqual({
      "16": "dist/assets/icon-16.png",
      "32": "dist/assets/icon-32.png"
    });
  });

  it("keeps outward-facing extension copy aligned with local runtime capture", () => {
    const en = JSON.parse(
      readFileSync(resolve("_locales/en/messages.json"), "utf-8")
    ) as { extDescription?: { message?: string } };
    const zh = JSON.parse(
      readFileSync(resolve("_locales/zh_CN/messages.json"), "utf-8")
    ) as { extDescription?: { message?: string } };
    const popupSource = readFileSync(resolve("src/popup/index.ts"), "utf-8");
    const optionsSource = readFileSync(resolve("src/options/index.ts"), "utf-8");

    expect(en.extDescription?.message).toContain("local runtime");
    expect(en.extDescription?.message).toContain("Account");
    expect(en.extDescription?.message).toContain("supported live paper pages");
    expect(zh.extDescription?.message).toContain("本地运行时");
    expect(zh.extDescription?.message).toContain("账户");
    expect(zh.extDescription?.message).toContain("支持的实时论文页");
    expect(popupSource).toContain("Prefer direct publisher APIs and TDM routes first");
    expect(optionsSource).toContain("publisher API");
    expect(optionsSource).toContain("TDM");
  });
});
