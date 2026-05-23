# Install

This directory is the public install contract for Mdtero.

Mdtero Account is the control plane for API keys, quota, billing, history, diagnostics, and install prompts. The runtime CLI is the Python package. Agent skill installation is also handled by the Python CLI, so npm is no longer required for the normal install path.

## Recommended Quick Start

```bash
uv tool install git+https://github.com/JonbinC/doi2md.git
mdtero setup
```

This is the current alpha install path. After the PyPI handoff, `uv tool install mdtero` becomes the stable command. Until then, install from GitHub to get the tested `0.2.0a8` client.

`mdtero setup` is the preferred human onboarding flow: it authenticates, offers optional academic-key setup, detects local Codex/Claude/Gemini/Hermes/OpenCode workspaces, and can install selected agent skills before showing next commands. Headless setup with `mdtero setup --api-key <key>` or `MDTERO_API_KEY` intentionally skips agent detection; run `mdtero agent install --interactive` later on the machine that owns the agent workspace.

For a one-command install:

```bash
curl -Ls https://mdtero.com/install.sh | sh -s -- --agent codex
```

For a reviewable install:

```bash
curl -Ls https://mdtero.com/install.sh -o install-mdtero.sh
sh install-mdtero.sh --agent codex
```

The install script requires `uv`, installs the Python runtime from the public GitHub repo during alpha, then runs `mdtero agent install --target <target>`.

## Connect An Agent Workspace

| Agent | Command |
|---|---|
| Claude Code | `mdtero agent install --target claude_code` |
| Codex | `mdtero agent install --target codex` |
| Gemini CLI | `mdtero agent install --target gemini_cli` |
| Hermes Agent | `mdtero agent install --target hermes` |
| OpenCode | `mdtero agent install --target opencode` |
| OpenClaw | `clawhub install mdtero` |

Useful variants:

```bash
mdtero agent install              # auto-detect existing agent directories
mdtero agent install --interactive # prompt and multi-select by number or target name
mdtero agent install --all
mdtero agent install --target codex --dry-run
mdtero agent uninstall --target codex
```

The old npm installer runtime has been retired from this repository. Use the Python CLI for both runtime commands and agent skill installation.

## Use Mdtero After Setup

```bash
mdtero doctor
mdtero discover "thermochemical energy storage" --limit 5
mdtero discover "thermochemical energy storage" --limit 5 --interactive
mdtero discover "thermochemical energy storage" --limit 5 --add --select 1,3
mdtero config academic --semantic-scholar-key <key> --json
mdtero parse 10.48550/arXiv.1706.03762
mdtero parse https://example.org/open-paper --trace
mdtero parse --file paper.pdf
mdtero parse --batch ./papers
mdtero project init --json
mdtero project status --json
mdtero project import-bib references.bib
mdtero project parse --wait
mdtero project refresh
mdtero project download --output-dir ./mdtero-output
mdtero config zotero
mdtero zotero import --collection <collection-id>
mdtero status <task-id>
mdtero download <task-id> paper_md --json
mdtero translate <parse-task-id> --to zh-CN
mdtero translate paper.md --to zh-CN
mdtero rag status --json
mdtero rag build --json
mdtero rag query "What are the strongest findings?" --json
mdtero mcp serve
```

What is validated in the current alpha:

- interactive and headless academic-key setup. `mdtero config academic --json` prints a safe configured/missing summary, and flags such as `--semantic-scholar-key <key>` let agents or headless servers configure local Semantic Scholar discovery without a prompt.
- DOI/arXiv parse, status polling, Markdown download, and bundle download.
- PDF upload through the backend MinerU URL API path. The backend fetches the uploaded file URL for MinerU instead of relying on the older external OSS upload path.
- backend-planned local source acquisition through `curl_cffi` for HTML/XML/EPUB/PDF URLs, with `httpx` fallback and `--trace` visibility.
- local project state, BibTeX import, de-duplication, project parse/refresh/download.
- Zotero metadata import into the current Mdtero project, plus conservative note/tag sync for succeeded Zotero-origin parse tasks.
- discovery with local Semantic Scholar when configured, otherwise backend OpenAlex fallback. `--interactive` shows numbered results and lets a human multi-select papers into the local project queue; `--add --select 1,3` keeps the same flow scriptable.
- server-side Voyage RAG query responses with extractive `answer`, stable `citations`, raw `matches`, `reason_code`, and `next_commands` for CLI and agent continuation.
- agent skill installation without npm for Codex, Claude Code, Gemini CLI, Hermes, and OpenCode, with TUI/MCP status showing detected, installed, and pending skill targets.

Current boundaries:

- RAG is server-side Voyage RAG. `mdtero rag build` creates and binds a server project when needed, imports succeeded parse tasks, and starts the backend Voyage build; `mdtero rag status --json` reports readiness and next commands; `mdtero rag query --json` returns `answer`, `citations`, and `matches`.
- `mdtero zotero sync` is conservative: it writes Mdtero result notes/tags for succeeded Zotero-origin parse tasks with known Zotero item keys; it does not rewrite Zotero bibliographic metadata.
- GROBID is not exposed as a user-selectable public engine; PDF parsing is MinerU-first on the backend.

For machines with a browser, run `mdtero login`; it opens Mdtero Account and stores the one-time CLI key returned through the local loopback callback.

For headless agents, create a fresh API key in Mdtero Account and use:

```bash
mdtero login --api-key <key>
```

## Update Or Uninstall

```bash
uv tool upgrade mdtero
mdtero agent install --target codex
mdtero agent uninstall --target codex
uv tool uninstall mdtero
```

`mdtero agent uninstall <target>` removes only the selected skill bundle. It does not remove API keys, generated Markdown, downloaded papers, Zotero data, local project state, or backend artifacts.

## Troubleshooting

- If `mdtero` is missing during alpha, run `uv tool install git+https://github.com/JonbinC/doi2md.git`.
- If `uv` is missing, install it from `https://docs.astral.sh/uv/getting-started/installation/`.
- If `mdtero doctor` reports a missing API key, run `mdtero setup` or `mdtero login --api-key <key>`.
- If no agent workspace is detected, pass an explicit `--target`.
- If OpenClaw is needed, use `clawhub install mdtero`; `mdtero agent install --target openclaw` is intentionally unsupported.

## Boundary

The Python runtime owns setup, login, discovery, parse, task polling, download, BibTeX/Zotero import, project state, RAG commands, MCP context, TUI, and agent skill installation.

The browser extension owns browser-context capture, OAuth bridge, user-selected PDF/EPUB upload, translation requests, polling, and artifact download. It does not include Python packages or local parser engines.

## 中文版

Mdtero 当前公开主线是 Python/uv 客户端。alpha 阶段推荐：

```bash
uv tool install git+https://github.com/JonbinC/doi2md.git
mdtero setup
mdtero doctor
```

安装 agent skill 不再依赖 npm：

```bash
mdtero agent install --target codex
mdtero agent install --interactive
mdtero agent install --all
```

常用验证流程：

```bash
mdtero project init --name alpha-test
mdtero project status --json
mdtero parse 10.48550/arXiv.1706.03762 --json
mdtero parse --file paper.pdf --json
mdtero status <task-id> --wait --json
mdtero download <task-id> paper_md --output-dir ./out --json
mdtero project import-bib references.bib
mdtero rag status --json
mdtero rag build --json
mdtero rag query "这批论文的核心方法是什么？" --json
mdtero config zotero
mdtero zotero import --limit 20 --json
mdtero zotero sync --json
mdtero mcp serve
```

当前已经验证 DOI 解析、PDF 上传解析、项目管理、BibTeX 导入、Zotero 导入、Zotero 成功任务 note/tag 反向同步、下载、后端 Voyage RAG 绑定/导入/build/query、agent skill 安装和 MCP 本地上下文。RAG query 会返回 `answer`、`citations` 和 `matches`，TUI/MCP 会显示 agent skill 的 detected/installed/pending 状态，agent skill 安装走 Python CLI，不再依赖 npm。
