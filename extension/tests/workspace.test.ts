import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { ApiErrorCode, DEFAULT_API_BASE_URL } from "@mdtero/shared";

describe("workspace", () => {
  it("exposes the shared package entrypoint", () => {
    expect(DEFAULT_API_BASE_URL).toBe("https://api.mdtero.com");
    expect(ApiErrorCode.ParseFailed).toBe("parse_failed");
  });

  it("uses built script names in extension html entrypoints", () => {
    const popupHtml = readFileSync(resolve("src/popup/index.html"), "utf-8");
    const optionsHtml = readFileSync(resolve("src/options/index.html"), "utf-8");

    expect(popupHtml).toContain('href="./styles.css"');
    expect(popupHtml).toContain('src="./popup.js"');
    expect(popupHtml).toContain('id="supported-sources-inline"');
    expect(popupHtml).toContain("Elsevier");
    expect(popupHtml).toContain("arXiv");
    expect(optionsHtml).toContain('href="./styles.css"');
    expect(optionsHtml).toContain('src="./options.js"');
    expect(optionsHtml).toContain('id="settings-overview-card"');
  });

  it("keeps public install guides beside the extension package", () => {
    const readme = readFileSync(resolve("../README.md"), "utf-8");
    const codexInstall = readFileSync(resolve("../codex/INSTALL.md"), "utf-8");
    const openClawInstall = readFileSync(resolve("../openclaw/INSTALL.md"), "utf-8");

    expect(readme).toContain("Chrome Web Store");
    expect(readme).toContain("Edge Add-ons");
    expect(readme).not.toContain("mdtero-extension-beta.zip");
    expect(readme).toContain("./openclaw/INSTALL.md");
    expect(codexInstall).toContain("inspect it locally, then run it");
    expect(codexInstall).not.toContain("| sh");
    expect(openClawInstall).toContain("inspect it locally, then run it");
    expect(openClawInstall).not.toContain("| sh");
  });

  it("declares release assets and icons for the public extension repo", () => {
    const manifest = readFileSync(resolve("manifest.json"), "utf-8");
    const readme = readFileSync(resolve("../README.md"), "utf-8");
    const englishMessages = readFileSync(resolve("_locales/en/messages.json"), "utf-8");

    expect(manifest).toContain('"icons"');
    expect(manifest).toContain('"16": "assets/icon-16.png"');
    expect(manifest).toContain('"128": "assets/icon-128.png"');
    expect(manifest).toContain('"default_icon"');
    expect(englishMessages).toContain("Local paper capture");
    expect(englishMessages).toContain("Markdown-first");
    expect(readme).toContain("Chrome Web Store");
    expect(readme).toContain("Edge Add-ons");
  });
});
