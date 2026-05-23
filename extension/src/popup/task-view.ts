import type { TaskResult } from "@mdtero/shared";
import type { PopupState, UiLanguage } from "../lib/storage";
import { requiresElsevierLocalAcquire } from "../lib/elsevier";
import { isBridgeSupportedPage } from "../lib/bridge-wake";

const SECONDARY_ORDER = ["paper_md", "paper_bundle", "translated_md"] as const;
const SOURCE_ORDER = ["paper_pdf", "paper_xml"] as const;

export function getPreferredArtifactKey(result?: TaskResult | null): string | undefined {
  if (!result?.artifacts) {
    return undefined;
  }
  if (result.preferred_artifact && result.artifacts[result.preferred_artifact]) {
    return result.preferred_artifact;
  }
  return Object.keys(result.artifacts)[0];
}

export function getSecondaryArtifactKeys(result?: TaskResult | null): string[] {
  const preferred = getPreferredArtifactKey(result);
  const artifactKeys = Object.keys(result?.artifacts ?? {});
  return SECONDARY_ORDER.filter(
    (key) => artifactKeys.includes(key) && key !== preferred
  );
}

export function getSourceArtifactKeys(result?: TaskResult | null): string[] {
  const artifactKeys = Object.keys(result?.artifacts ?? {});
  return SOURCE_ORDER.filter((key) => artifactKeys.includes(key));
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
    return errorMessage.trim();
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
  const livePageSupported = isBridgeSupportedPage(candidate);
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

  if (input && requiresElsevierLocalAcquire(input)) {
    return language === "zh"
      ? "当前输入命中了 Elsevier / ScienceDirect。扩展不保存出版社密钥；若需要机构全文，请确认当前浏览器已能打开原文，或用 CLI 配置学术 key 后重试。"
      : "This input maps to Elsevier / ScienceDirect. The extension does not store publisher keys; for licensed full text, confirm this browser can already open the article or configure academic keys in the CLI.";
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
  if (result.warning_code === "elsevier_abstract_only") {
    return language === "zh"
      ? "Elsevier 仅返回了摘要。请确认你当前是否处于校园网或机构 IP 环境。"
      : "Elsevier only returned the abstract. Check whether this machine is on a campus or institutional network IP.";
  }
  return result.warning_message ?? "";
}

export function getTaskFailureText(
  task:
    | (Pick<TaskRecord, "error_message" | "error_code" | "reason_code" | "action_hint" | "next_commands"> & {
        result?: Pick<TaskResult, "reason_code" | "action_hint" | "next_commands" | "translation_attempts"> | null;
      })
    | null
    | undefined,
  fallback: string,
  language: UiLanguage = "en"
): string {
  const message = task?.error_message?.trim() || fallback;
  const reason = (task?.reason_code || task?.result?.reason_code || task?.error_code || "").trim();
  const actionHint = (task?.action_hint || task?.result?.action_hint || "").trim();
  const parts = [message];
  if (reason) {
    parts.push(language === "zh" ? `原因：${reason}` : `Reason: ${reason}`);
  }
  if (actionHint) {
    parts.push(language === "zh" ? `下一步：${actionHint}` : `Next: ${actionHint}`);
  }
  const attempts = getTranslationAttemptSummary(task?.result?.translation_attempts, language);
  if (attempts) {
    parts.push(attempts);
  }
  const nextCommand = firstTaskNextCommand(task);
  if (nextCommand) {
    parts.push(language === "zh" ? `命令：${nextCommand}` : `Command: ${nextCommand}`);
  }
  return parts.join(" ");
}

export function getTranslationAttemptSummary(
  attempts: TaskResult["translation_attempts"] | null | undefined,
  language: UiLanguage = "en"
): string {
  const items = (attempts ?? [])
    .map((attempt) => {
      const provider = String(attempt?.provider || "provider").trim();
      const reason = String(attempt?.reason_code || attempt?.provider_error_code || "failed").trim();
      const statusCode = attempt?.provider_status_code;
      const status = typeof statusCode === "number" ? ` ${statusCode}` : "";
      return `${provider}: ${reason}${status}`;
    })
    .filter(Boolean);
  if (!items.length) {
    return "";
  }
  return language === "zh" ? `服务端尝试：${items.join("; ")}` : `Provider attempts: ${items.join("; ")}`;
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

export function firstNextCommand(commands?: string[] | null): string {
  const command = (commands ?? []).map((value) => String(value || "").trim()).find(Boolean) || "";
  return normalizeCliHandoffCommand(command);
}

export function normalizeCliHandoffCommand(command?: string | null): string {
  const trimmed = String(command || "").trim();
  if (!trimmed || !/^mdtero\s+parse\b/.test(trimmed)) {
    return trimmed;
  }
  const withoutTraceOnly = trimmed.replace(/\s+--trace(?!\S)/g, "");
  const withoutJson = withoutTraceOnly.replace(/\s+--json(?!\S)/g, "");
  const withoutTimeout = withoutJson.replace(/\s+--timeout\s+\S+/g, "").replace(/\s+--interval\s+\S+/g, "");
  const withoutWait = withoutTimeout.replace(/\s+--wait(?!\S)/g, "");
  return `${withoutWait} --trace --wait --timeout 300 --json`;
}

export function buildCliParseCommand(input?: string | null): string {
  const normalized = String(input || "").trim();
  if (!normalized) {
    return "";
  }
  if (!/^https?:\/\//i.test(normalized) && !/^10\.\S+/i.test(normalized)) {
    return "";
  }
  return `mdtero parse ${shellQuote(normalized)} --trace --wait --timeout 300 --json`;
}

function shellQuote(value: string): string {
  if (/^[A-Za-z0-9_/:.=?&%+@,;#~-]+$/.test(value)) {
    return value;
  }
  return `'${value.replace(/'/g, `'"'"'`)}'`;
}
