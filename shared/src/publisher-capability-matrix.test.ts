import { describe, expect, it } from "vitest";
import * as shared from "./index";

describe("publisher capability matrix", () => {
  it("exports a shared matrix and locale-aware grouping helpers", () => {
    expect(shared).toHaveProperty("PUBLISHER_CAPABILITY_MATRIX");
    expect(shared).toHaveProperty("getPublisherCapabilityGroups");
    expect(shared).toHaveProperty("getPublisherCapabilityEntry");
  });

  it("covers the agreed first-pass sources with stable ids", () => {
    const matrix = (shared as Record<string, unknown>).PUBLISHER_CAPABILITY_MATRIX as Array<Record<string, unknown>>;

    expect(Array.isArray(matrix)).toBe(true);
    expect(matrix).toHaveLength(11);
    expect(matrix.map((entry) => entry.id)).toEqual([
      "arxiv",
      "pmc_europe_pmc",
      "plos",
      "biorxiv_medrxiv",
      "chemrxiv",
      "mdpi",
      "elsevier",
      "springer_oa",
      "springer_subscription",
      "wiley",
      "taylor_francis"
    ]);
  });

  it("stores structured user-facing metadata for rendering", () => {
    const matrix = (shared as Record<string, unknown>).PUBLISHER_CAPABILITY_MATRIX as Array<Record<string, unknown>>;
    const elsevier = matrix.find((entry) => entry.id === "elsevier");
    const springerSubscription = matrix.find((entry) => entry.id === "springer_subscription");

    expect(elsevier).toMatchObject({
      variantOf: "elsevier",
      accessVariant: "api",
      presentationGroup: "api_key",
      rightsMode: "licensed",
      acquisitionMode: "official_api",
      requiresHelper: true,
      requiresBrowser: false,
      requiresApiKey: true,
      mayNeedInstitutionAccess: true,
      configureTarget: "connector_keys",
      status: "stable",
      validationRef: expect.any(String)
    });
    expect((elsevier?.fallbacks as unknown[] | undefined) ?? []).toContain("pdf");

    expect(springerSubscription).toMatchObject({
      variantOf: "springer",
      accessVariant: "subscription_page",
      presentationGroup: "browser_assisted",
      rightsMode: "licensed",
      acquisitionMode: "browser_page_capture",
      requiresHelper: true,
      requiresBrowser: true,
      requiresApiKey: false,
      configureTarget: "browser_assisted_sources",
      status: "demo"
    });
  });

  it("returns localized groups for English and Chinese", () => {
    const getGroups = (shared as Record<string, unknown>).getPublisherCapabilityGroups as
      | ((language: "en" | "zh") => Array<Record<string, unknown>>)
      | undefined;

    const enGroups = getGroups?.("en") ?? [];
    const zhGroups = getGroups?.("zh") ?? [];

    expect(enGroups.map((group) => group.id)).toEqual([
      "helper_only",
      "api_key",
      "browser_assisted"
    ]);
    expect(enGroups.map((group) => group.label)).toEqual([
      "Helper only",
      "Helper + API key",
      "Helper + browser extension"
    ]);
    expect(zhGroups.map((group) => group.label)).toEqual([
      "只需本地 helper",
      "需要 helper 和 API key",
      "需要 helper 和浏览器扩展"
    ]);
  });
});
