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
    expect(popupHtml).toContain('id="mdtero-popup-bg"');
    expect(popupHtml).not.toContain('id="mdtero-popup-ink"');
    expect(popupHtml).toContain('id="workflow-translate"');
    expect(popupHtml).toContain('Parse / Upload');
    expect(popupHtml).toContain('Translate');
    expect(popupHtml).not.toContain('id="workflow-upload"');
    expect(popupHtml).toContain('id="open-settings-login"');
    expect(popupHtml).not.toContain('id="supported-sources-inline"');
    expect(popupHtml).not.toContain('id="support-shadow-title"');
    expect(popupHtml).not.toContain('id="support-experimental-title"');
    expect(popupHtml).toContain('id="file-intake-card"');
    expect(popupHtml).toContain('id="local-file-input"');
    expect(popupHtml).toContain('id="cli-handoff"');
    expect(popupHtml).toContain('id="cli-handoff-note"');
    expect(popupHtml).toContain('id="cli-handoff-plan"');
    expect(popupHtml).toContain('id="copy-cli-handoff"');
    expect(popupHtml).toContain('Copy handoff');
    expect(popupHtml).not.toContain('Copy CLI command');
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
    expect(optionsHtml).toContain('id="mdtero-options-bg"');
    expect(optionsHtml).not.toContain('id="mdtero-options-ink"');
    expect(optionsHtml).toContain('id="open-account"');
    expect(optionsHtml).toContain('id="website-auth-note"');
    expect(optionsHtml).toContain('id="connection-guide-card"');
    expect(optionsHtml).toContain('id="connection-guide-list"');
    expect(optionsHtml).toContain('id="input-route-card"');
    expect(optionsHtml).toContain('id="input-route-list"');
    expect(optionsHtml).toContain('Extension + CLI');
    expect(optionsHtml).toContain('id="cli-handoff-guide-card"');
    expect(optionsHtml).toContain('id="cli-handoff-guide-command"');
    expect(optionsHtml).toContain('id="copy-cli-handoff-guide"');
    expect(optionsHtml).toContain('id="mcp-server-config-card"');
    expect(optionsHtml).toContain('id="mcp-server-config-command"');
    expect(optionsHtml).toContain('id="copy-mcp-server-config"');
    expect(optionsHtml).toContain('FastMCP');
    expect(optionsHtml).toContain('stdio');
    expect(optionsHtml).toContain('id="setup-step-auth"');
    expect(optionsHtml).toContain('Parse / Upload');
    expect(optionsHtml).toContain('Translate');
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

  it("documents extension auth and helper boundaries", () => {
    const readme = readFileSync(resolve("README.md"), "utf-8");

    expect(readme).toContain("The auth bridge only accepts messages from `https://mdtero.com` and `https://www.mdtero.com`");
    expect(readme).toContain("Publisher pages cannot mint extension tokens");
    expect(readme).toContain("does not store publisher API keys, TDM keys, or local helper credentials");
    expect(readme).toContain("does not use native messaging or a local helper process");
    expect(readme).toContain("shows a CLI handoff command");
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

  it("keeps the extension shell aligned with the Mdtero website palette", () => {
    const styles = readFileSync(resolve("src/styles.css"), "utf-8");

    expect(styles).toContain("--background: #fcf7f1");
    expect(styles).toContain("--primary: #6d3920");
    expect(styles).toContain("--secondary: #f7efe6");
    expect(styles).toContain("--accent: #e2b792");
    expect(styles).toContain("--input-background: #f8f1e9");
    expect(styles).toContain("--surface: rgba(255, 253, 249, 0.88)");
    expect(styles).toContain("--surface-muted: rgba(244, 236, 227, 0.58)");
    expect(styles).toContain("--success: #0f766e");
    expect(styles).not.toContain("--primary: #111827");
  });

  it("keeps popup and options layouts bounded for extension viewports", () => {
    const popupHtml = readFileSync(resolve("src/popup/index.html"), "utf-8");
    const optionsHtml = readFileSync(resolve("src/options/index.html"), "utf-8");
    const styles = stripWhitespace(readFileSync(resolve("src/styles.css"), "utf-8"));

    expect(popupHtml).toContain('class="panel panel-popup"');
    expect(optionsHtml).toContain('class="panel panel-options"');
    expect(styles).toContain("html { min-width: 380px; min-height: 600px; }");
    expect(styles).toContain(".panel-popup { width: 380px; height: 600px; min-height: 600px; max-width: 100vw; overflow: hidden; }");
    expect(styles).toContain(".panel-popup .shell { height: 600px; max-height: 600px; overflow-y: auto; }");
    expect(styles).toContain(".workflow-strip { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));");
    expect(styles).toContain('.workflow-strip span[data-state="active"]');
    expect(styles).toContain('.workflow-strip span[data-state="done"]');
    expect(styles).toContain('.workflow-strip span[data-state="pending"]');
    expect(styles).toContain(".guide-item { display: grid; grid-template-columns: auto minmax(0, 1fr);");
    expect(styles).toContain(".input-route-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }");
    expect(styles).toContain(".input-route-copy { width: 100%; }");
    expect(styles).toContain(".handoff-guide-header { display: grid; grid-template-columns: minmax(0, 1fr) auto;");
    expect(styles).toContain(".handoff-guide-command { display: block;");
    expect(styles).toContain("#account-email, #account-status, #usage-status { overflow-wrap: anywhere; }");
    expect(styles).toContain("button { min-height: 40px;");
    expect(styles).toContain(".cli-handoff code { min-width: 0; overflow: auto;");
    expect(styles).toContain(".cli-handoff-plan { grid-column: 1 / -1;");
    expect(styles).toContain(".cli-handoff-plan li { overflow-wrap: anywhere;");
    expect(styles).toContain("white-space: pre-wrap;");
    expect(styles).toContain(".hero { background: linear-gradient(180deg, rgba(255, 253, 249, 0.96), rgba(255, 250, 244, 0.88)), linear-gradient(135deg, rgba(109, 57, 32, 0.06), transparent 52%);");
  });

  it("keeps extension-to-CLI onboarding aligned with the Python setup checklist", () => {
    const optionsSource = readFileSync(resolve("src/options/index.ts"), "utf-8");

    expect(optionsSource).toContain('const CLI_INSTALL_COMMAND = "uv tool install --force --reinstall git+https://github.com/JonbinC/doi2md.git"');
    expect(optionsSource).toContain('const CLI_PYPI_COMMAND = "uv tool install mdtero"');
    expect(optionsSource).toContain("known-good public Python client");
    expect(optionsSource).toContain("mdtero setup");
    expect(optionsSource).toContain("mdtero setup --json");
    expect(optionsSource).toContain("Choose the shortest path to a Markdown artifact");
    expect(optionsSource).toContain("mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json");
    expect(optionsSource).toContain("mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json");
    expect(optionsSource).toContain("onboarding checklist");
    expect(optionsSource).toContain("mdtero config academic");
    expect(optionsSource).toContain("mdtero mcp briefing --json");
    expect(optionsSource).toContain("mdtero mcp serve");
    expect(optionsSource).toContain("mcpServers");
    expect(optionsSource).toContain("<local-mdtero-project-root>");
    expect(optionsSource).not.toContain("mdtero setup --api-key <key>");
  });

  it("keeps popup workflow steps stateful for OAuth, parse, translate, and download", () => {
    const popupSource = readFileSync(resolve("src/popup/index.ts"), "utf-8");

    expect(popupSource).toContain('type WorkflowState = "pending" | "active" | "done"');
    expect(popupSource).toContain("function updateWorkflowState()");
    expect(popupSource).toContain("setWorkflowStep(workflowAuthEl, isSignedIn ? \"done\" : \"active\")");
    expect(popupSource).toContain("setWorkflowStep(workflowParseEl, hasParsedArtifact ? \"done\" : isSignedIn ? \"active\" : \"pending\")");
    expect(popupSource).toContain("setWorkflowStep(workflowTranslateEl, hasTranslatedArtifact ? \"done\" : isTranslating || hasParsedArtifact ? \"active\" : \"pending\")");
    expect(popupSource).toContain("setWorkflowStep(workflowDownloadEl, hasDownloadableArtifact ? \"done\" : hasParsedArtifact || hasTranslatedArtifact ? \"active\" : \"pending\")");
    expect(popupSource).toContain('workflowDone: "done"');
    expect(popupSource).toContain('workflowDone: "完成"');
  });
});
