import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";

const outputDir = resolve("releases");
const outputPath = resolve(outputDir, "mdtero-extension-webstore.zip");

await mkdir(outputDir, { recursive: true });

const result = spawnSync(
  "python3",
  ["-m", "zipfile", "-c", outputPath, "."],
  { cwd: resolve("dist"), stdio: "inherit" }
);

if (result.status !== 0) {
  process.exit(result.status ?? 1);
}

console.log(`Web Store extension package: releases/mdtero-extension-webstore.zip`);
