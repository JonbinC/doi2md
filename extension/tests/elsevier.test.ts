import { describe, expect, it, vi } from "vitest";

import {
  buildElsevierLocalAcquireGuidance,
  fetchElsevierXml,
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

describe("fetchElsevierXml", () => {
  it("keeps Elsevier figure links remote instead of bundling downloaded image bytes", async () => {
    const originalFetch = globalThis.fetch;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("https://api.elsevier.com/content/article/pii/S0360544226002970")) {
        return new Response(
          `
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
          `,
          { status: 200, headers: { "content-type": "application/xml" } }
        );
      }
      return new Response("unexpected", { status: 500 });
    });
    globalThis.fetch = fetchMock as typeof fetch;

    try {
      const uploaded = await fetchElsevierXml(
        "https://www.sciencedirect.com/science/article/pii/S0360544226002970",
        "els-demo"
      );

      expect(uploaded.bundleExtraFiles).toEqual({});
      expect(fetchMock).toHaveBeenCalledTimes(1);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
