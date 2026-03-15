import { describe, expect, it } from "vitest";

import { createParseMessage, createTranslateMessage } from "../src/lib/runtime";
import {
  getActionStatusText,
  getDownloadLabel,
  getPreferredArtifactKey,
  getSavedResultSummary,
  getSecondaryArtifactKeys,
  getSourceArtifactKeys
} from "../src/popup/task-view";

describe("createParseMessage", () => {
  it("builds a parse message from detected DOI", () => {
    expect(createParseMessage("10.1016/j.conbuildmat.2026.145877")).toEqual({
      type: "mdtero.parse.request",
      input: "10.1016/j.conbuildmat.2026.145877"
    });
  });
});

describe("createTranslateMessage", () => {
  it("builds a translation message from a parsed markdown path", () => {
    expect(
      createTranslateMessage("/tmp/zhou2025performance/paper.md", "zh", "standard")
    ).toEqual({
      type: "mdtero.translate.request",
      sourceMarkdownPath: "/tmp/zhou2025performance/paper.md",
      targetLanguage: "zh",
      mode: "standard"
    });
  });
});

describe("getPreferredArtifactKey", () => {
  it("prefers paper bundles over raw markdown downloads", () => {
    expect(
      getPreferredArtifactKey({
        preferred_artifact: "paper_bundle",
        artifacts: {
          paper_bundle: {
            path: "/tmp/paper_bundle.zip",
            filename: "zhou2025performance_bundle.zip",
            media_type: "application/zip"
          },
          paper_md: {
            path: "/tmp/paper.md",
            filename: "zhou2025performance.md",
            media_type: "text/markdown"
          }
        }
      })
    ).toBe("paper_bundle");
  });
});

describe("getSecondaryArtifactKeys", () => {
  it("only keeps translated markdown as a secondary main action", () => {
    expect(
      getSecondaryArtifactKeys({
        preferred_artifact: "paper_bundle",
        artifacts: {
          paper_bundle: {
            path: "/tmp/tang2026simulation.zip",
            filename: "tang2026simulation.zip",
            media_type: "application/zip"
          },
          paper_md: {
            path: "/tmp/paper.md",
            filename: "tang2026simulation.md",
            media_type: "text/markdown"
          },
          paper_xml: {
            path: "/tmp/paper.xml",
            filename: "tang2026simulation.xml",
            media_type: "application/xml"
          },
          translated_md: {
            path: "/tmp/tang2026simulation.zh.md",
            filename: "tang2026simulation.zh.md",
            media_type: "text/markdown"
          }
        }
      })
    ).toEqual(["translated_md"]);
  });
});

describe("getSourceArtifactKeys", () => {
  it("surfaces pdf and xml in a dedicated source-files section", () => {
    expect(
      getSourceArtifactKeys({
        preferred_artifact: "paper_bundle",
        artifacts: {
          paper_bundle: {
            path: "/tmp/tang2026simulation.zip",
            filename: "tang2026simulation.zip",
            media_type: "application/zip"
          },
          paper_pdf: {
            path: "/tmp/tang2026simulation.pdf",
            filename: "tang2026simulation.pdf",
            media_type: "application/pdf"
          },
          paper_xml: {
            path: "/tmp/tang2026simulation.xml",
            filename: "tang2026simulation.xml",
            media_type: "application/xml"
          }
        }
      })
    ).toEqual(["paper_pdf", "paper_xml"]);
  });
});

describe("getDownloadLabel", () => {
  it("renders localized user-facing labels instead of artifact keys", () => {
    expect(getDownloadLabel("paper_bundle", "en")).toBe(
      "Download ZIP"
    );
    expect(getDownloadLabel("translated_md", "en")).toBe("Download Translation");
    expect(getDownloadLabel("paper_pdf", "en")).toBe(
      "Download PDF"
    );
    expect(getDownloadLabel("paper_xml", "en")).toBe(
      "Download XML"
    );
    expect(getDownloadLabel("paper_bundle", "zh")).toBe("下载压缩包");
    expect(getDownloadLabel("translated_md", "zh")).toBe("下载译文");
  });
});

describe("getActionStatusText", () => {
  it("avoids surfacing raw task identifiers in status copy", () => {
    expect(getActionStatusText("detecting", "en")).toBe("Detecting DOI from this page...");
    expect(getActionStatusText("queued_parse", "en")).toBe("Parse request sent. Preparing files...");
    expect(getActionStatusText("running_parse", "en")).toBe("Parsing paper and packaging files...");
    expect(getActionStatusText("queued_translate", "zh")).toBe("翻译任务已提交，正在准备...");
    expect(getActionStatusText("failed", "zh")).toBe("处理失败，请重试。");
  });
});

describe("getSavedResultSummary", () => {
  it("summarizes saved results with stable filenames only", () => {
    expect(
      getSavedResultSummary(
        {
          input: "10.1016/j.conbuildmat.2026.145877",
          parseTaskId: "task-1",
          parseFilename: "tang2026simulation.zip",
          translatedTaskId: "task-2",
          translatedFilename: "tang2026simulation.zh.md"
        },
        "en"
      )
    ).toBe("Ready: tang2026simulation.zh.md");
    expect(
      getSavedResultSummary(
        {
          input: "10.1016/j.conbuildmat.2026.145877",
          parseTaskId: "task-1",
          parseFilename: "tang2026simulation.zip"
        },
        "zh"
      )
    ).toBe("已就绪：tang2026simulation.zip");
  });
});
