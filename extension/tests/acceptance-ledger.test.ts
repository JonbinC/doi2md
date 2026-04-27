import { afterEach, describe, expect, it } from "vitest";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { collectAcceptanceSamples } from "../../scripts/collect_acceptance_samples.mjs";

describe("collectAcceptanceSamples", () => {
  let sandboxDir: string | null = null;

  afterEach(async () => {
    if (sandboxDir) {
      await rm(sandboxDir, { recursive: true, force: true });
      sandboxDir = null;
    }
  });

  it("merges sample files into the matching publisher bucket", async () => {
    sandboxDir = await mkdtemp(join(tmpdir(), "mdtero-acceptance-"));
    const basePath = join(sandboxDir, "base.json");
    const samplesDir = join(sandboxDir, "samples");
    const outputPath = join(sandboxDir, "out.json");
    await mkdir(samplesDir, { recursive: true });

    await writeFile(
      basePath,
      JSON.stringify(
        {
          run_date: "2026-03-26",
          environment: {
            network_context: "campus_ip_or_vpn",
            helper_version: "local_probe_only",
            extension_version: "experimental_line",
            backend_base_url: "not_exercised"
          },
          publishers: [
            {
              publisher: "Springer subscription pages",
              target_samples: 5,
              samples: []
            },
            {
              publisher: "arXiv",
              target_samples: 5,
              samples: []
            }
          ]
        },
        null,
        2
      )
    );

    await writeFile(
      join(samplesDir, "springer-bridge.json"),
      JSON.stringify(
        {
          publisher: "Springer subscription pages",
          label: "springer-bridge-demo",
          input: "https://link.springer.com/article/10.1007/s12011-024-04385-0",
          access_mode: "licensed_or_oa",
          acquisition_path: "extension_current_tab_capture",
          evidence_scope: "browser_page_probe",
          expected_outcome: "success",
          actual_outcome: "success",
          probe_status: "success",
          task_id: "bridge-task-1",
          artifacts: ["html"],
          failure_code: null,
          failure_message: null,
          notes: "Springer HTML Example"
        },
        null,
        2
      )
    );

    await writeFile(
      join(samplesDir, "arxiv-task.json"),
      JSON.stringify(
        {
          publisher: "arXiv",
          label: "arxiv-e2e-demo",
          input: "https://arxiv.org/html/2401.00001",
          access_mode: "open",
          acquisition_path: "extension_current_tab_capture",
          evidence_scope: "e2e_parse_task",
          expected_outcome: "success",
          actual_outcome: "success",
          probe_status: "success",
          task_id: "task-demo-1",
          artifacts: ["paper_bundle", "paper_md"],
          failure_code: null,
          failure_message: null,
          notes: ""
        },
        null,
        2
      )
    );

    await collectAcceptanceSamples({
      basePath,
      samplesDir,
      outputPath
    });

    const merged = JSON.parse(await readFile(outputPath, "utf8"));
    const springer = merged.publishers.find((item: { publisher: string }) => item.publisher === "Springer subscription pages");
    const arxiv = merged.publishers.find((item: { publisher: string }) => item.publisher === "arXiv");

    expect(springer.samples).toHaveLength(1);
    expect(springer.samples[0].label).toBe("springer-bridge-demo");
    expect(arxiv.samples).toHaveLength(1);
    expect(arxiv.samples[0].label).toBe("arxiv-e2e-demo");
  });

  it("replaces an existing sample with the same publisher and label", async () => {
    sandboxDir = await mkdtemp(join(tmpdir(), "mdtero-acceptance-"));
    const basePath = join(sandboxDir, "base.json");
    const samplesDir = join(sandboxDir, "samples");
    const outputPath = join(sandboxDir, "out.json");
    await mkdir(samplesDir, { recursive: true });

    await writeFile(
      basePath,
      JSON.stringify(
        {
          run_date: "2026-03-26",
          environment: {
            network_context: "campus_ip_or_vpn",
            helper_version: "local_probe_only",
            extension_version: "experimental_line",
            backend_base_url: "not_exercised"
          },
          publishers: [
            {
              publisher: "Wiley pages",
              target_samples: 5,
              samples: [
                {
                  label: "wiley-bridge-demo",
                  input: "https://onlinelibrary.wiley.com/doi/full/10.1002/er.7490",
                  access_mode: "licensed_with_campus_or_vpn",
                  acquisition_path: "extension_current_tab_capture",
                  evidence_scope: "browser_page_probe",
                  expected_outcome: "success",
                  actual_outcome: "blocked",
                  probe_status: "challenge",
                  task_id: "bridge-old",
                  artifacts: [],
                  failure_code: "challenge_page_detected",
                  failure_message: "Old message",
                  notes: "old"
                }
              ]
            }
          ]
        },
        null,
        2
      )
    );

    await writeFile(
      join(samplesDir, "wiley-bridge.json"),
      JSON.stringify(
        {
          publisher: "Wiley pages",
          label: "wiley-bridge-demo",
          input: "https://onlinelibrary.wiley.com/doi/full/10.1002/er.7490",
          access_mode: "licensed_with_campus_or_vpn",
          acquisition_path: "extension_current_tab_capture",
          evidence_scope: "browser_page_probe",
          expected_outcome: "success",
          actual_outcome: "blocked",
          probe_status: "challenge",
          task_id: "bridge-new",
          artifacts: [],
          failure_code: "challenge_page_detected",
          failure_message: "New message",
          notes: "new"
        },
        null,
        2
      )
    );

    await collectAcceptanceSamples({
      basePath,
      samplesDir,
      outputPath
    });

    const merged = JSON.parse(await readFile(outputPath, "utf8"));
    const wiley = merged.publishers.find((item: { publisher: string }) => item.publisher === "Wiley pages");

    expect(wiley.samples).toHaveLength(1);
    expect(wiley.samples[0].task_id).toBe("bridge-new");
    expect(wiley.samples[0].notes).toBe("new");
  });
});
