---
name: mdtero
description: Install Mdtero into Claude Code and keep account setup in Mdtero Account
---

# Mdtero For Claude Code

Use the npm-first installer:

```bash
npx mdtero-install install claude_code
```

This copies the Mdtero skill into `.claude/skills/mdtero` for the current workspace.

## After Install

1. Run `mdtero login` or `mdtero login --api-key <key>`.
2. Run `mdtero doctor` before parse, translation, status, or download work.
3. Keep keyword discovery and API-key management inside Mdtero Account.

## Usage Boundary

Use Claude Code for normal agent-side parsing, translation, task status, and Markdown download workflows.

Use the browser extension only when a paper page or local file must stay on the user's machine for local capture.

## Direct API Notes

- base URL: `https://api.mdtero.com`
- auth header: `Authorization: ApiKey ${MDTERO_API_KEY}`
- parse endpoint: `POST /tasks/parse`
- translate endpoint: `POST /tasks/translate`
- Markdown download: `/tasks/<task_id>/download/paper_md`
- translated Markdown download: `/tasks/<task_id>/download/translated_md`
