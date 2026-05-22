import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const TEST_DIR = dirname(fileURLToPath(import.meta.url));
const PUBLIC_ROOT = join(TEST_DIR, "..");
const REPO_ROOT = join(PUBLIC_ROOT, "..");
const FRONTEND_ROOT = join(REPO_ROOT, "nextmdtero");

const MANIFEST_PATH = join(PUBLIC_ROOT, "install", "manifest.json");
const PUBLIC_README_PATH = join(PUBLIC_ROOT, "README.md");
const INSTALL_README_PATH = join(PUBLIC_ROOT, "install", "README.md");
const PUBLIC_PACKAGE_PATH = join(PUBLIC_ROOT, "package.json");
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

function expectMissing(content, forbidden, label) {
  assert.doesNotMatch(
    content,
    new RegExp(escapeRegExp(forbidden), "i"),
    `${label} must not include: ${forbidden}`
  );
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

test("install manifest stays mirrored and names Python as the runtime truth", async () => {
  const [manifest, siteManifest] = await Promise.all([readJson(MANIFEST_PATH), readJson(SITE_MANIFEST_PATH)]);

  assert.deepEqual(manifest, siteManifest, "public install manifest must stay mirrored with the site manifest");
  assert.equal(manifest.manifestUrl, "https://mdtero.com/install/manifest.json");
  assert.equal(manifest.installScriptUrl, "https://mdtero.com/install.sh");
  assert.equal(manifest.quickInstallCommand, "curl -Ls https://mdtero.com/install.sh | sh -s -- --agent <target>");
  assert.equal(manifest.cli?.packageName, "mdtero");
  assert.equal(manifest.cli?.packageVersion, "0.2.0a4");
  assert.equal(manifest.cli?.packageManager, "uv");
  assert.equal(manifest.cli?.runtimeInstallCommand, "uv tool install git+https://github.com/JonbinC/doi2md.git");
  assert.equal(manifest.cli?.skillInstallCommand, "mdtero agent install --target <target>");
  assert.equal(manifest.cli?.legacyNpmCompatibility?.npxCommand, "npx mdtero-install");
  assert.equal(manifest.releaseTruth?.boundaries?.pythonRuntimeSourceOfTruth, "cli.runtimeInstallCommand");
  assert.equal(manifest.releaseTruth?.boundaries?.agentSkillInstallSourceOfTruth, "targets[*].skillInstallCommand except openclaw");
  assert.deepEqual(manifest.targets.map((target) => target.target), ["openclaw", "claude_code", "codex", "gemini_cli", "hermes", "opencode"]);
  for (const target of manifest.targets.filter((item) => item.target !== "openclaw")) {
    assert.equal(target.installCommand, `curl -Ls https://mdtero.com/install.sh | sh -s -- --agent ${target.target}`);
    assert.equal(target.skillInstallCommand, `mdtero agent install --target ${target.target}`);
  }
});

test("public install docs present uv and Python agent install as the default path", async () => {
  const [publicReadme, installReadme] = await Promise.all([readMarkdown(PUBLIC_README_PATH), readMarkdown(INSTALL_README_PATH)]);

  for (const [label, content] of [
    ["README.md", publicReadme],
    ["install/README.md", installReadme]
  ]) {
    expectContains(content, "uv tool install git+https://github.com/JonbinC/doi2md.git", label);
    expectContains(content, "mdtero setup", label);
    expectContains(content, "mdtero agent install --target codex", label);
    expectContains(content, "mdtero project import-bib references.bib", label);
    expectContains(content, "mdtero project parse --wait", label);
    expectContains(content, "mdtero zotero import", label);
    expectContains(content, "mdtero parse --file paper.pdf", label);
    expectContains(content, "mdtero mcp serve", label);
    expectContains(content, "clawhub install mdtero", label);
    expectMissing(content, "npm install -g mdtero-install@0.1.8", label);
    expectMissing(content, "npx --yes mdtero-install install", label);
    expectMissing(content, "not implemented in the npm CLI yet", label);
  }

  expectContains(publicReadme, "The old npm package `mdtero-install` is now only a legacy compatibility installer.", "README.md");
  expectContains(installReadme, "The legacy npm package `mdtero-install` remains available only as a compatibility path", "install/README.md");
});

test("legacy npm package metadata remains scoped to compatibility install only", async () => {
  const pkg = await readJson(PUBLIC_PACKAGE_PATH);

  assert.equal(pkg.name, "mdtero-install");
  assert.equal(pkg.description, "Compatibility installer for Mdtero agent skill bundles. The Mdtero runtime CLI is the Python package.");
  assert.equal(pkg.bin?.["mdtero-install"], "bin/mdtero-install");
  assert.equal(pkg.bin?.mdtero, undefined);
  assert.deepEqual(pkg.files, ["bin", "install", "install.sh", "skills"]);
  assert.equal(pkg.scripts?.["test:install"], "node --test tests/mdtero-install.test.mjs tests/opencode-install.test.mjs");
  assert.equal(
    pkg.scripts?.["test:public-contract"],
    "node --test tests/public-contract-truth.test.mjs tests/mdtero-install.test.mjs tests/opencode-install.test.mjs"
  );
  for (const keyword of ["mdtero", "installer", "claude-code", "codex", "gemini-cli", "hermes-agent", "opencode", "openclaw"]) {
    assert.ok(pkg.keywords?.includes(keyword), `package keywords must include ${keyword}`);
  }
});
