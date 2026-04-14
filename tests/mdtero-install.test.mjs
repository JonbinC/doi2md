import assert from "node:assert/strict";
import { mkdtemp, readFile, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const PROJECT_ROOT = fileURLToPath(new URL("..", import.meta.url));
const CLI_PATH = join(PROJECT_ROOT, "bin", "mdtero-install.mjs");
const CLI_WRAPPER_PATH = join(PROJECT_ROOT, "bin", "mdtero-install");
const MANIFEST_PATH = join(PROJECT_ROOT, "install", "manifest.json");

function runNode(args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, args, {
      ...options,
      stdio: ["ignore", "pipe", "pipe"]
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += String(chunk);
    });
    child.stderr.on("data", (chunk) => {
      stderr += String(chunk);
    });
    child.on("error", reject);
    child.on("close", (code) => {
      resolve({ code, stdout, stderr });
    });
  });
}

function createManifestDataUrl(manifest) {
  return `data:application/json,${encodeURIComponent(JSON.stringify(manifest))}`;
}

test("install writes the mdtero skill bundle into a codex workspace", async () => {
  const root = await mkdtemp(join(tmpdir(), "mdtero-install-"));

  const manifest = {
    version: 1,
    manifestUrl: "http://127.0.0.1/install/manifest.json",
    installGuideUrl: "https://api.mdtero.com/skills/install.md",
    helperCommand: "mdtero",
    helperInstallerUrl: "https://api.mdtero.com/helpers/install_mdtero_helper.sh",
    accountBoundaryNote:
      "Keyword discovery and API-key management stay in Mdtero Account. Use the agent install for parse, translate, task-status, and download workflows.",
    cli: {
      packageName: "mdtero-install",
      npxCommand: "npx mdtero-install"
    },
    targets: [
      {
        target: "codex",
        label: "Codex",
        installCommand: "npx mdtero-install install codex",
        skillDirectory: ".codex/skills/mdtero"
      }
    ]
  };

  const completed = await runNode(
    [CLI_PATH, "install", "codex", "--root", root, "--manifest-url", createManifestDataUrl(manifest)],
    { cwd: PROJECT_ROOT }
  );

  assert.equal(completed.code, 0, completed.stderr);
  const skillPath = join(root, ".codex", "skills", "mdtero", "SKILL.md");
  const content = await readFile(skillPath, "utf8");
  assert.match(content, /name: mdtero/);
  assert.match(completed.stdout, /Installed Mdtero skill for Codex at /);
  assert.match(completed.stdout, /If local acquisition is needed, review and run: https:\/\/api\.mdtero\.com\/helpers\/install_mdtero_helper\.sh/);
});

test("package metadata stays publishable for the unified install entry", async () => {
  const packageJsonPath = join(PROJECT_ROOT, "package.json");
  const content = await readFile(packageJsonPath, "utf8");
  const pkg = JSON.parse(content);

  assert.equal(pkg.name, "mdtero-install");
  assert.equal(typeof pkg.version, "string");
  assert.match(pkg.version, /^\d+\.\d+\.\d+$/);
  assert.notEqual(pkg.private, true);
  assert.equal(pkg.bin?.["mdtero-install"], "bin/mdtero-install");
  assert.equal(pkg.publishConfig?.access, "public");
  assert.equal(pkg.repository?.type, "git");
  assert.match(pkg.repository?.url ?? "", /JonbinC\/doi2md/);
  assert.equal(pkg.homepage, "https://mdtero.com");
  assert.equal(
    pkg.scripts?.["test:public-contract"],
    "node --test tests/public-contract-truth.test.mjs tests/mdtero-install.test.mjs",
    "package metadata must expose the combined public contract proof command"
  );
});

test("bin entry stays executable for npm-run installs", async () => {
  const stats = await stat(CLI_WRAPPER_PATH);
  assert.ok((stats.mode & 0o111) !== 0, "mdtero-install CLI must keep its executable bit");
});

test("show prints the canonical manifest contract from the remote manifest", async () => {
  const manifest = JSON.parse(await readFile(MANIFEST_PATH, "utf8"));
  const completed = await runNode([CLI_PATH, "show", "--manifest-url", createManifestDataUrl(manifest)], {
    cwd: PROJECT_ROOT
  });

  assert.equal(completed.code, 0, completed.stderr);
  assert.match(completed.stdout, /Mdtero install manifest v1/);
  assert.match(completed.stdout, /Manifest URL: https:\/\/mdtero\.com\/install\/manifest\.json/);
  assert.match(completed.stdout, /Unified CLI: npx mdtero-install/);
  assert.match(
    completed.stdout,
    /OpenClaw: clawhub install mdtero[\s\S]*Claude Code: npx mdtero-install install claude_code[\s\S]*Codex: npx mdtero-install install codex[\s\S]*Gemini CLI: npx mdtero-install install gemini_cli/,
    "show output must list the canonical targets and commands in manifest order"
  );
  assert.doesNotMatch(completed.stdout, /fallback/i, "show should not mention fallback when the remote manifest is reachable");
});

test("show falls back to the bundled manifest when the remote manifest is unavailable", async () => {
  const completed = await runNode([CLI_PATH, "show"], {
    cwd: PROJECT_ROOT,
    env: {
      ...process.env,
      MDTERO_INSTALL_MANIFEST_URL: "http://127.0.0.1:9/missing.json"
    }
  });

  assert.equal(completed.code, 0, completed.stderr);
  assert.match(completed.stdout, /Mdtero install manifest v1/);
  assert.match(completed.stdout, /Manifest URL: https:\/\/mdtero\.com\/install\/manifest\.json/);
  assert.match(completed.stdout, /Unified CLI: npx mdtero-install/);
  assert.match(completed.stdout, /Notice: Using bundled manifest fallback after fetch failure:/);
  assert.match(completed.stdout, /OpenClaw: clawhub install mdtero/);
  assert.match(completed.stdout, /Claude Code: npx mdtero-install install claude_code/);
  assert.match(completed.stdout, /Codex: npx mdtero-install install codex/);
  assert.match(completed.stdout, /Gemini CLI: npx mdtero-install install gemini_cli/);
});

test("install rejects unsupported targets with a clear target-specific error", async () => {
  const completed = await runNode([CLI_PATH, "install", "unsupported"], {
    cwd: PROJECT_ROOT,
    env: {
      ...process.env,
      MDTERO_INSTALL_MANIFEST_URL: createManifestDataUrl(JSON.parse(await readFile(MANIFEST_PATH, "utf8")))
    }
  });

  assert.equal(completed.code, 1, "unsupported installs must fail closed");
  assert.match(completed.stderr, /Unsupported target: unsupported/);
});
