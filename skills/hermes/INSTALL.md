---
name: mdtero
description: Install Mdtero into Hermes Agent using its SKILL.md workflow directory
---

# Mdtero For Hermes Agent

Use the npm-first installer:

```bash
npx mdtero-install install hermes
```

This copies the Mdtero skill into `.hermes/skills/mdtero` for the current workspace. Hermes can load `SKILL.md` workflows from its skills directory and expose them as slash-command style workflows.

## After Install

1. Run `mdtero login` or `mdtero login --api-key <key>`.
2. Run `mdtero doctor` before parse, translation, status, or download work.
3. Keep API-key management and keyword discovery in Mdtero Account.

## MCP Boundary

Hermes Agent supports MCP through `~/.hermes/config.yaml` and `mcp_servers`, but Mdtero does not currently publish an active public MCP installer flow through `mdtero-install`.

Use the Mdtero skill first. Add MCP only after a maintained Mdtero MCP server is published and documented as an active public surface.

## Direct API Notes

- base URL: `https://api.mdtero.com`
- auth header: `Authorization: ApiKey ${MDTERO_API_KEY}`
- parse endpoint: `POST /tasks/parse`
- translate endpoint: `POST /tasks/translate`
- Markdown download: `/tasks/<task_id>/download/paper_md`
- translated Markdown download: `/tasks/<task_id>/download/translated_md`
