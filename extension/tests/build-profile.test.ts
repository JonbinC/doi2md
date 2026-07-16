import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { describe, expect, it } from "vitest";

describe("extension build profiles", () => {
  it("builds store and dev packages without campus proxy permission or UI", () => {
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
    const storeBackground = readFileSync(resolve("dist/background.js"), "utf-8");

    expect(storeManifest.permissions ?? []).not.toContain("proxy");
    expect(storeOptionsHtml).not.toContain('id="proxy-settings-card"');
    expect(storeBackground).not.toContain("nativeMessaging");
    expect(storeManifest.permissions ?? []).not.toContain("nativeMessaging");

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

    expect(devManifest.permissions ?? []).not.toContain("proxy");
    expect(devManifest.permissions ?? []).toContain("nativeMessaging");
    expect(devOptionsHtml).not.toContain('id="proxy-settings-card"');
  });
});
