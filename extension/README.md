# Mdtero Extension

Mdtero Extension is the browser surface for login, current-page/DOI parse, user-selected PDF/EPUB upload, task polling, translation, and artifact download. It uses Mdtero Account for sign-in and the Mdtero backend for routing, parsing, packaging, translation, and quota.

## Install

Build or install the packaged extension, then load the extension folder in a Chromium browser. The extension needs storage for your Mdtero token, downloads for Markdown/zip/translation artifacts, tabs for supported paper pages, and host access for Mdtero plus scholarly sources it may inspect from the active tab.

```bash
npm install
npm run build
```

## Sign In

Open the popup or options page and choose **Open Mdtero Account**. Sign in at `https://mdtero.com/auth`; the website hands the extension a `{ type: "mdtero.auth.token", token, email }` message through the trusted auth bridge on Mdtero origins. The extension no longer maintains its own email, password, or email-code login form.

The auth bridge only accepts messages from `https://mdtero.com` and `https://www.mdtero.com` (plus localhost during development). Publisher pages cannot mint extension tokens, and the extension does not store publisher API keys, TDM keys, or local helper credentials.

## Parse Papers

Start from a DOI, the current paper tab, or a local PDF/EPUB. The extension creates a backend task, polls it, and shows returned artifacts. Markdown is the primary download when `paper_md` is available; when figure/assets are packaged separately, the backend returns a `paper_bundle` zip.

Supported paths work best for DOI/arXiv pages, open publisher pages, and user-selected PDF/EPUB files. PDF parsing is MinerU-first on the backend and uses the URL API path for uploaded files when available. GROBID is not exposed as a public engine choice in the extension.

## Translate

After a parse task succeeds, the Translate button uses the parsed Markdown artifact as the source for the backend translation task. The extension polls the translation task and exposes the returned translated Markdown artifact for download.

## Privacy And Local Files

Tokens, email, and UI language are stored in browser local storage. Local PDF/EPUB intake uploads the chosen file to create a parse task. The extension does not bundle Python dependencies such as `curl_cffi`, `pyzotero`, or `fastmcp`; those belong to the Python CLI.

The extension does not use native messaging or a local helper process. When browser capture is blocked by a challenge page, campus-network dependency, or logged-in session state, the popup shows a CLI handoff command instead of trying to bypass the page inside the extension.

## CLI Handoff

When browser context is not enough, install the Python client and let its setup checklist guide the local workflow:

```bash
uv tool install --force git+https://github.com/JonbinC/doi2md.git
mdtero setup
mdtero setup --json
```

During alpha, use the GitHub command above because the old PyPI `mdtero` package still points at a retired backend bundle. Use `uv tool install mdtero` only after the public client is republished there.

`mdtero setup --json` returns a secret-safe onboarding checklist for local agents: website OAuth or trusted headless auth, optional academic keys, Semantic Scholar versus OpenAlex discovery, project creation, DOI/file/batch parsing, Zotero intake, backend Voyage RAG, FastMCP briefing/serve, and interactive agent skill install.

## 中文版

Mdtero 浏览器扩展只保留主线能力：登录、当前页/DOI 解析、PDF/EPUB 上传、任务轮询、翻译和下载。解析、MinerU PDF 处理、打包、额度和翻译都由后端完成；扩展不内置 Python 依赖，也不暴露 GROBID 引擎选择。

常规路径：

1. 在扩展弹窗或设置页登录 Mdtero Account。
2. 从当前论文页、DOI、PDF 或 EPUB 创建解析任务。
3. 等待任务完成后下载 `paper_md` 或 `paper_bundle`。
4. 需要中文版本时，对成功任务发起翻译并下载翻译后的 Markdown。

如果需要项目管理、BibTeX/Zotero 导入、RAG、MCP 或 agent skill，请使用 Python CLI：`uv tool install --force git+https://github.com/JonbinC/doi2md.git`。alpha 阶段先走 GitHub，等 PyPI 包重新发布后再切回 PyPI。
