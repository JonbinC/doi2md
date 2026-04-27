import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const TEST_DIR = dirname(fileURLToPath(import.meta.url));
const PUBLIC_ROOT = join(TEST_DIR, "..");
const REPO_ROOT = join(PUBLIC_ROOT, "..");
const FRONTEND_ROOT = join(REPO_ROOT, "mdtero-frontend");

const DEPLOY_WORKFLOW_PATH = join(FRONTEND_ROOT, ".github", "workflows", "deploy-site.yml");
const DESKTOP_WORKFLOW_PATH = join(FRONTEND_ROOT, ".github", "workflows", "build-desktop-installers.yml");
const DESKTOP_PACKAGE_PATH = join(FRONTEND_ROOT, "apps", "desktop", "package.json");
const RUNBOOK_PATH = join(FRONTEND_ROOT, "docs", "LAUNCH_RUNBOOK.md");
const RELEASE_CHAIN_PATH = join(FRONTEND_ROOT, "docs", "RELEASE_CHAIN.md");
const FRONTEND_PACKAGE_PATH = join(FRONTEND_ROOT, "package.json");

async function readText(path) {
  return readFile(path, "utf8");
}

async function readJson(path) {
  return JSON.parse(await readText(path));
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function expectContains(content, expected, label) {
  assert.match(content, new RegExp(escapeRegExp(expected)), `${label} must include: ${expected}`);
}

function expectMatches(content, pattern, label, message) {
  assert.match(content, pattern, `${label} ${message}`);
}

function expectMissing(content, pattern, message) {
  assert.doesNotMatch(content, pattern, message);
}

test("release-workflow: site deploy automation stays Vercel-only", async () => {
  const workflow = await readText(DEPLOY_WORKFLOW_PATH);

  expectContains(workflow, "name: Deploy Site to Vercel", "deploy-site.yml");
  expectMatches(workflow, /VERCEL_TOKEN:\s*\$\{\{\s*secrets\.VERCEL_TOKEN\s*\}\}/, "deploy-site.yml", "must keep Vercel token secret wiring");
  expectMatches(workflow, /vercel@[^\s]+\s+deploy --prebuilt --prod/, "deploy-site.yml", "must deploy the prebuilt Vercel artifact");
  expectMissing(workflow, /stage:public-installers|mirror:public-installer-manifest|doi2md|desktop\/releases/i, "deploy-site.yml must stay site-only automation");
});

test("release-workflow: deferred desktop CI stays build-and-upload only", async () => {
  const workflow = await readText(DESKTOP_WORKFLOW_PATH);

  expectContains(workflow, "name: Build Desktop Installers", "build-desktop-installers.yml");
  expectMatches(workflow, /package:installer:mac/, "build-desktop-installers.yml", "must build the mac installer");
  expectMatches(workflow, /package:installer:win/, "build-desktop-installers.yml", "must build the windows installer");
  expectMissing(workflow, /stage:public-installers|mirror:public-installer-manifest|publish|doi2md|deploy-site|vercel/i, "desktop CI must not publish public mirrors");
});

test("release-workflow: desktop package still exposes manual archive-maintenance commands", async () => {
  const pkg = await readJson(DESKTOP_PACKAGE_PATH);
  const scripts = pkg.scripts ?? {};

  assert.equal(scripts["write:installer-manifest"], "node ./scripts/write-installer-manifest.mjs");
  assert.equal(scripts["mirror:public-installer-manifest"], "npm run write:installer-manifest && node ./scripts/mirror-public-installer-manifest.mjs");
  assert.equal(scripts["stage:public-installers"], "node ./scripts/stage-public-installers.mjs");
});

test("release-workflow: maintainer docs keep desktop out of the active launch sequence", async () => {
  const [runbook, releaseChain] = await Promise.all([readText(RUNBOOK_PATH), readText(RELEASE_CHAIN_PATH)]);

  expectContains(runbook, "single authoritative release sequence", "LAUNCH_RUNBOOK.md");
  expectContains(runbook, "desktop preview is deferred and archived for the current launch cycle", "LAUNCH_RUNBOOK.md");
  expectContains(runbook, "active launch surfaces are the site, the public install manifest/docs, and the extension + CLI install flow", "LAUNCH_RUNBOOK.md");
  expectContains(releaseChain, "Desktop preview is a deferred archive surface, not an active launch surface", "RELEASE_CHAIN.md");
  expectContains(releaseChain, "desktop workflow and docs may still be maintained for archive fidelity", "RELEASE_CHAIN.md");
});

test("release-workflow: frontend exposes only the active launchability proof chain", async () => {
  const pkg = await readJson(FRONTEND_PACKAGE_PATH);
  const releaseWorkflowCommand = pkg.scripts?.["test:release-workflow-contract"];
  const desktopPreviewCommand = pkg.scripts?.["test:desktop-preview-contract"];
  const launchabilityProofCommand = pkg.scripts?.["test:launchability-proof"];

  assert.equal(typeof releaseWorkflowCommand, "string");
  assert.equal(typeof desktopPreviewCommand, "string");
  assert.equal(typeof launchabilityProofCommand, "string");
  assert.match(releaseWorkflowCommand, /node --test \.\.\/mdtero-public\/tests\/release-workflow-contract\.test\.mjs/);
  assert.match(desktopPreviewCommand, /node --test \.\.\/mdtero-public\/tests\/desktop-preview-contract\.test\.mjs/);
  assert.match(launchabilityProofCommand, /npm run test:public-contract/);
  assert.match(launchabilityProofCommand, /npm run test:release-workflow-contract/);
  assert.doesNotMatch(launchabilityProofCommand, /desktop-preview-contract/);
});
