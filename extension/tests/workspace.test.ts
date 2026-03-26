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
    expect(popupHtml).toContain('id="helper-status"');
    expect(popupHtml).toContain("Elsevier");
    expect(popupHtml).toContain("arXiv");
    expect(popupHtml).toContain('id="support-stable-title"');
    expect(popupHtml).toContain('id="support-shadow-title"');
    expect(popupHtml).toContain('id="support-experimental-title"');
    expect(popupHtml).toContain('id="file-intake-card"');
    expect(popupHtml).toContain('id="local-file-input"');
    expect(popupHtml).toContain('id="pdf-engine-select"');
    expect(popupHtml).toContain("PMC");
    expect(popupHtml).toContain("Wiley");
    expect(optionsHtml).toContain('href="./styles.css"');
    expect(optionsHtml).toContain('src="./options.js"');
    expect(optionsHtml).toContain('id="settings-overview-card"');
    expect(optionsHtml).toContain('id="password-input"');
    expect(optionsHtml).toContain('id="auth-mode-password"');
    expect(optionsHtml).toContain('id="shadow-status"');
    expect(optionsHtml).toContain('id="springer-oa-api-key"');
    expect(optionsHtml).toContain('id="permissions-card"');
    expect(optionsHtml).toContain('id="permissions-title"');
    expect(optionsHtml).toContain('id="settings-support-stable-title"');
    expect(optionsHtml).toContain('id="settings-support-experimental-title"');
    expect(optionsHtml).toContain("Taylor &amp; Francis");
    expect(optionsHtml.indexOf('id="code-input"')).toBeLessThan(optionsHtml.indexOf('id="verify-code"'));
  });

  it("declares warm brand assets for the extension package", () => {
    const manifest = readFileSync(resolve("manifest.json"), "utf-8");

    expect(manifest).toContain('"icons"');
    expect(manifest).toContain('"16": "assets/icon-16.png"');
    expect(manifest).toContain('"128": "assets/icon-128.png"');
    expect(manifest).toContain('"default_icon"');
  });
});
