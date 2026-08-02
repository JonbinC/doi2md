import type { TaskResult } from "@mdtero/shared";
import type { PopupState, UiLanguage } from "../lib/storage";
import {
  buildCliFileParseCommand,
  buildCliParseCommand,
  normalizeCliHandoffCommand
} from "../lib/cli-handoff";
import { redactSensitiveText } from "../lib/redact";
import { isSupportedPaperPage } from "../lib/supported-page";

const SECONDARY_ORDER = ["paper_md", "paper_bundle", "translated_md"] as const;
const SOURCE_ORDER = ["paper_pdf", "paper_epub", "paper_html", "paper_xml"] as const;

function getArtifactKeys(result?: TaskResult | null): string[] {
  const keyed = Object.keys(result?.artifacts ?? {});
  const listed = (result?.download_artifacts ?? [])
    .map((artifact) => String(artifact.artifact || "").trim())
    .filter((artifact) => artifact.length > 0);
  return Array.from(new Set([...keyed, ...listed]));
}

export function getArtifactFilename(result: TaskResult | null | undefined, artifactKey: string): string | undefined {
  return (
    result?.artifacts?.[artifactKey]?.filename ||
    result?.download_artifacts?.find((artifact) => artifact.artifact === artifactKey)?.filename
  );
}

export function getPreferredArtifactKey(result?: TaskResult | null): string | undefined {
  const artifactKeys = getArtifactKeys(result);
  if (artifactKeys.length === 0) {
    return undefined;
  }
  if (result?.preferred_artifact && artifactKeys.includes(result.preferred_artifact)) {
    return result.preferred_artifact;
  }
  return artifactKeys[0];
}

export function getSecondaryArtifactKeys(result?: TaskResult | null): string[] {
  const preferred = getPreferredArtifactKey(result);
  const artifactKeys = getArtifactKeys(result);
  return SECONDARY_ORDER.filter(
    (key) => artifactKeys.includes(key) && key !== preferred
  );
}

export function getSourceArtifactKeys(result?: TaskResult | null): string[] {
  const artifactKeys = getArtifactKeys(result);
  return SOURCE_ORDER.filter((key) => artifactKeys.includes(key));
}

export function getTaskProcessingSummary(
  task:
    | (Pick<
        TaskRecord,
        | "preferred_artifact"
      > & {
        result?: Pick<
          TaskResult,
          | "preferred_artifact"
          | "download_artifacts"
          | "artifacts"
        > | null;
      })
    | null
    | undefined,
  language: UiLanguage = "en"
): string[] {
  const result = task?.result;
  const preferredArtifact = firstPresentString(task?.preferred_artifact, result?.preferred_artifact);
  const artifacts = summarizeDownloadArtifacts(result);
  const lines: string[] = [];
  const queue = (task as TaskRecord | null | undefined)?.queue;
  if (queue?.position) {
    lines.push(
      language === "zh"
        ? `队列位置：${queue.position}${queue.ahead ? `（前面还有 ${queue.ahead} 个）` : ""}`
        : `Queue position: ${queue.position}${queue.ahead ? ` (${queue.ahead} ahead)` : ""}`
    );
  }

  if (preferredArtifact) {
    lines.push(language === "zh" ? `首选产物：${preferredArtifact}` : `Preferred artifact: ${preferredArtifact}`);
  }
  if (artifacts) {
    lines.push(language === "zh" ? `可下载：${artifacts}` : `Downloads: ${artifacts}`);
  }
  return lines.map(redactSensitiveText).filter(Boolean);
}

export function getDownloadLabel(artifactKey: string, language: UiLanguage = "en"): string {
  if (language === "zh") {
    if (artifactKey === "paper_md") {
      return "下载 Markdown";
    }
    if (artifactKey === "paper_bundle") {
      return "下载压缩包";
    }
    if (artifactKey === "translated_md") {
      return "下载译文";
    }
    if (artifactKey === "paper_pdf") {
      return "下载 PDF";
    }
    if (artifactKey === "paper_epub") {
      return "下载 EPUB";
    }
    if (artifactKey === "paper_html") {
      return "下载 HTML";
    }
    if (artifactKey === "paper_xml") {
      return "下载 XML";
    }
    return "下载文件";
  }
  if (artifactKey === "paper_md") {
    return "Download Markdown";
  }
  if (artifactKey === "paper_bundle") {
    return "Download ZIP";
  }
  if (artifactKey === "translated_md") {
    return "Download Translation";
  }
  if (artifactKey === "paper_pdf") {
    return "Download PDF";
  }
  if (artifactKey === "paper_epub") {
    return "Download EPUB";
  }
  if (artifactKey === "paper_html") {
    return "Download HTML";
  }
  if (artifactKey === "paper_xml") {
    return "Download XML";
  }
  return "Download File";
}

export type ActionStatusKind =
  | "detecting"
  | "queued_parse"
  | "running_parse"
  | "queued_translate"
  | "running_translate"
  | "failed";

export function getActionStatusText(kind: ActionStatusKind, language: UiLanguage = "en"): string {
  if (language === "zh") {
    if (kind === "detecting") {
      return "正在识别当前页面的 DOI...";
    }
    if (kind === "queued_parse") {
      return "解析任务已提交，正在准备文件...";
    }
    if (kind === "running_parse") {
      return "正在解析论文并准备 Markdown...";
    }
    if (kind === "queued_translate") {
      return "翻译任务已提交，正在准备...";
    }
    if (kind === "running_translate") {
      return "正在翻译 Markdown...";
    }
    return "处理失败，请重试。";
  }
  if (kind === "detecting") {
    return "Detecting DOI from this page...";
  }
  if (kind === "queued_parse") {
    return "Parse request sent. Preparing files...";
  }
  if (kind === "running_parse") {
    return "Parsing paper and preparing Markdown...";
  }
  if (kind === "queued_translate") {
    return "Translation request sent. Preparing text...";
  }
  if (kind === "running_translate") {
    return "Translating Markdown...";
  }
  return "Something went wrong. Please try again.";
}

export function getUsageStatusText(
  usage:
    | {
        wallet_balance_display?: string;
        parse_quota_remaining?: number;
        translation_quota_remaining?: number;
      }
    | null
    | undefined,
  language: UiLanguage = "en",
  errorMessage?: string | null
): string {
  if (errorMessage?.trim()) {
    return redactSensitiveText(errorMessage.trim());
  }
  const wallet = usage?.wallet_balance_display?.trim() || (language === "zh" ? "¥0.00" : "$0.00");
  const parse = Number.isFinite(usage?.parse_quota_remaining) ? Number(usage?.parse_quota_remaining) : 0;
  const translation = Number.isFinite(usage?.translation_quota_remaining)
    ? Number(usage?.translation_quota_remaining)
    : 0;
  return language === "zh"
    ? `余额 ${wallet} · 解析 ${parse} · 翻译 ${translation}`
    : `Balance ${wallet} · Parse ${parse} · Translation ${translation}`;
}

export function getBridgeStatusText(
  status:
    | {
        state?: string | null;
        runnerState?: string | null;
      }
    | null
    | undefined,
  language: UiLanguage = "en"
): string {
  const state = String(status?.state || "").trim().toLowerCase();
  const runnerState = String(status?.runnerState || "").trim().toLowerCase();

  if (language === "zh") {
    if (state === "connected" && runnerState === "busy") {
      return "扩展正在读取当前论文页。";
    }
    if (state === "connected") {
      return "扩展可读取当前论文页并在需要时上传页面内容。";
    }
    if (state === "disconnected") {
      return "当前页面读取不可用。请重载页面或直接上传 PDF/EPUB。";
    }
    if (state === "unavailable") {
      return "当前页面读取不可用。直连失败时，请用扩展上传文件或改用 mdtero CLI。";
    }
    return "当前页面读取状态未知。";
  }

  if (state === "connected" && runnerState === "busy") {
    return "The extension is reading the current paper page.";
  }
  if (state === "connected") {
    return "The extension can read this paper page and upload page content when needed.";
  }
  if (state === "disconnected") {
    return "Current-page capture is unavailable. Reload the page or upload a PDF/EPUB directly.";
  }
  if (state === "unavailable") {
    return "Current-page capture is unavailable. If direct routing fails, upload the file or continue with mdtero CLI.";
  }
  return "Current-page capture status unknown.";
}

export function getPreflightHintText(
  params: {
    input?: string | null;
    pageUrl?: string | null;
    bridgeStatus?:
      | {
          state?: string | null;
          runnerState?: string | null;
        }
      | null
      | undefined;
  },
  language: UiLanguage = "en"
): string {
  const input = String(params.input || "").trim();
  const pageUrl = String(params.pageUrl || "").trim();
  const bridgeState = String(params.bridgeStatus?.state || "").trim().toLowerCase();
  const bridgeReady = bridgeState === "connected";
  const bridgeMissing = bridgeState === "unavailable" || bridgeState === "disconnected";
  const candidate = pageUrl || input;
  const livePageSupported = isSupportedPaperPage(candidate);
  const looksLikePdfShell =
    candidate.includes("/pdf") ||
    candidate.includes("/epdf") ||
    candidate.includes("download=true") ||
    candidate.includes("/epub/");

  if (looksLikePdfShell) {
    return language === "zh"
      ? "当前更像 PDF/EPUB 页面。建议直接上传 PDF/EPUB，或先切到 HTML 正文页。"
      : "This looks like a PDF/EPUB page. Upload the PDF/EPUB directly or open the HTML full-text page first.";
  }

  if (!livePageSupported) {
    return "";
  }

  if (bridgeMissing) {
    return language === "zh"
      ? "当前页面可由扩展读取。若直连失败，请上传 PDF/EPUB，或在终端用 `mdtero parse` 继续。"
      : "The extension can read this page. If direct routing fails, upload the PDF/EPUB or continue with `mdtero parse` in the terminal.";
  }

  if (bridgeReady) {
    return language === "zh"
      ? "当前页面可由扩展读取，并在需要时上传给 Mdtero 解析。"
      : "This page can be read by the extension and uploaded to Mdtero when needed.";
  }

  return language === "zh"
    ? "当前页面支持扩展读取。解析前请确认页面正文已经加载。"
    : "This page supports extension capture. Confirm the article body has loaded before parsing.";
}

export function shouldShowCliHandoffForPreflight(hint: string, input?: string | null): boolean {
  const normalizedHint = String(hint || "").trim().toLowerCase();
  if (!buildCliParseCommand(input)) {
    return false;
  }
  return normalizedHint.includes("mdtero parse") || normalizedHint.includes("cli") || normalizedHint.includes("终端");
}

export function getCliHandoffNote(command?: string | null, language: UiLanguage = "en"): string {
  const normalized = String(command || "").trim();
  if (!normalized) {
    return "";
  }
  if (language === "zh") {
    if (/^mdtero\s+parse\s+--file\b/.test(normalized)) {
      return "在终端继续上传本地文件；复制命令后把文件路径替换为你的 PDF/EPUB。";
    }
    return "在终端继续解析，并按提示完成后续操作。";
  }
  if (/^mdtero\s+parse\s+--file\b/.test(normalized)) {
    return "Continue local file upload in the terminal; replace the path with your PDF/EPUB.";
  }
  return "Continue parsing in the terminal and follow the prompts.";
}

export function getSavedResultSummary(
  state: Pick<PopupState, "parseFilename" | "translatedFilename"> | undefined,
  language: UiLanguage = "en"
): string {
  const filename = state?.translatedFilename ?? state?.parseFilename;
  if (!filename) {
    return "";
  }
  return language === "zh" ? `已就绪：${filename}` : `Ready: ${filename}`;
}

export function getResultWarningText(result?: TaskResult | null, language: UiLanguage = "en"): string {
  if (!result) {
    return "";
  }
  if (result.warning_code === "publisher_abstract_only" || result.warning_code === "elsevier_abstract_only") {
    return language === "zh"
      ? "当前页面仅提供摘要。请打开全文页面，或上传 PDF/EPUB。"
      : "This page only provided an abstract. Open the full-text page or upload a PDF/EPUB.";
  }
  return redactSensitiveText(result.warning_message ?? "");
}

export function getTaskFailureText(
  task:
    | (Pick<TaskRecord, "error_message" | "next_commands"> & {
        result?: Pick<TaskResult, "next_commands"> | null;
      })
    | null
    | undefined,
  fallback: string,
  _language: UiLanguage = "en"
): string {
  // Backend diagnostics are intentionally not part of the browser product contract.
  // The popup provides a stable recovery path without exposing implementation details.
  void task;
  return fallback;
}

export function getDownloadFailureText(
  _error: unknown,
  fallback: string,
  _language: UiLanguage = "en"
): string {
  return fallback;
}

export function getTranslationAttemptSummary(
  _attempts: TaskResult["translation_attempts"] | null | undefined,
  _language: UiLanguage = "en"
): string {
  return "";
}

export function firstTaskNextCommand(
  task:
    | (Pick<TaskRecord, "next_commands"> & {
        result?: Pick<TaskResult, "next_commands"> | null;
      })
    | null
    | undefined
): string {
  return firstNextCommand([...(task?.next_commands ?? []), ...(task?.result?.next_commands ?? [])]);
}

export function getTaskFailureCliHandoff(
  task:
    | (Pick<TaskRecord, "next_commands"> & {
        result?: Pick<TaskResult, "next_commands"> | null;
      })
    | null
    | undefined,
  input?: string | null,
  kind: "parse" | "translate" = "parse"
): string {
  return buildTaskFailureCliHandoffPlan(task, input, kind).primaryCommand;
}

export function firstNextCommand(commands?: string[] | null): string {
  const command = (commands ?? []).map((value) => String(value || "").trim()).find(Boolean) || "";
  return normalizeCliHandoffCommand(command);
}

export interface CliHandoffPlan {
  primaryCommand: string;
  commands: string[];
  source: "backend_task" | "backend_result" | "fallback_parse" | "none";
  kind: "parse" | "translate";
}

export type ApiErrorLike = Error & {
  nextCommands?: string[];
};

export function buildApiErrorCliHandoffPlan(
  error: unknown,
  input?: string | null,
  kind: "parse" | "translate" = "parse"
): CliHandoffPlan {
  if (!error || typeof error !== "object") {
    return buildTaskFailureCliHandoffPlan(null, input, kind);
  }
  const nextCommands = Array.isArray((error as ApiErrorLike).nextCommands)
    ? (error as ApiErrorLike).nextCommands
    : [];
  return buildTaskFailureCliHandoffPlan({ next_commands: nextCommands }, input, kind);
}

const PARSE_HANDOFF_FOLLOWUPS = [
  "mdtero status <task-id> --wait --timeout 300 --json",
  "mdtero download <task-id> paper_md --output-dir ./mdtero-output --json",
  "mdtero project ingest --json",
  "mdtero project refresh --wait --timeout 300 --json",
  "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json",
  "mdtero rag status --json",
  "mdtero rag build --wait --json",
  "mdtero rag query \"<question>\" --build-if-needed --json",
  "mdtero mcp briefing --json",
  "mdtero mcp serve",
];

export function buildCliHandoffCommandPlan(primaryCommand: string, planCommands?: string[] | null): string[] {
  const commands = normalizeCommandList([primaryCommand, ...(planCommands ?? [])]);
  const primary = commands[0] || "";
  if (!/^mdtero\s+parse\b/.test(primary)) {
    return commands;
  }
  const statusCommands = commands.filter((command) => /^mdtero\s+status\b/.test(command));
  const downloadCommands = commands.filter((command) => /^mdtero\s+download\b/.test(command));
  const ingestCommands = commands.filter((command) => command === "mdtero project ingest --json");
  const projectRefreshCommands = commands.filter((command) => command === "mdtero project refresh --wait --timeout 300 --json");
  const ragBootstrapCommands = commands.filter((command) => command === PARSE_HANDOFF_FOLLOWUPS[4]);
  const ragStatusCommands = commands.filter((command) => command === "mdtero rag status --json");
  const ragBuildCommands = commands.filter((command) => command === "mdtero rag build --wait --json");
  const ragQueryCommands = commands.filter((command) => /^mdtero\s+rag\s+query\b/.test(command));
  const genericRagQueryCommands = ragQueryCommands.filter((command) => command !== PARSE_HANDOFF_FOLLOWUPS[4]);
  const mcpBriefingCommands = commands.filter((command) => command === "mdtero mcp briefing --json");
  const mcpServeCommands = commands.filter((command) => command === "mdtero mcp serve");
  const otherCommands = commands.filter(
    (command) =>
      command !== primary &&
      !/^mdtero\s+status\b/.test(command) &&
      !/^mdtero\s+download\b/.test(command) &&
      command !== "mdtero project ingest --json" &&
      command !== "mdtero project refresh --wait --timeout 300 --json" &&
      command !== "mdtero rag build --wait --json" &&
      command !== "mdtero rag status --json" &&
      !/^mdtero\s+rag\s+query\b/.test(command) &&
      command !== "mdtero mcp briefing --json" &&
      command !== "mdtero mcp serve"
  );
  return normalizeCommandList([
    primary,
    ...(statusCommands.length ? statusCommands : [PARSE_HANDOFF_FOLLOWUPS[0]]),
    ...(downloadCommands.length ? downloadCommands : [PARSE_HANDOFF_FOLLOWUPS[1]]),
    ...(ingestCommands.length ? ingestCommands : [PARSE_HANDOFF_FOLLOWUPS[2]]),
    ...(projectRefreshCommands.length ? projectRefreshCommands : [PARSE_HANDOFF_FOLLOWUPS[3]]),
    ...(ragBootstrapCommands.length ? ragBootstrapCommands : [PARSE_HANDOFF_FOLLOWUPS[4]]),
    ...(ragStatusCommands.length ? ragStatusCommands : [PARSE_HANDOFF_FOLLOWUPS[5]]),
    ...(ragBuildCommands.length ? ragBuildCommands : [PARSE_HANDOFF_FOLLOWUPS[6]]),
    ...(genericRagQueryCommands.length ? genericRagQueryCommands : [PARSE_HANDOFF_FOLLOWUPS[7]]),
    ...(mcpBriefingCommands.length ? mcpBriefingCommands : [PARSE_HANDOFF_FOLLOWUPS[8]]),
    ...(mcpServeCommands.length ? mcpServeCommands : [PARSE_HANDOFF_FOLLOWUPS[9]]),
    ...otherCommands,
  ]);
}

export function formatCliHandoffClipboard(
  primaryCommand: string,
  planCommands?: string[] | null
): string {
  const commands = buildCliHandoffCommandPlan(primaryCommand, planCommands);
  if (commands.length <= 1) {
    return commands[0] || "";
  }
  const parseHandoff = /^mdtero\s+parse\b/.test(commands[0] || "");
  return [
    "# Mdtero CLI handoff",
    "",
    ...(parseHandoff
      ? [
          "Continue this paper in the Mdtero CLI.",
          "",
        ]
      : []),
    "Run these commands in order:",
    ...commands.map((command, index) => `${index + 1}. ${command}`),
    ...(parseHandoff
      ? [
          "",
          "The CLI will show the next available actions after parsing finishes.",
        ]
      : []),
  ].join("\n");
}

function firstPresentString(...values: unknown[]): string | undefined {
  for (const value of values) {
    const normalized = String(value || "").trim();
    if (normalized) {
      return normalized;
    }
  }
  return undefined;
}

function summarizeDownloadArtifacts(result?: Pick<TaskResult, "download_artifacts" | "artifacts"> | null): string | undefined {
  const listed = (result?.download_artifacts ?? [])
    .map((artifact) => {
      const name = firstPresentString(artifact.artifact);
      const filename = firstPresentString(artifact.filename);
      return [name, filename].filter(Boolean).join(": ");
    })
    .filter(Boolean);
  const keyed = Object.entries(result?.artifacts ?? {})
    .map(([artifact, descriptor]) => [artifact, descriptor?.filename].filter(Boolean).join(": "))
    .filter(Boolean);
  const artifacts = Array.from(new Set([...listed, ...keyed]));
  return artifacts.length ? artifacts.join("; ") : undefined;
}

export function buildTaskFailureCliHandoffPlan(
  task:
    | (Pick<TaskRecord, "next_commands"> & {
        result?: Pick<TaskResult, "next_commands"> | null;
      })
    | null
    | undefined,
  input?: string | null,
  kind: "parse" | "translate" = "parse"
): CliHandoffPlan {
  const taskCommands = normalizeCommandList(task?.next_commands);
  if (taskCommands.length > 0) {
    return {
      primaryCommand: taskCommands[0],
      commands: buildCliHandoffCommandPlan(taskCommands[0], taskCommands),
      source: "backend_task",
      kind
    };
  }

  const resultCommands = normalizeCommandList(task?.result?.next_commands);
  if (resultCommands.length > 0) {
    return {
      primaryCommand: resultCommands[0],
      commands: buildCliHandoffCommandPlan(resultCommands[0], resultCommands),
      source: "backend_result",
      kind
    };
  }

  const fallback = kind === "parse" ? buildCliParseCommand(input) : "";
  if (fallback) {
    return {
      primaryCommand: fallback,
      commands: buildCliHandoffCommandPlan(fallback),
      source: "fallback_parse",
      kind
    };
  }

  return {
    primaryCommand: "",
    commands: [],
    source: "none",
    kind
  };
}


function normalizeCommandList(commands?: string[] | null): string[] {
  const normalized = (commands ?? [])
    .map((value) => normalizeCliHandoffCommand(String(value || "").trim()))
    .filter((value) => value.length > 0);
  return Array.from(new Set(normalized));
}

export { buildCliFileParseCommand, buildCliParseCommand, normalizeCliHandoffCommand };
