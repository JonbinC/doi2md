import { describe, expect, it } from "vitest";

import { buildHelperBundleBlob } from "../src/lib/helper-bundle";

describe("buildHelperBundleBlob", () => {
  it("packages a browser-captured html payload into a helper bundle zip", async () => {
    const blob = buildHelperBundleBlob({
      connector: "springer_subscription_connector",
      artifactKind: "html",
      payload: "<html><body><article>Demo</article></body></html>",
      payloadName: "paper.html",
      sourceUrl: "https://link.springer.com/article/10.1000/demo",
      access: "licensed"
    });

    expect(blob.type).toBe("application/zip");
    const bytes = new Uint8Array(await blob.arrayBuffer());
    expect(bytes[0]).toBe(0x50);
    expect(bytes[1]).toBe(0x4b);
    const text = new TextDecoder().decode(bytes);
    expect(text).toContain("manifest.json");
    expect(text).toContain("paper.html");
    expect(text).toContain("springer_subscription_connector");
    expect(text).toContain("\"artifact_kind\":\"html\"");
  });

  it("marks local PDF uploads as user-retained helper bundles", async () => {
    const blob = buildHelperBundleBlob({
      connector: "local_file_upload",
      artifactKind: "pdf",
      payload: new Uint8Array([0x25, 0x50, 0x44, 0x46]),
      payloadName: "paper.pdf",
      sourceType: "browser_extension_local_upload_pdf",
      sourceUrl: "file://demo.pdf"
    });

    const text = new TextDecoder().decode(new Uint8Array(await blob.arrayBuffer()));
    expect(text).toContain("local_file_upload");
    expect(text).toContain("\"artifact_kind\":\"pdf\"");
    expect(text).toContain("\"user_private_retention\":true");
    expect(text).toContain("paper.pdf");
  });

  it("packages declared extra asset files into the helper bundle manifest and archive", async () => {
    const blob = buildHelperBundleBlob({
      connector: "springer_subscription_connector",
      artifactKind: "html",
      payload: "<html><body><article>Demo</article></body></html>",
      payloadName: "paper.html",
      sourceUrl: "https://link.springer.com/article/10.1000/demo",
      access: "licensed",
      extraFiles: {
        "assets/figure-1.png": new Uint8Array([0x89, 0x50, 0x4e, 0x47])
      }
    });

    const text = new TextDecoder().decode(new Uint8Array(await blob.arrayBuffer()));
    expect(text).toContain("\"artifact_kind\":\"html\"");
    expect(text).toContain("\"extra_files\":[\"assets/figure-1.png\"]");
    expect(text).toContain("paper.html");
    expect(text).toContain("assets/figure-1.png");
  });
});
