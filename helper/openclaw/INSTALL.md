---
name: mdtero
description: Install Mdtero into OpenClaw and keep local acquisition on the right machine
---

# Mdtero For OpenClaw

Use the normal path in this order:

1. Start from [mdtero.com/account](https://mdtero.com/account)
2. Create or select an API key
3. Paste the prepared install message into OpenClaw

OpenClaw should own the downstream workflow after setup.

## Local Acquisition Rule

If OpenClaw is running on a server, do not force campus-only or institutional acquisition through the server.

- keep Elsevier and ScienceDirect local acquisition on the user's own machine
- use the Mdtero local helper when you need scripted local acquisition:
  download `https://api.mdtero.com/helpers/install_mdtero_helper.sh`, inspect it locally, then run it
- use the browser extension when the user is already reading the paper locally in the browser
- then hand the Markdown package or bundle back to OpenClaw

## Output Rule

Treat PDF as optional input. Prefer the Markdown package first and only fall back to PDF when the workflow truly requires it.

## Direct API Notes

- base URL: `https://api.mdtero.com`
- auth header: `Authorization: ApiKey ${MDTERO_API_KEY}`
- parse endpoint: `POST /tasks/parse`
- translate endpoint: `POST /tasks/translate`
- Markdown download: `/tasks/<task_id>/download/paper_md`
- translated Markdown download: `/tasks/<task_id>/download/translated_md`

If an Elsevier parse only returns the abstract, ask whether the user is on a campus or institutional IP.
