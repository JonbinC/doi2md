---
name: mdtero
description: Use when Mdtero should be available inside an agent workspace for scientific paper parsing, translation, task-status checks, Zotero/BibTeX project import, RAG, MCP, and backend-run Markdown workflows.
---

# Mdtero

## Quick Start

1. Install the Python runtime with `uv tool install mdtero`; if PyPI propagation lags during alpha testing, use `uv tool install git+https://github.com/JonbinC/doi2md.git` as the temporary fallback
2. Run `mdtero setup`
3. Use `mdtero setup --api-key --json` when the environment is headless
4. Run `mdtero doctor --json` before parse, translate, status, download, Zotero, RAG, or MCP work; use its `next_commands` before guessing recovery steps
5. To refresh this agent skill, run `mdtero agent install --target <target>` from the same Python runtime; for human setup, use `mdtero agent install --interactive`

## Setup Rules

- `MDTERO_API_KEY` or a saved Mdtero API key is required before cloud parse, translation, discovery fallback, and RAG work
- `mdtero doctor --json` is the preferred first diagnostic for agents because it reports auth, dependencies, academic key presence, Zotero config, project queue counts, server project binding, RAG readiness, and safe `next_commands` without echoing secrets
- CLI JSON and MCP payloads sanitize signed MinerU/OSS URLs, bearer/API-key headers, Mdtero API keys, and common token query parameters before returning data to agents; do not ask users to paste long-lived secrets into prompts when a dashboard-created key or saved config can be used
- normal DOI/URL parsing should use the installed `mdtero` CLI and Mdtero backend parser
- when the backend route plan includes a fetchable HTML/XML/EPUB/PDF source, the CLI may acquire it locally with `curl_cffi` and upload the raw artifact automatically; use `mdtero parse <input> --trace --wait --timeout 300 --json` to inspect `client_acquisition` and final task state
- local PDF/EPUB/XML/HTML files should be uploaded with `mdtero parse --file <path> --trace --wait --timeout 600 --json`
- keep user-provided files and licensed browser-context capture on the user's own machine when required
- use the browser extension only for browser-context capture and user-triggered upload/download flows
- if extension capture is blocked by a publisher challenge, campus-network/session-bound access, or a user-saved file workflow, continue with `mdtero parse <doi-or-url> --trace --wait --timeout 300 --json` or `mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json`; after a successful parse, continue with `mdtero rag query "What are the strongest findings?" --build-if-needed --json`, `mdtero mcp briefing --json`, and `mdtero mcp serve`; preserve `client_acquisition`, raw upload status, `reason_code`, `action_hint`, `next_commands`, and the MCP server startup contract in the handoff back to the user
- if the dashboard provides copied task handoff JSON, treat it as a starting state rather than live truth: preserve `task_id`, `selected_provider`, `parser_strategy`, `client_acquisition`, `parse_outcome`, `preferred_artifact`, `download_artifacts`, `reason_code`, `action_hint`, and `next_commands`; call `task_status(task_id)` or `mdtero status <task-id> --json` first, then continue with `download_artifact`, `request_translation`, `server_rag_status`, or `rag_query` according to the returned state

## CLI Workflow

- initialize a project: `mdtero project init`
- inspect project state for agents: `mdtero project status --json` or `mdtero project list --json`
- add or remove project entries for agents: `mdtero project add <doi-or-url> --json`, `mdtero project remove <doi-or-url-or-task-id> --json`
- import a BibTeX file: `mdtero project import-bib references.bib --json`
- import Zotero items: `mdtero config zotero`, then `mdtero zotero import --json`
- sync succeeded Zotero-origin parse task notes/tags back to Zotero: `mdtero zotero sync`
- submit a project queue: `mdtero project parse --wait --timeout 300 --json`
- refresh project tasks: `mdtero project refresh --wait --timeout 300 --json`
- download project Markdown: `mdtero project download --output-dir ./mdtero-output --json`
- bootstrap server-side Voyage RAG and query from one command: `mdtero rag query "What are the strongest findings?" --build-if-needed --json`
- use a reusable project question when automating: `mdtero rag query "<question>" --build-if-needed --json`
- explicit recovery/debug commands remain available: `mdtero rag build --wait --json`, `mdtero project ingest --json`, `mdtero project create-server --json`, or `mdtero project link --server-project-id <id> --json`
- parse a DOI/URL: `mdtero parse <doi-or-url> --trace --wait --timeout 300 --json`
- parse a local paper file: `mdtero parse --file <paper.pdf|paper.html|paper.xml|paper.epub> --trace --wait --timeout 600 --json`
- continue from an extension handoff: `mdtero parse <doi-or-url> --trace --wait --timeout 300 --json` or `mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json`
- parse a directory of files: `mdtero parse --batch ./papers --wait --timeout 300 --json`
- search discovery: `mdtero discover "<query>" --json`
- add discovery results to the local parse queue interactively: `mdtero discover "<query>" --limit 5 --interactive`
- add discovery results to the local parse queue from a script: `mdtero discover "<query>" --limit 5 --add --select 1,3 --json`
- poll status: `mdtero status <task-id> --wait --timeout 300 --json`
- download Markdown: `mdtero download <task-id> paper_md --output-dir <dir> --json`
- translate a parse task or local Markdown file: `mdtero translate <parse-task-id> --to zh-CN --wait --timeout 600 --json` or `mdtero translate <paper.md> --to zh-CN --wait --timeout 600 --json`
- query server project RAG, automatically creating/binding/importing/building when needed: `mdtero rag query "<question>" --build-if-needed --json`
- print local agent context without starting a server: `mdtero mcp briefing --json`
- serve project MCP context: `mdtero mcp serve`
- detect or install agent skills: `mdtero agent detect --json`, `mdtero agent install --interactive`, or `mdtero agent install --target <target>`
- inspect install/project/RAG readiness for agents: `mdtero doctor --json`
- `mdtero parse`, `mdtero project parse`, `mdtero status`, and `mdtero project refresh` JSON responses include `next_commands`; follow those returned commands before inventing a new continuation. For succeeded tasks, prefer the returned `preferred_artifact` and download command. For failed tasks, report `reason_code` / `action_hint` and use the returned retry or status command.

## MCP Workflow

Before starting a long agent workflow, run `mdtero mcp briefing --json` for a one-shot account/project/RAG handoff. This command is safe even before `mdtero project init`; if it returns `project_not_initialized`, follow its `next_commands` before parsing or querying RAG. If the payload includes `mcp_tool_plan`, follow that structured playbook first: each entry tells you the `tool`, `when` to use it, example `arguments`, `success_signal`, and `failure_fields` to preserve in the user handoff. When `mdtero mcp serve` is available, use these tools before guessing project state:

- `agent_briefing`: one-call account status, project health, ready downloads, blocked items, RAG status, and recommended next commands
- Agent-facing recommended commands include `--json` where supported. Prefer those exact commands over human-readable variants when automating workflows.
- `project_init(name=None)`: create the local `.mdtero/project.json` project state from MCP so an agent can start project mode without dropping back to shell commands
- `project_status`: current project name, server project id, paper statuses, and next actions
- `project_add(input_value, title=None, doi=None, source="mcp")`: add a DOI, URL, or local file target to the project queue before calling `submit_parse` or `mdtero project parse`
- `paper_context(input_or_task_id)`: one paper/task record plus recommended CLI commands
- `submit_parse(input_value, wait=False)`: submit a DOI/URL/file handoff through the same route-aware CLI path and update the local project record; use this when the agent should start work without asking the user to copy a terminal command
- `task_status(task_id, wait=False)`: poll a parse or translation task, sync the local project state, and return `preferred_artifact`, `download_artifacts`, `reason_code`, `action_hint`, and `next_commands`
- `download_artifact(task_id, artifact=None, output_dir="./mdtero-output")`: download the preferred task artifact, or an explicit `paper_md`, `paper_bundle`, or `translated_md`, and return the local path plus next commands for translation/RAG/MCP
- `request_translation(task_id_or_markdown_path, target_language="zh-CN", wait=False)`: request backend translation for a completed parse task or local Markdown file and return provider-attempt diagnostics when translation fails
- `rag_context`: whether server RAG is ready, why not, and the exact ingest/build/query commands
- `server_rag_status`: live backend RAG readiness, embedding counts, failure reason, and next commands
- `project_ingest(project_id=None)`: import succeeded parse tasks into the bound or newly created backend project before building Voyage embeddings; preserve per-task `failures` with `reason_code` and `action_hint`
- `server_rag_build(wait=true)`: build backend Voyage RAG for the bound project and wait until `status_after_build.ready_for_query` is true before querying
- `rag_query(question)`: ask server-side Voyage RAG from MCP; it can create/bind a server project, import succeeded parse tasks, build, and query before returning. When ready, use `evidence_pack.context_markdown`, `source_nodes`, and `citations` as the grounded evidence surface; treat `answer` as an extractive summary, then inspect `matches` for deeper evidence. Preserve `citation_contract.required_for_final_answer` and keep its required `citations` plus `source_nodes` in the final answer. If it is not ready, report the returned `reason_code`, `action_hint`, and `next_commands`
- `agent_commands`: canonical command map for parse, refresh, ingest, RAG, download, and MCP

Use the `mcp_tool_plan` steps to choose between `project_init`, `project_add`, `submit_parse`, `task_status`, `download_artifact`, `request_translation`, `project_ingest`, `server_rag_status`, `server_rag_build`, and `rag_query`. When the plan says `ingest_project_documents`, call `project_ingest(project_id=None)` first; when it says `build_rag_index`, call `server_rag_build(wait=true)` before `rag_query(question)`. On failures, report the step's `failure_fields` such as `reason_code`, `action_hint`, `next_commands`, `translation_attempts`, `client_acquisition`, `failures`, or `readiness` before retrying.

If `agent_briefing` includes `dashboard_handoff_json`, use its `expected_fields`, `validation_step`, and `tool_sequence` as the contract for dashboard-to-agent continuation. The copied JSON should already redact signed URLs, bearer/API keys, OSS tokens, and Mdtero secrets; do not request unredacted credentials in chat.

If `agent_briefing` or the dashboard API key dialog provides `dashboard_setup_handoff_json`, treat it as the setup contract for a newly created one-time key. Preserve `auth_boundary`, `first_cli_command`, `next_commands`, `mcp`, `rag`, and `redaction_policy`; verify `api_key.full_secret_included` is false. Ask the user to paste the one-time secret only into the secure `mdtero setup --api-key --json` prompt, then rerun `mdtero doctor --json` and `mdtero mcp briefing --json`. Do not paste the secret into shell commands, MCP output, logs, or this chat.

Prefer MCP tools for multi-step agent work when `mdtero mcp serve` is already running. Prefer CLI commands when the user is reading along in a terminal, when a file path must be selected manually, or when browser-extension handoff copy should remain visible to the user.

The CLI talks to `https://api.mdtero.com` by default. Use `MDTERO_API_URL` only for staging or local verification.

## Output Rule

- prefer Markdown first
- treat PDF as input, not as the normal output
- use fallback bundles only when the workflow truly needs image or asset files
- keep task ids, `reason_code`, `action_hint`, `preferred_artifact`, RAG `answer` / `citations` / `source_nodes` / `evidence_pack` / `citation_contract`, `next_commands`, and download artifact names visible in handoffs

## Verification Rule

- do not treat installation as complete until `mdtero doctor --json` reports `authenticated: true` and an API key source
- if `mdtero` is missing, install the Python runtime with `uv tool install mdtero`; during alpha, fall back to `uv tool install git+https://github.com/JonbinC/doi2md.git` only if the PyPI package is unavailable
- if a task fails, report `reason_code` and the server action hint before retrying
