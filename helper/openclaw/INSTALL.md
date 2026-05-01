---
name: mdtero
description: Install Mdtero into OpenClaw while keeping OpenClaw on its dedicated public route
---

# Mdtero For OpenClaw

Use the normal path in this order:

1. Start from [mdtero.com/account](https://mdtero.com/account)
2. Create or select an API key
3. Paste the prepared install message into OpenClaw

The website-led install manifest at `https://mdtero.com/install/manifest.json` is the canonical public release seam.

OpenClaw stays on the dedicated `clawhub install mdtero` path and is not part of the npm-first CLI release truth used by Claude Code, Codex, Gemini CLI, and Hermes Agent.

Confirm that the ClawHub route is available in your OpenClaw environment before relying on it. If the workflow later needs helper-first local acquisition, local PDF / EPUB intake, or licensed full-text retrieval, install the local `mdtero` helper on the user machine separately.

GitHub Releases and the public `doi2md` repository only mirror the website-led release chain.

Helpful public checks:

- `npx mdtero-install version`
- `npx mdtero-install show`
- `npm --prefix mdtero-frontend run test:launchability-proof`

Do not use `npx mdtero-install install openclaw`; OpenClaw stays on `clawhub install mdtero`.

## Other agent targets

The npm-first installer supports Claude Code, Codex, Gemini CLI, and Hermes Agent. OpenClaw should still use ClawHub even though the public manifest lists all five supported environments.

Hermes Agent supports MCP through its own `~/.hermes/config.yaml` `mcp_servers` configuration, but Mdtero does not currently publish an active MCP installer flow through `mdtero-install`. Do not present MCP as part of the OpenClaw/ClawHub install until a maintained Mdtero MCP server is published and documented.

## Local acquisition rule

If OpenClaw is running on a server, do not force campus-only or institutional acquisition through the server.

- keep Elsevier and ScienceDirect local acquisition on the user's own machine
- use the Mdtero local helper when you need scripted local acquisition
- use the browser extension when the user is already reading the paper locally in the browser
- then hand the Markdown package back to OpenClaw

## Output rule

Treat PDF as optional input. Prefer the Markdown package first and only fall back to PDF when the workflow truly requires it.
