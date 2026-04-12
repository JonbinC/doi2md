import { describe, expect, it } from "vitest";

import {
  createFileParseMessage,
  createParseMessage,
  createTranslateMessage
} from "../src/lib/runtime";
import {
  getActionStatusText,
  getBridgeStatusText,
  getDownloadLabel,
  getPreflightHintText,
  getUsageStatusText,
  getPreferredArtifactKey,
  getResultWarningText,
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

  it("can include current-page context for helper-first capture", () => {
    expect(
      createParseMessage("https://example.com/paper", undefined, {
        tabId: 42,
        tabUrl: "https://example.com/paper"
      })
    ).toEqual({
      type: "mdtero.parse.request",
      input: "https://example.com/paper",
      pageContext: {
        tabId: 42,
        tabUrl: "https://example.com/paper"
      }
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

describe("createFileParseMessage", () => {
  it("builds a PDF local file parse message with an explicit grobid engine", () => {
    const file = new File(["pdf"], "demo.pdf", { type: "application/pdf" });

    expect(createFileParseMessage(file, "pdf", "grobid")).toEqual({
      type: "mdtero.parse.file.request",
      file,
      filename: "demo.pdf",
      mediaType: "application/pdf",
      artifactKind: "pdf",
      pdfEngine: "grobid"
    });
  });

  it("keeps the default PDF local file parse message engine-free so backend auto-resolution can decide", () => {
    const file = new File(["pdf"], "demo.pdf", { type: "application/pdf" });

    expect(createFileParseMessage(file, "pdf")).toEqual({
      type: "mdtero.parse.file.request",
      file,
      filename: "demo.pdf",
      mediaType: "application/pdf",
      artifactKind: "pdf"
    });
  });

  it("keeps the default PDF local file parse message engine-free so backend auto-resolution can decide", () => {
    const file = new File(["pdf"], "demo.pdf", { type: "application/pdf" });

    expect(createFileParseMessage(file, "pdf")).toEqual({
      type: "mdtero.parse.file.request",
      file,
      filename: "demo.pdf",
      mediaType: "application/pdf",
      artifactKind: "pdf"
    });
  });

  it("builds an EPUB local file parse message without a PDF engine", () => {
    const file = new File(["epub"], "demo.epub", { type: "application/epub+zip" });

    expect(createFileParseMessage(file, "epub")).toEqual({
      type: "mdtero.parse.file.request",
      file,
      filename: "demo.epub",
      mediaType: "application/epub+zip",
      artifactKind: "epub"
    });
  });
});

describe("getPreferredArtifactKey", () => {
  it("returns the backend-selected primary artifact", () => {
    expect(
      getPreferredArtifactKey({
        preferred_artifact: "paper_md",
        artifacts: {
          paper_md: {
            path: "/tmp/paper.md",
            filename: "zhou2025performance.md",
            media_type: "text/markdown"
          },
          paper_bundle: {
            path: "/tmp/paper_bundle.zip",
            filename: "zhou2025performance.zip",
            media_type: "application/zip"
          }
        }
      })
    ).toBe("paper_md");
  });
});

describe("getSecondaryArtifactKeys", () => {
  it("keeps fallback zip and translation as secondary actions when markdown is primary", () => {
    expect(
      getSecondaryArtifactKeys({
        preferred_artifact: "paper_md",
        artifacts: {
          paper_md: {
            path: "/tmp/paper.md",
            filename: "tang2026simulation.md",
            media_type: "text/markdown"
          },
          paper_bundle: {
            path: "/tmp/tang2026simulation.zip",
            filename: "tang2026simulation.zip",
            media_type: "application/zip"
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
    ).toEqual(["paper_bundle", "translated_md"]);
  });

  it("keeps markdown available when zip becomes the fallback-safe primary action", () => {
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
          translated_md: {
            path: "/tmp/tang2026simulation.zh.md",
            filename: "tang2026simulation.zh.md",
            media_type: "text/markdown"
          }
        }
      })
    ).toEqual(["paper_md", "translated_md"]);
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
    expect(getDownloadLabel("paper_md", "en")).toBe("Download Markdown");
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
    expect(getDownloadLabel("paper_md", "zh")).toBe("下载 Markdown");
    expect(getDownloadLabel("paper_bundle", "zh")).toBe("下载压缩包");
    expect(getDownloadLabel("translated_md", "zh")).toBe("下载译文");
  });
});

describe("getActionStatusText", () => {
  it("avoids surfacing raw task identifiers in status copy", () => {
    expect(getActionStatusText("detecting", "en")).toBe("Detecting DOI from this page...");
    expect(getActionStatusText("queued_parse", "en")).toBe("Parse request sent. Preparing files...");
    expect(getActionStatusText("running_parse", "en")).toBe("Parsing paper and preparing Markdown...");
    expect(getActionStatusText("queued_translate", "zh")).toBe("翻译任务已提交，正在准备...");
    expect(getActionStatusText("failed", "zh")).toBe("处理失败，请重试。");
  });
});

describe("getUsageStatusText", () => {
  it("formats usage summaries from live account data", () => {
    expect(
      getUsageStatusText(
        {
          wallet_balance_display: "¥5.00",
          parse_quota_remaining: 156,
          translation_quota_remaining: 26
        },
        "zh"
      )
    ).toBe("余额 ¥5.00 · 解析 156 · 翻译 26");
  });

  it("preserves backend or network errors instead of masking them as sign-in hints", () => {
    expect(getUsageStatusText(null, "en", "503 Service Unavailable")).toBe("503 Service Unavailable");
    expect(getUsageStatusText(null, "zh", "请求超时")).toBe("请求超时");
  });
});

describe("getBridgeStatusText", () => {
  it("formats helper bridge status for popup surfaces", () => {
    expect(getBridgeStatusText({ state: "connected", runnerState: "idle" }, "en")).toBe(
      "Local helper ready for browser-assisted capture."
    );
    expect(getBridgeStatusText({ state: "connected", runnerState: "busy" }, "zh")).toBe(
      "本地 helper 已连接，正在处理浏览器任务。"
    );
    expect(getBridgeStatusText({ state: "unavailable", runnerState: "idle" }, "en")).toContain(
      "not detected"
    );
    expect(getBridgeStatusText(undefined, "zh")).toBe("本地 helper 状态未知。");
  });
});

describe("getPreflightHintText", () => {
  it("warns when Elsevier input is missing the required API key", () => {
    expect(
      getPreflightHintText(
        {
          input: "https://www.sciencedirect.com/science/article/pii/S0016236124023456",
          hasElsevierApiKey: false
        },
        "en"
      )
    ).toContain("Elsevier / ScienceDirect");
    expect(
      getPreflightHintText(
        {
          input: "https://www.sciencedirect.com/science/article/pii/S0016236124023456",
          hasElsevierApiKey: false
        },
        "en"
      )
    ).toContain("campus or institutional network");
  });

  it("warns when a supported live page is open but the helper is unavailable", () => {
    expect(
      getPreflightHintText(
        {
          input: "https://onlinelibrary.wiley.com/doi/full/10.1002/er.7490",
          pageUrl: "https://onlinelibrary.wiley.com/doi/full/10.1002/er.7490",
          bridgeStatus: { state: "unavailable", runnerState: "idle" },
          hasElsevierApiKey: true
        },
        "en"
      )
    ).toContain("Start `mdtero`");
  });

  it("confirms helper-first capture readiness on supported live pages", () => {
    expect(
      getPreflightHintText(
        {
          input: "https://arxiv.org/html/2401.00001",
          pageUrl: "https://arxiv.org/html/2401.00001",
          bridgeStatus: { state: "connected", runnerState: "idle" },
          hasElsevierApiKey: true
        },
        "zh"
      )
    ).toContain("helper-first");
  });

  it("nudges users away from PDF or EPUB shells", () => {
    expect(
      getPreflightHintText(
        {
          input: "https://www.tandfonline.com/doi/epub/10.1080/26395940.2021.1947159?download=true",
          pageUrl: "https://www.tandfonline.com/doi/epub/10.1080/26395940.2021.1947159?download=true",
          bridgeStatus: { state: "connected", runnerState: "idle" }
        },
        "en"
      )
    ).toContain("HTML full-text page");
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

describe("getResultWarningText", () => {
  it("localizes the abstract-only Elsevier campus-network hint", () => {
    expect(
      getResultWarningText(
        {
          warning_code: "elsevier_abstract_only",
          warning_message: "Elsevier only returned the abstract."
        },
        "en"
      )
    ).toContain("campus or institutional network IP");
    expect(
      getResultWarningText(
        {
          warning_code: "elsevier_abstract_only",
          warning_message: "Elsevier only returned the abstract."
        },
        "zh"
      )
    ).toContain("校园网");
  });
});
