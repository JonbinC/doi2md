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

For Elsevier inputs, prefer raw DOI form such as `10.1016/j.energy.2026.140192`.
