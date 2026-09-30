# MCP workflow

Before a long agent workflow, run `mdtero mcp briefing --json` for a one-shot account/project/RAG handoff. Safe even before `mdtero project init`; if it returns `project_not_initialized`, follow its `next_commands`. If the payload includes `mcp_tool_plan`, follow that playbook first.

Start the server with `mdtero mcp serve` (usually after `mdtero project init`).

## Tools

- `agent_briefing`: account status, project health, downloads, blocked items, RAG status, recommended next commands
- `project_init(name=None)`: create local `.mdtero/project.json`
- `project_status`: project name, server project id, paper statuses, next actions
- `project_add(input_value, title=None, doi=None, source="mcp")`: queue a DOI/URL/file
- `paper_context(input_or_task_id)`: one paper/task record plus CLI commands
- `submit_parse(input_value, wait=False)`: route-aware parse handoff that updates the local project
- `task_status(task_id, wait=False)`: poll parse/translation; returns `preferred_artifact`, `download_artifacts`, `reason_code`, `action_hint`, `next_commands`
- `download_artifact(task_id, artifact=None, output_dir="./mdtero-output")`: download preferred or explicit `paper_md` / `paper_bundle` / `translated_md`
- `request_translation(task_id_or_markdown_path, target_language="zh-CN", wait=False)`: backend translation with provider-attempt diagnostics on failure
- `rag_context` / `server_rag_status`: readiness, embedding counts, failure reason, next commands
- `project_ingest(project_id=None)`: import succeeded parse tasks; preserve per-task `failures` with `reason_code` / `action_hint`
- `server_rag_build(wait=true)`: build until `status_after_build.ready_for_query`
- `rag_query(question)`: create/bind/import/build/query as needed. When ready, use `evidence_pack.context_markdown`, `source_nodes`, and `citations` as the grounded evidence surface; treat `answer` as an extractive summary; preserve `citation_contract.required_for_final_answer`
- `agent_commands`: canonical command map
- `paper_summary` / `discover`: inspect local Markdown packages and search literature

Use the `mcp_tool_plan` steps to choose between `project_init`, `project_add`, `submit_parse`, `task_status`, `download_artifact`, `request_translation`, `project_ingest`, `server_rag_status`, `server_rag_build`, and `rag_query`. When the plan says `ingest_project_documents`, call `project_ingest` first; when it says `build_rag_index`, call `server_rag_build(wait=true)` before `rag_query`. On failures, report the step's `failure_fields` such as `reason_code`, `action_hint`, `next_commands`, `translation_attempts`, `client_acquisition`, `failures`, or `readiness` before retrying.

## Dashboard handoff

- If `agent_briefing` includes `dashboard_handoff_json`, use its `expected_fields`, `validation_step`, and `tool_sequence`. Copied JSON should already redact secrets; do not request unredacted credentials in chat.
- If `dashboard_setup_handoff_json` is present, preserve `auth_boundary`, `first_cli_command`, `next_commands`, `mcp`, `rag`, and `redaction_policy`; verify `api_key.full_secret_included` is false. Ask the user to paste the one-time secret only into `mdtero setup --api-key --json`, then rerun doctor + briefing.

Prefer MCP tools for multi-step agent work when `mdtero mcp serve` is already running. Prefer CLI commands when the user is reading along in a terminal, when a file path must be selected manually, or when browser-extension handoff copy should remain visible to the user.

Default API base is `https://api.mdtero.com`. Use `MDTERO_API_URL` only for staging/local verification.

## Example MCP configs

Cursor / Claude-compatible:

```json
{
  "mcpServers": {
    "mdtero": {
      "command": "mdtero",
      "args": ["mcp", "serve"],
      "cwd": "<local-mdtero-project-root>"
    }
  }
}
```

Trae project file: `.trae/mcp.json` (same shape). WorkBuddy user file: `~/.workbuddy/mcp.json` (same shape).
