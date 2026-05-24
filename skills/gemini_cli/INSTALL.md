---
name: mdtero
description: Install Mdtero into Gemini CLI and keep the workflow in the local Gemini skill directory
---

# Mdtero For Gemini CLI

Use the one-command installer:

```bash
curl -Ls https://mdtero.com/install.sh | sh -s -- --agent gemini_cli
```

This installs the Mdtero CLI runtime, then copies the Mdtero workflow into `.gemini/skills/mdtero` for the current workspace.

## After Install

1. Run `mdtero setup` or `mdtero setup --api-key <key>`.
2. Run `mdtero doctor` to confirm `MDTERO_API_KEY` is visible.
3. Continue with parse, translation, task status, or download work only after doctor passes.

## Usage Boundary

Gemini CLI gets the same agent-side Mdtero workflow as the other install-script targets.

Keep user-provided PDFs, local files, and licensed browser-context capture on the user's machine when required. Use the browser extension for those upload/capture cases; use the CLI/API/backend parser for normal DOI/URL parsing and Markdown generation.

## Cloud CLI Workflow

```bash
mdtero parse <doi-or-url> --trace --wait --timeout 300 --json
mdtero status <task-id> --wait --timeout 300 --json
mdtero download <task-id> paper_md --output-dir . --json
mdtero translate <parse-task-id> --to zh-CN --json
mdtero download <task-id> translated_md --output-dir . --json
```

For user-provided PDF/HTML/XML/EPUB files, use:

```bash
mdtero parse --file <path> --wait --timeout 300 --json
```

For project RAG and local agent context, use:

```bash
mdtero rag build --json
mdtero rag status --json
mdtero rag query "<question>" --build-if-needed --json
mdtero mcp briefing --json
mdtero mcp serve
```

## Direct API Notes

- base URL: `https://api.mdtero.com`
- auth header: `Authorization: ApiKey ${MDTERO_API_KEY}`
- route endpoint: `POST /api/v1/route`
- parse endpoint: `POST /api/v1/tasks/parse`
- upload endpoint: `POST /api/v1/tasks/upload`
- status endpoint: `GET /api/v1/tasks/<task_id>`
- translate endpoint: `POST /api/v1/tasks/translate`
- Markdown download: `/api/v1/tasks/<task_id>/download/paper_md`
- translated Markdown download: `/api/v1/tasks/<task_id>/download/translated_md`
