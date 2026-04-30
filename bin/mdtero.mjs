#!/usr/bin/env node

import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { dirname, resolve } from "node:path";
import { randomBytes, timingSafeEqual } from "node:crypto";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const PROJECT_ROOT = fileURLToPath(new URL("..", import.meta.url));
const BUNDLED_MANIFEST_PATH = fileURLToPath(new URL("../install/manifest.json", import.meta.url));
const DEFAULT_API_BASE = process.env.MDTERO_API_URL || "https://api.mdtero.com";
const DEFAULT_SITE_BASE = process.env.MDTERO_SITE_URL || "https://mdtero.com";
const LOGIN_TIMEOUT_MS = Number(process.env.MDTERO_LOGIN_TIMEOUT_MS || 180000);

function usage() {
  console.log(`Usage:
  mdtero --version
  mdtero login [--api-key KEY] [--config-file PATH] [--site-url URL]
  mdtero doctor [--config-file PATH]
  mdtero setup
  mdtero parse <doi-or-url>
  mdtero translate <task-id>
  mdtero status <task-id>
  mdtero discover <doi-or-url>
  mdtero download <task-id> <artifact>

Supported today:
  mdtero version
  mdtero login
  mdtero doctor
  mdtero setup

Placeholder guidance only:
  mdtero parse
  mdtero translate
  mdtero status
  mdtero discover
  mdtero parse-bib
  mdtero parse-files
  mdtero download
  mdtero shadow-status

Mdtero's npm CLI uses API keys from https://mdtero.com/account.
Run: mdtero login --api-key <your-key>`);
}

function parseArgs(argv) {
  const args = [...argv];
  const options = {
    envFile: resolve(process.cwd(), ".env"),
    apiKey: "",
    siteUrl: DEFAULT_SITE_BASE
  };
  const positionals = [];

  while (args.length > 0) {
    const current = args.shift();
    if (current === "--env-file" || current === "--config-file") {
      options.envFile = resolve(args.shift() || options.envFile);
      continue;
    }
    if (current === "--api-key") {
      options.apiKey = args.shift() || "";
      continue;
    }
    if (current === "--site-url") {
      options.siteUrl = args.shift() || options.siteUrl;
      continue;
    }
    if (current) {
      positionals.push(current);
    }
  }

  return { command: positionals[0], rest: positionals.slice(1), options };
}

async function packageVersion() {
  const content = await readFile(resolve(PROJECT_ROOT, "package.json"), "utf8");
  return JSON.parse(content).version;
}

async function manifestVersion() {
  const content = await readFile(BUNDLED_MANIFEST_PATH, "utf8");
  const manifest = JSON.parse(content);
  return manifest.cli?.packageVersion || manifest.releaseTruth?.latest?.cli?.version || "unknown";
}

async function readEnvFile(path) {
  try {
    return await readFile(path, "utf8");
  } catch (error) {
    if (error && error.code === "ENOENT") {
      return "";
    }
    throw error;
  }
}

function upsertEnvValue(content, key, value) {
  const line = `${key}=${JSON.stringify(value)}`;
  const lines = content.split(/\r?\n/);
  let replaced = false;
  const next = lines.map((existing) => {
    if (existing.startsWith(`${key}=`) || existing.startsWith(`export ${key}=`)) {
      replaced = true;
      return line;
    }
    return existing;
  });
  if (!replaced) {
    if (next.length > 0 && next[next.length - 1] !== "") {
      next.push(line);
    } else {
      next[next.length - 1] = line;
    }
  }
  return `${next.join("\n").replace(/\n*$/, "")}\n`;
}

function safeCompare(a, b) {
  const left = Buffer.from(String(a || ""));
  const right = Buffer.from(String(b || ""));
  return left.length === right.length && timingSafeEqual(left, right);
}

function openBrowser(url) {
  const platform = process.platform;
  const command = platform === "darwin" ? "open" : platform === "win32" ? "cmd" : "xdg-open";
  const args = platform === "win32" ? ["/c", "start", "", url] : [url];
  try {
    const child = spawn(command, args, { detached: true, stdio: "ignore" });
    child.unref();
  } catch {
    // The printed URL remains the fallback.
  }
}

function waitForCliCallback({ state, envFile, siteUrl }) {
  return new Promise((resolve, reject) => {
    let settled = false;
    let server;
    const timeout = setTimeout(() => {
      if (settled) return;
      settled = true;
      server?.close();
      reject(new Error("Timed out waiting for Mdtero Account login. Re-run mdtero login when ready."));
    }, LOGIN_TIMEOUT_MS);

    server = createServer((request, response) => {
      if (request.method === "OPTIONS" && request.url === "/callback") {
        response.writeHead(204, {
          "access-control-allow-origin": new URL(siteUrl).origin,
          "access-control-allow-methods": "POST, OPTIONS",
          "access-control-allow-headers": "Content-Type",
          "access-control-allow-private-network": "true"
        });
        response.end();
        return;
      }

      if (request.method === "GET" && request.url?.startsWith("/callback")) {
        response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
        response.end("<h1>Mdtero CLI login is waiting</h1><p>Return to the Mdtero Account tab to finish sign-in.</p>");
        return;
      }

      if (request.method !== "POST" || request.url !== "/callback") {
        response.writeHead(404, { "content-type": "application/json" });
        response.end(JSON.stringify({ error: "not_found" }));
        return;
      }

      let body = "";
      request.setEncoding("utf8");
      request.on("data", (chunk) => {
        body += chunk;
        if (body.length > 65536) {
          request.destroy();
        }
      });
      request.on("end", async () => {
        try {
          const payload = JSON.parse(body || "{}");
          if (!safeCompare(payload.state, state)) {
            response.writeHead(403, { "content-type": "application/json" });
            response.end(JSON.stringify({ error: "invalid_state" }));
            return;
          }
          const apiKey = String(payload.apiKey || payload.secret || "").trim();
          if (!apiKey) {
            response.writeHead(422, { "content-type": "application/json" });
            response.end(JSON.stringify({ error: "missing_api_key" }));
            return;
          }
          await saveApiKey(envFile, apiKey);
          response.writeHead(200, { "content-type": "application/json", "access-control-allow-origin": new URL(siteUrl).origin });
          response.end(JSON.stringify({ ok: true }));
          if (!settled) {
            settled = true;
            clearTimeout(timeout);
            server.close();
            resolve(undefined);
          }
        } catch (error) {
          response.writeHead(400, { "content-type": "application/json" });
          response.end(JSON.stringify({ error: error instanceof Error ? error.message : String(error) }));
        }
      });
    });

    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address !== "object") {
        if (!settled) {
          settled = true;
          clearTimeout(timeout);
          reject(new Error("Could not start local Mdtero login callback."));
        }
        return;
      }
      const callbackUrl = `http://127.0.0.1:${address.port}/callback`;
      const loginUrl = new URL("/auth", siteUrl);
      loginUrl.searchParams.set("cli_callback", callbackUrl);
      loginUrl.searchParams.set("cli_state", state);
      loginUrl.searchParams.set("market", "cny");
      console.log("Opening Mdtero Account login in your browser...");
      console.log(String(loginUrl));
      openBrowser(String(loginUrl));
    });
  });
}

async function saveApiKey(envFile, apiKey) {
  await mkdir(dirname(envFile), { recursive: true });
  const content = await readEnvFile(envFile);
  const next = upsertEnvValue(content, "MDTERO_API_KEY", apiKey.trim());
  await writeFile(envFile, next, { mode: 0o600 });
}

async function cmdLogin(options) {
  const apiKey = options.apiKey || "";
  if (apiKey.trim()) {
    await saveApiKey(options.envFile, apiKey.trim());
    console.log(`Saved MDTERO_API_KEY to ${options.envFile}`);
    console.log("Mdtero login configured for this project. Restart your agent shell if it does not read .env automatically.");
    return;
  }

  const state = randomBytes(24).toString("hex");
  await waitForCliCallback({ state, envFile: options.envFile, siteUrl: options.siteUrl });
  console.log(`Saved MDTERO_API_KEY to ${options.envFile}`);
  console.log("Mdtero login complete. Restart your agent shell if it does not read .env automatically.");
}

async function cmdDoctor(options) {
  const envContent = await readEnvFile(options.envFile);
  const envHasKey = /^(?:export\s+)?MDTERO_API_KEY=/m.test(envContent);
  const shellHasKey = Boolean(process.env.MDTERO_API_KEY);
  const version = await packageVersion();
  console.log(`Mdtero CLI: ${version}`);
  console.log(`API base: ${DEFAULT_API_BASE}`);
  console.log(`Shell MDTERO_API_KEY: ${shellHasKey ? "set" : "missing"}`);
  console.log(`${options.envFile} MDTERO_API_KEY: ${envHasKey ? "set" : "missing"}`);
  if (!shellHasKey && !envHasKey) {
    console.log("Next step: create an API key at https://mdtero.com/account and run mdtero login --api-key <key>");
  }
}

function explainApiCommand(command, rest) {
  const suffix = rest.length ? ` ${rest.join(" ")}` : "";
  console.log(`mdtero ${command}${suffix} is not implemented in the npm CLI yet.`);
  console.log("Supported today: mdtero login, mdtero doctor, mdtero setup, mdtero version.");
  console.log(`When this command is ready, it will need MDTERO_API_KEY.`);
  console.log("Run mdtero login to open Mdtero Account in your browser, or mdtero login --api-key <key>.");
  console.log("Agent users can also run /mdtero-setup inside their workspace.");
}

async function main() {
  const { command, rest, options } = parseArgs(process.argv.slice(2));

  if (!command || command === "--help" || command === "-h") {
    usage();
    return;
  }

  if (command === "--version" || command === "version") {
    console.log(await manifestVersion());
    return;
  }

  if (command === "setup") {
    console.log("Run mdtero login to open Mdtero Account in your browser, or use mdtero login --api-key <key>.");
    return;
  }

  if (command === "login") {
    await cmdLogin(options);
    return;
  }

  if (command === "doctor") {
    await cmdDoctor(options);
    return;
  }

  if (["parse", "translate", "status", "discover", "parse-bib", "parse-files", "download", "shadow-status"].includes(command)) {
    explainApiCommand(command, rest);
    return;
  }

  throw new Error(`Unknown command: ${command}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
