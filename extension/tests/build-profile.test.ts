import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { describe, expect, it } from "vitest";

describe("extension build profiles", () => {
  it("builds store and dev packages with different proxy surfaces", () => {
    const storeBuild = spawnSync("node", ["esbuild.config.mjs"], {
      cwd: resolve("."),
      env: { ...process.env, MDTERO_EXTENSION_PROFILE: "store" },
      encoding: "utf-8"
    });
    expect(storeBuild.status).toBe(0);

    const storeManifest = JSON.parse(readFileSync(resolve("dist/manifest.json"), "utf-8")) as {
      permissions?: string[];
    };
    const storeOptionsHtml = readFileSync(resolve("dist/options.html"), "utf-8");

    expect(storeManifest.permissions ?? []).not.toContain("proxy");
    expect(storeOptionsHtml).not.toContain('id="proxy-settings-card"');

    const devBuild = spawnSync("node", ["esbuild.config.mjs"], {
      cwd: resolve("."),
      env: { ...process.env, MDTERO_EXTENSION_PROFILE: "dev" },
      encoding: "utf-8"
    });
    expect(devBuild.status).toBe(0);

    const devManifest = JSON.parse(readFileSync(resolve("dist/manifest.json"), "utf-8")) as {
      permissions?: string[];
    };
    const devOptionsHtml = readFileSync(resolve("dist/options.html"), "utf-8");

    expect(devManifest.permissions ?? []).toContain("proxy");
    expect(devOptionsHtml).toContain('id="proxy-settings-card"');
  });
});
