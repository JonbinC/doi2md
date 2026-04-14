import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const TEST_DIR = dirname(fileURLToPath(import.meta.url));
const PUBLIC_ROOT = join(TEST_DIR, "..");
const REPO_ROOT = join(PUBLIC_ROOT, "..");
const FRONTEND_ROOT = join(REPO_ROOT, "mdtero-frontend");

const UPSTREAM_MANIFEST_PATH = join(FRONTEND_ROOT, "apps", "desktop", "installers", "manifest.json");
const MIRRORED_MANIFEST_PATH = join(PUBLIC_ROOT, "desktop", "releases", "installer-manifest.json");
const DESKTOP_README_PATH = join(PUBLIC_ROOT, "desktop", "README.md");
const DESKTOP_DOC_PATH = join(PUBLIC_ROOT, "docs", "public", "desktop-preview.md");
const FRONTEND_PACKAGE_PATH = join(FRONTEND_ROOT, "package.json");

async function readJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

async function readMarkdown(path) {
  return readFile(path, "utf8");
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function expectContains(content, expected, label) {
  assert.match(content, new RegExp(escapeRegExp(expected)), `${label} must include: ${expected}`);
}

function expectMissing(content, forbidden, label) {
  assert.doesNotMatch(content, new RegExp(escapeRegExp(forbidden), "i"), `${label} must not include: ${forbidden}`);
}

function getArtifactSets(manifest) {
  const installerArtifacts = manifest.artifacts.filter((artifact) => /\.(dmg|exe)$/i.test(artifact.fileName));
  const blockmapArtifacts = manifest.artifacts.filter((artifact) => artifact.fileName.endsWith(".blockmap"));
  return { installerArtifacts, blockmapArtifacts };
}

test("desktop preview public surfaces stay aligned with the upstream and mirrored installer manifests", async () => {
  const [upstreamManifest, mirroredManifest, desktopReadme, desktopDoc] = await Promise.all([
    readJson(UPSTREAM_MANIFEST_PATH),
    readJson(MIRRORED_MANIFEST_PATH),
    readMarkdown(DESKTOP_README_PATH),
    readMarkdown(DESKTOP_DOC_PATH)
  ]);

  assert.deepEqual(
    mirroredManifest,
    upstreamManifest,
    "desktop-release: mdtero-public/desktop/releases/installer-manifest.json must stay byte-for-byte faithful to the upstream installer ledger"
  );

  const { installerArtifacts, blockmapArtifacts } = getArtifactSets(upstreamManifest);

  assert.equal(installerArtifacts.length, 2, "desktop-installer: expected exactly two public preview installer classes (.dmg and .exe)");
  assert.ok(blockmapArtifacts.length >= 1, "desktop-installer: canonical ledger must keep .blockmap metadata for updater parity");

  for (const artifact of installerArtifacts) {
    expectContains(desktopReadme, artifact.fileName, "mdtero-public/desktop/README.md");
    expectContains(desktopDoc, artifact.fileName, "mdtero-public/docs/public/desktop-preview.md");
    expectContains(desktopReadme, artifact.publicFilePath, "mdtero-public/desktop/README.md");
    expectContains(desktopDoc, artifact.publicFilePath, "mdtero-public/docs/public/desktop-preview.md");
  }

  for (const artifact of blockmapArtifacts) {
    expectMissing(desktopReadme, artifact.fileName, "mdtero-public/desktop/README.md");
    expectMissing(desktopDoc, artifact.fileName, "mdtero-public/docs/public/desktop-preview.md");
  }

  expectContains(desktopReadme, upstreamManifest.version, "mdtero-public/desktop/README.md");
  expectContains(desktopDoc, upstreamManifest.version, "mdtero-public/docs/public/desktop-preview.md");
  expectContains(desktopReadme, "preview installer classes only", "mdtero-public/desktop/README.md");
  expectContains(desktopReadme, "not notarized", "mdtero-public/desktop/README.md");
  expectContains(desktopReadme, "no auto-update yet", "mdtero-public/desktop/README.md");
  expectContains(desktopDoc, "public preview", "mdtero-public/docs/public/desktop-preview.md");
  expectContains(desktopDoc, "signing, notarization, and auto-update are not part of this preview stage", "mdtero-public/docs/public/desktop-preview.md");

  expectMissing(desktopReadme, "portable preview bundle", "mdtero-public/desktop/README.md");
  expectMissing(desktopDoc, "portable preview bundle", "mdtero-public/docs/public/desktop-preview.md");
  expectMissing(desktopReadme, "notarized production release", "mdtero-public/desktop/README.md");
  expectMissing(desktopDoc, "notarized production release", "mdtero-public/docs/public/desktop-preview.md");
});

test("frontend exposes both the desktop seam proof and the aggregate launchability proof command", async () => {
  const pkg = await readJson(FRONTEND_PACKAGE_PATH);
  const command = pkg.scripts?.["test:desktop-preview-contract"];
  const launchabilityProofCommand = pkg.scripts?.["test:launchability-proof"];

  assert.equal(typeof command, "string", "desktop-release: mdtero-frontend/package.json must define scripts.test:desktop-preview-contract");
  assert.equal(
    typeof launchabilityProofCommand,
    "string",
    "desktop-release: mdtero-frontend/package.json must define scripts.test:launchability-proof"
  );
  assert.match(
    launchabilityProofCommand,
    /npm run test:desktop-preview-contract/,
    "desktop-release: test:launchability-proof must re-run test:desktop-preview-contract"
  );
  assert.match(
    launchabilityProofCommand,
    /npm run test:public-contract/,
    "desktop-release: test:launchability-proof must re-run test:public-contract"
  );
  assert.match(
    launchabilityProofCommand,
    /npm run test:release-workflow-contract/,
    "desktop-release: test:launchability-proof must re-run test:release-workflow-contract"
  );
  assert.match(
    command,
    /apps\/desktop\/tests\/desktop-installer\.test\.ts/,
    "desktop-installer: test:desktop-preview-contract must run the canonical installer ledger proof"
  );
  assert.match(
    command,
    /apps\/desktop\/tests\/desktop-release\.test\.ts/,
    "desktop-release: test:desktop-preview-contract must run the public mirror\/staging proof"
  );
  assert.match(
    command,
    /tests\/marketing-routes\.test\.tsx/,
    "guide route: test:desktop-preview-contract must run the guide parity proof"
  );
  assert.match(
    command,
    /node --test \.\.\/mdtero-public\/tests\/desktop-preview-contract\.test\.mjs/,
    "desktop-release: test:desktop-preview-contract must run the public desktop docs\/manifest audit"
  );
});
