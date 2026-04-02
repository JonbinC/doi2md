#!/usr/bin/env node

import { readdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

export async function collectAcceptanceSamples(params) {
  const basePath = String(params?.basePath || "").trim();
  const samplesDir = String(params?.samplesDir || "").trim();
  const outputPath = String(params?.outputPath || "").trim();

  if (!basePath || !samplesDir || !outputPath) {
    throw new Error("collectAcceptanceSamples requires basePath, samplesDir, and outputPath.");
  }

  const acceptance = JSON.parse(await readFile(basePath, "utf8"));
  const entries = await readdir(samplesDir, { withFileTypes: true });

  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith(".json")) {
      continue;
    }
    const samplePath = join(samplesDir, entry.name);
    const sample = JSON.parse(await readFile(samplePath, "utf8"));
    const publisher = String(sample.publisher || "").trim();
    const label = String(sample.label || "").trim();
    if (!publisher || !label) {
      continue;
    }
    const bucket = (acceptance.publishers || []).find((item) => item.publisher === publisher);
    if (!bucket) {
      continue;
    }
    bucket.samples = Array.isArray(bucket.samples) ? bucket.samples : [];
    const existingIndex = bucket.samples.findIndex((item) => String(item?.label || "").trim() === label);
    const normalized = {
      label: sample.label,
      input: sample.input,
      access_mode: sample.access_mode,
      acquisition_path: sample.acquisition_path,
      evidence_scope: sample.evidence_scope,
      expected_outcome: sample.expected_outcome,
      actual_outcome: sample.actual_outcome,
      probe_status: sample.probe_status,
      task_id: sample.task_id ?? null,
      artifacts: Array.isArray(sample.artifacts) ? sample.artifacts : [],
      failure_code: sample.failure_code ?? null,
      failure_message: sample.failure_message ?? null,
      notes: sample.notes ?? ""
    };
    if (existingIndex >= 0) {
      bucket.samples.splice(existingIndex, 1, normalized);
    } else {
      bucket.samples.push(normalized);
    }
  }

  await writeFile(outputPath, `${JSON.stringify(acceptance, null, 2)}\n`, "utf8");
  return acceptance;
}

async function main() {
  const basePath = process.argv[2];
  const samplesDir = process.argv[3];
  const outputPath = process.argv[4];

  if (!basePath || !samplesDir || !outputPath) {
    console.error("Usage: node scripts/collect_acceptance_samples.mjs <base.json> <samples_dir> <output.json>");
    process.exit(1);
  }

  await collectAcceptanceSamples({
    basePath,
    samplesDir,
    outputPath
  });
  console.log(`Wrote ${outputPath}`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  await main();
}
