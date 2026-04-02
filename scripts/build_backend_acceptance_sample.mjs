#!/usr/bin/env node

import { access, readFile, writeFile } from "node:fs/promises";
import { basename, dirname, join } from "node:path";

function parseArgs(argv) {
  const options = {
    kind: "",
    inputPath: "",
    publisher: "",
    label: "",
    accessMode: "unknown",
    acquisitionPath: "unknown",
    evidenceScope: "e2e_parse_task",
    expectedOutcome: "success",
    inputOverride: "",
    outputPath: ""
  };

  for (let index = 2; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--kind") options.kind = argv[++index] || "";
    else if (arg === "--input") options.inputPath = argv[++index] || "";
    else if (arg === "--publisher") options.publisher = argv[++index] || "";
    else if (arg === "--label") options.label = argv[++index] || "";
    else if (arg === "--access-mode") options.accessMode = argv[++index] || "";
    else if (arg === "--acquisition-path") options.acquisitionPath = argv[++index] || "";
    else if (arg === "--scope") options.evidenceScope = argv[++index] || "";
    else if (arg === "--expected") options.expectedOutcome = argv[++index] || "";
    else if (arg === "--input-override") options.inputOverride = argv[++index] || "";
    else if (arg === "--output") options.outputPath = argv[++index] || "";
  }

  if (!options.kind || !options.inputPath || !options.publisher || !options.label) {
    console.error(
      "Usage: node scripts/build_backend_acceptance_sample.mjs --kind <validation|compare|bridge_capture> --input <json> --publisher <publisher> --label <label> [--access-mode <mode>] [--acquisition-path <path>] [--scope <scope>] [--expected <success|blocked|wrong_page>] [--input-override <input>] [--output <sample.json>]"
    );
    process.exit(1);
  }

  return options;
}

async function fileExists(path) {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

function formatMetric(label, value) {
  return typeof value === "number" ? `${label}=${value}` : "";
}

function qualityNotes(quality) {
  if (!quality || typeof quality !== "object") {
    return "";
  }
  return [
    formatMetric("coverage", quality.coverage_score),
    formatMetric("structure", quality.structure_score),
    formatMetric("fidelity", quality.fidelity_score),
    formatMetric("refs", quality.reference_count),
    formatMetric("figures", quality.figure_count),
    formatMetric("tables", quality.table_count),
    formatMetric("paragraphs", quality.paragraph_count)
  ]
    .filter(Boolean)
    .join(", ");
}

function joinNotes(parts) {
  return parts
    .map((part) => String(part || "").trim())
    .filter(Boolean)
    .join(" | ");
}

function normalizeValidationPayload(payload, options) {
  const failedChecks = Array.isArray(payload.failed_checks) ? payload.failed_checks : [];
  const passedChecks = Array.isArray(payload.passed_checks) ? payload.passed_checks : [];
  const title = String(payload.title || "").trim();
  const loweredTitle = title.toLowerCase();
  const quality = payload.quality && typeof payload.quality === "object" ? payload.quality : null;
  const artifacts = [];

  if (payload.bundle) {
    artifacts.push("paper_bundle");
  }
  if (passedChecks.includes("pdf_payload_present")) {
    artifacts.push("paper_pdf");
  }
  if (quality) {
    artifacts.push("quality_summary");
  }
  if (quality?.figure_count > 0) {
    artifacts.push("figure_metadata");
  }
  if (quality?.table_count > 0) {
    artifacts.push("table_metadata");
  }

  let actualOutcome = "failed";
  let probeStatus = "unknown";
  let failureCode = null;
  let failureMessage = null;

  if (payload.accepted === true) {
    actualOutcome = "success";
    probeStatus = "success";
  } else if (failedChecks.includes("challenge_page_detected") || loweredTitle === "just a moment...") {
    actualOutcome = "blocked";
    probeStatus = "challenge";
    failureCode = "challenge_page_detected";
    failureMessage = "Challenge shell was detected in helper validation.";
  } else if (loweredTitle.includes("page unavailable")) {
    actualOutcome = "wrong_page";
    probeStatus = "wrong_page";
    failureCode = "page_unavailable";
    failureMessage = "Publisher returned an unavailable shell instead of article content.";
  } else {
    actualOutcome = "failed";
    probeStatus = "unknown";
    failureCode = failedChecks[0] || "validation_failed";
    failureMessage = failedChecks.length > 0
      ? `Validation failed checks: ${failedChecks.join(", ")}`
      : "Validation payload was not accepted.";
  }

  return {
    publisher: options.publisher,
    label: options.label,
    input: options.inputOverride || payload.doi || payload.title || basename(options.inputPath),
    access_mode: options.accessMode,
    acquisition_path: options.acquisitionPath,
    evidence_scope: options.evidenceScope,
    expected_outcome: options.expectedOutcome,
    actual_outcome: actualOutcome,
    probe_status: probeStatus,
    task_id: null,
    artifacts,
    failure_code: failureCode,
    failure_message: failureMessage,
    notes: joinNotes([
      payload.connector ? `connector=${payload.connector}` : "",
      title ? `title=${title}` : "",
      qualityNotes(quality)
    ])
  };
}

async function normalizeComparePayload(payload, options) {
  const compareDir = dirname(options.inputPath);
  const paperMarkdownPath = join(compareDir, "paper.v2.md");
  const renderBundlePath = join(compareDir, "render.bundle.json");
  const artifacts = [];

  if (await fileExists(paperMarkdownPath)) {
    artifacts.push("paper_md");
  }
  if (await fileExists(renderBundlePath)) {
    artifacts.push("render_bundle");
  }
  if (payload.quality && typeof payload.quality === "object") {
    artifacts.push("quality_summary");
  }

  const success = String(payload.status || "").trim().toLowerCase() === "ok" && artifacts.length > 0;
  const actualOutcome = success ? "success" : "failed";

  return {
    publisher: options.publisher,
    label: options.label,
    input: options.inputOverride || payload.input || basename(options.inputPath),
    access_mode: options.accessMode,
    acquisition_path: options.acquisitionPath,
    evidence_scope: options.evidenceScope,
    expected_outcome: options.expectedOutcome,
    actual_outcome: actualOutcome,
    probe_status: success ? "success" : "unknown",
    task_id: null,
    artifacts,
    failure_code: success ? null : "compare_probe_failed",
    failure_message: success ? null : "Compare summary did not produce expected V2 artifacts.",
    notes: joinNotes([
      payload.importer ? `importer=${payload.importer}` : "",
      payload.name ? `name=${payload.name}` : "",
      qualityNotes(payload.quality)
    ])
  };
}

function normalizeBridgeCapturePayload(payload, options) {
  const response = payload.response && typeof payload.response === "object" ? payload.response : {};
  const request = payload.request && typeof payload.request === "object" ? payload.request : {};
  const artifacts = [];

  if (response.payload_name) {
    artifacts.push(response.payload_name);
  } else if (response.artifact_kind) {
    artifacts.push(response.artifact_kind);
  }
  if (payload.bundle_path) {
    artifacts.push("paper_bundle");
  }

  const responseStatus = String(response.status || "").trim().toLowerCase();
  const success = responseStatus === "succeeded" && artifacts.length > 0;
  const failureCode = success ? null : (response.failure_code || "bridge_capture_failed");
  const failureMessage = success ? null : (response.failure_message || "Browser bridge capture failed.");

  return {
    publisher: options.publisher,
    label: options.label,
    input: options.inputOverride || request.source_url || request.input || basename(options.inputPath),
    access_mode: options.accessMode,
    acquisition_path: options.acquisitionPath,
    evidence_scope: options.evidenceScope,
    expected_outcome: options.expectedOutcome,
    actual_outcome: success ? "success" : "failed",
    probe_status: success ? "success" : "unknown",
    task_id: response.task_id || request.task_id || null,
    artifacts,
    failure_code: failureCode,
    failure_message: failureMessage,
    notes: joinNotes([
      payload.route_kind ? `route=${payload.route_kind}` : "",
      response.connector ? `connector=${response.connector}` : "",
      response.page_title ? `title=${response.page_title}` : ""
    ])
  };
}

export async function buildBackendAcceptanceSample(params) {
  const options = {
    kind: String(params?.kind || "").trim(),
    inputPath: String(params?.inputPath || "").trim(),
    publisher: String(params?.publisher || "").trim(),
    label: String(params?.label || "").trim(),
    accessMode: String(params?.accessMode || "unknown").trim(),
    acquisitionPath: String(params?.acquisitionPath || "unknown").trim(),
    evidenceScope: String(params?.evidenceScope || "e2e_parse_task").trim(),
    expectedOutcome: String(params?.expectedOutcome || "success").trim(),
    inputOverride: String(params?.inputOverride || "").trim()
  };

  if (!options.kind || !options.inputPath || !options.publisher || !options.label) {
    throw new Error("buildBackendAcceptanceSample requires kind, inputPath, publisher, and label.");
  }

  const payload = JSON.parse(await readFile(options.inputPath, "utf8"));
  if (options.kind === "validation") {
    return normalizeValidationPayload(payload, options);
  }
  if (options.kind === "compare") {
    return normalizeComparePayload(payload, options);
  }
  if (options.kind === "bridge_capture") {
    return normalizeBridgeCapturePayload(payload, options);
  }
  throw new Error(`Unsupported backend acceptance kind: ${options.kind}`);
}

async function main() {
  const options = parseArgs(process.argv);
  const sample = await buildBackendAcceptanceSample(options);
  const output = `${JSON.stringify(sample, null, 2)}\n`;

  if (options.outputPath) {
    await writeFile(options.outputPath, output, "utf8");
    console.log(`Wrote ${options.outputPath}`);
    return;
  }

  process.stdout.write(output);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  await main();
}
