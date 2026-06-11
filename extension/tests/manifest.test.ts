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
      content_scripts?: Array<{ matches?: string[]; js?: string[]; run_at?: string }>;
    };

    expect(manifest.permissions).toEqual(["storage", "downloads", "tabs", "activeTab", "scripting"]);
    expect(manifest.host_permissions).toEqual([
      "https://api.mdtero.com/*",
      "https://api.elsevier.com/*",
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
    expect(manifest.content_scripts?.[0]?.run_at).toBe("document_start");
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
    expect(manifest.content_scripts?.[1]?.run_at).toBe("document_idle");
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

  it("keeps outward-facing extension copy aligned with the shipping browser flow", () => {
    const en = JSON.parse(
      readFileSync(resolve("_locales/en/messages.json"), "utf-8")
    ) as { extDescription?: { message?: string } };
    const zh = JSON.parse(
      readFileSync(resolve("_locales/zh_CN/messages.json"), "utf-8")
    ) as { extDescription?: { message?: string } };
    const popupSource = readFileSync(resolve("src/popup/index.ts"), "utf-8");
    const optionsSource = readFileSync(resolve("src/options/index.ts"), "utf-8");

    expect(en.extDescription?.message).toContain("Account");
    expect(en.extDescription?.message).toContain("parse the current paper page");
    expect(en.extDescription?.message).toContain("upload local PDF or EPUB");
    expect(en.extDescription?.message).not.toContain("publisher API / TDM");
    expect(zh.extDescription?.message).toContain("账户");
    expect(zh.extDescription?.message).toContain("解析当前论文页");
    expect(zh.extDescription?.message).toContain("上传本地 PDF 或 EPUB");
    expect(zh.extDescription?.message).not.toContain("publisher API / TDM");
    expect(popupSource).toContain("Local file intake");
    expect(popupSource).toContain("Use PDF");
    expect(popupSource).toContain("Use EPUB");
    expect(popupSource).toContain("mdtero.com/auth");
    expect(popupSource).not.toContain("mdtero.com/account");
    expect(popupSource).toContain("Open website OAuth");
    expect(popupSource).toContain("Copy handoff");
    expect(optionsSource).toContain("Website sign-in");
    expect(optionsSource).toContain("mdtero.com/auth");
    expect(optionsSource).not.toContain("mdtero.com/account");
    expect(optionsSource).toContain("Open website OAuth");
    expect(optionsSource).toContain("trusted auth bridge");
    expect(optionsSource).toContain("Connection guide");
    expect(optionsSource).toContain("Website OAuth is connected");
    expect(optionsSource).toContain("browser-side paper capture");
    expect(optionsSource).toContain("Browser capture reuses the active tab");
    expect(optionsSource).toContain("Elsevier API key");
    expect(optionsSource).toContain("Elsevier access");
    expect(optionsSource).not.toContain("Wiley TDM");
    expect(optionsSource).not.toContain("wiley-tdm-token");
    expect(optionsSource).not.toContain("springer-oa-api-key");
    expect(optionsSource).not.toContain("nativeMessaging` is reserved");
    expect(optionsSource).not.toContain("uv tool install");
    expect(optionsSource).not.toContain("MCP server");
    expect(optionsSource).not.toContain("CLI-assisted capture");
  });

  it("does not expose a native host helper dependency in the shipping extension", () => {
    const manifest = JSON.parse(readFileSync(resolve("manifest.json"), "utf-8")) as { permissions?: string[] };
    const backgroundSource = readFileSync(resolve("src/background.ts"), "utf-8");
    const contentSource = readFileSync(resolve("src/content.ts"), "utf-8");

    expect(manifest.permissions ?? []).not.toContain("nativeMessaging");
    expect(manifest.permissions ?? []).toContain("activeTab");
    expect(manifest.permissions ?? []).toContain("scripting");
    expect(backgroundSource).not.toContain("connectNative");
    expect(backgroundSource).not.toContain("initializeBrowserBridge");
    expect(backgroundSource).not.toContain("mdtero.bridge.status");
    expect(backgroundSource).not.toContain("mdtero.source_connectivity.observation");
    expect(contentSource).not.toContain("announceBridgePageReady");
  });

  it("allows user-owned Elsevier API access without exposing TDM key storage", () => {
    const manifest = JSON.parse(readFileSync(resolve("manifest.json"), "utf-8")) as { host_permissions?: string[] };
    const storageSource = readFileSync(resolve("src/lib/storage.ts"), "utf-8");
    const backgroundSource = readFileSync(resolve("src/background.ts"), "utf-8");

    expect(manifest.host_permissions ?? []).toContain("https://api.elsevier.com/*");
    expect(manifest.host_permissions ?? []).not.toContain("https://api.wiley.com/*");
    expect(manifest.host_permissions ?? []).not.toContain("https://api.springernature.com/*");
    expect(storageSource).toContain("elsevierApiKey");
    expect(storageSource).not.toContain("wileyTdmToken");
    expect(storageSource).not.toContain("springerOpenAccessApiKey");
    expect(backgroundSource).toContain("elsevierApiKey");
    expect(backgroundSource).not.toContain("wileyTdmToken");
    expect(backgroundSource).not.toContain("springerOpenAccessApiKey");
  });
});
