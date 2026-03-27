import { describe, expect, it } from "vitest";

import {
  collectElsevierImageAssetFiles,
  buildElsevierLocalAcquireGuidance,
  normalizeElsevierInput,
  requiresElsevierLocalAcquire
} from "../src/lib/elsevier";

describe("normalizeElsevierInput", () => {
  it("recognizes raw Elsevier DOIs and doi.org URLs", () => {
    expect(normalizeElsevierInput("10.1016/j.energy.2026.140192")).toEqual({
      kind: "doi",
      value: "10.1016/j.energy.2026.140192"
    });
    expect(normalizeElsevierInput("https://doi.org/10.1016/j.energy.2026.140192")).toEqual({
      kind: "doi",
      value: "10.1016/j.energy.2026.140192"
    });
  });

  it("recognizes ScienceDirect PII inputs", () => {
    expect(
      normalizeElsevierInput("https://www.sciencedirect.com/science/article/pii/S0360544226002970")
    ).toEqual({
      kind: "pii",
      value: "S0360544226002970"
    });
  });
});

describe("requiresElsevierLocalAcquire", () => {
  it("flags Elsevier inputs and ignores arxiv", () => {
    expect(requiresElsevierLocalAcquire("10.1016/j.energy.2026.140192")).toBe(true);
    expect(requiresElsevierLocalAcquire("https://arxiv.org/abs/1706.03762")).toBe(false);
  });
});

describe("buildElsevierLocalAcquireGuidance", () => {
  it("gives user-facing setup guidance instead of a blunt API key error", () => {
    expect(buildElsevierLocalAcquireGuidance()).toContain("local acquisition");
    expect(buildElsevierLocalAcquireGuidance()).toContain("Mdtero extension settings");
    expect(buildElsevierLocalAcquireGuidance()).toContain("campus or institutional network IP");
    expect(buildElsevierLocalAcquireGuidance()).not.toBe(
      "Elsevier API Key is required for Elsevier / ScienceDirect parsing."
    );
  });
});

describe("collectElsevierImageAssetFiles", () => {
  it("downloads figure assets into helper bundle paper_files members", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (input) => {
      const url = String(input);
      if (url === "https://ars.els-cdn.com/content/image/1-s2.0-S0360544226002970-gr1.jpg") {
        return new Response(new Uint8Array([0xff, 0xd8, 0xff]), {
          status: 200,
          headers: {
            "content-type": "image/jpeg"
          }
        });
      }
      return new Response("missing", { status: 404 });
    };

    try {
      const assets = await collectElsevierImageAssetFiles(`
        <full-text-retrieval-response>
          <coredata>
            <dc:identifier>PII:S0360544226002970</dc:identifier>
          </coredata>
          <originalText>
            <xocs:doc xmlns:xocs="http://www.elsevier.com/xml/xocs/dtd"
                      xmlns:ce="http://www.elsevier.com/xml/common/dtd">
              <xocs:attachment>
                <ce:object ref="gr1" category="standard">https://api.elsevier.com/content/object/eid/1-s2.0-S0360544226002970-gr1.jpg</ce:object>
              </xocs:attachment>
              <ce:figure id="fig1">
                <ce:label>Figure 1</ce:label>
                <ce:link locator="gr1" />
              </ce:figure>
            </xocs:doc>
          </originalText>
        </full-text-retrieval-response>
      `);

      expect(assets).toEqual({
        "paper_files/1-s2.0-S0360544226002970-gr1.jpg": expect.any(Uint8Array)
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
