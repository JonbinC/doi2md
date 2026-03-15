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
    expect(optionsHtml).toContain('href="./styles.css"');
    expect(optionsHtml).toContain('src="./options.js"');
  });

  it("keeps a separate launch-site workspace with built html entrypoints", () => {
    const sitePackage = readFileSync(resolve("../site/package.json"), "utf-8");
    const siteIndexHtml = readFileSync(resolve("../site/src/index.html"), "utf-8");
    const siteGuideHtml = readFileSync(resolve("../site/src/guide.html"), "utf-8");
    const siteAccountHtml = readFileSync(resolve("../site/src/account.html"), "utf-8");
    const siteDemoHtml = readFileSync(resolve("../site/src/demo.html"), "utf-8");

    expect(sitePackage).toContain('"name": "@mdtero/site"');
    expect(siteIndexHtml).toContain('href="./styles.css"');
    expect(siteIndexHtml).toContain('src="./main.js"');
    expect(siteGuideHtml).toContain('src="./guide.js"');
    expect(siteAccountHtml).toContain('src="./account.js"');
    expect(siteDemoHtml).toContain('src="./demo.js"');
  });

  it("declares warm brand assets for the extension and the launch site", () => {
    const manifest = readFileSync(resolve("manifest.json"), "utf-8");
    const siteBuildConfig = readFileSync(resolve("../site/esbuild.config.mjs"), "utf-8");

    expect(manifest).toContain('"icons"');
    expect(manifest).toContain('"16": "assets/icon-16.png"');
    expect(manifest).toContain('"128": "assets/icon-128.png"');
    expect(manifest).toContain('"default_icon"');
    expect(siteBuildConfig).toContain('copyFile("src/assets/brand-mark.svg", "dist/assets/brand-mark.svg")');
  });
});
