import assert from "node:assert/strict";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const PROJECT_ROOT = fileURLToPath(new URL("..", import.meta.url));
const CLI_PATH = join(PROJECT_ROOT, "bin", "mdtero-install.mjs");

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

test("install writes the mdtero skill bundle into an OpenCode workspace", async () => {
  const root = await mkdtemp(join(tmpdir(), "mdtero-opencode-install-"));

  const completed = await runNode([CLI_PATH, "install", "opencode", "--root", root], {
    cwd: PROJECT_ROOT,
    env: {
      ...process.env,
      MDTERO_INSTALL_MANIFEST_URL: "http://127.0.0.1:9/unavailable-manifest.json"
    }
  });

  assert.equal(completed.code, 0, completed.stderr);
  const skillPath = join(root, ".opencode", "skills", "mdtero", "SKILL.md");
  const content = await readFile(skillPath, "utf8");
  assert.match(content, /name: mdtero/);
  assert.match(completed.stdout, /Installed Mdtero skill for OpenCode/);
});
