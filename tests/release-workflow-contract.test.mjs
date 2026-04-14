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
const PUBLIC_DESKTOP_README_PATH = join(PUBLIC_ROOT, "desktop", "README.md");
const PUBLIC_DESKTOP_DOC_PATH = join(PUBLIC_ROOT, "docs", "public", "desktop-preview.md");
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

test("release-workflow: site deploy automation stays Vercel-only and secret-backed", async () => {
  const workflow = await readText(DEPLOY_WORKFLOW_PATH);

  expectContains(workflow, "name: Deploy Site to Vercel", "deploy-site.yml");
  expectMatches(
    workflow,
    /VERCEL_TOKEN:\s*\$\{\{\s*secrets\.VERCEL_TOKEN\s*\}\}/,
    "deploy-site.yml",
    "must keep Vercel token secret wiring"
  );
  expectMatches(
    workflow,
    /VERCEL_ORG_ID:\s*\$\{\{\s*vars\.VERCEL_ORG_ID\s*\}\}/,
    "deploy-site.yml",
    "must keep Vercel org wiring"
  );
  expectMatches(
    workflow,
    /VERCEL_PROJECT_ID:\s*\$\{\{\s*vars\.VERCEL_PROJECT_ID\s*\}\}/,
    "deploy-site.yml",
    "must keep Vercel project wiring"
  );
  expectMatches(
    workflow,
    /vercel@[^\s]+\s+pull --yes --environment=production/,
    "deploy-site.yml",
    "must pull Vercel project settings before deployment"
  );
  expectMatches(
    workflow,
    /vercel@[^\s]+\s+build --prod/,
    "deploy-site.yml",
    "must build the Vercel deployment"
  );
  expectMatches(
    workflow,
    /vercel@[^\s]+\s+deploy --prebuilt --prod/,
    "deploy-site.yml",
    "must deploy the prebuilt Vercel artifact"
  );
  expectMissing(
    workflow,
    /stage:public-installers|mirror:public-installer-manifest|doi2md|desktop\/releases/i,
    "release-workflow: deploy-site.yml must stay site-only automation and must not publish desktop mirrors"
  );
});

test("release-workflow: desktop CI stays build-and-upload only", async () => {
  const workflow = await readText(DESKTOP_WORKFLOW_PATH);

  expectContains(workflow, "name: Build Desktop Installers", "build-desktop-installers.yml");
  expectMatches(
    workflow,
    /package:installer:mac/,
    "build-desktop-installers.yml",
    "must build the mac installer"
  );
  expectMatches(
    workflow,
    /package:installer:win/,
    "build-desktop-installers.yml",
    "must build the windows installer"
  );
  expectMatches(
    workflow,
    /actions\/upload-artifact@v\d+/,
    "build-desktop-installers.yml",
    "must upload build artifacts for maintainer retrieval"
  );
  expectMatches(
    workflow,
    /apps\/desktop\/installers\/manifest\.json/,
    "build-desktop-installers.yml",
    "must upload the installer manifest alongside artifacts"
  );
  expectMissing(
    workflow,
    /stage:public-installers|mirror:public-installer-manifest|publish|doi2md|deploy-site|vercel/i,
    "release-workflow: desktop CI must not be described as public mirroring automation"
  );
});

test("release-workflow: desktop maintainer scripts keep the manual manifest and staging seam exposed", async () => {
  const pkg = await readJson(DESKTOP_PACKAGE_PATH);
  const scripts = pkg.scripts ?? {};

  assert.equal(
    scripts["write:installer-manifest"],
    "node ./scripts/write-installer-manifest.mjs",
    "release-workflow: desktop package must expose a dedicated manual manifest refresh command"
  );
  assert.equal(
    scripts["mirror:public-installer-manifest"],
    "npm run write:installer-manifest && node ./scripts/mirror-public-installer-manifest.mjs",
    "release-workflow: desktop package must expose the public manifest mirror command"
  );
  assert.equal(
    scripts["stage:public-installers"],
    "node ./scripts/stage-public-installers.mjs",
    "release-workflow: desktop package must expose the public installer staging command"
  );
  assert.equal(
    scripts["package:preview"],
    "npm run build && node ./scripts/package-preview.mjs",
    "release-workflow: desktop package must keep the local preview packaging command"
  );
});

test("release-workflow: maintainer docs must state manifest-before-site ordering and manual desktop publication boundaries", async () => {
  const [runbook, releaseChain] = await Promise.all([readText(RUNBOOK_PATH), readText(RELEASE_CHAIN_PATH)]);

  expectContains(runbook, "single authoritative release sequence", "LAUNCH_RUNBOOK.md");
  expectContains(runbook, "deploy-site.yml` deploys the site to Vercel", "LAUNCH_RUNBOOK.md");
  expectContains(runbook, "build-desktop-installers.yml` builds preview desktop installers and uploads CI artifacts only", "LAUNCH_RUNBOOK.md");
  expectContains(runbook, "refreshing installer metadata, mirroring installer metadata into the public repo, staging public installer binaries, mirroring public docs/assets, and publishing `JonbinC/doi2md`", "LAUNCH_RUNBOOK.md");
  expectContains(runbook, "Refresh the installer manifest before any site or public-doc update", "LAUNCH_RUNBOOK.md");
  expectContains(runbook, "apps/site-next/app/guide/page.tsx` reads `apps/desktop/installers/manifest.json`", "LAUNCH_RUNBOOK.md");
  expectContains(runbook, "npm run mirror:public-installer-manifest --workspace=@mdtero/desktop", "LAUNCH_RUNBOOK.md");
  expectContains(runbook, "npm run stage:public-installers --workspace=@mdtero/desktop", "LAUNCH_RUNBOOK.md");
  expectContains(runbook, "do not treat site deployment as valid release proof until the manifest refresh in Step 3 is already complete", "LAUNCH_RUNBOOK.md");

  expectContains(releaseChain, "build-desktop-installers.yml` is **automated build/upload only**", "RELEASE_CHAIN.md");
  expectContains(releaseChain, "installer manifest refresh, public staging, doc mirroring, and public repo publication remain **manual maintainer work**", "RELEASE_CHAIN.md");
  expectContains(releaseChain, "manifest refresh must happen before site/public surfaces advertise new installer names", "RELEASE_CHAIN.md");
});

test("release-workflow: frontend exposes dedicated release-workflow and aggregate launchability proof commands", async () => {
  const pkg = await readJson(FRONTEND_PACKAGE_PATH);
  const releaseWorkflowCommand = pkg.scripts?.["test:release-workflow-contract"];
  const launchabilityProofCommand = pkg.scripts?.["test:launchability-proof"];

  assert.equal(
    typeof releaseWorkflowCommand,
    "string",
    "release-workflow: mdtero-frontend/package.json must define scripts.test:release-workflow-contract"
  );
  assert.match(
    releaseWorkflowCommand,
    /node --test \.\.\/mdtero-public\/tests\/release-workflow-contract\.test\.mjs/,
    "release-workflow: test:release-workflow-contract must run the seam-localized release workflow audit"
  );

  assert.equal(
    typeof launchabilityProofCommand,
    "string",
    "release-workflow: mdtero-frontend/package.json must define scripts.test:launchability-proof"
  );
  assert.match(
    launchabilityProofCommand,
    /npm run test:desktop-preview-contract/,
    "release-workflow: test:launchability-proof must re-run the desktop preview proof command"
  );
  assert.match(
    launchabilityProofCommand,
    /npm run test:public-contract/,
    "release-workflow: test:launchability-proof must re-run the public contract proof command"
  );
  assert.match(
    launchabilityProofCommand,
    /npm run test:release-workflow-contract/,
    "release-workflow: test:launchability-proof must re-run the release-workflow proof command"
  );
});
