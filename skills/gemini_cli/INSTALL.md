---
name: mdtero
description: Install Mdtero into Gemini CLI and keep the workflow in the local Gemini skill directory
---

# Mdtero For Gemini CLI

Use the npm-first installer:

```bash
npx mdtero-install install gemini_cli
```

This copies the Mdtero workflow into `.gemini/skills/mdtero` for the current workspace.

## After Install

1. Run `mdtero login` or `mdtero login --api-key <key>`.
2. Run `mdtero doctor` to confirm `MDTERO_API_KEY` is visible.
3. Continue with parse, translation, task status, or download work only after doctor passes.

## Usage Boundary

Gemini CLI gets the same agent-side Mdtero workflow as the other npm-first targets.

Keep browser capture, local files, and licensed full-text acquisition on the user's machine when required; use the browser extension or local helper path for those cases.

## Direct API Notes

- base URL: `https://api.mdtero.com`
- auth header: `Authorization: ApiKey ${MDTERO_API_KEY}`
- parse endpoint: `POST /tasks/parse`
- translate endpoint: `POST /tasks/translate`
- Markdown download: `/tasks/<task_id>/download/paper_md`
- translated Markdown download: `/tasks/<task_id>/download/translated_md`
