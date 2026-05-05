import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const TEST_DIR = dirname(fileURLToPath(import.meta.url));
const PUBLIC_ROOT = join(TEST_DIR, "..");
const REPO_ROOT = join(PUBLIC_ROOT, "..");
const FRONTEND_ROOT = join(REPO_ROOT, "Nextmdtero");

const MANIFEST_PATH = join(PUBLIC_ROOT, "install", "manifest.json");
const PUBLIC_README_PATH = join(PUBLIC_ROOT, "README.md");
const DESKTOP_README_PATH = join(PUBLIC_ROOT, "desktop", "README.md");
const INSTALL_README_PATH = join(PUBLIC_ROOT, "install", "README.md");
const PUBLIC_PACKAGE_PATH = join(PUBLIC_ROOT, "package.json");
const FRONTEND_PACKAGE_PATH = join(FRONTEND_ROOT, "package.json");
const SITE_MANIFEST_PATH = join(FRONTEND_ROOT, "public", "install", "manifest.json");

async function readJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

async function readMarkdown(path) {
  return readFile(path, "utf8");
}

function expectContains(content, expected, label) {
  assert.match(content, new RegExp(escapeRegExp(expected)), `${label} must include: ${expected}`);
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function expectMissing(content, forbidden, label) {
  assert.doesNotMatch(
    content,
    new RegExp(escapeRegExp(forbidden), "i"),
    `${label} must not include: ${forbidden}`
  );
}

test("install manifest stays mirrored with the active site manifest and keeps CLI-first public truth", async () => {
  const [manifest, siteManifest, desktopManifest, pkg] = await Promise.all([
    readJson(MANIFEST_PATH),
    readJson(SITE_MANIFEST_PATH),
    readJson(join(PUBLIC_ROOT, "desktop", "releases", "installer-manifest.json")),
    readJson(PUBLIC_PACKAGE_PATH)
  ]);

  assert.deepEqual(manifest, siteManifest, "mdtero-public/install/manifest.json must stay mirrored with the site manifest");
  assert.equal(manifest.manifestUrl, "https://mdtero.com/install/manifest.json");
  assert.equal(manifest.cli?.npxCommand, "npx mdtero-install");
  assert.equal(manifest.cli?.packageVersion, pkg.version);
  assert.equal(manifest.releaseTruth?.source, "website-first");
  assert.equal(manifest.releaseTruth?.boundaries?.cliInstallSourceOfTruth, "targets[*] except openclaw");
  assert.equal(manifest.releaseTruth?.boundaries?.openclawInstallSourceOfTruth, "targets[target=openclaw]");
  assert.equal(manifest.releaseTruth?.boundaries?.desktopSourceOfTruth, "mdtero-public/desktop/releases/installer-manifest.json");
  assert.equal(manifest.releaseTruth?.current?.cli?.version, pkg.version);
  assert.equal(manifest.releaseTruth?.latest?.cli?.version, pkg.version);
  assert.equal(manifest.releaseTruth?.current?.desktop?.version, desktopManifest.version);
  assert.deepEqual(manifest.targets.map((target) => target.target), ["openclaw", "claude_code", "codex", "gemini_cli", "hermes", "opencode"]);
  const hermes = manifest.targets.find((target) => target.target === "hermes");
  assert.equal(hermes?.skillDirectory, ".hermes/skills/mdtero");
  assert.match(hermes?.mcpNote ?? "", /public MCP installer flow is not active yet/);
  const opencode = manifest.targets.find((target) => target.target === "opencode");
  assert.equal(opencode?.skillDirectory, ".opencode/skills/mdtero");
  assert.deepEqual(manifest.releaseTruth?.current?.cli?.installTargets, ["claude_code", "codex", "gemini_cli", "hermes", "opencode"]);
  assert.deepEqual(manifest.releaseTruth?.latest?.cli?.installTargets, ["claude_code", "codex", "gemini_cli", "hermes", "opencode"]);
});

test("public install docs keep CLI + extension launch truth and desktop as deferred archive", async () => {
  const [publicReadme, desktopReadme, installReadme, openclawInstallReadme] = await Promise.all([
    readMarkdown(PUBLIC_README_PATH),
    readMarkdown(DESKTOP_README_PATH),
    readMarkdown(INSTALL_README_PATH),
    readMarkdown(join(PUBLIC_ROOT, "helper", "openclaw", "INSTALL.md"))
  ]);

  expectContains(publicReadme, "Mdtero turns papers into reusable Markdown research packages.", "mdtero-public/README.md");
  expectContains(publicReadme, "npx mdtero-install show", "mdtero-public/README.md");
  expectContains(publicReadme, "npx mdtero-install version", "mdtero-public/README.md");
  expectContains(publicReadme, "npx mdtero-install install codex", "mdtero-public/README.md");
  expectContains(publicReadme, "npx mdtero-install install claude_code", "mdtero-public/README.md");
  expectContains(publicReadme, "npx mdtero-install install gemini_cli", "mdtero-public/README.md");
  expectContains(publicReadme, "npx mdtero-install install hermes", "mdtero-public/README.md");
  expectContains(publicReadme, "npx mdtero-install install opencode", "mdtero-public/README.md");
  expectContains(publicReadme, "mdtero-install show` prints the active public manifest", "mdtero-public/README.md");
  expectContains(publicReadme, "mdtero doctor` checks that `MDTERO_API_KEY` is available", "mdtero-public/README.md");
  expectContains(publicReadme, "For headless agents, create a fresh API key in Mdtero Account", "mdtero-public/README.md");
  expectContains(publicReadme, "clawhub install mdtero", "mdtero-public/README.md");
  expectContains(publicReadme, "`npx mdtero-install install openclaw` is intentionally unsupported.", "mdtero-public/README.md");
  expectContains(publicReadme, "Keyword discovery and API-key management stay in Mdtero Account.", "mdtero-public/README.md");
  expectContains(publicReadme, "OpenClaw keeps the dedicated route", "mdtero-public/README.md");
  expectContains(publicReadme, "Claude Code, Codex, Gemini CLI, Hermes Agent, and OpenCode stay on the npm-first install path via `npx mdtero-install install <target>`.", "mdtero-public/README.md");
  expectContains(publicReadme, "https://github.com/JonbinC/doi2md", "mdtero-public/README.md");
  expectContains(publicReadme, "Mdtero does not yet publish an active public MCP installer flow through `mdtero-install`.", "mdtero-public/README.md");
  expectContains(publicReadme, "Desktop preview artifacts remain a deferred archive / preview surface", "mdtero-public/README.md");

  expectContains(installReadme, "npx mdtero-install show", "mdtero-public/install/README.md");
  expectContains(installReadme, "npx mdtero-install version", "mdtero-public/install/README.md");
  expectContains(installReadme, "npx mdtero-install install codex", "mdtero-public/install/README.md");
  expectContains(installReadme, "npx mdtero-install install claude_code", "mdtero-public/install/README.md");
  expectContains(installReadme, "npx mdtero-install install gemini_cli", "mdtero-public/install/README.md");
  expectContains(installReadme, "npx mdtero-install install hermes", "mdtero-public/install/README.md");
  expectContains(installReadme, "npx mdtero-install install opencode", "mdtero-public/install/README.md");
  expectContains(installReadme, "mdtero-install install <target>` writes the Mdtero skill bundle", "mdtero-public/install/README.md");
  expectContains(installReadme, "For a headless agent, create a fresh API key in Mdtero Account", "mdtero-public/install/README.md");
  expectContains(installReadme, "https://github.com/JonbinC/doi2md", "mdtero-public/install/README.md");
  expectContains(installReadme, "clawhub install mdtero", "mdtero-public/install/README.md");
  expectContains(installReadme, "`npx mdtero-install install openclaw` is intentionally unsupported.", "mdtero-public/install/README.md");
  expectContains(installReadme, "Keyword discovery and API-key management stay in Mdtero Account.", "mdtero-public/install/README.md");
  expectContains(installReadme, "https://mdtero.com/install/manifest.json", "mdtero-public/install/README.md");
  expectContains(installReadme, "https://api.mdtero.com/skills/install.md", "mdtero-public/install/README.md");
  expectContains(installReadme, "Hermes Agent supports MCP through its own `~/.hermes/config.yaml` `mcp_servers` configuration", "mdtero-public/install/README.md");
  expectContains(installReadme, "Mdtero does not currently expose a maintained public MCP installer flow", "mdtero-public/install/README.md");

  expectContains(openclawInstallReadme, "The website-led install manifest at `https://mdtero.com/install/manifest.json` is the canonical public release seam.", "mdtero-public/helper/openclaw/INSTALL.md");
  expectContains(openclawInstallReadme, "OpenClaw stays on the dedicated `clawhub install mdtero` path", "mdtero-public/helper/openclaw/INSTALL.md");
  expectContains(openclawInstallReadme, "Claude Code, Codex, Gemini CLI, Hermes Agent, and OpenCode", "mdtero-public/helper/openclaw/INSTALL.md");
  expectContains(openclawInstallReadme, "Do not present MCP as part of the OpenClaw/ClawHub install", "mdtero-public/helper/openclaw/INSTALL.md");
  expectContains(openclawInstallReadme, "Do not use `npx mdtero-install install openclaw`", "mdtero-public/helper/openclaw/INSTALL.md");
  expectContains(openclawInstallReadme, "GitHub Releases and the public `doi2md` repository only mirror the website-led release chain.", "mdtero-public/helper/openclaw/INSTALL.md");
  expectContains(openclawInstallReadme, "npm --prefix mdtero-frontend run test:launchability-proof", "mdtero-public/helper/openclaw/INSTALL.md");
  expectContains(openclawInstallReadme, "npx mdtero-install version", "mdtero-public/helper/openclaw/INSTALL.md");

  expectContains(desktopReadme, "archived public mirror surface", "mdtero-public/desktop/README.md");
  expectContains(desktopReadme, "not part of the current extension-and-CLI launch path", "mdtero-public/desktop/README.md");
  expectContains(desktopReadme, "unsigned by default", "mdtero-public/desktop/README.md");
  expectContains(desktopReadme, "not notarized", "mdtero-public/desktop/README.md");
  expectContains(desktopReadme, "no auto-update yet", "mdtero-public/desktop/README.md");

  for (const [label, content] of [["mdtero-public/README.md", publicReadme], ["mdtero-public/install/README.md", installReadme]]) {
    expectMissing(content, "signed production installer", label);
    expectMissing(content, "notarized production release", label);
    expectMissing(content, "desktop preview is the recommended path", label);
  }
});

test("public package metadata stays aligned with the installer contract", async () => {
  const [pkg, manifest] = await Promise.all([readJson(PUBLIC_PACKAGE_PATH), readJson(MANIFEST_PATH)]);

  assert.equal(pkg.name, manifest.cli.packageName);
  assert.equal(pkg.description, "Unified installer for Mdtero agent skill bundles across Claude Code, Codex, Gemini CLI, Hermes Agent, OpenCode, and OpenClaw guidance.");
  assert.deepEqual(pkg.files, ["bin", "install", "skills"]);
  assert.equal(pkg.scripts?.["test:install"], "node --test tests/mdtero-install.test.mjs tests/opencode-install.test.mjs");
  assert.equal(pkg.scripts?.["test:public-contract"], "node --test tests/public-contract-truth.test.mjs tests/mdtero-install.test.mjs tests/opencode-install.test.mjs");
  for (const keyword of ["mdtero", "installer", "claude-code", "codex", "gemini-cli", "hermes-agent", "opencode", "openclaw"]) {
    assert.ok(pkg.keywords?.includes(keyword), `mdtero-public/package.json keywords must include ${keyword}`);
  }
});

test("active site package exposes the dashboard test and build gates", async () => {
  const pkg = await readJson(FRONTEND_PACKAGE_PATH);

  assert.equal(pkg.name, "nextmdtero");
  assert.equal(pkg.private, true);
  assert.equal(pkg.scripts?.test, "vitest run");
  assert.match(pkg.scripts?.build ?? "", /vite build/);
  assert.match(pkg.scripts?.build ?? "", /vitepress build docs/);
});
