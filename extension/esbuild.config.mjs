import { copyFile, mkdir, cp } from "node:fs/promises";
import { resolve } from "node:path";
import esbuild from "esbuild";

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
  copyFile("manifest.json", "dist/manifest.json"),
  copyFile("src/popup/index.html", "dist/popup.html"),
  copyFile("src/options/index.html", "dist/options.html"),
  copyFile("src/styles.css", "dist/styles.css"),
  copyFile("src/assets/icon-16.png", "dist/assets/icon-16.png"),
  copyFile("src/assets/icon-32.png", "dist/assets/icon-32.png"),
  copyFile("src/assets/icon-48.png", "dist/assets/icon-48.png"),
  copyFile("src/assets/icon-128.png", "dist/assets/icon-128.png"),
  cp("_locales", "dist/_locales", { recursive: true })
]);

console.log(`Extension build output: ${outdir}`);
