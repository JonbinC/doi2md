import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { ApiErrorCode, DEFAULT_API_BASE_URL } from "@mdtero/shared";

function stripWhitespace(value: string): string {
  return value.replace(/\s+/g, " ");
}

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
    expect(popupHtml).toContain('id="connection-pill"');
    expect(popupHtml).toContain('id="workflow-upload"');
    expect(popupHtml).toContain('id="open-settings-login"');
    expect(popupHtml).not.toContain('id="supported-sources-inline"');
    expect(popupHtml).not.toContain('id="support-shadow-title"');
    expect(popupHtml).not.toContain('id="support-experimental-title"');
    expect(popupHtml).toContain('id="file-intake-card"');
    expect(popupHtml).toContain('id="local-file-input"');
    expect(popupHtml).not.toContain('id="campus-hint"');
    expect(popupHtml).not.toContain('id="helper-status"');
    expect(popupHtml).not.toContain('id="pdf-engine-select"');
    expect(popupHtml).not.toContain("Docling");
    expect(popupHtml).not.toContain("MinerU");
    expect(popupHtml).not.toContain("PMC");
    expect(popupHtml).not.toContain("Wiley");
    expect(optionsHtml).not.toContain("Elsevier");
    expect(optionsHtml).not.toContain("PMC");
    expect(optionsHtml).not.toContain("Wiley");
    expect(optionsHtml).toContain('href="./styles.css"');
    expect(optionsHtml).toContain('src="./options.js"');
    expect(optionsHtml).toContain('id="settings-overview-card"');
    expect(optionsHtml).toContain('id="open-account"');
    expect(optionsHtml).toContain('id="website-auth-note"');
    expect(optionsHtml).not.toContain('id="password-input"');
    expect(optionsHtml).not.toContain('id="auth-mode-password"');
    expect(optionsHtml).not.toContain('id="code-input"');
    expect(optionsHtml).not.toContain('id="verify-code"');
    expect(optionsHtml).not.toContain('id="shadow-status"');
    expect(optionsHtml).not.toContain('id="springer-oa-api-key"');
    expect(optionsHtml).not.toContain('id="wiley-tdm-token"');
    expect(optionsHtml).not.toContain('id="elsevier-api-key"');
    expect(optionsHtml).toContain('id="permissions-card"');
    expect(optionsHtml).toContain('id="permissions-title"');
    expect(optionsHtml).not.toContain('id="publisher-capability-groups"');
    expect(optionsHtml).not.toContain('id="connector-keys-section"');
    expect(optionsHtml).not.toContain('id="browser-assisted-note"');
  });

  it("keeps the public repo scoped away from the site workspace", () => {
    const repoReadme = readFileSync(resolve("../README.md"), "utf-8");

    expect(repoReadme).toContain("Python/uv CLI, TUI, browser extension, and agent skill bundle");
    expect(() => readFileSync(resolve("../site/package.json"), "utf-8")).toThrow();
    expect(() => readFileSync(resolve("../site/src/index.html"), "utf-8")).toThrow();
  });

  it("declares warm brand assets for the extension", () => {
    const manifest = readFileSync(resolve("manifest.json"), "utf-8");
    const localeEn = readFileSync(resolve("_locales/en/messages.json"), "utf-8");
    const localeZh = readFileSync(resolve("_locales/zh_CN/messages.json"), "utf-8");

    expect(manifest).toContain('"icons"');
    expect(manifest).toContain('"16": "dist/assets/icon-16.png"');
    expect(manifest).toContain('"128": "dist/assets/icon-128.png"');
    expect(manifest).toContain('"default_icon"');
    expect(manifest).toContain('"service_worker": "dist/background.js"');
    expect(manifest).toContain('"default_popup": "dist/popup.html"');
    expect(localeEn).toContain("parse the current paper page");
    expect(localeEn).toContain("reusable Markdown outputs");
    expect(localeEn).not.toContain("reusable Markdown research packages");
    expect(localeEn).not.toContain("publisher API / TDM");
    expect(localeZh).toContain("解析当前论文页");
    expect(localeZh).toContain("可复用的 Markdown 产物");
    expect(localeZh).not.toContain("可复用的 Markdown 文献包");
    expect(localeZh).not.toContain("publisher API / TDM");
  });

  it("keeps the extension shell aligned with the neutral Mdtero product palette", () => {
    const styles = readFileSync(resolve("src/styles.css"), "utf-8");

    expect(styles).toContain("--background: #f7f8fb");
    expect(styles).toContain("--primary: #111827");
    expect(styles).toContain("--accent-foreground: #0f766e");
    expect(styles).not.toContain("#6d3920");
    expect(styles).not.toContain("#f6e6d5");
    expect(styles).not.toContain("#50291a");
  });

  it("keeps popup and options layouts bounded for extension viewports", () => {
    const popupHtml = readFileSync(resolve("src/popup/index.html"), "utf-8");
    const optionsHtml = readFileSync(resolve("src/options/index.html"), "utf-8");
    const styles = stripWhitespace(readFileSync(resolve("src/styles.css"), "utf-8"));

    expect(popupHtml).toContain('class="panel panel-popup"');
    expect(optionsHtml).toContain('class="panel panel-options"');
    expect(styles).toContain(".panel-popup { width: 380px; max-width: 100vw; }");
    expect(styles).toContain(".panel-popup .shell { max-height: min(600px, 100vh); overflow-y: auto; }");
    expect(styles).toContain(".workflow-strip { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));");
    expect(styles).toContain("#account-email, #account-status, #usage-status { overflow-wrap: anywhere; }");
    expect(styles).toContain("button { min-height: 40px;");
  });
});
