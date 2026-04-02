#!/usr/bin/env node

import { mkdir, writeFile } from "node:fs/promises";

import { buildBackendAcceptanceSample } from "./build_backend_acceptance_sample.mjs";

function parseArgs(argv) {
  const options = {
    manifestPath: "",
    outputDir: ""
  };

  for (let index = 2; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--manifest") options.manifestPath = argv[++index] || "";
    else if (arg === "--output-dir") options.outputDir = argv[++index] || "";
  }

  if (!options.manifestPath || !options.outputDir) {
    console.error(
      "Usage: node scripts/build_backend_acceptance_samples.mjs --manifest <targets.tsv> --output-dir <samples_dir>"
    );
    process.exit(1);
  }

  return options;
}

function parseManifest(text) {
  const rows = [];
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }
    const parts = trimmed.split("\t");
    if (parts.length < 8) {
      throw new Error(`Manifest row must have at least 8 tab-separated columns: ${trimmed}`);
    }
    const [
      kind,
      inputPath,
      publisher,
      label,
      accessMode,
      acquisitionPath,
      evidenceScope,
      expectedOutcome,
      inputOverride = ""
    ] = parts;
    rows.push({
      kind,
      inputPath,
      publisher,
      label,
      accessMode,
      acquisitionPath,
      evidenceScope,
      expectedOutcome,
      inputOverride
    });
  }
  return rows;
}

export async function buildBackendAcceptanceSamples(params) {
  const manifestPath = String(params?.manifestPath || "").trim();
  const outputDir = String(params?.outputDir || "").trim();
  if (!manifestPath || !outputDir) {
    throw new Error("buildBackendAcceptanceSamples requires manifestPath and outputDir.");
  }

  const { readFile } = await import("node:fs/promises");
  const manifestText = await readFile(manifestPath, "utf8");
  const rows = parseManifest(manifestText);
  await mkdir(outputDir, { recursive: true });

  for (const row of rows) {
    const sample = await buildBackendAcceptanceSample(row);
    await writeFile(`${outputDir}/${row.label}.json`, `${JSON.stringify(sample, null, 2)}\n`, "utf8");
  }

  return rows.length;
}

async function main() {
  const options = parseArgs(process.argv);
  const count = await buildBackendAcceptanceSamples(options);
  console.log(`Wrote ${count} samples to ${options.outputDir}`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  await main();
}
