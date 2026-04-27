import assert from "node:assert/strict";
import { mkdtemp, readFile, stat } from "node:fs/promises";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const PROJECT_ROOT = fileURLToPath(new URL("..", import.meta.url));
const CLI_PATH = join(PROJECT_ROOT, "bin", "mdtero-install.mjs");
const CLI_WRAPPER_PATH = join(PROJECT_ROOT, "bin", "mdtero-install");

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

test("install writes the mdtero skill bundle into a codex workspace", async () => {
  const root = await mkdtemp(join(tmpdir(), "mdtero-install-"));

  const manifest = {
    version: 1,
    manifestUrl: "http://127.0.0.1/install/manifest.json",
    helperCommand: "mdtero",
    helperInstallerUrl: "https://api.mdtero.com/helpers/install_mdtero_helper.sh",
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

  const server = createServer((request, response) => {
    if (request.url === "/install/manifest.json") {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(manifest));
      return;
    }
    response.writeHead(404);
    response.end("not found");
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));

  try {
    const address = server.address();
    assert.ok(address && typeof address === "object");
    const manifestUrl = `http://127.0.0.1:${address.port}/install/manifest.json`;

    const completed = await runNode(
      [CLI_PATH, "install", "codex", "--root", root, "--manifest-url", manifestUrl],
      { cwd: PROJECT_ROOT }
    );

    assert.equal(completed.code, 0, completed.stderr);
    const skillPath = join(root, ".codex", "skills", "mdtero", "SKILL.md");
    const content = await readFile(skillPath, "utf8");
    assert.match(content, /name: mdtero/);
    assert.match(completed.stdout, /Installed Mdtero skill/);
  } finally {
    server.close();
  }
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
});

test("bin entry stays executable for npm-run installs", async () => {
  const stats = await stat(CLI_WRAPPER_PATH);
  assert.ok((stats.mode & 0o111) !== 0, "mdtero-install CLI must keep its executable bit");
});

test("show falls back to the bundled manifest when the remote manifest is unavailable", async () => {
  const server = createServer((request, response) => {
    if (request.url === "/missing.json") {
      response.writeHead(404, { "content-type": "application/json" });
      response.end(JSON.stringify({ error: "missing" }));
      return;
    }
    response.writeHead(404);
    response.end("not found");
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));

  try {
    const address = server.address();
    assert.ok(address && typeof address === "object");
    const missingManifestUrl = `http://127.0.0.1:${address.port}/missing.json`;

    const completed = await runNode([CLI_PATH, "show"], {
      cwd: PROJECT_ROOT,
      env: {
        ...process.env,
        MDTERO_INSTALL_MANIFEST_URL: missingManifestUrl
      }
    });

    assert.equal(completed.code, 0, completed.stderr);
    assert.match(completed.stdout, /Mdtero install manifest v1/);
    assert.match(completed.stdout, /npx mdtero-install/);
  } finally {
    server.close();
  }
});

test("install rejects openclaw because it stays on the dedicated ClawHub path", async () => {
  const completed = await runNode([CLI_PATH, "install", "openclaw"], {
    cwd: PROJECT_ROOT
  });

  assert.equal(completed.code, 1);
  assert.match(completed.stderr, /OpenClaw uses clawhub install mdtero/);
});
