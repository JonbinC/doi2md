---
name: mdtero
description: Install Mdtero into Codex and keep parsing on the CLI/API/backend path
---

# Mdtero For Codex

Use the normal path in this order:

1. Start from [mdtero.com/account](https://mdtero.com/account)
2. Create or select an API key
3. Paste the prepared install message into Codex
4. Run `mdtero login` or `mdtero login --api-key <key>`
5. Run `mdtero doctor` before continuing with parse, translation, status, or download work

Keep Mdtero inside Codex for normal parse, translation, and review work.

## When The Extension Still Matters

Use the browser extension only when a user needs to upload a PDF/local file from their own machine, or when a live paper page needs browser-context raw data capture.

- normal DOI/URL parsing should use the installed CLI/API and Mdtero backend parser
- user-provided PDFs, local files, and licensed browser-context capture should stay on the user's own machine when required
- the extension captures or uploads raw data; backend parsing still produces the Markdown package

## Output Rule

Treat PDF as optional input. Prefer the Markdown package first and only fall back to PDF when the workflow truly requires it.

## Direct API Notes

- base URL: `https://api.mdtero.com`
- auth header: `Authorization: ApiKey ${MDTERO_API_KEY}`
- parse endpoint: `POST /tasks/parse`
- translate endpoint: `POST /tasks/translate`
- Markdown download: `/tasks/<task_id>/download/paper_md`
- translated Markdown download: `/tasks/<task_id>/download/translated_md`

For Elsevier inputs, prefer raw DOI form such as `10.1016/j.energy.2026.140192`.
