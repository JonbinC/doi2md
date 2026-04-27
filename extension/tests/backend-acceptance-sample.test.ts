import { afterEach, describe, expect, it } from "vitest";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  buildBackendAcceptanceSample
} from "../../scripts/build_backend_acceptance_sample.mjs";
import {
  buildBackendAcceptanceSamples
} from "../../scripts/build_backend_acceptance_samples.mjs";

describe("buildBackendAcceptanceSample", () => {
  let sandboxDir: string | null = null;

  afterEach(async () => {
    if (sandboxDir) {
      await rm(sandboxDir, { recursive: true, force: true });
      sandboxDir = null;
    }
  });

  it("maps accepted validation payloads to successful samples", async () => {
    sandboxDir = await mkdtemp(join(tmpdir(), "mdtero-backend-acceptance-"));
    const validationPath = join(sandboxDir, "validation.json");
    await writeFile(
      validationPath,
      JSON.stringify(
        {
          connector: "wiley_tdm",
          bundle: "runs/wiley/paper.bundle.zip",
          accepted: true,
          passed_checks: ["pdf_payload_present"],
          failed_checks: [],
          title: "Example Wiley Paper",
          doi: "10.1002/example",
          quality: {
            coverage_score: 1,
            structure_score: 0.75,
            fidelity_score: 0.8,
            reference_count: 10,
            figure_count: 2,
            table_count: 1,
            paragraph_count: 20
          }
        },
        null,
        2
      )
    );

    const sample = await buildBackendAcceptanceSample({
      kind: "validation",
      inputPath: validationPath,
      publisher: "Wiley pages",
      label: "wiley-sample",
      accessMode: "licensed",
      acquisitionPath: "helper_bundle_html",
      evidenceScope: "browser_page_probe",
      expectedOutcome: "success"
    });

    expect(sample.actual_outcome).toBe("success");
    expect(sample.probe_status).toBe("success");
    expect(sample.artifacts).toEqual(["paper_bundle", "paper_pdf", "quality_summary", "figure_metadata", "table_metadata"]);
    expect(sample.input).toBe("10.1002/example");
  });

  it("maps blocked validation payloads to blocked samples", async () => {
    sandboxDir = await mkdtemp(join(tmpdir(), "mdtero-backend-acceptance-"));
    const validationPath = join(sandboxDir, "validation.json");
    await writeFile(
      validationPath,
      JSON.stringify(
        {
          connector: "taylor_francis_tdm",
          bundle: "runs/tandf/paper.bundle.zip",
          accepted: false,
          passed_checks: [],
          failed_checks: ["challenge_page_detected"],
          title: "Just a moment..."
        },
        null,
        2
      )
    );

    const sample = await buildBackendAcceptanceSample({
      kind: "validation",
      inputPath: validationPath,
      publisher: "Taylor & Francis pages",
      label: "tandf-blocked",
      accessMode: "licensed",
      acquisitionPath: "helper_bundle_html",
      evidenceScope: "browser_page_probe",
      expectedOutcome: "success"
    });

    expect(sample.actual_outcome).toBe("blocked");
    expect(sample.failure_code).toBe("challenge_page_detected");
  });

  it("maps compare payloads using sibling artifacts", async () => {
    sandboxDir = await mkdtemp(join(tmpdir(), "mdtero-backend-acceptance-"));
    const compareDir = join(sandboxDir, "compare-run");
    await mkdir(compareDir, { recursive: true });
    const comparePath = join(compareDir, "compare.summary.json");
    await writeFile(join(compareDir, "paper.v2.md"), "# Example\n");
    await writeFile(join(compareDir, "render.bundle.json"), "{}\n");
    await writeFile(
      comparePath,
      JSON.stringify(
        {
          name: "local_elsevier_example",
          status: "ok",
          importer: "elsevier_xml_raw",
          input: "/tmp/paper.xml",
          quality: {
            coverage_score: 1,
            structure_score: 0.75,
            fidelity_score: 0.81,
            reference_count: 31,
            figure_count: 3,
            table_count: 1,
            paragraph_count: 44
          }
        },
        null,
        2
      )
    );

    const sample = await buildBackendAcceptanceSample({
      kind: "compare",
      inputPath: comparePath,
      publisher: "Elsevier / ScienceDirect",
      label: "elsevier-compare",
      accessMode: "licensed",
      acquisitionPath: "helper_api_xml",
      evidenceScope: "e2e_parse_task",
      expectedOutcome: "success",
      inputOverride: "10.1016/example"
    });

    expect(sample.actual_outcome).toBe("success");
    expect(sample.artifacts).toEqual(["paper_md", "render_bundle", "quality_summary"]);
    expect(sample.input).toBe("10.1016/example");
  });

  it("builds a sample directory from manifest rows", async () => {
    sandboxDir = await mkdtemp(join(tmpdir(), "mdtero-backend-acceptance-"));
    const manifestPath = join(sandboxDir, "targets.tsv");
    const outputDir = join(sandboxDir, "samples");
    const validationPath = join(sandboxDir, "validation.json");
    await writeFile(
      validationPath,
      JSON.stringify(
        {
          connector: "springer_subscription_connector",
          bundle: "runs/springer/paper.bundle.zip",
          accepted: true,
          passed_checks: [],
          failed_checks: [],
          title: "Springer Example",
          doi: "10.1007/example"
        },
        null,
        2
      )
    );
    await writeFile(
      manifestPath,
      [
        "# kind\tinput_path\tpublisher\tlabel\taccess_mode\tacquisition_path\tevidence_scope\texpected_outcome\tinput_override",
        `validation\t${validationPath}\tSpringer subscription pages\tspringer-example\tlicensed_or_oa\textension_current_tab_capture\tbrowser_page_probe\tsuccess\t`
      ].join("\n")
    );

    const count = await buildBackendAcceptanceSamples({
      manifestPath,
      outputDir
    });

    expect(count).toBe(1);
  });
});
