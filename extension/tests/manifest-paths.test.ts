import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { rewriteManifestForDistribution } from "../build/manifest-paths.mjs";

describe("distribution manifest rewriting", () => {
  it("strips workspace-only dist prefixes for the packed extension output", () => {
    const workspaceManifest = JSON.parse(
      readFileSync(resolve("manifest.json"), "utf-8")
    ) as Record<string, unknown>;

    const distributionManifest = rewriteManifestForDistribution(workspaceManifest) as {
      background?: { service_worker?: string };
      action?: { default_popup?: string; default_icon?: Record<string, string> };
      options_page?: string;
      icons?: Record<string, string>;
      content_scripts?: Array<{ js?: string[] }>;
    };

    expect(distributionManifest.background?.service_worker).toBe("background.js");
    expect(distributionManifest.action?.default_popup).toBe("popup.html");
    expect(distributionManifest.options_page).toBe("options.html");
    expect(distributionManifest.content_scripts?.[0]?.js).toEqual(["content.js"]);
    expect(distributionManifest.content_scripts?.[1]?.js).toEqual(["content.js"]);
    expect(distributionManifest.icons).toEqual({
      "16": "assets/icon-16.png",
      "32": "assets/icon-32.png",
      "48": "assets/icon-48.png",
      "128": "assets/icon-128.png"
    });
    expect(distributionManifest.action?.default_icon).toEqual({
      "16": "assets/icon-16.png",
      "32": "assets/icon-32.png"
    });
  });
});
