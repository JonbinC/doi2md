---
name: mdtero
description: Install Mdtero into Codex and keep the extension as the local capture fallback
---

# Mdtero For Codex

Use the normal path in this order:

1. Start from [mdtero.com/account](https://mdtero.com/account)
2. Create or select an API key
3. Paste the prepared install message into Codex

Keep Mdtero inside Codex for normal parse, translation, and review work.

## When The Extension Still Matters

Use the browser extension only when a live paper page needs local capture on the user machine.

- Elsevier and ScienceDirect local acquisition should stay on the user's own machine
- the local helper is preferred for scripted local acquisition:
  download `https://api.mdtero.com/helpers/install_mdtero_helper.sh`, inspect it locally, then run it
- the browser extension is the fallback local capture path when the user is already in the browser

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
