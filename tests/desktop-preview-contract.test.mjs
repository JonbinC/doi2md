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

test("desktop archive docs stay aligned with the mirrored installer ledger", async () => {
  const [upstreamManifest, mirroredManifest, desktopReadme, desktopDoc] = await Promise.all([
    readJson(UPSTREAM_MANIFEST_PATH),
    readJson(MIRRORED_MANIFEST_PATH),
    readText(DESKTOP_README_PATH),
    readText(DESKTOP_DOC_PATH)
  ]);

  assert.deepEqual(mirroredManifest, upstreamManifest, "desktop archive mirror must stay faithful to the upstream installer ledger");
  expectContains(desktopReadme, "archived public mirror surface", "mdtero-public/desktop/README.md");
  expectContains(desktopReadme, "not part of the current extension-and-CLI launch path", "mdtero-public/desktop/README.md");
  expectContains(desktopReadme, upstreamManifest.version, "mdtero-public/desktop/README.md");
  expectContains(desktopDoc, "Desktop is no longer part of the current public launch path.", "mdtero-public/docs/public/desktop-preview.md");
  expectContains(desktopDoc, upstreamManifest.version, "mdtero-public/docs/public/desktop-preview.md");
});

test("desktop archive keeps a dedicated seam-localized audit command but stays out of launchability", async () => {
  const pkg = await readJson(FRONTEND_PACKAGE_PATH);
  const desktopPreviewCommand = pkg.scripts?.["test:desktop-preview-contract"];
  const launchabilityProofCommand = pkg.scripts?.["test:launchability-proof"];

  assert.equal(typeof desktopPreviewCommand, "string");
  assert.match(desktopPreviewCommand, /node --test \.\.\/mdtero-public\/tests\/desktop-preview-contract\.test\.mjs/);
  assert.equal(typeof launchabilityProofCommand, "string");
  assert.doesNotMatch(launchabilityProofCommand, /desktop-preview-contract/);
});
