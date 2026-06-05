import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";

const outputDir = resolve("releases");
const outputPath = resolve(outputDir, "mdtero-extension-dev.zip");

await mkdir(outputDir, { recursive: true });

const result = spawnSync(
  "python3",
  [
    "-m",
    "zipfile",
    "-c",
    outputPath,
    "dist",
  ],
  { stdio: "inherit" }
);

if (result.status !== 0) {
  process.exit(result.status ?? 1);
}

console.log(`Development extension package: releases/mdtero-extension-dev.zip`);
