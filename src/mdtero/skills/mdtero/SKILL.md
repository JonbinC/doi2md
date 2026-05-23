---
name: mdtero
description: Use when Mdtero should be available inside an agent workspace for scientific paper parsing, translation, task-status checks, Zotero/BibTeX project import, RAG, MCP, and backend-run Markdown workflows.
---

# Mdtero

## Quick Start

1. During alpha, install the Python runtime with `uv tool install git+https://github.com/JonbinC/doi2md.git`
2. Run `mdtero setup`
3. Use `mdtero login --api-key <key>` when the environment is headless
4. Run `mdtero doctor --json` before parse, translate, status, download, Zotero, RAG, or MCP work; use its `next_commands` before guessing recovery steps
5. To refresh this agent skill, run `mdtero agent install --target <target>` from the same Python runtime; for human setup, use `mdtero agent install --interactive`

## Setup Rules

- `MDTERO_API_KEY` or a saved Mdtero API key is required before cloud parse, translation, discovery fallback, and RAG work
- `mdtero doctor --json` is the preferred first diagnostic for agents because it reports auth, dependencies, academic key presence, Zotero config, project queue counts, server project binding, RAG readiness, and safe `next_commands` without echoing secrets
- normal DOI/URL parsing should use the installed `mdtero` CLI and Mdtero backend parser
- when the backend route plan includes a fetchable HTML/XML/EPUB/PDF source, the CLI may acquire it locally with `curl_cffi` and upload the raw artifact automatically; use `mdtero parse <input> --trace --wait --json` to inspect `client_acquisition` and final task state
- local PDF/EPUB/XML/HTML files should be uploaded with `mdtero parse --file <path> --json`
- keep user-provided files and licensed browser-context capture on the user's own machine when required
- use the browser extension only for browser-context capture and user-triggered upload/download flows

## CLI Workflow

- initialize a project: `mdtero project init`
- inspect project state for agents: `mdtero project status --json` or `mdtero project list --json`
- add or remove project entries for agents: `mdtero project add <doi-or-url> --json`, `mdtero project remove <doi-or-url-or-task-id> --json`
- import a BibTeX file: `mdtero project import-bib references.bib --json`
- import Zotero items: `mdtero config zotero`, then `mdtero zotero import --json`
- sync succeeded Zotero-origin parse task notes/tags back to Zotero: `mdtero zotero sync`
- submit a project queue: `mdtero project parse --wait --json`
- refresh project tasks: `mdtero project refresh --wait --json`
- download project Markdown: `mdtero project download --output-dir ./mdtero-output --json`
- bootstrap server-side Voyage RAG for the current project: `mdtero rag build --json`
- optionally create or bind a server project explicitly: `mdtero project create-server --json` or `mdtero project link --server-project-id <id> --json`
- optionally re-import succeeded parse tasks into the bound server project: `mdtero project ingest --json`
- parse a DOI/URL: `mdtero parse <doi-or-url> --trace --wait --json`
- parse a local paper file: `mdtero parse --file <paper.pdf|paper.html|paper.xml|paper.epub> --json`
- parse a directory of files: `mdtero parse --batch ./papers --json`
- search discovery: `mdtero discover "<query>" --json`
- add discovery results to the local parse queue interactively: `mdtero discover "<query>" --limit 5 --interactive`
- add discovery results to the local parse queue from a script: `mdtero discover "<query>" --limit 5 --add --select 1,3`
- poll status: `mdtero status <task-id> --wait --json`
- download Markdown: `mdtero download <task-id> paper_md --output-dir <dir> --json`
- translate a parse task or local Markdown file: `mdtero translate <parse-task-id> --to zh-CN --json` or `mdtero translate <paper.md> --to zh-CN --json`
- build server project RAG, automatically creating/binding/importing when needed: `mdtero rag build --json`
- query server project RAG after build: `mdtero rag query "<question>" --json`
- serve project MCP context: `mdtero mcp serve`
- detect or install agent skills: `mdtero agent detect --json`, `mdtero agent install --interactive`, or `mdtero agent install --target <target>`
- inspect install/project/RAG readiness for agents: `mdtero doctor --json`
- `mdtero parse`, `mdtero project parse`, `mdtero status`, and `mdtero project refresh` JSON responses include `next_commands`; follow those returned commands before inventing a new continuation. For succeeded tasks, prefer the returned `preferred_artifact` and download command. For failed tasks, report `reason_code` / `action_hint` and use the returned retry or status command.

## MCP Workflow

When `mdtero mcp serve` is available, use these tools before guessing project state:

- `agent_briefing`: one-call account status, project health, ready downloads, blocked items, RAG status, and recommended next commands
- Agent-facing recommended commands include `--json` where supported. Prefer those exact commands over human-readable variants when automating workflows.
- `project_status`: current project name, server project id, paper statuses, and next actions
- `paper_context(input_or_task_id)`: one paper/task record plus recommended CLI commands
- `rag_context`: whether server RAG is ready, why not, and the exact ingest/build/query commands
- `server_rag_status`: live backend RAG readiness, embedding counts, failure reason, and next commands
- `rag_query(question)`: directly ask the bound server-side Voyage RAG index; when ready, use the returned `answer` and `citations` first, then inspect `matches` for deeper evidence. If it is not ready, report the returned `reason_code`, `action_hint`, and `next_commands`
- `agent_commands`: canonical command map for parse, refresh, ingest, RAG, download, and MCP

The CLI talks to `https://api.mdtero.com` by default. Use `MDTERO_API_URL` only for staging or local verification.

## Output Rule

- prefer Markdown first
- treat PDF as input, not as the normal output
- use fallback bundles only when the workflow truly needs image or asset files
- keep task ids, `reason_code`, `action_hint`, `preferred_artifact`, RAG `answer` / `citations`, `next_commands`, and download artifact names visible in handoffs

## Verification Rule

- do not treat installation as complete until `mdtero doctor --json` reports `authenticated: true` and an API key source
- if `mdtero` is missing during alpha, install the Python runtime with `uv tool install git+https://github.com/JonbinC/doi2md.git`
- if a task fails, report `reason_code` and the server action hint before retrying
