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
const MDTERO_CLI_PATH = join(PROJECT_ROOT, "bin", "mdtero.mjs");
const MDTERO_WRAPPER_PATH = join(PROJECT_ROOT, "bin", "mdtero");
const PACKAGE_JSON_PATH = join(PROJECT_ROOT, "package.json");

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

test("install writes the mdtero skill bundle into a Hermes workspace", async () => {
  const root = await mkdtemp(join(tmpdir(), "mdtero-hermes-install-"));

  const completed = await runNode([CLI_PATH, "install", "hermes", "--root", root], {
    cwd: PROJECT_ROOT,
    env: {
      ...process.env,
      MDTERO_INSTALL_MANIFEST_URL: "http://127.0.0.1:9/unavailable-manifest.json"
    }
  });

  assert.equal(completed.code, 0, completed.stderr);
  const skillPath = join(root, ".hermes", "skills", "mdtero", "SKILL.md");
  const content = await readFile(skillPath, "utf8");
  assert.match(content, /name: mdtero/);
  assert.match(completed.stdout, /Installed Mdtero skill for Hermes Agent/);
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
  assert.equal(pkg.bin?.mdtero, "bin/mdtero");
  assert.equal(pkg.publishConfig?.access, "public");
  assert.equal(pkg.repository?.type, "git");
  assert.match(pkg.repository?.url ?? "", /JonbinC\/doi2md/);
  assert.equal(pkg.homepage, "https://mdtero.com");
});

test("bin entry stays executable for npm-run installs", async () => {
  const stats = await stat(CLI_WRAPPER_PATH);
  assert.ok((stats.mode & 0o111) !== 0, "mdtero-install CLI must keep its executable bit");
  const mdteroStats = await stat(MDTERO_WRAPPER_PATH);
  assert.ok((mdteroStats.mode & 0o111) !== 0, "mdtero CLI must keep its executable bit");
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

test("mdtero CLI supports version, login, and doctor setup flow", async () => {
  const root = await mkdtemp(join(tmpdir(), "mdtero-cli-"));
  const envFile = join(root, ".env");
  const pkg = JSON.parse(await readFile(PACKAGE_JSON_PATH, "utf8"));

  const version = await runNode([MDTERO_CLI_PATH, "--version"], { cwd: PROJECT_ROOT });
  assert.equal(version.code, 0, version.stderr);
  assert.equal(version.stdout, `${pkg.version}\n`);

  const login = await runNode([MDTERO_CLI_PATH, "login", "--api-key", "test-key", "--config-file", envFile], { cwd: PROJECT_ROOT });
  assert.equal(login.code, 0, login.stderr);
  assert.match(login.stdout, /Saved MDTERO_API_KEY/);
  assert.equal(await readFile(envFile, "utf8"), 'MDTERO_API_KEY="test-key"\n');

  const doctor = await runNode([MDTERO_CLI_PATH, "doctor", "--config-file", envFile], { cwd: PROJECT_ROOT });
  assert.equal(doctor.code, 0, doctor.stderr);
  assert.match(doctor.stdout, new RegExp(`Mdtero CLI: ${pkg.version.replaceAll(".", "\\.")}`));
  assert.match(doctor.stdout, /MDTERO_API_KEY: set/);

  const setup = await runNode([MDTERO_CLI_PATH, "setup"], { cwd: PROJECT_ROOT });
  assert.equal(setup.code, 0, setup.stderr);
  assert.match(setup.stdout, /Run mdtero login to open Mdtero Account in your browser/);
});

test("mdtero CLI explains API-key setup for discover commands", async () => {
  const completed = await runNode([MDTERO_CLI_PATH, "discover", "10.48550/arXiv.1706.03762"], { cwd: PROJECT_ROOT });

  assert.equal(completed.code, 0, completed.stderr);
  assert.match(completed.stdout, /is not implemented in the npm CLI yet/i);
  assert.match(completed.stdout, /Supported today: mdtero login, mdtero doctor, mdtero setup, mdtero version\./);
  assert.match(completed.stdout, /mdtero login --api-key/);
});

test("mdtero CLI can create a parse task with an API key", async () => {
  const server = createServer((request, response) => {
    if (request.method === "POST" && request.url === "/tasks/parse") {
      assert.equal(request.headers.authorization, "ApiKey cli-key");
      let body = "";
      request.setEncoding("utf8");
      request.on("data", (chunk) => {
        body += chunk;
      });
      request.on("end", () => {
        assert.equal(body, JSON.stringify({ input: "10.48550/arXiv.1706.03762" }));
        response.writeHead(200, { "content-type": "application/json" });
        response.end(JSON.stringify({ task_id: "task-parse-1", status: "queued" }));
      });
      return;
    }
    response.writeHead(404);
    response.end("not found");
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));

  try {
    const address = server.address();
    assert.ok(address && typeof address === "object");
    const completed = await runNode([MDTERO_CLI_PATH, "parse", "10.48550/arXiv.1706.03762"], {
      cwd: PROJECT_ROOT,
      env: {
        ...process.env,
        MDTERO_API_KEY: "cli-key",
        MDTERO_API_URL: `http://127.0.0.1:${address.port}`,
      },
    });

    assert.equal(completed.code, 0, completed.stderr);
    assert.match(completed.stdout, /Created parse task: task-parse-1/);
    assert.match(completed.stdout, /Initial status: queued/);
    assert.match(completed.stdout, /Next: mdtero status task-parse-1/);
  } finally {
    server.close();
  }
});

test("mdtero CLI can inspect task status with an API key", async () => {
  const server = createServer((request, response) => {
    if (request.method === "GET" && request.url === "/tasks/task-123") {
      assert.equal(request.headers.authorization, "ApiKey cli-key");
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({
        task_id: "task-123",
        status: "succeeded",
        task_kind: "parse",
        input_summary: "10.48550/arXiv.1706.03762",
        stage: "completed",
        created_at: "2026-04-30T14:00:00Z",
        result: {
          preferred_artifact: "paper_md",
          artifacts: {
            paper_md: {
              path: "/tmp/paper.md",
              filename: "paper.md",
              media_type: "text/markdown"
            }
          }
        }
      }));
      return;
    }
    response.writeHead(404);
    response.end("not found");
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));

  try {
    const address = server.address();
    assert.ok(address && typeof address === "object");
    const completed = await runNode([MDTERO_CLI_PATH, "status", "task-123"], {
      cwd: PROJECT_ROOT,
      env: {
        ...process.env,
        MDTERO_API_KEY: "cli-key",
        MDTERO_API_URL: `http://127.0.0.1:${address.port}`,
      },
    });

    assert.equal(completed.code, 0, completed.stderr);
    assert.match(completed.stdout, /Task: task-123/);
    assert.match(completed.stdout, /Kind: parse/);
    assert.match(completed.stdout, /Status: succeeded/);
    assert.match(completed.stdout, /Stage: completed/);
    assert.match(completed.stdout, /Preferred artifact: paper_md/);
    assert.match(completed.stdout, /Artifacts: paper_md/);
  } finally {
    server.close();
  }
});

test("mdtero CLI can create a translate task from a parse task id with an API key", async () => {
  const server = createServer((request, response) => {
    if (request.method === "GET" && request.url === "/tasks/task-parse-1") {
      assert.equal(request.headers.authorization, "ApiKey cli-key");
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({
        task_id: "task-parse-1",
        status: "succeeded",
        task_kind: "parse",
        input_summary: "10.48550/arXiv.1706.03762",
        stage: "completed",
        created_at: "2026-04-30T14:00:00Z",
        result: {
          preferred_artifact: "paper_md",
          artifacts: {
            paper_md: {
              path: "/tmp/paper.md",
              filename: "paper.md",
              media_type: "text/markdown"
            }
          }
        }
      }));
      return;
    }
    if (request.method === "POST" && request.url === "/tasks/translate") {
      assert.equal(request.headers.authorization, "ApiKey cli-key");
      let body = "";
      request.setEncoding("utf8");
      request.on("data", (chunk) => {
        body += chunk;
      });
      request.on("end", () => {
        assert.equal(body, JSON.stringify({ source_markdown_path: "/tmp/paper.md", target_language: "zh", mode: "full" }));
        response.writeHead(200, { "content-type": "application/json" });
        response.end(JSON.stringify({ task_id: "task-translate-1", status: "queued" }));
      });
      return;
    }
    response.writeHead(404);
    response.end("not found");
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));

  try {
    const address = server.address();
    assert.ok(address && typeof address === "object");
    const completed = await runNode([MDTERO_CLI_PATH, "translate", "task-parse-1", "zh"], {
      cwd: PROJECT_ROOT,
      env: {
        ...process.env,
        MDTERO_API_KEY: "cli-key",
        MDTERO_API_URL: `http://127.0.0.1:${address.port}`,
      },
    });

    assert.equal(completed.code, 0, completed.stderr);
    assert.match(completed.stdout, /Created translate task: task-translate-1/);
    assert.match(completed.stdout, /Source artifact: \/tmp\/paper.md/);
    assert.match(completed.stdout, /Next: mdtero status task-translate-1/);
  } finally {
    server.close();
  }
});

test("mdtero CLI can download an artifact with an API key", async () => {
  const root = await mkdtemp(join(tmpdir(), "mdtero-download-"));
  const server = createServer((request, response) => {
    if (request.method === "GET" && request.url === "/tasks/task-123/download/paper_md") {
      assert.equal(request.headers.authorization, "ApiKey cli-key");
      response.writeHead(200, {
        "content-type": "text/markdown",
        "content-disposition": 'attachment; filename="paper.md"',
      });
      response.end("# translated\n");
      return;
    }
    response.writeHead(404);
    response.end("not found");
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));

  try {
    const address = server.address();
    assert.ok(address && typeof address === "object");
    const completed = await runNode([MDTERO_CLI_PATH, "download", "task-123", "paper_md", "--output-dir", root], {
      cwd: PROJECT_ROOT,
      env: {
        ...process.env,
        MDTERO_API_KEY: "cli-key",
        MDTERO_API_URL: `http://127.0.0.1:${address.port}`,
      },
    });

    assert.equal(completed.code, 0, completed.stderr);
    assert.match(completed.stdout, /Downloaded artifact: /);
    const saved = await readFile(join(root, "paper.md"), "utf8");
    assert.equal(saved, "# translated\n");
  } finally {
    server.close();
  }
});

test("mdtero CLI keeps every placeholder command on the same honest guidance surface", async () => {
  const placeholderCommands = [
    ["discover", "10.48550/arXiv.1706.03762"],
    ["parse-bib", "refs.bib"],
    ["parse-files", "paper.pdf"],
    ["shadow-status"]
  ];

  for (const args of placeholderCommands) {
    const completed = await runNode([MDTERO_CLI_PATH, ...args], { cwd: PROJECT_ROOT });
    assert.equal(completed.code, 0, `${args.join(" ")} should stay non-fatal`);
    assert.match(completed.stdout, /is not implemented in the npm CLI yet/i);
    assert.match(completed.stdout, /Supported today: mdtero login, mdtero doctor, mdtero setup, mdtero version\./);
    assert.match(completed.stdout, /Run mdtero login to open Mdtero Account in your browser, or mdtero login --api-key <key>\./);
  }
});

test("mdtero CLI usage lists the supported commands and placeholder surfaces clearly", async () => {
  const completed = await runNode([MDTERO_CLI_PATH, "--help"], { cwd: PROJECT_ROOT });

  assert.equal(completed.code, 0, completed.stderr);
  assert.match(completed.stdout, /Supported today:/);
  assert.match(completed.stdout, /mdtero login/);
  assert.match(completed.stdout, /mdtero doctor/);
  assert.match(completed.stdout, /mdtero parse <doi-or-url>/);
  assert.match(completed.stdout, /mdtero status <task-id>/);
  assert.match(completed.stdout, /Placeholder guidance only:/);
  assert.match(completed.stdout, /mdtero translate <task-id>/);
  assert.match(completed.stdout, /mdtero discover <doi-or-url>/);
});

test("mdtero CLI accepts help as a first-class command", async () => {
  const completed = await runNode([MDTERO_CLI_PATH, "help"], { cwd: PROJECT_ROOT });

  assert.equal(completed.code, 0, completed.stderr);
  assert.match(completed.stdout, /Supported today:/);
  assert.match(completed.stdout, /Placeholder guidance only:/);
  assert.doesNotMatch(completed.stdout, /Unknown command:/);
});


test("install rejects openclaw because it stays on the dedicated ClawHub path", async () => {
  const completed = await runNode([CLI_PATH, "install", "openclaw"], {
    cwd: PROJECT_ROOT
  });

  assert.equal(completed.code, 1);
  assert.match(completed.stderr, /OpenClaw uses clawhub install mdtero/);
});
