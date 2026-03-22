import { describe, expect, it } from "vitest";

import {
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
