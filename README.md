<div align="center">
  <img src="./extension/src/assets/icon-128.png" alt="Mdtero logo" width="120" />

  # Mdtero Public Install Surface

  *Python/uv CLI, TUI, browser extension, and agent skill bundle for paper-to-Markdown workflows.*
</div>

Mdtero turns papers into reusable Markdown research packages.

This repository is the public home for the active launch surfaces:

- Python runtime CLI/TUI package `mdtero`, installed from GitHub for the current alpha
- browser extension for OAuth login, DOI/current-page parse, PDF/EPUB upload, translation, polling, and download
- packaged agent skill bundle installed by the Python CLI with `mdtero agent install`

The old npm installer runtime has been retired from this repository. Skill installation is handled by the Python CLI.

## Quick Start

```bash
uv tool install git+https://github.com/JonbinC/doi2md.git
mdtero setup
```

After the PyPI handoff, the stable install command will be `uv tool install mdtero`. Until then, use the GitHub install above so you get the tested `0.2.0a9` Python client instead of an unrelated package name collision.

`mdtero setup` handles login, optional academic-key configuration, and local agent workspace detection in the interactive flow. When it finds existing `~/.codex`, `~/.claude`, `~/.gemini`, `~/.hermes`, or `~/.opencode` directories, it can multi-select and install the Mdtero skill during onboarding. Headless setup with `mdtero setup --api-key <key>` or `MDTERO_API_KEY` skips agent detection; run `mdtero agent install --interactive` later on the workstation where the agent lives.

For a one-command agent setup:

```bash
curl -Ls https://mdtero.com/install.sh | sh -s -- --agent codex
```

The script requires `uv`, installs the Python runtime, then runs `mdtero agent install --target <target>`.

## Agent Targets

```bash
mdtero agent install --target claude_code
mdtero agent install --target codex
mdtero agent install --target gemini_cli
mdtero agent install --target hermes
mdtero agent install --target opencode
mdtero agent detect --json
mdtero agent install --interactive
mdtero agent install --all
mdtero agent uninstall --target codex
```

Run `mdtero agent detect --json` first when an agent or script needs a machine-readable list of detected workspaces, current install state, and the exact `mdtero agent install --target ...` command. For a human setup flow, `mdtero agent install --interactive` shows detected workspaces and lets you multi-select by number or target name; Enter installs detected pending targets. If `--target` is omitted, Mdtero detects existing `~/.codex`, `~/.claude`, `~/.gemini`, `~/.hermes`, and `~/.opencode` directories and installs into the detected workspaces.

OpenClaw keeps the dedicated route:

```bash
clawhub install mdtero
```

## Runtime Commands

```bash
mdtero doctor
mdtero doctor --json
mdtero login
mdtero setup --api-key <key>
mdtero config academic
mdtero config academic --semantic-scholar-key <key> --json
mdtero project init --json
mdtero project status --json
mdtero project import-bib references.bib --json
mdtero project parse --wait --timeout 300 --json
mdtero project refresh --wait --timeout 300 --json
mdtero project download --output-dir ./mdtero-output --json
mdtero config zotero
mdtero zotero import --json
mdtero zotero sync --json
mdtero discover "thermochemical energy storage" --limit 5 --json
mdtero discover "thermochemical energy storage" --limit 5 --interactive
mdtero discover "thermochemical energy storage" --limit 5 --add --select 1,3
mdtero parse 10.48550/arXiv.1706.03762 --json
mdtero parse https://example.org/open-paper --trace --wait --timeout 300 --json
mdtero parse --file paper.pdf --wait --timeout 300 --json
mdtero parse --batch ./papers --wait --timeout 300 --json
mdtero status <task-id> --wait --timeout 300 --json
mdtero download <task-id> paper_md --json
mdtero translate <parse-task-id> --to zh-CN --json
mdtero translate paper.md --to zh-CN --json
mdtero rag status --json
mdtero rag build --json
mdtero rag query "What are the strongest findings?" --build-if-needed --json
mdtero mcp serve
mdtero tui
```

## Current Alpha Scope

Validated in the current alpha:

- API-key login, `mdtero doctor`, `mdtero doctor --json`, and local config; JSON diagnostics include safe auth/dependency/academic/Zotero/project/RAG summaries plus `next_commands` without echoing secrets
- optional academic-key setup through either the interactive `mdtero config academic` flow or headless flags such as `--semantic-scholar-key <key> --json`; JSON output reports configured keys without echoing secrets
- DOI/arXiv parse with task polling and Markdown/bundle download
- PDF upload through the backend MinerU URL API path, returning Markdown and zip artifacts when parsing succeeds
- local project init/add/remove/list/status, BibTeX import with de-duplication, project parse/refresh/download, and agent-readable JSON for project management commands
- Zotero metadata import into a local Mdtero project, plus reverse sync of succeeded parse task notes/tags back to Zotero items imported after `0.2.0a7`
- discovery through local Semantic Scholar when configured, otherwise the backend OpenAlex fallback; if Semantic Scholar is unavailable, `--json` reports `local_semantic_scholar_failure` and `discovery_fallback` so agents can continue with OpenAlex while preserving the reason code; use `mdtero discover "<query>" --interactive` to inspect results and multi-select papers into the local project queue, or `--add --select 1,3` for scripts
- local route acquisition with `curl_cffi` for backend-planned HTML/XML/EPUB/PDF source fetches, with `httpx` fallback and visible `client_acquisition` trace output
- server-side translation requests from parse task ids or local Markdown files
- server-side Voyage RAG build/query; query JSON returns extractive `answer`, stable `citations`, raw `matches`, LlamaIndex-style `source_nodes`, an `evidence_pack.context_markdown`, `reason_code`, and `next_commands` for agents
- local FastMCP project context server, including the `agent_briefing` tool for one-call account status, project health, ready downloads, blocked items, RAG status, detected/installed/pending agent skills, recommended next commands, and a `rag_query(question)` tool that can bootstrap server RAG before querying
- MCP and agent-facing recommended commands prefer `--json` on doctor, parse, refresh, ingest, RAG, and download steps so local agents can parse results without scraping terminal tables
- agent skill installation for Codex, Claude Code, Gemini CLI, Hermes, and OpenCode

Known boundaries:

- Zotero reverse sync is conservative: it creates Mdtero result notes/tags for succeeded Zotero-origin parse tasks with known Zotero item keys; it does not rewrite Zotero bibliographic metadata.
- `mdtero rag build/query` talks to server-side Voyage RAG. `mdtero rag build` now bootstraps the server project when needed, imports succeeded parse tasks, and starts the backend Voyage build. `mdtero rag query --build-if-needed --json` can create, bind, import, build, and query from one agent-safe command, returning `answer`, `citations`, `matches`, `source_nodes`, and `evidence_pack`; `mdtero project create-server` and `mdtero project ingest` remain available for explicit or recovery workflows.
- GROBID is not a public product option. PDF parsing is MinerU-first on the backend, with internal fallback behavior owned by the service.

## Product Boundary

Mdtero Account is the control plane for Mdtero API keys, quota, billing, history, and install prompts. Academic source keys stay in local `mdtero config academic` configuration. The Python client owns local project state, BibTeX/Zotero import, TUI, MCP context, and agent skill installation. The backend owns parsing, MinerU PDF processing, OpenAlex fallback discovery, LLM translation, task artifacts, and server-side RAG.

The browser extension stays a browser surface. It does not ship Python dependencies such as `curl_cffi`, `pyzotero`, or `fastmcp`; it only handles browser-context capture and user-selected file upload/download.

## Repo Map

- [`src/mdtero`](./src/mdtero): Python CLI/TUI/client package
- [`extension`](./extension): MV3 browser extension source, tests, and build output
- [`install`](./install): website install manifest and install guide
- [`skills`](./skills): agent skill source mirrored into the Python CLI installer

## Local Development

```bash
uv run --with pytest --with rich --with textual --with httpx --with requests --with curl_cffi --with pyzotero --with fastmcp pytest tests_py -q
uv run --with build python -m build --wheel
npm --prefix extension test
npm --prefix extension run build
```

## 中文说明

Mdtero 当前公开主线是 Python/uv 客户端、浏览器扩展和 agent skill。alpha 阶段请从 GitHub 安装：

```bash
uv tool install git+https://github.com/JonbinC/doi2md.git
mdtero setup
mdtero doctor
mdtero doctor --json
```

常用流程：

```bash
mdtero parse 10.48550/arXiv.1706.03762 --json
mdtero parse --file paper.pdf --wait --timeout 300 --json
mdtero status <task-id> --wait --timeout 300 --json
mdtero download <task-id> paper_md --output-dir ./out --json
mdtero project init --name literature-review
mdtero project status --json
mdtero project import-bib references.bib --json
mdtero project parse --wait --timeout 300 --json
mdtero translate <parse-task-id> --to zh-CN --json
mdtero rag status --json
mdtero rag build --json
mdtero rag query "这批论文的核心方法是什么？" --build-if-needed --json
mdtero zotero import --limit 20 --json
mdtero zotero sync --json
mdtero agent install --interactive
mdtero agent install --target codex
mdtero mcp serve
```

当前已经跑通 DOI 解析、PDF 上传解析、项目管理、BibTeX 导入、Zotero 导入、Zotero 成功任务 note/tag 反向同步、下载、后端 Voyage RAG 自动绑定/导入/build/query、agent skill 安装和 MCP 本地上下文。RAG query 会返回 `answer`、`citations`、`matches`、`source_nodes` 和 `evidence_pack.context_markdown`，方便 agent 直接引用证据并保留来源。MCP 的首选入口是 `agent_briefing`，会一次返回账户状态、项目健康、可下载成果、失败项、RAG 状态、agent skill 安装状态和下一步命令；MCP `rag_query(question)` 工具也会在需要时创建/绑定 server project、导入成功任务并触发 build，然后再查询。agent skill 安装由 Python CLI 负责，不依赖 npm。
`mdtero doctor --json` 是给本地 agent 和上线 smoke 用的结构化入口，会返回认证、依赖、学术 key 是否配置、Zotero、项目队列、server project/RAG readiness 和下一步命令，但不会输出任何 secret。
