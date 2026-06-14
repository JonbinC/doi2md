<div align="center">
  <img src="./extension/src/assets/icon-128.png" alt="Mdtero logo" width="120" />

  # Mdtero Public Install Surface

  *Python/uv CLI, TUI, browser extension, and agent skill bundle for paper-to-Markdown workflows.*
</div>

Mdtero turns papers into reusable Markdown research packages for humans, local agents, and downstream RAG workflows.

**Languages:** English | [简体中文](./README_CN.md)

This repository is the public home for the active launch surfaces:

- Python runtime CLI/TUI package `mdtero`, installed with `uv tool install --force --reinstall git+https://github.com/JonbinC/doi2md.git` during alpha.
- Browser extension for OAuth login, DOI/current-page parse, PDF/EPUB upload, translation, polling, and download.
- Packaged agent skill bundle installed by the Python CLI with `mdtero agent install`.

The old npm installer runtime has been retired from this repository. Skill installation is handled by the Python CLI.

## Quick Start

```bash
uv tool install --force --reinstall git+https://github.com/JonbinC/doi2md.git
mdtero setup
mdtero doctor --json
```

During alpha, install the known-good public client from GitHub with `uv tool install --force --reinstall git+https://github.com/JonbinC/doi2md.git`. The old PyPI `mdtero` package currently points at a retired backend bundle; use `uv tool install mdtero` only after the public client is republished there.

If a machine has no `uv`, use the installer script:

```bash
curl -Ls https://mdtero.com/install.sh | sh
curl -Ls https://mdtero.com/install.sh | sh -s -- --agent codex
```

The script prefers `uv`, falls back to `pipx install --force git+https://github.com/JonbinC/doi2md.git`, then falls back to `python3 -m pip install --user --force-reinstall git+https://github.com/JonbinC/doi2md.git`. Pass `--agent <target>` to also install an agent skill.

`mdtero setup` handles login, optional academic-key configuration, and local agent workspace detection in the interactive flow. It detects local Codex/Claude/Gemini/Hermes/OpenCode workspaces and can install selected agent skills during onboarding. Headless setup with `mdtero setup --api-key --json` or `MDTERO_API_KEY` skips agent detection; run `mdtero agent install --interactive` later on the workstation where the agent lives. Do not put the API key value directly in shell history.

## Human Workflow

Use this path when you are working directly from a terminal or local workstation:

```bash
mdtero discover "thermochemical energy storage" --limit 5 --interactive
mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json
mdtero parse --file paper.pdf --trace --wait --timeout 600 --json
mdtero status <task-id> --wait --timeout 300 --json
mdtero download <task-id> paper_md --output-dir ./mdtero-output --json
mdtero translate <parse-task-id> --to zh-CN --wait --timeout 600 --json
mdtero rag query "What are the strongest findings?" --build-if-needed --json
mdtero tui
```

Use the browser extension when content depends on browser login, campus-network/session-bound access, a publisher challenge page, or current-page capture. The extension can hand the DOI, URL, PDF, EPUB, HTML, or XML artifact back to the CLI so route planning, raw upload, task polling, downloads, and structured failure fields remain visible.

## Project Workflow

Use a local Mdtero project when you are handling a paper set:

```bash
mdtero project init --name literature-review
mdtero project add 10.48550/arXiv.1706.03762 --json
mdtero project status --json
mdtero project import-bib references.bib --json
mdtero project parse --wait --timeout 300 --json
mdtero project refresh --wait --timeout 300 --json
mdtero project download --output-dir ./mdtero-output --json
```

Zotero import and sync are conservative:

```bash
mdtero config zotero
mdtero zotero import --json
mdtero zotero sync --json
```

`mdtero zotero sync` creates Mdtero result notes/tags for succeeded Zotero-origin parse tasks with known Zotero item keys; it does not rewrite Zotero bibliographic metadata.

## Agent Workflow

Use JSON and MCP surfaces when a local agent should continue work without scraping terminal tables:

```bash
mdtero setup --json
mdtero doctor --json
mdtero mcp briefing --json
mdtero mcp serve
```

Agent rules:

- Start with `mdtero doctor --json` before parse, project, RAG, or MCP work; it returns safe auth/dependency/academic/Zotero/project/RAG summaries plus safe `next_commands` without echoing secrets.
- Follow `next_commands` returned by setup, doctor, parse, status, project refresh, RAG status, and MCP tools.
- Preserve task ids, route diagnostics, quality labels, preferred artifacts, download artifacts, reason codes, action hints, translation attempts, citation contracts, citations, and source nodes.
- Treat copied task handoff JSON and `dashboard_handoff_json` as starting state, then validate it with `task_status` or `server_rag_status` before continuing.
- Do not ask users to paste long-lived secrets into prompts when a dashboard-created key or saved config can be used.
- Keep API keys, signed URLs, bearer tokens, storage tokens, and service credentials out of prompts and logs.

The preferred MCP entry point is `agent_briefing`. It returns account status, project health, ready downloads, blocked items, RAG status, extension/CLI handoff, recommended next commands, and a structured `mcp_tool_plan` playbook with `step`, `tool`, `when`, `arguments`, `success_signal`, and `failure_fields`. Use the plan to choose `project_init`, `project_add`, `submit_parse`, `task_status`, `download_artifact`, `request_translation`, `server_rag_status`, `server_rag_build`, or `rag_query`.

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
# In the interactive discovery session: enter numbers to add, `n`/`p` to page, `r <query>` to refine, `a` to add the current page, or `q` to quit.
mdtero discover "thermochemical energy storage" --limit 5 --add --select 1,3 --json
mdtero discover "<query>" --limit 5 --add --select 1,3 --json
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
mdtero rag build --wait --json
mdtero smoke --json --timeout 600 --interval 2
mdtero smoke --skip-translate --json
mdtero mcp briefing --json
mdtero mcp serve
mdtero agent detect --json
mdtero agent install --interactive
mdtero agent install --target codex
mdtero agent install --all
mdtero tui
```

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

## RAG And Evidence Contract

The primary server-side RAG path is:

```bash
mdtero rag query "What are the strongest findings?" --build-if-needed --json
```

It can create, bind, import, build, and query from one agent-safe command. Query JSON returns extractive `answer`, stable `citations`, raw `matches`, LlamaIndex-style `source_nodes`, an `evidence_pack.context_markdown`, `citation_contract.required_for_final_answer`, `reason_code`, and `next_commands` for agents. Final answers must preserve `citations` plus `source_nodes`.

Explicit recovery/debug commands remain available when the one-command path is not enough:

```bash
mdtero project ingest --json
mdtero project create-server --json
mdtero project link --server-project-id <id> --json
mdtero rag status --json
mdtero rag build --wait --json
```

## Extension-to-CLI Handoff

Extension-to-CLI handoff is the public recovery contract for publisher challenge pages, campus-network/session-bound access, and browser-saved files:

```bash
mdtero doctor --json
mdtero parse <doi-or-url> --trace --wait --timeout 300 --json
mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json
mdtero status <task-id> --wait --timeout 300 --json
mdtero download <task-id> paper_md --output-dir ./mdtero-output --json
mdtero project ingest --json
mdtero rag query "<question>" --build-if-needed --json
mdtero rag query "What are the strongest findings?" --build-if-needed --json
mdtero mcp briefing --json
mdtero mcp serve
```

This path preserves `client_acquisition`, raw upload, status polling, `reason_code`, `action_hint`, `download_artifacts`, and `next_commands` instead of hiding failures inside the browser extension.

## Current Alpha Scope

Validated in the current alpha:

- API-key login, `mdtero doctor`, `mdtero doctor --json`, and local config; JSON diagnostics include safe auth/dependency/academic/Zotero/project/RAG summaries plus `next_commands` without echoing secrets.
- Deploy smoke with `mdtero smoke --json`; it creates an isolated project, runs discovery, arXiv/DOI parse with task polling, artifact download, server-side RAG build/status/query, validates `mdtero mcp briefing --json` exposes `agent_briefing`, `server_rag_status`, `server_rag_build`, and `rag_query`, and returns step-level `reason_code`, `action_hint`, task ids, paths, server project id, plus top-level `primary_failure`, `failed_steps`, and recovery `next_commands` when a smoke step fails.
- Optional academic-key setup through either the interactive `mdtero config academic` flow or headless flags such as `--semantic-scholar-key <key> --json`; JSON output reports configured keys without echoing secrets.
- DOI/arXiv parse with task polling and Markdown/bundle download.
- Batch DOI/URL parse with `mdtero parse-batch dois.txt --wait --download paper_md --output-dir ./mdtero-output --json`, writing `manifest.csv` and `failed.csv`.
- PDF upload through the backend document parsing path, returning Markdown and zip artifacts when parsing succeeds.
- Local project init/add/remove/list/status, BibTeX import with de-duplication, project parse/refresh/download, and agent-readable JSON for project management commands.
- Zotero metadata import into a local Mdtero project, plus reverse sync of succeeded parse task notes/tags back to Zotero items imported after `0.2.0a7`.
- Discovery through local Semantic Scholar when configured, otherwise the backend OpenAlex fallback. `mdtero discover "<query>" --limit 5 --interactive` opens a paging/refinement session where users can add selected results to the local project queue. If Semantic Scholar is unavailable, `--json` reports `local_semantic_scholar_failure` and `discovery_fallback` so agents can continue with OpenAlex while preserving the reason code.
- `status`, waited parse results, and downloads expose `quality_label` / `quality_warning` for low-content artifacts such as `metadata_only`, `abstract_only`, `section_only_fulltext`, and `low_confidence_parse`; Markdown downloads default to `author_year_shorttitle.md`, append `.low_quality.md` for low-confidence full text, and update `manifest.csv`.
- Local route acquisition with `curl_cffi` for backend-planned HTML/XML/EPUB/PDF source fetches, with `httpx` fallback and visible `client_acquisition` trace output.
- Server-side translation requests from parse task ids or local Markdown files.
- Local FastMCP project context server, including the `agent_briefing` tool for one-call account status, project health, ready downloads, blocked items, RAG status, detected/installed/pending agent skills, recommended next commands, and `mcp_tool_plan`.
- TUI dashboard command palette for copyable setup, discovery, parse, Zotero, RAG, MCP, and agent-install commands, with current next commands highlighted for workstation or local-agent handoff.
- Agent-facing CLI JSON and MCP payloads sanitize signed artifact URLs, bearer/API-key headers, Mdtero API keys, and common token query parameters before returning data to local agents. They keep `reason_code`, `action_hint`, `next_commands`, and evidence fields visible.
- Agent skill installation for Codex, Claude Code, Gemini CLI, Hermes, and OpenCode.

## Shared `/api/v1` server contract

| Purpose | Route |
| --- | --- |
| Route planning | `/api/v1/route` |
| Extension route planning | `/api/v1/extension/route` |
| DOI/URL parse task | `/api/v1/tasks/parse` |
| PDF/EPUB/XML/HTML upload | `/api/v1/tasks/upload` |
| Task status | `/api/v1/tasks/{task_id}` |
| Artifact download | `/api/v1/tasks/{task_id}/download/{artifact}` |
| Discovery search | `/api/v1/discovery/search` |
| Translation task | `/api/v1/tasks/translate` |
| Server project create/list/read | `/api/v1/projects` |
| Import parsed Markdown into a server project | `/api/v1/projects/{project_id}/tasks/{task_id}/import` |
| RAG status | `/api/v1/projects/{project_id}/rag/status` |
| Build backend RAG | `/api/v1/projects/{project_id}/rag/build` |
| Query backend RAG | `/api/v1/projects/{project_id}/rag/query` |

The CLI, extension, dashboard, and MCP briefing expose this contract so browser capture, CLI retry, raw upload, task polling, download, project import, and backend RAG handoff stay aligned.

## Product Boundary

Mdtero Account is the control plane for Mdtero API keys, quota, billing, history, and install prompts. Academic source keys stay in local `mdtero config academic` configuration. The Python client owns local project state, BibTeX/Zotero import, TUI, MCP context, and agent skill installation. The backend owns parsing, discovery fallback, translation, task artifacts, and server-side RAG.

The browser extension stays a browser surface. It does not ship Python dependencies such as `curl_cffi`, `pyzotero`, or `fastmcp`; it only handles browser-context capture and user-selected file upload/download. When a publisher challenge, campus network, or logged-in browser session blocks automatic capture, hand the DOI, URL, or saved PDF/EPUB/XML/HTML file to the Python CLI.

Known boundaries:

- `mdtero zotero sync` is conservative and does not rewrite Zotero bibliographic metadata.
- `mdtero rag query --build-if-needed --json` is the primary server-side RAG path. `mdtero rag build`, `mdtero project create-server`, and `mdtero project ingest` remain available for explicit recovery/debug workflows.
- Parser engine selection is not a public product option. PDF parsing is handled by the backend, with internal fallback behavior owned by the service.

## Repo Map

- [`src/mdtero`](./src/mdtero): Python CLI/TUI/client package
- [`extension`](./extension): MV3 browser extension source, tests, and build output
- [`install`](./install): website install manifest and install guide
- [`skills`](./skills): agent skill source mirrored into the Python CLI installer
- [`README_CN.md`](./README_CN.md): Simplified Chinese README

## Local Development

```bash
uv run --with pytest --with rich --with textual --with httpx --with requests --with curl_cffi --with pyzotero --with fastmcp pytest tests_py -q
uv run --with build python -m build --wheel
npm --prefix extension test
npm --prefix extension run build
```
