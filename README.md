<div align="center">
  <img src="./extension/src/assets/icon-128.png" alt="Mdtero logo" width="120" />

  # Mdtero Public Install Surface

  *Python/uv CLI, TUI, browser extension, and agent skill bundle for paper-to-Markdown workflows.*
</div>

Mdtero turns papers into reusable Markdown research packages.

This repository is the public home for the active launch surfaces:

- Python runtime CLI/TUI package `mdtero`, installed with `uv tool install --force git+https://github.com/JonbinC/doi2md.git`
- browser extension for OAuth login, DOI/current-page parse, PDF/EPUB upload, translation, polling, and download
- packaged agent skill bundle installed by the Python CLI with `mdtero agent install`

The old npm installer runtime has been retired from this repository. Skill installation is handled by the Python CLI.

## Quick Start

```bash
uv tool install --force git+https://github.com/JonbinC/doi2md.git
mdtero setup
```

During alpha, install the known-good public client from GitHub with `uv tool install --force git+https://github.com/JonbinC/doi2md.git`. The old PyPI `mdtero` package currently points at a retired backend bundle; use the PyPI command only after the public client is republished there.

`mdtero setup` handles login, optional academic-key configuration, and local agent workspace detection in the interactive flow. When it finds existing `~/.codex`, `~/.claude`, `~/.gemini`, `~/.hermes`, or `~/.opencode` directories, it can multi-select and install the Mdtero skill during onboarding. Headless setup with `mdtero setup --api-key --json` or `MDTERO_API_KEY` skips agent detection; run `mdtero agent install --interactive` later on the workstation where the agent lives.

For a one-command agent setup:

```bash
curl -Ls https://mdtero.com/install.sh | sh
curl -Ls https://mdtero.com/install.sh | sh -s -- --agent codex
```

The script installs `uv` when needed and installs the Python runtime. Pass `--agent <target>` to also install an agent skill.

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
mdtero setup --api-key --json
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
mdtero discover Thermochemical Energy storage Vermiculite --limit 5 --json
mdtero discover "thermochemical energy storage" --limit 5 --interactive
mdtero discover "thermochemical energy storage" --limit 5 --add --select 1,3 --json
mdtero parse 10.48550/arXiv.1706.03762 --json
mdtero parse '10.1016/S0260-8774(02)00304-7' --trace --wait --timeout 300 --json
mdtero parse https://example.org/open-paper --trace --wait --timeout 300 --json
mdtero parse --file paper.pdf --trace --wait --timeout 600 --json
mdtero parse --batch ./papers --wait --timeout 300 --json
mdtero parse-batch dois.txt --wait --download paper_md --output-dir ./mdtero-output --json
mdtero status <task-id> --wait --timeout 300 --json
mdtero download <task-id> paper_md --output-dir ./mdtero-output --json
mdtero download <task-id> paper_md --filename-template "{author}_{year}_{shorttitle}" --output-dir ./mdtero-output --json
mdtero translate <parse-task-id> --to zh-CN --wait --timeout 600 --json
mdtero translate paper.md --to zh-CN --wait --timeout 600 --json
mdtero rag status --json
mdtero rag query "What are the strongest findings?" --build-if-needed --json
mdtero rag build --json
mdtero smoke --json --timeout 600 --interval 2
mdtero mcp briefing --json
mdtero mcp serve
mdtero tui
```

## Current Alpha Scope

Validated in the current alpha:

- API-key login, `mdtero doctor`, `mdtero doctor --json`, and local config; JSON diagnostics include safe auth/dependency/academic/Zotero/project/RAG summaries plus `next_commands` without echoing secrets
- deploy smoke with `mdtero smoke --json`; it creates an isolated project, runs discovery, arXiv/DOI parse with task polling, artifact download, server-side Voyage RAG build/status/query, validates `mdtero mcp briefing --json` exposes `agent_briefing`, `server_rag_status`, `server_rag_build`, and `rag_query`, and returns step-level `reason_code`, `action_hint`, task ids, paths, server project id, plus top-level `primary_failure`, `failed_steps`, and recovery `next_commands` when a smoke step fails
- optional academic-key setup through either the interactive `mdtero config academic` flow or headless flags such as `--semantic-scholar-key <key> --json`; JSON output reports configured keys without echoing secrets
- DOI/arXiv parse with task polling and Markdown/bundle download
- batch DOI/URL parse with `mdtero parse-batch dois.txt --wait --download paper_md --output-dir ./mdtero-output --json`, writing `manifest.csv` and `failed.csv`
- PDF upload through the backend MinerU URL API path, returning Markdown and zip artifacts when parsing succeeds
- local project init/add/remove/list/status, BibTeX import with de-duplication, project parse/refresh/download, and agent-readable JSON for project management commands
- Zotero metadata import into a local Mdtero project, plus reverse sync of succeeded parse task notes/tags back to Zotero items imported after `0.2.0a7`
- discovery through local Semantic Scholar when configured, otherwise the backend OpenAlex fallback; if Semantic Scholar is unavailable, `--json` reports `local_semantic_scholar_failure` and `discovery_fallback` so agents can continue with OpenAlex while preserving the reason code; multi-word queries work with or without shell quotes, and `mdtero discover "<query>" --interactive` can inspect results and multi-select papers into the local project queue
- `status`, waited parse results, and downloads expose `quality_label` / `quality_warning` for low-content artifacts such as `metadata_only`, `abstract_only`, `section_only_fulltext`, and `low_confidence_parse`; Markdown downloads default to `author_year_shorttitle.md`, append `.low_quality.md` for low-confidence full text, and update `manifest.csv`
- local route acquisition with `curl_cffi` for backend-planned HTML/XML/EPUB/PDF source fetches, with `httpx` fallback and visible `client_acquisition` trace output
- server-side translation requests from parse task ids or local Markdown files
- server-side Voyage RAG query/bootstrap; `mdtero rag query "What are the strongest findings?" --build-if-needed --json` creates or reuses the server project, imports completed Markdown, builds the backend Voyage index, and queries without asking the user to copy a server project id; query JSON returns extractive `answer`, stable `citations`, raw `matches`, LlamaIndex-style `source_nodes`, an `evidence_pack.context_markdown`, `citation_contract.required_for_final_answer`, `reason_code`, and `next_commands` for agents
- local FastMCP project context server, including the `agent_briefing` tool for one-call account status, project health, ready downloads, blocked items, RAG status, detected/installed/pending agent skills, recommended next commands, and a structured `mcp_tool_plan` playbook that tells local agents when to call `project_init`, `project_add`, `submit_parse`, `task_status`, `download_artifact`, `request_translation`, `server_rag_status`, `server_rag_build`, or `rag_query`; `mdtero mcp briefing --json` also works in a directory before `project init` and returns initialization commands instead of a traceback
- TUI dashboard command palette for copyable setup, discovery, parse, Zotero, RAG, MCP, and agent-install commands, with current next commands highlighted for workstation or local-agent handoff
- Extension-to-CLI handoff for publisher challenge pages, campus-network/session-bound access, and browser-saved files keeps a full recovery plan visible to the user and local agent:

```bash
mdtero doctor --json
mdtero parse <doi-or-url> --trace --wait --timeout 300 --json
mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json
mdtero status <task-id> --wait --timeout 300 --json
mdtero download <task-id> paper_md --output-dir ./mdtero-output --json
mdtero rag query "What are the strongest findings?" --build-if-needed --json
mdtero mcp briefing --json
```

  This path preserves `client_acquisition`, raw upload, status polling, `reason_code`, `action_hint`, `download_artifacts`, and `next_commands` instead of hiding failures inside the browser extension.
- MCP and agent-facing recommended commands prefer `--json` on doctor, parse, refresh, ingest, RAG, and download steps so local agents can parse results without scraping terminal tables
- agent-facing JSON and MCP payloads sanitize signed MinerU/OSS URLs, bearer/API-key headers, Mdtero API keys, and common token query parameters before returning data to local agents; keep `reason_code`, `action_hint`, `next_commands`, and evidence fields visible, but do not use agent prompts as long-term secret storage
- agent skill installation for Codex, Claude Code, Gemini CLI, Hermes, and OpenCode

Shared `/api/v1` server contract for every intake surface:

| Purpose | Route |
| --- | --- |
| Route planning | `/api/v1/route` |
| DOI/URL parse task | `/api/v1/tasks/parse` |
| PDF/EPUB/XML/HTML upload | `/api/v1/tasks/upload` |
| Task status | `/api/v1/tasks/{task_id}` |
| Artifact download | `/api/v1/tasks/{task_id}/download/{artifact}` |
| Import parsed Markdown into a server project | `/api/v1/projects/{project_id}/tasks/{task_id}/import` |
| Build backend Voyage RAG | `/api/v1/projects/{project_id}/rag/build` |
| Query backend Voyage RAG | `/api/v1/projects/{project_id}/rag/query` |

The CLI, extension, dashboard, and MCP briefing expose this contract so browser capture, CLI retry, raw upload, task polling, download, project import, and backend Voyage RAG handoff stay aligned.

Known boundaries:

- Zotero reverse sync is conservative: it creates Mdtero result notes/tags for succeeded Zotero-origin parse tasks with known Zotero item keys; it does not rewrite Zotero bibliographic metadata.
- `mdtero rag query --build-if-needed --json` is the primary server-side Voyage RAG path. It can create, bind, import, build, and query from one agent-safe command, returning `answer`, `citations`, `matches`, `source_nodes`, `evidence_pack`, and `citation_contract`; `citation_contract.required_for_final_answer` tells agents to preserve `citations` and `source_nodes` in final answers. `mdtero rag build`, `mdtero project create-server`, and `mdtero project ingest` remain available for explicit recovery/debug workflows.
- GROBID is not a public product option. PDF parsing is MinerU-first on the backend, with internal fallback behavior owned by the service.

## Product Boundary

Mdtero Account is the control plane for Mdtero API keys, quota, billing, history, and install prompts. Academic source keys stay in local `mdtero config academic` configuration. The Python client owns local project state, BibTeX/Zotero import, TUI, MCP context, and agent skill installation. The backend owns parsing, MinerU PDF processing, OpenAlex fallback discovery, LLM translation, task artifacts, and server-side RAG.

The browser extension stays a browser surface. It does not ship Python dependencies such as `curl_cffi`, `pyzotero`, or `fastmcp`; it only handles browser-context capture and user-selected file upload/download. When a publisher challenge, campus network, or logged-in browser session blocks automatic capture, hand the DOI, URL, or saved PDF/EPUB/XML/HTML file to the Python CLI. That path keeps route planning, `curl_cffi` acquisition, raw artifact upload, task polling, and structured failure fields visible to local agents.

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

Mdtero 当前公开主线是 Python/uv 客户端、浏览器扩展和 agent skill。alpha 阶段默认从 GitHub 安装已验证客户端；等 PyPI 包重新发布后再切回 PyPI：

```bash
uv tool install --force git+https://github.com/JonbinC/doi2md.git
# fallback: uv tool install --force git+https://github.com/JonbinC/doi2md.git
mdtero setup
mdtero doctor
mdtero doctor --json
```

常用流程：

```bash
mdtero parse 10.48550/arXiv.1706.03762 --json
mdtero parse --file paper.pdf --trace --wait --timeout 600 --json
mdtero status <task-id> --wait --timeout 300 --json
mdtero download <task-id> paper_md --output-dir ./out --json
mdtero project init --name literature-review
mdtero project status --json
mdtero project import-bib references.bib --json
mdtero project parse --wait --timeout 300 --json
mdtero translate <parse-task-id> --to zh-CN --wait --timeout 600 --json
mdtero rag query "这批论文的核心方法是什么？" --build-if-needed --json
mdtero rag status --json
mdtero rag build --json
mdtero zotero import --limit 20 --json
mdtero zotero sync --json
mdtero agent install --interactive
mdtero agent install --target codex
mdtero mcp serve
```

当前已经跑通 DOI 解析、PDF 上传解析、项目管理、BibTeX 导入、Zotero 导入、Zotero 成功任务 note/tag 反向同步、下载、后端 Voyage RAG 自动绑定/导入/build/query、agent skill 安装和 MCP 本地上下文。RAG query 会返回 `answer`、`citations`、`matches`、`source_nodes`、`evidence_pack.context_markdown` 和 `citation_contract.required_for_final_answer`，方便 agent 直接引用证据并保留来源；最终回答必须保留 `citations` 和 `source_nodes`。MCP 的首选入口是 `agent_briefing`，会一次返回账户状态、项目健康、可下载成果、失败项、RAG 状态、agent skill 安装状态、下一步命令和 `mcp_tool_plan`；本地 agent 应按这个 playbook 选择 `project_init`、`project_add`、`submit_parse`、`task_status`、`download_artifact`、`request_translation`、`server_rag_status`、`server_rag_build` 或 `rag_query`，并在失败时读取 `failure_fields` 中的 `reason_code`、`action_hint` 和 `next_commands`。当后端返回 `needs_build` 时，MCP agent 应先调用 `server_rag_build(wait=true)`，等待 `status_after_build.ready_for_query` 后再调用 `rag_query(question)`；agent skill 安装由 Python CLI 负责，不依赖 npm。
`mdtero doctor --json` 是给本地 agent 和上线 smoke 用的结构化入口，会返回认证、依赖、学术 key 是否配置、Zotero、项目队列、server project/RAG readiness 和下一步命令，但不会输出任何 secret。
`mdtero smoke --json` 是上线后复测入口，会在临时项目里跑 discovery、DOI/arXiv 解析、下载、服务端 Voyage RAG build/status/query，并验证 `mdtero mcp briefing --json` 暴露 `agent_briefing`、`server_rag_status`、`server_rag_build` 和 `rag_query`；同时输出每一步的 `reason_code`、`action_hint`、task id、下载路径和 server project id，失败时顶层还会返回 `primary_failure`、`failed_steps` 和可继续执行的 `next_commands`。
CLI JSON 和 MCP payload 会在交给本地 agent 前清理带签名的 MinerU/OSS URL、Bearer/API-key header、Mdtero API key 和常见 token query 参数；`reason_code`、`action_hint`、`next_commands` 和证据字段仍会保留，方便 agent 继续执行。
当浏览器扩展遇到 publisher challenge、校园网/机构登录态或只能由用户保存文件的场景时，把 DOI、URL 或已保存的 PDF/EPUB/XML/HTML 交给 Python CLI 继续，并保留完整交接链路：

```bash
mdtero doctor --json
mdtero parse <doi-or-url> --trace --wait --timeout 300 --json
mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json
mdtero status <task-id> --wait --timeout 300 --json
mdtero download <task-id> paper_md --output-dir ./mdtero-output --json
mdtero rag query "What are the strongest findings?" --build-if-needed --json
mdtero mcp briefing --json
```

这样 `client_acquisition`、raw upload、状态轮询、`reason_code`、`action_hint`、`download_artifacts` 和 `next_commands` 仍然对本地 agent 可见。

所有输入入口共用同一组 `/api/v1` 服务端契约：`/api/v1/route`、`/api/v1/tasks/parse`、`/api/v1/tasks/upload`、`/api/v1/tasks/{task_id}`、`/api/v1/tasks/{task_id}/download/{artifact}`、`/api/v1/projects/{project_id}/tasks/{task_id}/import`、`/api/v1/projects/{project_id}/rag/build` 和 `/api/v1/projects/{project_id}/rag/query`。CLI、扩展、dashboard 和 MCP briefing 都会暴露这组 contract，保证浏览器抓取、CLI 重试、raw upload、任务轮询、下载、项目导入和后端 Voyage RAG 交接保持一致。
