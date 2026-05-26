import { describe, expect, it } from "vitest";

import {
  createFileParseMessage,
  createSsotParseMessage,
  createTranslateMessage
} from "../src/lib/runtime";
import {
  getActionStatusText,
  getBridgeStatusText,
  getDownloadLabel,
  getPreflightHintText,
  buildCliParseCommand,
  buildCliFileParseCommand,
  getCliHandoffNote,
  normalizeCliHandoffCommand,
  shouldShowCliHandoffForPreflight,
  getUsageStatusText,
  getArtifactFilename,
  getPreferredArtifactKey,
  getResultWarningText,
  getTaskFailureText,
  getTaskFailureCliHandoff,
  firstNextCommand,
  firstTaskNextCommand,
  getTranslationAttemptSummary,
  getSavedResultSummary,
  getDownloadFailureText,
  getSecondaryArtifactKeys,
  getSourceArtifactKeys
} from "../src/popup/task-view";

describe("createSsotParseMessage", () => {
  it("builds the popup parse message for backend SSOT route planning", () => {
    expect(
      createSsotParseMessage("10.1002/demo", {
        tabId: 42,
        tabUrl: "https://onlinelibrary.wiley.com/doi/full/10.1002/demo"
      })
    ).toEqual({
      type: "mdtero.parse.ssot.request",
      input: "10.1002/demo",
      pageContext: {
        tabId: 42,
        tabUrl: "https://onlinelibrary.wiley.com/doi/full/10.1002/demo"
      }
    });
  });
});

describe("createTranslateMessage", () => {
  it("builds a translation message from a parsed markdown path", () => {
    expect(
      createTranslateMessage({ path: "/tmp/zhou2025performance/paper.md" }, "zh", "standard")
    ).toEqual({
      type: "mdtero.translate.request",
      sourceMarkdownPath: "/tmp/zhou2025performance/paper.md",
      targetLanguage: "zh",
      mode: "standard"
    });
  });

  it("builds a translation message from a v1 task artifact when no server path is exposed", () => {
    expect(
      createTranslateMessage(
        {
          taskId: "task-parse",
          artifactKey: "paper_md",
          filename: "vaswani2017attention.md"
        },
        "zh",
        "standard"
      )
    ).toEqual({
      type: "mdtero.translate.request",
      sourceMarkdownPath: undefined,
      sourceTaskId: "task-parse",
      sourceArtifactKey: "paper_md",
      sourceFilename: "vaswani2017attention.md",
      targetLanguage: "zh",
      mode: "standard"
    });
  });
});

describe("createFileParseMessage", () => {
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

  it("uses v1 download_artifacts when legacy artifact descriptors are absent", () => {
    expect(
      getPreferredArtifactKey({
        preferred_artifact: "paper_md",
        download_artifacts: [
          { artifact: "paper_md", filename: "zhou2025performance.md", media_type: "text/markdown" },
          { artifact: "paper_bundle", filename: "zhou2025performance.zip", media_type: "application/zip" }
        ]
      })
    ).toBe("paper_md");
  });
});

describe("getArtifactFilename", () => {
  it("falls back to v1 download_artifacts filenames", () => {
    expect(
      getArtifactFilename(
        {
          download_artifacts: [
            { artifact: "paper_md", filename: "chen2026hydrate.md", media_type: "text/markdown" }
          ]
        },
        "paper_md"
      )
    ).toBe("chen2026hydrate.md");
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

  it("keeps secondary actions from v1 download_artifacts", () => {
    expect(
      getSecondaryArtifactKeys({
        preferred_artifact: "paper_md",
        download_artifacts: [
          { artifact: "paper_md", filename: "tang2026simulation.md" },
          { artifact: "paper_bundle", filename: "tang2026simulation.zip" },
          { artifact: "translated_md", filename: "tang2026simulation_CN.md" }
        ]
      })
    ).toEqual(["paper_bundle", "translated_md"]);
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

  it("surfaces source files from v1 download_artifacts", () => {
    expect(
      getSourceArtifactKeys({
        download_artifacts: [
          { artifact: "paper_pdf", filename: "source.pdf" },
          { artifact: "paper_xml", filename: "source.xml" }
        ]
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
  it("formats browser capture status for popup surfaces", () => {
    expect(getBridgeStatusText({ state: "connected", runnerState: "idle" }, "en")).toBe(
      "The extension can read this paper page and upload page content when needed."
    );
    expect(getBridgeStatusText({ state: "connected", runnerState: "busy" }, "zh")).toBe(
      "扩展正在读取当前论文页。"
    );
    expect(getBridgeStatusText({ state: "unavailable", runnerState: "idle" }, "en")).toContain(
      "unavailable"
    );
    expect(getBridgeStatusText(undefined, "zh")).toBe("当前页面读取状态未知。");
  });
});

describe("getPreflightHintText", () => {
  it("keeps publisher-specific URL inputs on the generic browser-capture path", () => {
    const hint = getPreflightHintText(
      {
        input: "https://www.sciencedirect.com/science/article/pii/S0016236124023456",
        pageUrl: "https://www.sciencedirect.com/science/article/pii/S0016236124023456",
        bridgeStatus: { state: "connected", runnerState: "idle" },
      },
      "en"
    );

    expect(hint).toContain("extension");
    expect(hint).toContain("uploaded to Mdtero");
    expect(hint).not.toContain("Elsevier");
    expect(hint).not.toContain("ScienceDirect");
    expect(hint).not.toContain("publisher keys");
  });

  it("warns when a supported live page is open but browser capture is unavailable", () => {
    const hint = getPreflightHintText(
        {
          input: "https://onlinelibrary.wiley.com/doi/full/10.1002/er.7490",
          pageUrl: "https://onlinelibrary.wiley.com/doi/full/10.1002/er.7490",
          bridgeStatus: { state: "unavailable", runnerState: "idle" },
        },
        "en"
      );

    expect(hint).toContain("mdtero parse");
    expect(shouldShowCliHandoffForPreflight(hint, "https://onlinelibrary.wiley.com/doi/full/10.1002/er.7490")).toBe(true);
  });

  it("confirms local capture readiness on supported live pages", () => {
    expect(
      getPreflightHintText(
        {
          input: "https://arxiv.org/html/2401.00001",
          pageUrl: "https://arxiv.org/html/2401.00001",
          bridgeStatus: { state: "connected", runnerState: "idle" },
        },
        "zh"
      )
    ).toContain("扩展读取");
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

describe("getCliHandoffNote", () => {
  it("explains terminal handoff for campus-network and challenge-page cases", () => {
    expect(getCliHandoffNote("mdtero parse https://example.org/paper --trace --wait --timeout 300 --json", "en")).toContain("campus networks");
    expect(getCliHandoffNote("mdtero parse https://example.org/paper --trace --wait --timeout 300 --json", "zh")).toContain("反爬挑战页");
  });

  it("explains file-upload command placeholders separately", () => {
    expect(getCliHandoffNote("mdtero parse --file paper.pdf --trace --wait --timeout 300 --json", "en")).toContain("replace the path");
    expect(getCliHandoffNote("mdtero parse --file paper.pdf --trace --wait --timeout 300 --json", "zh")).toContain("文件路径");
  });

  it("redacts sensitive URLs and provider secrets from task failure text", () => {
    const text = getTaskFailureText(
      {
        error_message:
          "MinerU failed at https://mineru.oss-cn-shanghai.aliyuncs.com/file.pdf?OSSAccessKeyId=abc&Signature=sig&security-token=tok",
        error_code: "uploaded_pdf_v2_parse_failed",
        reason_code: "mineru_urlapi_timeout",
        action_hint: "Retry later; Bearer voyage-secret-token api_key=raw-key",
        next_commands: ["mdtero parse --file paper.pdf --json"],
        result: {
          translation_attempts: [
            {
              provider: "codex",
              reason_code: "translation_provider_auth_failed",
              provider_status_code: 401,
              message: "Bearer codex-secret-token failed"
            }
          ]
        }
      },
      "failed",
      "en"
    );

    expect(text).toContain("[redacted-url]");
    expect(text).toContain("Bearer [redacted]");
    expect(text).not.toContain("OSSAccessKeyId=abc");
    expect(text).not.toContain("Signature=sig");
    expect(text).not.toContain("security-token=tok");
    expect(text).not.toContain("voyage-secret-token");
    expect(text).not.toContain("codex-secret-token");
    expect(text).not.toContain("raw-key");
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

describe("getDownloadFailureText", () => {
  it("surfaces backend download failure detail without leaking signed URLs", () => {
    const text = getDownloadFailureText(
      new Error(
        "artifact not available. Reason: parser_failed Next: retry https://mineru.oss-cn-shanghai.aliyuncs.com/file.pdf?OSSAccessKeyId=abc&Signature=sig&security-token=tok"
      ),
      "Download failed. Please try again.",
      "en"
    );

    expect(text).toContain("Download failed. Please try again. Detail: artifact not available");
    expect(text).toContain("Reason: parser_failed");
    expect(text).toContain("[redacted-url]");
    expect(text).not.toContain("OSSAccessKeyId=abc");
    expect(text).not.toContain("Signature=sig");
    expect(text).not.toContain("security-token=tok");
  });

  it("localizes empty download failures to the existing fallback", () => {
    expect(getDownloadFailureText(null, "下载失败，请重试。", "zh")).toBe("下载失败，请重试。");
  });
});

describe("getResultWarningText", () => {
  it("localizes abstract-only publisher access hints", () => {
    expect(
      getResultWarningText(
        {
          warning_code: "publisher_abstract_only",
          warning_message: "The source only returned an abstract."
        },
        "en"
      )
    ).toContain("institutional access");
    expect(
      getResultWarningText(
        {
          warning_code: "publisher_abstract_only",
          warning_message: "The source only returned an abstract."
        },
        "zh"
      )
    ).toContain("校园网");
  });

  it("keeps legacy abstract-only warning codes generic while backend rollout catches up", () => {
    expect(
      getResultWarningText(
        {
          warning_code: "elsevier_abstract_only",
          warning_message: "Elsevier only returned the abstract."
        },
        "en"
      )
    ).not.toContain("Elsevier");
  });
});

describe("getTaskFailureText", () => {
  it("surfaces backend reason codes and action hints for failed tasks", () => {
    expect(
      getTaskFailureText(
        {
          error_message: "MinerU timed out while fetching the PDF.",
          error_code: "uploaded_pdf_v2_parse_failed",
          reason_code: "mineru_urlapi_timeout",
          action_hint: "Retry later or upload a smaller PDF.",
          next_commands: ["mdtero parse --file paper.pdf --trace --json"]
        },
        "Parse failed. Please try again.",
        "en"
      )
    ).toBe(
      "MinerU timed out while fetching the PDF. Reason: mineru_urlapi_timeout Next: Retry later or upload a smaller PDF. Command: mdtero parse --file paper.pdf --trace --wait --timeout 300 --json"
    );
  });

  it("falls back to result-level reasons and localizes labels", () => {
    expect(
      getTaskFailureText(
        {
          error_message: null,
          error_code: "parser_failed",
          reason_code: null,
          action_hint: null,
          result: {
            reason_code: "client_acquisition_challenge_page",
            action_hint: "请用扩展上传 PDF/EPUB，或在 CLI 中继续。"
          }
        },
        "解析失败，请重试。",
        "zh"
      )
    ).toBe("解析失败，请重试。 原因：client_acquisition_challenge_page 下一步：请用扩展上传 PDF/EPUB，或在 CLI 中继续。");
  });

  it("summarizes translation provider attempts for failed translation tasks", () => {
    expect(
      getTaskFailureText(
        {
          error_message: "translate provider chain failed",
          error_code: "translation_provider_chain_failed",
          reason_code: "translation_provider_chain_failed",
          action_hint: "Refresh provider API keys or quota.",
          result: {
            translation_attempts: [
              {
                provider: "codex",
                reason_code: "translation_provider_auth_failed",
                provider_error_code: "auth_error",
                provider_status_code: 401
              },
              {
                provider: "local_legacy",
                reason_code: "translation_provider_rate_limited",
                provider_error_code: "rate_limited",
                provider_status_code: 429
              }
            ]
          }
        },
        "Translation failed. Please try again.",
        "en"
      )
    ).toContain(
      "Provider attempts: codex: translation_provider_auth_failed 401; local_legacy: translation_provider_rate_limited 429"
    );
  });

  it("localizes translation provider attempt summaries", () => {
    expect(
      getTranslationAttemptSummary(
        [
          {
            provider: "mimo",
            reason_code: "translation_provider_auth_failed",
            provider_status_code: 401
          }
        ],
        "zh"
      )
    ).toBe("服务端尝试：mimo: translation_provider_auth_failed 401");
  });

  it("summarizes skipped translation provider configuration attempts", () => {
    expect(
      getTaskFailureText(
        {
          error_message: "No translation provider configured.",
          error_code: "translation_provider_not_configured",
          reason_code: "translation_provider_not_configured",
          action_hint: "No server translation provider is configured. Operators need to configure provider keys before retrying.",
          result: {
            translation_attempts: [
              {
                provider: "mimo",
                status: "skipped",
                reason_code: "translation_provider_not_configured",
                message: "missing MIMO_API_KEY"
              },
              {
                provider: "codex",
                status: "skipped",
                reason_code: "translation_provider_not_configured",
                message: "missing CODEX_API_KEY or OPENAI_API_KEY"
              }
            ]
          }
        },
        "Translation failed. Please try again.",
        "en"
      )
    ).toContain(
      "Provider attempts: mimo: translation_provider_not_configured skipped missing MIMO_API_KEY; codex: translation_provider_not_configured skipped missing CODEX_API_KEY or OPENAI_API_KEY"
    );
  });

  it("selects the first non-empty next command for CLI handoff", () => {
    expect(firstNextCommand(["", "  ", "mdtero rag status --json"])).toBe("mdtero rag status --json");
    expect(firstNextCommand(["mdtero parse --file paper.pdf --trace --json"])).toBe("mdtero parse --file paper.pdf --trace --wait --timeout 300 --json");
    expect(firstNextCommand(null)).toBe("");
  });

  it("uses backend next commands for failed translation handoff", () => {
    expect(
      getTaskFailureCliHandoff(
        {
          next_commands: [
            "mdtero translate task-123 --to zh-CN --wait --timeout 600 --json"
          ]
        },
        "10.1000/demo",
        "translate"
      )
    ).toBe("mdtero translate task-123 --to zh-CN --wait --timeout 600 --json");
  });

  it("falls back to a traceable parse command only for parse failures", () => {
    expect(
      getTaskFailureCliHandoff(
        {
          next_commands: []
        },
        "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC7517829/fullTextXML",
        "parse"
      )
    ).toBe(
      "mdtero parse https://www.ebi.ac.uk/europepmc/webservices/rest/PMC7517829/fullTextXML --trace --wait --timeout 300 --json"
    );
  });

  it("does not invent a parse handoff for failed translation tasks without next commands", () => {
    expect(
      getTaskFailureCliHandoff(
        {
          next_commands: [],
          result: { next_commands: [] }
        },
        "10.1000/demo",
        "translate"
      )
    ).toBe("");
  });

  it("falls back to result-level next commands for CLI handoff", () => {
    expect(
      firstTaskNextCommand({
        next_commands: [],
        result: {
          next_commands: ["mdtero parse https://example.org/paper --json"]
        }
      })
    ).toBe("mdtero parse https://example.org/paper --trace --wait --timeout 300 --json");
  });
});

describe("normalizeCliHandoffCommand", () => {
  it("keeps parse handoffs aligned with the wait-first CLI contract", () => {
    expect(normalizeCliHandoffCommand("mdtero parse 10.1000/demo --json")).toBe("mdtero parse 10.1000/demo --trace --wait --timeout 300 --json");
    expect(normalizeCliHandoffCommand("mdtero parse --file paper.pdf --wait --timeout 300 --json")).toBe("mdtero parse --file paper.pdf --trace --wait --timeout 300 --json");
    expect(normalizeCliHandoffCommand("mdtero rag status --json")).toBe("mdtero rag status --json");
  });
});

describe("buildCliParseCommand", () => {
  it("builds a traceable wait-and-json CLI handoff command for DOI and URL inputs", () => {
    expect(buildCliParseCommand("10.48550/arXiv.1706.03762")).toBe(
      "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json"
    );
    expect(buildCliParseCommand("https://www.ebi.ac.uk/europepmc/webservices/rest/PMC7517829/fullTextXML")).toBe(
      "mdtero parse https://www.ebi.ac.uk/europepmc/webservices/rest/PMC7517829/fullTextXML --trace --wait --timeout 300 --json"
    );
  });

  it("quotes shell-sensitive URLs and avoids fake local-file commands", () => {
    expect(buildCliParseCommand("https://example.org/paper?q=a b&x='demo'")).toBe(
      "mdtero parse 'https://example.org/paper?q=a b&x='\"'\"'demo'\"'\"'' --trace --wait --timeout 300 --json"
    );
    expect(buildCliParseCommand("paper.pdf")).toBe("");
    expect(buildCliParseCommand("")).toBe("");
  });
});

describe("buildCliFileParseCommand", () => {
  it("builds terminal handoff commands for failed local file uploads", () => {
    expect(buildCliFileParseCommand("paper.pdf", "pdf")).toBe(
      "mdtero parse --file paper.pdf --trace --wait --timeout 300 --json"
    );
    expect(buildCliFileParseCommand("paper.epub", "epub")).toBe(
      "mdtero parse --file paper.epub --trace --wait --timeout 300 --json"
    );
  });

  it("quotes shell-sensitive local filenames and uses stable placeholders", () => {
    expect(buildCliFileParseCommand("My Paper's Draft.pdf", "pdf")).toBe(
      "mdtero parse --file 'My Paper'\"'\"'s Draft.pdf' --trace --wait --timeout 300 --json"
    );
    expect(buildCliFileParseCommand("", "epub")).toBe(
      "mdtero parse --file paper.epub --trace --wait --timeout 300 --json"
    );
  });
});
