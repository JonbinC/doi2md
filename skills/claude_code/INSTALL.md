---
name: mdtero
description: Install Mdtero into Claude Code and keep account setup in Mdtero Account
---

# Mdtero For Claude Code

Use the one-command installer:

```bash
curl -Ls https://mdtero.com/install.sh | sh -s -- --agent claude_code
```

This installs the Mdtero CLI runtime, then copies the Mdtero skill into `.claude/skills/mdtero` for the current workspace.

## After Install

1. Run `mdtero login` or `mdtero login --api-key <key>`.
2. Run `mdtero doctor` before parse, translation, status, or download work.
3. Use Mdtero Account for API keys, quota, history, diagnostics, and install prompts; use the `mdtero` CLI for discovery, parse, translation, status, and download work.

## Usage Boundary

Use Claude Code for normal agent-side parsing, translation, task status, and Markdown download workflows.

Use the browser extension only when a paper page or local file must stay on the user's machine for local capture.

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
mdtero rag query "<question>" --json
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
