#!/usr/bin/env node

import { copyFile, mkdir, readdir } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PROJECT_ROOT = fileURLToPath(new URL("..", import.meta.url));
const DEFAULT_MANIFEST_URL =
  process.env.MDTERO_INSTALL_MANIFEST_URL || "https://mdtero.com/install/manifest.json";

function printUsage() {
  console.log(`Usage:
  mdtero-install show [--manifest-url URL]
  mdtero-install install <target> [--root DIR] [--manifest-url URL]`);
}

function parseArgs(argv) {
  const args = [...argv];
  const options = {
    manifestUrl: DEFAULT_MANIFEST_URL,
    root: process.cwd()
  };
  const positionals = [];

  while (args.length > 0) {
    const current = args.shift();
    if (current === "--manifest-url") {
      options.manifestUrl = args.shift() || options.manifestUrl;
      continue;
    }
    if (current === "--root") {
      options.root = resolve(args.shift() || options.root);
      continue;
    }
    if (current) {
      positionals.push(current);
    }
  }

  return {
    command: positionals[0],
    target: positionals[1],
    options
  };
}

async function fetchManifest(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch install manifest: HTTP ${response.status}`);
  }
  return response.json();
}

async function copyDirectory(sourceDir, targetDir) {
  await mkdir(targetDir, { recursive: true });
  const entries = await readdir(sourceDir, { withFileTypes: true });

  for (const entry of entries) {
    const sourcePath = join(sourceDir, entry.name);
    const targetPath = join(targetDir, entry.name);
    if (entry.isDirectory()) {
      await copyDirectory(sourcePath, targetPath);
      continue;
    }
    await mkdir(dirname(targetPath), { recursive: true });
    await copyFile(sourcePath, targetPath);
  }
}

function bundledSkillDir() {
  return join(PROJECT_ROOT, "skills", "mdtero");
}

async function showManifest(manifest) {
  console.log(`Mdtero install manifest v${manifest.version}`);
  console.log(`Manifest URL: ${manifest.manifestUrl}`);
  console.log(`Unified CLI: ${manifest.cli?.npxCommand || "n/a"}`);
  console.log("");
  for (const target of manifest.targets || []) {
    console.log(`${target.label}: ${target.installCommand}`);
  }
}

async function installSkill(manifest, target, rootDir) {
  const definition = (manifest.targets || []).find((item) => item.target === target);
  if (!definition) {
    throw new Error(`Unsupported target: ${target}`);
  }
  if (!definition.skillDirectory) {
    throw new Error(`Target ${target} did not expose a skillDirectory.`);
  }

  const targetDir = join(rootDir, definition.skillDirectory);
  await copyDirectory(bundledSkillDir(), targetDir);

  console.log(`Installed Mdtero skill for ${definition.label} at ${targetDir}`);
  if (manifest.helperInstallerUrl) {
    console.log(`If local acquisition is needed, review and run: ${manifest.helperInstallerUrl}`);
  }
}

async function main() {
  const { command, target, options } = parseArgs(process.argv.slice(2));
  if (!command || command === "--help" || command === "-h") {
    printUsage();
    return;
  }

  const manifest = await fetchManifest(options.manifestUrl);

  if (command === "show") {
    await showManifest(manifest);
    return;
  }

  if (command === "install") {
    if (!target) {
      throw new Error("Missing install target.");
    }
    await installSkill(manifest, target, options.root);
    return;
  }

  throw new Error(`Unknown command: ${command}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
