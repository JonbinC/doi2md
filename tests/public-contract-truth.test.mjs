import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const TEST_DIR = dirname(fileURLToPath(import.meta.url));
const PUBLIC_ROOT = join(TEST_DIR, "..");
const REPO_ROOT = join(PUBLIC_ROOT, "..");
const FRONTEND_ROOT = join(REPO_ROOT, "mdtero-frontend");

const MANIFEST_PATH = join(PUBLIC_ROOT, "install", "manifest.json");
const ROOT_README_PATH = join(REPO_ROOT, "README.md");
const PUBLIC_README_PATH = join(PUBLIC_ROOT, "README.md");
const DESKTOP_README_PATH = join(PUBLIC_ROOT, "desktop", "README.md");
const INSTALL_README_PATH = join(PUBLIC_ROOT, "install", "README.md");
const PUBLIC_PACKAGE_PATH = join(PUBLIC_ROOT, "package.json");
const FRONTEND_PACKAGE_PATH = join(FRONTEND_ROOT, "package.json");
const SITE_MANIFEST_PATH = join(FRONTEND_ROOT, "apps", "site-next", "public", "install", "manifest.json");

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
    `${label} must not include release-maturity overclaim: ${forbidden}`
  );
}

test("install manifest stays the canonical audited agent target contract", async () => {
  const [manifest, siteManifest] = await Promise.all([readJson(MANIFEST_PATH), readJson(SITE_MANIFEST_PATH)]);

  assert.deepEqual(manifest, siteManifest, "mdtero-public/install/manifest.json must stay mirrored with the site manifest");
  assert.equal(manifest.manifestUrl, "https://mdtero.com/install/manifest.json", "manifest must point to the canonical public manifest URL");
  assert.equal(manifest.cli?.npxCommand, "npx mdtero-install", "manifest must expose the unified install CLI command");
  assert.equal(
    manifest.accountBoundaryNote,
    "Keyword discovery and API-key management stay in Mdtero Account. Use the agent install for parse, translate, task-status, and download workflows.",
    "manifest must keep the Mdtero Account boundary note"
  );
  assert.deepEqual(
    manifest.targets.map((target) => target.target),
    ["openclaw", "claude_code", "codex", "gemini_cli"],
    "manifest must keep the canonical agent target list"
  );
  assert.deepEqual(
    manifest.targets.map((target) => target.installCommand),
    [
      "clawhub install mdtero",
      "npx mdtero-install install claude_code",
      "npx mdtero-install install codex",
      "npx mdtero-install install gemini_cli"
    ],
    "manifest install commands must stay aligned with the canonical target list"
  );
});

test("public markdown surfaces keep the same preview and install boundary truth", async () => {
  const [rootReadme, publicReadme, desktopReadme, installReadme] = await Promise.all([
    readMarkdown(ROOT_README_PATH),
    readMarkdown(PUBLIC_README_PATH),
    readMarkdown(DESKTOP_README_PATH),
    readMarkdown(INSTALL_README_PATH)
  ]);

  expectContains(rootReadme, "Mdtero turns papers into reusable Markdown research packages.", "README.md");
  expectContains(rootReadme, "Keyword discovery and API-key management stay in Mdtero Account.", "README.md");
  expectContains(rootReadme, "The desktop preview is not a signed, notarized, or auto-update-ready production release yet.", "README.md");
  expectContains(rootReadme, "npx mdtero-install show", "README.md");
  expectContains(rootReadme, "npx mdtero-install install codex", "README.md");
  expectContains(rootReadme, "npx mdtero-install install claude_code", "README.md");
  expectContains(rootReadme, "npx mdtero-install install gemini_cli", "README.md");
  expectContains(rootReadme, "clawhub install mdtero", "README.md");

  expectContains(publicReadme, "Mdtero turns papers into reusable Markdown research packages.", "mdtero-public/README.md");
  expectContains(publicReadme, "npx mdtero-install show", "mdtero-public/README.md");
  expectContains(publicReadme, "npx mdtero-install install codex", "mdtero-public/README.md");
  expectContains(publicReadme, "npx mdtero-install install claude_code", "mdtero-public/README.md");
  expectContains(publicReadme, "npx mdtero-install install gemini_cli", "mdtero-public/README.md");
  expectContains(publicReadme, "clawhub install mdtero", "mdtero-public/README.md");
  expectContains(publicReadme, "Keyword discovery and API-key management stay in Mdtero Account.", "mdtero-public/README.md");

  expectContains(desktopReadme, "preview release", "mdtero-public/desktop/README.md");
  expectContains(desktopReadme, "unsigned by default", "mdtero-public/desktop/README.md");
  expectContains(desktopReadme, "not notarized", "mdtero-public/desktop/README.md");
  expectContains(desktopReadme, "no auto-update yet", "mdtero-public/desktop/README.md");

  expectContains(installReadme, "npx mdtero-install show", "mdtero-public/install/README.md");
  expectContains(installReadme, "npx mdtero-install install codex", "mdtero-public/install/README.md");
  expectContains(installReadme, "npx mdtero-install install claude_code", "mdtero-public/install/README.md");
  expectContains(installReadme, "npx mdtero-install install gemini_cli", "mdtero-public/install/README.md");
  expectContains(installReadme, "clawhub install mdtero", "mdtero-public/install/README.md");
  expectContains(installReadme, "Keyword discovery and API-key management stay in Mdtero Account.", "mdtero-public/install/README.md");
  expectContains(installReadme, "https://mdtero.com/install/manifest.json", "mdtero-public/install/README.md");
  expectContains(installReadme, "https://api.mdtero.com/skills/install.md", "mdtero-public/install/README.md");

  for (const [label, content] of [
    ["README.md", rootReadme],
    ["mdtero-public/README.md", publicReadme],
    ["mdtero-public/desktop/README.md", desktopReadme],
    ["mdtero-public/install/README.md", installReadme]
  ]) {
    expectMissing(content, "signed production installer", label);
    expectMissing(content, "signed production release", label);
    expectMissing(content, "notarized production release", label);
    expectMissing(content, "auto-update ready", label);
  }
});

test("public package metadata stays aligned with the canonical installer contract", async () => {
  const [pkg, manifest] = await Promise.all([readJson(PUBLIC_PACKAGE_PATH), readJson(MANIFEST_PATH)]);

  assert.equal(pkg.name, manifest.cli.packageName, "mdtero-public/package.json package name must match the manifest cli package");
  assert.equal(
    pkg.description,
    "Unified installer for Mdtero agent skill bundles across Claude Code, Codex, Gemini CLI, and OpenClaw guidance.",
    "mdtero-public/package.json description must describe the unified installer surface"
  );
  assert.deepEqual(
    pkg.files,
    ["bin", "install", "skills"],
    "mdtero-public/package.json must publish the full install docs, manifest, and skill bundle surface"
  );
  assert.equal(pkg.scripts?.["test:install"], "node --test tests/mdtero-install.test.mjs", "test:install must stay focused on the installer CLI contract");
  assert.equal(
    pkg.scripts?.["test:public-contract"],
    "node --test tests/public-contract-truth.test.mjs tests/mdtero-install.test.mjs",
    "mdtero-public/package.json must expose the combined public proof command"
  );

  for (const keyword of ["mdtero", "installer", "claude-code", "codex", "gemini-cli", "openclaw"]) {
    assert.ok(pkg.keywords?.includes(keyword), `mdtero-public/package.json keywords must include ${keyword}`);
  }
});

test("frontend maintainer commands expose both seam-localized and aggregate launchability proof wiring", async () => {
  const pkg = await readJson(FRONTEND_PACKAGE_PATH);
  const publicCommand = pkg.scripts?.["test:public-contract"];
  const launchabilityProofCommand = pkg.scripts?.["test:launchability-proof"];

  assert.equal(typeof publicCommand, "string", "mdtero-frontend/package.json must define scripts.test:public-contract");
  assert.equal(
    typeof launchabilityProofCommand,
    "string",
    "mdtero-frontend/package.json must define scripts.test:launchability-proof"
  );
  assert.match(
    launchabilityProofCommand,
    /npm run test:public-contract/,
    "test:launchability-proof must re-run test:public-contract instead of duplicating its underlying files"
  );
  assert.match(
    launchabilityProofCommand,
    /npm run test:desktop-preview-contract/,
    "test:launchability-proof must re-run test:desktop-preview-contract"
  );
  assert.match(
    launchabilityProofCommand,
    /npm run test:release-workflow-contract/,
    "test:launchability-proof must re-run test:release-workflow-contract"
  );

  assert.match(
    publicCommand,
    /tests\/marketing-routes\.test\.tsx/,
    "test:public-contract must run the site marketing contract test"
  );
  assert.match(
    publicCommand,
    /tests\/agent-installs\.test\.ts/,
    "test:public-contract must run the site agent install contract test"
  );
  assert.match(
    publicCommand,
    /node --test \.\.\/mdtero-public\/tests\/public-contract-truth\.test\.mjs \.\.\/mdtero-public\/tests\/mdtero-install\.test\.mjs/,
    "test:public-contract must run the public markdown and CLI contract checks together"
  );
});
