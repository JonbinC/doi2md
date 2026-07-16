import { copyFile, mkdir, cp, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import esbuild from "esbuild";
import { rewriteManifestForDistribution } from "./build/manifest-paths.mjs";

const profile = resolveBuildProfile(process.env.MDTERO_EXTENSION_PROFILE);
const nativeMessagingEnabled = profile === "dev";
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
  sourcemap: true,
  define: {
    __MDTERO_NATIVE_MESSAGING_ENABLED__: nativeMessagingEnabled ? "true" : "false"
  },
  plugins: nativeMessagingEnabled
    ? []
    : [
        {
          name: "strip-native-bridge-for-store",
          setup(build) {
            build.onResolve({ filter: /native-bridge(\.ts)?$/ }, (args) => {
              if (args.path.includes("native-bridge.empty")) {
                return null;
              }
              return { path: resolve("src/lib/native-bridge.empty.ts") };
            });
          },
        },
      ],
});
console.log(
  `esbuild define profile=${profile} nativeMessaging=${nativeMessagingEnabled}`
);

await mkdir("dist/assets", { recursive: true });

const manifestSource = nativeMessagingEnabled ? "manifest.dev.json" : "manifest.json";

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

const sourceManifest = JSON.parse(await readFile(manifestSource, "utf-8"));
await writeFile(
  "dist/manifest.json",
  JSON.stringify(rewriteManifestForDistribution(sourceManifest), null, 2)
);

console.log(
  `Extension build output: ${outdir} (${profile}${nativeMessagingEnabled ? ", native messaging enabled" : ", store profile"})`
);

function resolveBuildProfile(rawProfile) {
  const normalized = String(rawProfile || "store").trim().toLowerCase();
  if (normalized === "dev" || normalized === "development") {
    return "dev";
  }
  if (normalized === "store" || normalized === "webstore") {
    return "store";
  }
  throw new Error(`Unknown MDTERO_EXTENSION_PROFILE: ${rawProfile}. Use "store" or "dev".`);
}
