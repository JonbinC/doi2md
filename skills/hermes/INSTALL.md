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

Hermes Agent supports MCP through `~/.hermes/config.yaml` and `mcp_servers`, but Mdtero does not currently publish an active public MCP installer flow through `mdtero-install`.

Use the Mdtero skill first. Add MCP only after a maintained Mdtero MCP server is published and documented as an active public surface.

## Cloud CLI Workflow

```bash
mdtero parse <doi-or-url>
mdtero status <task-id>
mdtero download <task-id> paper_md --output-dir .
mdtero translate <parse-task-id> zh
mdtero download <task-id> translated_md --output-dir .
```

For user-provided PDF/HTML/XML/EPUB files, use:

```bash
mdtero parse --file <path> [--source-input DOI_OR_URL] [--source-doi DOI]
```

## Direct API Notes

- base URL: `https://api.mdtero.com`
- auth header: `Authorization: ApiKey ${MDTERO_API_KEY}`
- parse endpoint: `POST /tasks/parse`
- upload endpoint: `POST /tasks/parse-upload-v2`
- status endpoint: `GET /tasks/<task_id>`
- translate endpoint: `POST /tasks/translate`
- Markdown download: `/tasks/<task_id>/download/paper_md`
- translated Markdown download: `/tasks/<task_id>/download/translated_md`
