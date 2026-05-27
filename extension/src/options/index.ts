import type { TaskRecord } from "@mdtero/shared";

import { createApiClient } from "../lib/api";
import { MDTERO_ACCOUNT_URL } from "../lib/auth-bridge";
import { triggerBlobDownload } from "../lib/download";
import {
  mergeSettings,
  readSettings,
  resolveUiLanguage,
  writeSettings,
  type UiLanguage
} from "../lib/storage";

const ONE_COMMAND_RAG_BOOTSTRAP = 'mdtero rag query "What are the strongest findings?" --build-if-needed --json';

const COPY = {
  en: {
    title: "Mdtero Extension",
    subtitle: "Use website OAuth for sign-in, check balance and quota, and manage browser capture, upload, translation, and download settings.",
    permissionsTitle: "Why Mdtero asks for these permissions",
    permissionsTabs: "`tabs` lets the extension read the current paper page and open website OAuth when you sign in.",
    permissionsDownloads: "`downloads` saves Markdown files, translations, ZIP bundles, and uploaded-source results back to your machine.",
    permissionsCapture: "Browser capture reuses the active tab only when you ask Mdtero to parse the current paper page.",
    permissionsHosts: "Host permissions stay limited to Mdtero Auth, supported scholarly pages, and files you choose to upload.",
    notSignedIn: "Not signed in with website OAuth.",
    usagePending: "Balance and quota appear after sign-in.",
    signedIn: (email: string) => `Signed in as ${email}`,
    usageSummary: (wallet: string, parse: number, translation: number) =>
      `Balance ${wallet} · Parse ${parse} · Translation ${translation}`,
    openAccount: "Open website OAuth",
    websiteAuthTitle: "Website sign-in",
    websiteAuthNote: "The extension opens mdtero.com/auth for OAuth sign-in. Complete login on the website, and the trusted auth bridge will hand the token back to this extension.",
    cliHandoffGuideTitle: "Extension + CLI handoff",
    cliHandoffGuideNote: "Use the extension for browser context, current-page parse, PDF/EPUB upload, translation, and downloads. When a publisher challenge, campus login, or saved file blocks capture, continue in the Python CLI; `mdtero setup --json` returns the onboarding checklist for agents. After one parse succeeds, use one-command RAG bootstrap instead of hand-copying a server project id; MCP agents should follow `mcp_tool_plan` and call `server_rag_build(wait=true)` before `rag_query` when a build is needed.",
    cliHandoffGuideBoundary: "The extension does not install Python dependencies, run native helpers, or store Elsevier/Wiley/Semantic Scholar keys; those stay in `mdtero config academic` on the local CLI.",
    copyCliHandoffGuide: "Copy handoff",
    cliHandoffGuideCopied: "CLI handoff copied.",
    mcpServerConfigTitle: "Agent MCP server",
    mcpServerConfigNote: "After `mdtero setup`, start `mdtero mcp serve` from a local project and paste this stdio server config into Codex, Claude, Gemini, Hermes, or OpenCode.",
    mcpServerConfigMeta: "FastMCP · stdio · local project root",
    copyMcpServerConfig: "Copy MCP config",
    mcpServerConfigCopied: "MCP config copied.",
    cliOnboardingTitle: "CLI setup checklist",
    cliOnboardingNote: "The Python client handles local acquisition, project queues, Zotero, backend Voyage RAG, MCP, and agent skills.",
    cliOnboardingPill: "Python / uv",
    inputRouteTitle: "Input routes",
    inputRouteNote: "Choose the shortest path to a Markdown artifact. The extension covers browser context; the CLI continues local files, RAG, MCP, and agent handoff.",
    inputRoutePill: "Extension + CLI",
    inputRouteCopy: "Copy",
    inputRouteCopied: "Route copied.",
    serverApiContractTitle: "Server API contract",
    serverApiContractNote: "The same /api/v1 routes back extension capture, CLI upload, task polling, downloads, project import, and backend Voyage RAG.",
    copyServerApiContract: "Copy API contract",
    serverApiContractCopied: "API contract copied.",
    serverApiContract: [
      ["route", "/api/v1/route"],
      ["parse", "/api/v1/tasks/parse"],
      ["upload", "/api/v1/tasks/upload"],
      ["status", "/api/v1/tasks/{task_id}"],
      ["download", "/api/v1/tasks/{task_id}/download/{artifact}"],
      ["project_import", "/api/v1/projects/{project_id}/tasks/{task_id}/import"],
      ["rag_build", "/api/v1/projects/{project_id}/rag/build"],
      ["rag_query", "/api/v1/projects/{project_id}/rag/query"]
    ],
    inputRoutes: [
      ["DOI or URL", "fast smoke", "Use the CLI for DOI, arXiv, EuropePMC XML, or an open URL the backend route can recognize.", "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json"],
      ["PDF / EPUB file", "upload", "Use direct file upload for local PDF, EPUB, XML, or HTML. PDFs go through the backend MinerU-first path.", "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json"],
      ["Browser extension", "manual capture", "Use the extension when OAuth, campus network, cookies, or a selected PDF/EPUB matter, then hand off saved inputs to the CLI.", "mdtero parse <doi-or-current-page-url> --trace --wait --timeout 300 --json\nmdtero parse --file <saved-browser-artifact.pdf|epub|html|xml> --trace --wait --timeout 600 --json"],
      ["RAG / MCP", "after parse", "Build backend Voyage RAG from completed Markdown and expose the same project to local agents through FastMCP. The bootstrap query creates or reuses the server project, binds it locally, imports Markdown, builds RAG, and queries without asking you to copy a server project id.", `${ONE_COMMAND_RAG_BOOTSTRAP}\nmdtero mcp briefing --json\nmdtero mcp serve`]
    ],
    cliOnboardingItems: [
      ["Install", "uv tool install git+https://github.com/JonbinC/doi2md.git", "Install the public Python client; the extension never installs Python dependencies."],
      ["Authenticate", "mdtero setup", "Use website OAuth on a workstation, or API-key setup on a trusted headless server."],
      ["Checklist", "mdtero setup --json", "Return the same secret-safe onboarding checklist used by local agents."],
      ["Academic keys", "mdtero config academic", "Optional academic resource keys stay in local CLI config."],
      ["Discover", "mdtero discover \"<topic>\" --limit 5 --interactive", "Use local Semantic Scholar when configured; otherwise use server OpenAlex."],
      ["Parse", "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json", "Preserve route, client_acquisition, reason_code, action_hint, and artifacts."],
      ["File upload", "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json", "Continue from browser-saved files or challenged publisher pages; PDF/MinerU tasks can take longer than DOI route checks."],
      ["RAG", ONE_COMMAND_RAG_BOOTSTRAP, "Backend Voyage RAG is driven by the CLI project. This one command can create or bind the server project, import succeeded Markdown, build Voyage RAG, and query with citations; citation_contract requires final answers to preserve citations and source_nodes."],
      ["MCP briefing", "mdtero mcp briefing --json", "Expose account, project, extension_handoff, RAG readiness, citation_contract, and the mcp_tool_plan steps including server_rag_build(wait=true) before rag_query."],
      ["MCP server", "mdtero mcp serve", "Run the FastMCP stdio server from the local project root for agent context tools."],
      ["Agent skills", "mdtero agent install --interactive", "Detect Codex, Claude, Gemini, Hermes, or OpenCode and select workspaces with Space."]
    ],
    guideTitle: "Connection guide",
    setupStepAuth: "OAuth",
    setupStepParse: "Parse / Upload",
    setupStepTranslate: "Translate",
    setupStepDownload: "Download",
    guideSignedOut: [
      "Open website OAuth and complete sign-in at mdtero.com/auth.",
      "Return to this popup after the trusted auth bridge connects your account.",
      "Optionally install the Python CLI with `uv tool install git+https://github.com/JonbinC/doi2md.git`, then run `mdtero setup` for workstation OAuth.",
      "Parse the current paper page or upload a local PDF/EPUB from the popup.",
      "Download Markdown, ZIP bundles, source files, or translations when tasks finish."
    ],
    guideSignedIn: [
      "Website OAuth is connected.",
      "Use the popup to parse the current page, paste a DOI, or upload PDF/EPUB.",
      "Translate parsed Markdown from the popup when a paper_md artifact is ready.",
      "Open history below to download previous artifacts without spending quota."
    ],
    uiLanguage: "Interface language",
    advanced: "Advanced",
    apiUrl: "API URL",
    save: "Save",
    historyTitle: "Account history",
    historyNote: "Downloads from your history are always free.",
    historyEmpty: "No parsing or translation history found yet.",
    historyError: "Failed to load history: ",
    downloadFailed: "Download failed:",
    download: "Download",
    artifactLabels: {
      paper_md: "Markdown",
      paper_bundle: "ZIP",
      translated_md: "Translation",
      paper_pdf: "PDF",
      paper_xml: "XML"
    },
    historyRefresh: "Refresh",
    historyRefreshing: "Refreshing..."
  },
  zh: {
    title: "Mdtero 扩展",
    subtitle: "使用网页登录授权扩展，并管理浏览器抓取、上传、翻译和下载设置。",
    permissionsTitle: "为什么 Mdtero 需要这些权限",
    permissionsTabs: "`tabs` 用来读取当前论文页，并在登录时打开网页登录页。",
    permissionsDownloads: "`downloads` 用来把 Markdown、译文、ZIP 包和上传文件的解析结果保存回你的电脑。",
    permissionsCapture: "浏览器补抓取只会在你主动解析当前论文页时复用当前标签页。",
    permissionsHosts: "站点权限只覆盖 Mdtero 登录页、受支持的学术页面，以及你主动选择上传的文件。",
    notSignedIn: "尚未通过网页登录授权扩展。",
    usagePending: "请在 mdtero.com/auth 登录以同步余额、额度和历史。",
    signedIn: (email: string) => `已登录：${email}`,
    usageSummary: (wallet: string, parse: number, translation: number) =>
      `余额 ${wallet} · 解析 ${parse} · 翻译 ${translation}`,
    openAccount: "打开网页登录",
    websiteAuthTitle: "官网登录",
    websiteAuthNote: "扩展统一打开 mdtero.com/auth 登录。请在官网完成登录，受信任 auth bridge 会把 token 交回扩展。",
    cliHandoffGuideTitle: "扩展 + CLI 交接",
    cliHandoffGuideNote: "扩展负责浏览器上下文、当前页解析、PDF/EPUB 上传、翻译和下载。遇到 publisher challenge、校园网登录态或用户已保存文件时，交给 Python CLI 继续；`mdtero setup --json` 会返回给 agent 使用的 onboarding checklist。已有一次成功解析后，用一条命令 RAG bootstrap，不要手工复制 server project id；MCP agent 应按 `mcp_tool_plan`，需要构建时先调用 `server_rag_build(wait=true)`，再调用 `rag_query`。",
    cliHandoffGuideBoundary: "扩展不安装 Python 依赖、不运行本地 helper，也不保存 Elsevier/Wiley/Semantic Scholar key；这些只留在本地 CLI 的 `mdtero config academic`。",
    copyCliHandoffGuide: "复制交接",
    cliHandoffGuideCopied: "CLI 交接已复制。",
    mcpServerConfigTitle: "Agent MCP 服务",
    mcpServerConfigNote: "运行 `mdtero setup` 后，在本地项目目录启动 `mdtero mcp serve`，再把这段 stdio server 配置粘贴到 Codex、Claude、Gemini、Hermes 或 OpenCode。",
    mcpServerConfigMeta: "FastMCP · stdio · 本地项目根目录",
    copyMcpServerConfig: "复制 MCP 配置",
    mcpServerConfigCopied: "MCP 配置已复制。",
    cliOnboardingTitle: "CLI 配置清单",
    cliOnboardingNote: "Python 客户端负责本地抓取、项目队列、Zotero、后端 Voyage RAG、MCP 和 agent skill。",
    cliOnboardingPill: "Python / uv",
    inputRouteTitle: "输入路径",
    inputRouteNote: "按输入类型选择最短 Markdown 路径。扩展负责浏览器上下文；CLI 继续处理本地文件、RAG、MCP 和 agent 交接。",
    inputRoutePill: "扩展 + CLI",
    inputRouteCopy: "复制",
    inputRouteCopied: "路径已复制。",
    serverApiContractTitle: "服务端 API 契约",
    serverApiContractNote: "扩展抓取、CLI 上传、任务轮询、下载、项目导入和后端 Voyage RAG 都落到同一组 /api/v1 路由。",
    copyServerApiContract: "复制 API 契约",
    serverApiContractCopied: "API 契约已复制。",
    serverApiContract: [
      ["route", "/api/v1/route"],
      ["parse", "/api/v1/tasks/parse"],
      ["upload", "/api/v1/tasks/upload"],
      ["status", "/api/v1/tasks/{task_id}"],
      ["download", "/api/v1/tasks/{task_id}/download/{artifact}"],
      ["project_import", "/api/v1/projects/{project_id}/tasks/{task_id}/import"],
      ["rag_build", "/api/v1/projects/{project_id}/rag/build"],
      ["rag_query", "/api/v1/projects/{project_id}/rag/query"]
    ],
    inputRoutes: [
      ["DOI 或 URL", "快速冒烟", "DOI、arXiv、EuropePMC XML，或后端 route 能识别的开放 URL，优先走 CLI。", "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json"],
      ["PDF / EPUB 文件", "上传", "本地 PDF、EPUB、XML 或 HTML 走直接上传。PDF 默认进入后端 MinerU-first 路径。", "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json"],
      ["浏览器扩展", "人工抓取", "遇到 OAuth、校园网、cookie 或人工选择 PDF/EPUB 时用扩展，再把已保存输入交给 CLI。", "mdtero parse <doi-or-current-page-url> --trace --wait --timeout 300 --json\nmdtero parse --file <saved-browser-artifact.pdf|epub|html|xml> --trace --wait --timeout 600 --json"],
      ["RAG / MCP", "解析后", "基于完成的 Markdown 构建后端 Voyage RAG，并通过 FastMCP 交给本地 agent。Bootstrap 查询会创建或复用服务端项目、写入本地绑定、导入 Markdown、构建 RAG 并查询，不需要你手工复制 server project id。", `${ONE_COMMAND_RAG_BOOTSTRAP}\nmdtero mcp briefing --json\nmdtero mcp serve`]
    ],
    cliOnboardingItems: [
      ["安装", "uv tool install git+https://github.com/JonbinC/doi2md.git", "安装公开 Python 客户端；扩展不会安装 Python 依赖。"],
      ["鉴权", "mdtero setup", "工作站走网页登录 OAuth；可信无头服务器可走 API-key setup。"],
      ["检查清单", "mdtero setup --json", "返回给本地 agent 使用的同一份 secret-safe onboarding checklist。"],
      ["学术 key", "mdtero config academic", "学术资源 key 都是可选增强，只存在本地 CLI 配置。"],
      ["发现", "mdtero discover \"<topic>\" --limit 5 --interactive", "有 Semantic Scholar 时走本地；否则走服务端 OpenAlex。"],
      ["解析", "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json", "保留 route、client_acquisition、reason_code、action_hint 和 artifacts。"],
      ["文件上传", "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json", "浏览器保存的文件或 publisher challenge 页面交给 CLI 继续；PDF/MinerU 任务通常比 DOI route 检查更慢。"],
      ["RAG", ONE_COMMAND_RAG_BOOTSTRAP, "后端 Voyage RAG 由 CLI 项目驱动。这一条命令可以创建或绑定服务端项目、导入成功 Markdown、构建 Voyage RAG，并带引用查询；citation_contract 要求最终回答保留 citations 和 source_nodes。"],
      ["MCP briefing", "mdtero mcp briefing --json", "把账户、项目、extension_handoff、RAG readiness、citation_contract 和 mcp_tool_plan 交给本地 agent，包括在 rag_query 前调用 server_rag_build(wait=true)。"],
      ["MCP 服务", "mdtero mcp serve", "在本地项目根目录运行 FastMCP stdio server，给 agent 提供上下文工具。"],
      ["Agent skill", "mdtero agent install --interactive", "动态检测 Codex、Claude、Gemini、Hermes、OpenCode，并用空格多选安装。"]
    ],
    guideTitle: "连接引导",
    setupStepAuth: "网页登录",
    setupStepParse: "解析 / 上传",
    setupStepTranslate: "翻译",
    setupStepDownload: "下载",
    guideSignedOut: [
      "打开网页登录，并在 mdtero.com/auth 完成授权。",
      "受信任 auth bridge 连接账户后，回到扩展弹窗继续。",
      "可选安装 Python CLI：`uv tool install git+https://github.com/JonbinC/doi2md.git`，再运行 `mdtero setup` 走工作站 OAuth。",
      "在弹窗解析当前论文页、粘贴 DOI，或上传本地 PDF/EPUB。",
      "任务完成后下载 Markdown、ZIP、源文件或译文。"
    ],
    guideSignedIn: [
      "网页登录已连接。",
      "在弹窗解析当前页面、粘贴 DOI，或上传 PDF/EPUB。",
      "当 paper_md 产物就绪后，可直接从弹窗请求翻译。",
      "下方历史记录可免费下载已生成产物。"
    ],
    uiLanguage: "界面语言",
    advanced: "高级设置",
    apiUrl: "API 地址",
    save: "保存",
    historyTitle: "账户历史",
    historyNote: "从历史记录下载内容永远免费，不扣除额度。",
    historyEmpty: "暂无解析或翻译记录。",
    historyError: "加载历史文档失败：",
    downloadFailed: "下载失败：",
    download: "下载",
    artifactLabels: {
      paper_md: "Markdown",
      paper_bundle: "压缩包",
      translated_md: "译文",
      paper_pdf: "PDF",
      paper_xml: "XML"
    },
    historyRefresh: "刷新",
    historyRefreshing: "刷新中..."
  }
} as const;

const titleEl = document.querySelector<HTMLHeadingElement>("#settings-title");
const subtitleEl = document.querySelector<HTMLParagraphElement>("#settings-subtitle");
const permissionsTitleEl = document.querySelector<HTMLHeadingElement>("#permissions-title");
const permissionsTabsEl = document.querySelector<HTMLParagraphElement>("#permissions-tabs");
const permissionsDownloadsEl = document.querySelector<HTMLParagraphElement>("#permissions-downloads");
const permissionsCaptureEl = document.querySelector<HTMLParagraphElement>("#permissions-capture");
const permissionsHostsEl = document.querySelector<HTMLParagraphElement>("#permissions-hosts");
const languageToggleEl = document.querySelector<HTMLButtonElement>("#language-toggle");
const apiBaseUrlInput = document.querySelector<HTMLInputElement>("#api-base-url");
const uiLanguageSelect = document.querySelector<HTMLSelectElement>("#ui-language");
const accountStatus = document.querySelector<HTMLParagraphElement>("#account-status");
const usageStatus = document.querySelector<HTMLParagraphElement>("#usage-status");
const saveButton = document.querySelector<HTMLButtonElement>("#save-settings");
const openAccountButton = document.querySelector<HTMLButtonElement>("#open-account");
const websiteAuthTitleEl = document.querySelector<HTMLHeadingElement>("#website-auth-title");
const websiteAuthNoteEl = document.querySelector<HTMLParagraphElement>("#website-auth-note");
const cliHandoffGuideTitleEl = document.querySelector<HTMLHeadingElement>("#cli-handoff-guide-title");
const cliHandoffGuideNoteEl = document.querySelector<HTMLParagraphElement>("#cli-handoff-guide-note");
const cliHandoffGuideBoundaryEl = document.querySelector<HTMLParagraphElement>("#cli-handoff-guide-boundary");
const cliHandoffGuideCommandEl = document.querySelector<HTMLElement>("#cli-handoff-guide-command");
const copyCliHandoffGuideButton = document.querySelector<HTMLButtonElement>("#copy-cli-handoff-guide");
const mcpServerConfigTitleEl = document.querySelector<HTMLHeadingElement>("#mcp-server-config-title");
const mcpServerConfigNoteEl = document.querySelector<HTMLParagraphElement>("#mcp-server-config-note");
const mcpServerConfigMetaEl = document.querySelector<HTMLSpanElement>("#mcp-server-config-meta");
const mcpServerConfigCommandEl = document.querySelector<HTMLElement>("#mcp-server-config-command");
const copyMcpServerConfigButton = document.querySelector<HTMLButtonElement>("#copy-mcp-server-config");
const cliOnboardingTitleEl = document.querySelector<HTMLHeadingElement>("#cli-onboarding-title");
const cliOnboardingNoteEl = document.querySelector<HTMLParagraphElement>("#cli-onboarding-note");
const cliOnboardingPillEl = document.querySelector<HTMLSpanElement>("#cli-onboarding-pill");
const cliOnboardingListEl = document.querySelector<HTMLDivElement>("#cli-onboarding-list");
const inputRouteTitleEl = document.querySelector<HTMLHeadingElement>("#input-route-title");
const inputRouteNoteEl = document.querySelector<HTMLParagraphElement>("#input-route-note");
const inputRoutePillEl = document.querySelector<HTMLSpanElement>("#input-route-pill");
const inputRouteListEl = document.querySelector<HTMLDivElement>("#input-route-list");
const serverApiContractTitleEl = document.querySelector<HTMLHeadingElement>("#server-api-contract-title");
const serverApiContractNoteEl = document.querySelector<HTMLParagraphElement>("#server-api-contract-note");
const serverApiContractListEl = document.querySelector<HTMLDivElement>("#server-api-contract-list");
const copyServerApiContractButton = document.querySelector<HTMLButtonElement>("#copy-server-api-contract");
const connectionGuideTitleEl = document.querySelector<HTMLHeadingElement>("#connection-guide-title");
const connectionGuideListEl = document.querySelector<HTMLDivElement>("#connection-guide-list");
const setupStepAuthEl = document.querySelector<HTMLSpanElement>("#setup-step-auth");
const setupStepParseEl = document.querySelector<HTMLSpanElement>("#setup-step-parse");
const setupStepTranslateEl = document.querySelector<HTMLSpanElement>("#setup-step-translate");
const setupStepDownloadEl = document.querySelector<HTMLSpanElement>("#setup-step-download");
const uiLanguageLabel = document.querySelector<HTMLLabelElement>("#ui-language-label");
const advancedSummary = document.querySelector<HTMLElement>("#advanced-summary");
const apiBaseUrlLabel = document.querySelector<HTMLLabelElement>("#api-base-url-label");
const historySection = document.querySelector<HTMLElement>("#history-section");
const historyList = document.querySelector<HTMLDivElement>("#history-list");
const historyTitle = document.querySelector<HTMLHeadingElement>("#history-title");
const historyNote = document.querySelector<HTMLParagraphElement>("#history-note");
const refreshHistoryBtn = document.querySelector<HTMLButtonElement>("#refresh-history");

type HistoryTaskRecord = TaskRecord & { paper_input?: string };

const client = createApiClient(readSettings);
let uiLanguage: UiLanguage = "en";

const CLI_HANDOFF_GUIDE_COMMAND = [
  "uv tool install git+https://github.com/JonbinC/doi2md.git",
  "mdtero setup",
  "mdtero setup --json",
  "mdtero doctor --json",
  "mdtero config academic",
  "mdtero discover \"<topic>\" --limit 5 --interactive",
  "mdtero discover \"<topic>\" --limit 5 --add --select 1,3 --json",
  "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
  "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json",
  "mdtero status <task-id> --wait --timeout 300 --json",
  "mdtero download <task-id> paper_md --output-dir ./mdtero-output --json",
  "mdtero project ingest --json",
  "mdtero project parse --wait --timeout 300 --json",
  "mdtero project refresh --wait --timeout 300 --json",
  ONE_COMMAND_RAG_BOOTSTRAP,
  "mdtero rag status --json",
  "mdtero rag build --wait --json",
  "mdtero rag query \"<question>\" --build-if-needed --json",
  "# MCP agents: if mcp_tool_plan says build_rag_index, call server_rag_build(wait=true), then rag_query(question).",
  "# Preserve citation_contract.required_for_final_answer: final RAG answers keep citations and source_nodes.",
  "mdtero mcp briefing --json",
  "mdtero mcp serve",
].join("\n");

const MCP_SERVER_CONFIG = JSON.stringify(
  {
    mcpServers: {
      mdtero: {
        command: "mdtero",
        args: ["mcp", "serve"],
        cwd: "<local-mdtero-project-root>",
      },
    },
  },
  null,
  2
);

function renderHistoryNotice(message: string, color?: string) {
  if (!historyList) return;
  historyList.textContent = "";
  const paragraph = document.createElement("p");
  paragraph.className = "meta-label";
  paragraph.textContent = message;
  if (color) {
    paragraph.style.color = color;
  }
  historyList.appendChild(paragraph);
}

function copyFor(language: UiLanguage) {
  return COPY[language];
}

function toggleLanguageLabel(language: UiLanguage) {
  return language === "en" ? "中文" : "EN";
}

async function openMdteroAccount() {
  await chrome.tabs.create({ url: MDTERO_ACCOUNT_URL });
}

function formatUsageSummary(usage: {
  wallet_balance_display?: string;
  parse_quota_remaining?: number;
  translation_quota_remaining?: number;
}): string {
  const wallet = usage.wallet_balance_display?.trim() || (uiLanguage === "zh" ? "¥0.00" : "$0.00");
  const parse = Number.isFinite(usage.parse_quota_remaining) ? Number(usage.parse_quota_remaining) : 0;
  const translation = Number.isFinite(usage.translation_quota_remaining)
    ? Number(usage.translation_quota_remaining)
    : 0;
  return copyFor(uiLanguage).usageSummary(wallet, parse, translation);
}

function formatArtifactActionLabel(artifactKey: string): string {
  const copy = copyFor(uiLanguage);
  const labels = copy.artifactLabels as Record<string, string>;
  const label = labels[artifactKey] || artifactKey.replace(/^paper_/, "").replace(/_/g, " ").toUpperCase();
  return `${copy.download} ${label}`;
}

function applyLanguage() {
  const copy = copyFor(uiLanguage);
  document.documentElement.lang = uiLanguage === "zh" ? "zh-CN" : "en";
  if (titleEl) titleEl.textContent = copy.title;
  if (subtitleEl) subtitleEl.textContent = copy.subtitle;
  if (permissionsTitleEl) permissionsTitleEl.textContent = copy.permissionsTitle;
  if (permissionsTabsEl) permissionsTabsEl.textContent = copy.permissionsTabs;
  if (permissionsDownloadsEl) permissionsDownloadsEl.textContent = copy.permissionsDownloads;
  if (permissionsCaptureEl) permissionsCaptureEl.textContent = copy.permissionsCapture;
  if (permissionsHostsEl) permissionsHostsEl.textContent = copy.permissionsHosts;
  if (languageToggleEl) languageToggleEl.textContent = toggleLanguageLabel(uiLanguage);
  if (uiLanguageLabel) uiLanguageLabel.textContent = copy.uiLanguage;
  if (advancedSummary) advancedSummary.textContent = copy.advanced;
  if (apiBaseUrlLabel) apiBaseUrlLabel.textContent = copy.apiUrl;
  if (openAccountButton) openAccountButton.textContent = copy.openAccount;
  if (websiteAuthTitleEl) websiteAuthTitleEl.textContent = copy.websiteAuthTitle;
  if (websiteAuthNoteEl) websiteAuthNoteEl.textContent = copy.websiteAuthNote;
  if (cliHandoffGuideTitleEl) cliHandoffGuideTitleEl.textContent = copy.cliHandoffGuideTitle;
  if (cliHandoffGuideNoteEl) cliHandoffGuideNoteEl.textContent = copy.cliHandoffGuideNote;
  if (cliHandoffGuideBoundaryEl) cliHandoffGuideBoundaryEl.textContent = copy.cliHandoffGuideBoundary;
  if (cliHandoffGuideCommandEl) cliHandoffGuideCommandEl.textContent = CLI_HANDOFF_GUIDE_COMMAND;
  if (copyCliHandoffGuideButton) copyCliHandoffGuideButton.textContent = copy.copyCliHandoffGuide;
  if (mcpServerConfigTitleEl) mcpServerConfigTitleEl.textContent = copy.mcpServerConfigTitle;
  if (mcpServerConfigNoteEl) mcpServerConfigNoteEl.textContent = copy.mcpServerConfigNote;
  if (mcpServerConfigMetaEl) mcpServerConfigMetaEl.textContent = copy.mcpServerConfigMeta;
  if (mcpServerConfigCommandEl) mcpServerConfigCommandEl.textContent = MCP_SERVER_CONFIG;
  if (copyMcpServerConfigButton) copyMcpServerConfigButton.textContent = copy.copyMcpServerConfig;
  if (cliOnboardingTitleEl) cliOnboardingTitleEl.textContent = copy.cliOnboardingTitle;
  if (cliOnboardingNoteEl) cliOnboardingNoteEl.textContent = copy.cliOnboardingNote;
  if (cliOnboardingPillEl) cliOnboardingPillEl.textContent = copy.cliOnboardingPill;
  if (inputRouteTitleEl) inputRouteTitleEl.textContent = copy.inputRouteTitle;
  if (inputRouteNoteEl) inputRouteNoteEl.textContent = copy.inputRouteNote;
  if (inputRoutePillEl) inputRoutePillEl.textContent = copy.inputRoutePill;
  if (serverApiContractTitleEl) serverApiContractTitleEl.textContent = copy.serverApiContractTitle;
  if (serverApiContractNoteEl) serverApiContractNoteEl.textContent = copy.serverApiContractNote;
  if (copyServerApiContractButton) copyServerApiContractButton.textContent = copy.copyServerApiContract;
  renderInputRouteList();
  renderServerApiContractList();
  renderCliOnboardingList();
  if (connectionGuideTitleEl) connectionGuideTitleEl.textContent = copy.guideTitle;
  setStepText(setupStepAuthEl, "1", copy.setupStepAuth);
  setStepText(setupStepParseEl, "2", copy.setupStepParse);
  setStepText(setupStepTranslateEl, "3", copy.setupStepTranslate);
  setStepText(setupStepDownloadEl, "4", copy.setupStepDownload);
  if (saveButton) saveButton.textContent = copy.save;
  if (historyTitle) historyTitle.textContent = copy.historyTitle;
  if (historyNote) historyNote.textContent = copy.historyNote;
  if (refreshHistoryBtn) refreshHistoryBtn.textContent = copy.historyRefresh;
}

function renderServerApiContractList() {
  if (!serverApiContractListEl) return;
  const copy = copyFor(uiLanguage);
  serverApiContractListEl.textContent = "";
  copy.serverApiContract.forEach(([label, value]) => {
    const item = document.createElement("div");
    item.className = "server-api-contract-item";
    const labelEl = document.createElement("span");
    labelEl.className = "server-api-label";
    labelEl.textContent = label;
    const valueEl = document.createElement("code");
    valueEl.className = "server-api-value";
    valueEl.textContent = value;
    item.appendChild(labelEl);
    item.appendChild(valueEl);
    serverApiContractListEl.appendChild(item);
  });
}

function renderInputRouteList() {
  if (!inputRouteListEl) return;
  const copy = copyFor(uiLanguage);
  inputRouteListEl.textContent = "";
  copy.inputRoutes.forEach(([title, status, detail, command]) => {
    const row = document.createElement("div");
    row.className = "input-route-item";
    const header = document.createElement("div");
    header.className = "input-route-header";
    const titleEl = document.createElement("p");
    titleEl.className = "onboarding-title";
    titleEl.textContent = title;
    const statusEl = document.createElement("span");
    statusEl.className = "meta-pill input-route-status";
    statusEl.textContent = status;
    header.appendChild(titleEl);
    header.appendChild(statusEl);
    const detailEl = document.createElement("p");
    detailEl.className = "meta-label";
    detailEl.textContent = detail;
    const commandEl = document.createElement("code");
    commandEl.className = "onboarding-command";
    commandEl.textContent = command;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ghost-chip input-route-copy";
    button.textContent = copy.inputRouteCopy;
    button.addEventListener("click", async () => {
      await navigator.clipboard?.writeText(command);
      button.textContent = copyFor(uiLanguage).inputRouteCopied;
    });
    row.appendChild(header);
    row.appendChild(detailEl);
    row.appendChild(commandEl);
    row.appendChild(button);
    inputRouteListEl.appendChild(row);
  });
}

function renderCliOnboardingList() {
  if (!cliOnboardingListEl) return;
  const copy = copyFor(uiLanguage);
  cliOnboardingListEl.textContent = "";
  copy.cliOnboardingItems.forEach(([title, command, detail], index) => {
    const row = document.createElement("div");
    row.className = "onboarding-item";
    const icon = document.createElement("span");
    icon.className = "guide-index";
    icon.textContent = String(index + 1);
    const body = document.createElement("div");
    body.className = "onboarding-body";
    const heading = document.createElement("p");
    heading.className = "onboarding-title";
    heading.textContent = title;
    const commandEl = document.createElement("code");
    commandEl.className = "onboarding-command";
    commandEl.textContent = command;
    const detailEl = document.createElement("p");
    detailEl.className = "meta-label";
    detailEl.textContent = detail;
    body.appendChild(heading);
    body.appendChild(commandEl);
    body.appendChild(detailEl);
    row.appendChild(icon);
    row.appendChild(body);
    cliOnboardingListEl.appendChild(row);
  });
}

function setStepText(element: HTMLSpanElement | null, index: string, label: string) {
  if (!element) return;
  element.textContent = "";
  const icon = document.createElement("span");
  icon.className = "support-icon";
  icon.textContent = index;
  element.appendChild(icon);
  element.append(label);
}

function renderConnectionGuide(isSignedIn: boolean) {
  if (!connectionGuideListEl) return;
  const copy = copyFor(uiLanguage);
  const items = isSignedIn ? copy.guideSignedIn : copy.guideSignedOut;
  connectionGuideListEl.textContent = "";
  items.forEach((item, index) => {
    const row = document.createElement("div");
    row.className = "guide-item";
    const icon = document.createElement("span");
    icon.className = "guide-index";
    icon.textContent = String(index + 1);
    const text = document.createElement("p");
    text.className = "meta-label";
    text.textContent = item;
    row.appendChild(icon);
    row.appendChild(text);
    connectionGuideListEl.appendChild(row);
  });
}

async function refreshHistory() {
  if (!historyList) return;
  const copy = copyFor(uiLanguage);
  
  try {
    const { items } = await client.getMyTasks();
    if (items.length === 0) {
      renderHistoryNotice(copy.historyEmpty);
      return;
    }

    historyList.textContent = "";
    for (const task of items) {
      const row = document.createElement("div");
      row.className = "history-item";
      
      const header = document.createElement("div");
      header.className = "history-item-header";
      
      const inputDiv = document.createElement("div");
      inputDiv.className = "history-item-input";
      const historyTask = task as HistoryTaskRecord;
      const inputVal = historyTask.paper_input || "Unknown Input";
      inputDiv.textContent = inputVal.length > 50 ? inputVal.substring(0, 50) + "..." : inputVal;
      
      const statusBadge = document.createElement("span");
      statusBadge.className = "history-status-badge";
      statusBadge.textContent = task.status;
      if (task.status === "succeeded") {
        statusBadge.classList.add("history-status-badge-succeeded");
      } else if (task.status === "failed") {
        statusBadge.classList.add("history-status-badge-failed");
      }
      
      header.appendChild(inputDiv);
      header.appendChild(statusBadge);
      row.appendChild(header);

      const artifactEntries = task.result
        ? task.result.artifacts
          ? Object.entries(task.result.artifacts).map(([key, desc]) => [key, desc.filename] as const)
          : (task.result.download_artifacts ?? []).map((desc) => [desc.artifact, desc.filename] as const)
        : [];

      if (task.status === "succeeded" && artifactEntries.length > 0) {
        const artifactsRow = document.createElement("div");
        artifactsRow.className = "history-actions";
        
        for (const [key, filename] of artifactEntries) {
          const dlBtn = document.createElement("button");
          dlBtn.className = "ghost-chip history-download-button";
          dlBtn.textContent = formatArtifactActionLabel(key);
          dlBtn.addEventListener("click", async () => {
            try {
              dlBtn.textContent = uiLanguage === "zh" ? "下载中..." : "Downloading...";
              const result = await client.downloadArtifact(task.task_id, key, filename);
              triggerBlobDownload(result.blob, result.filename);
              dlBtn.textContent = formatArtifactActionLabel(key);
            } catch (err) {
              renderHistoryNotice(`${copyFor(uiLanguage).downloadFailed} ${(err as Error).message}`, "#b91c1c");
              dlBtn.textContent = formatArtifactActionLabel(key);
            }
          });
          artifactsRow.appendChild(dlBtn);
        }
        row.appendChild(artifactsRow);
      }

      const dateStr = historyTask.created_at ? new Date(historyTask.created_at).toLocaleString() : "";
      if (dateStr) {
        const timeDiv = document.createElement("div");
        timeDiv.className = "history-item-time";
        timeDiv.textContent = dateStr;
        row.appendChild(timeDiv);
      }

      historyList.appendChild(row);
    }
  } catch (error) {
    const errorPrefix = copy.historyError;
    renderHistoryNotice(`${errorPrefix}${(error as Error).message}`, "#f44336");
  }
}

async function refreshView() {
  const settings = await readSettings();
  uiLanguage = resolveUiLanguage(settings.uiLanguage, globalThis.navigator?.language);
  applyLanguage();

  if (apiBaseUrlInput) apiBaseUrlInput.value = settings.apiBaseUrl;
  if (uiLanguageSelect) uiLanguageSelect.value = uiLanguage;
  if (accountStatus) {
    accountStatus.textContent = settings.email
      ? copyFor(uiLanguage).signedIn(settings.email)
      : copyFor(uiLanguage).notSignedIn;
  }
  renderConnectionGuide(Boolean(settings.token));

  if (!settings.token) {
    if (usageStatus) {
      usageStatus.textContent = copyFor(uiLanguage).usagePending;
    }
    if (historySection) {
      historySection.hidden = true;
      historySection.style.display = "none";
    }
    return;
  }

  if (historySection) {
    historySection.hidden = false;
    historySection.style.display = "block";
  }

  try {
    const usage = await client.getUsage();
    if (usageStatus) {
      usageStatus.textContent = formatUsageSummary(usage);
    }
  } catch (error) {
    if (usageStatus) {
      usageStatus.textContent = (error as Error).message;
    }
  }
  
  await refreshHistory();
}

if (refreshHistoryBtn) {
  refreshHistoryBtn.addEventListener("click", () => {
    refreshHistoryBtn.textContent = copyFor(uiLanguage).historyRefreshing;
    refreshHistory().then(() => {
      refreshHistoryBtn.textContent = copyFor(uiLanguage).historyRefresh;
    });
  });
}

openAccountButton?.addEventListener("click", () => {
  void openMdteroAccount();
});

copyCliHandoffGuideButton?.addEventListener("click", async () => {
  await navigator.clipboard?.writeText(CLI_HANDOFF_GUIDE_COMMAND);
  copyCliHandoffGuideButton.textContent = copyFor(uiLanguage).cliHandoffGuideCopied;
});

copyMcpServerConfigButton?.addEventListener("click", async () => {
  await navigator.clipboard?.writeText(MCP_SERVER_CONFIG);
  copyMcpServerConfigButton.textContent = copyFor(uiLanguage).mcpServerConfigCopied;
});

copyServerApiContractButton?.addEventListener("click", async () => {
  const contract = copyFor(uiLanguage).serverApiContract
    .map(([label, value]) => `${label}: ${value}`)
    .join("\n");
  await navigator.clipboard?.writeText(contract);
  copyServerApiContractButton.textContent = copyFor(uiLanguage).serverApiContractCopied;
});

saveButton?.addEventListener("click", async () => {
  const current = await readSettings();
  await writeSettings(
      mergeSettings(current, {
        apiBaseUrl: apiBaseUrlInput?.value.trim() || current.apiBaseUrl,
        uiLanguage: resolveUiLanguage(uiLanguageSelect?.value as UiLanguage | undefined, globalThis.navigator?.language)
    })
  );
  await refreshView();
});

uiLanguageSelect?.addEventListener("change", async () => {
  uiLanguage = resolveUiLanguage(uiLanguageSelect.value as UiLanguage, globalThis.navigator?.language);
  const current = await readSettings();
  await writeSettings(
    mergeSettings(current, {
      uiLanguage
    })
  );
  await refreshView();
});

languageToggleEl?.addEventListener("click", async () => {
  uiLanguage = uiLanguage === "en" ? "zh" : "en";
  const current = await readSettings();
  await writeSettings(
    mergeSettings(current, {
      uiLanguage
    })
  );
  await refreshView();
});

void refreshView();
