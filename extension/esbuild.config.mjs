import { copyFile, mkdir, cp, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import esbuild from "esbuild";
import { rewriteManifestForDistribution } from "./build/manifest-paths.mjs";

const outdir = resolve("dist");

await mkdir(outdir, { recursive: true });

await esbuild.build({
  entryPoints: {
    background: "src/background.ts",
    content: "src/content.ts",
    popup: "src/popup/index.ts",
    options: "src/options/index.ts"
  },
  bundle: true,
  format: "esm",
  outdir,
  sourcemap: true
});

await mkdir("dist/assets", { recursive: true });

await Promise.all([
  copyFile("src/popup/index.html", "dist/popup.html"),
  copyFile("src/options/index.html", "dist/options.html"),
  copyFile("src/styles.css", "dist/styles.css"),
  copyFile("src/assets/icon-16.png", "dist/assets/icon-16.png"),
  copyFile("src/assets/icon-32.png", "dist/assets/icon-32.png"),
  copyFile("src/assets/icon-48.png", "dist/assets/icon-48.png"),
  copyFile("src/assets/icon-128.png", "dist/assets/icon-128.png"),
  cp("_locales", "dist/_locales", { recursive: true })
]);

const sourceManifest = JSON.parse(await readFile("manifest.json", "utf-8"));
await writeFile(
  "dist/manifest.json",
  JSON.stringify(rewriteManifestForDistribution(sourceManifest), null, 2)
);

console.log(`Extension build output: ${outdir}`);
