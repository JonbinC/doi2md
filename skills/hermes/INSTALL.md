---
name: mdtero
description: Install Mdtero into Hermes Agent using its SKILL.md workflow directory
---

# Mdtero For Hermes Agent

Use the one-command installer:

```bash
curl -Ls https://mdtero.com/install.sh | sh -s -- --agent hermes
```

This installs the Mdtero CLI runtime, then copies the Mdtero skill into `.hermes/skills/mdtero` for the current workspace. Hermes can load `SKILL.md` workflows from its skills directory and expose them as slash-command style workflows.

## After Install

1. Run `mdtero login` or `mdtero login --api-key <key>`.
2. Run `mdtero doctor` before parse, translation, status, or download work.
3. Use Mdtero Account for API keys, quota, history, diagnostics, and install prompts; use the `mdtero` CLI for discovery, parse, translation, status, and download work.

## MCP Boundary

Hermes Agent supports MCP through `~/.hermes/config.yaml` and `mcp_servers`. Mdtero's maintained MCP server is exposed by the Python CLI with `mdtero mcp serve`.

Use the Mdtero skill first. Add MCP after the local project is initialized and `mdtero doctor` passes.

## Cloud CLI Workflow

```bash
mdtero parse <doi-or-url> --trace --json
mdtero status <task-id> --wait --json
mdtero download <task-id> paper_md --output-dir . --json
mdtero translate <parse-task-id> --to zh-CN --json
mdtero download <task-id> translated_md --output-dir . --json
```

For user-provided PDF/HTML/XML/EPUB files, use:

```bash
mdtero parse --file <path> --json
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
