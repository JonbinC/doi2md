import { describe, expect, it } from "vitest";
import { getPublisherCapabilityEntry } from "@mdtero/shared";
import {
  describeCapabilityReadiness,
  formatCapabilityFallbacks,
  formatCapabilityStatusLabel,
  resolveCapabilityReadiness
} from "../src/lib/publisher-capability-view";

describe("extension publisher capability view", () => {
  it("requires helper before any source is actionable", () => {
    const entry = getPublisherCapabilityEntry("arxiv");
    expect(entry).toBeDefined();

    expect(
      resolveCapabilityReadiness(entry!, {
        helperState: "unavailable",
        hasElsevierApiKey: false,
        hasSpringerOpenAccessApiKey: false
      })
    ).toBe("needs_helper");
  });

  it("detects when an API-key source is still missing its key", () => {
    const entry = getPublisherCapabilityEntry("elsevier");
    expect(entry).toBeDefined();

    expect(
      resolveCapabilityReadiness(entry!, {
        helperState: "connected",
        hasElsevierApiKey: false,
        hasSpringerOpenAccessApiKey: false
      })
    ).toBe("needs_api_key");

    expect(
      describeCapabilityReadiness("needs_api_key", "en")
    ).toContain("Add API key");
  });

  it("keeps browser-assisted sources readable instead of pretending they are blocked", () => {
    const entry = getPublisherCapabilityEntry("springer_subscription");
    expect(entry).toBeDefined();

    expect(
      resolveCapabilityReadiness(entry!, {
        helperState: "connected",
        hasElsevierApiKey: false,
        hasSpringerOpenAccessApiKey: false
      })
    ).toBe("browser_required");

    expect(describeCapabilityReadiness("browser_required", "zh")).toContain("浏览器");
  });

  it("formats localized status and fallback labels from shared values", () => {
    expect(formatCapabilityStatusLabel("stable", "en")).toBe("Stable");
    expect(formatCapabilityStatusLabel("experimental", "zh")).toBe("实验");
    expect(formatCapabilityFallbacks(["browser_page_capture", "pdf"], "en")).toBe(
      "Browser page capture → PDF"
    );
    expect(formatCapabilityFallbacks(["pdf"], "zh")).toBe("PDF");
  });
});
