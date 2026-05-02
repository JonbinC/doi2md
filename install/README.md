# Install

This directory is the umbrella entry point for the current Mdtero public install surface.

Keyword discovery and API-key management stay in Mdtero Account.

## Inspect the canonical public contract

- `npx mdtero-install show`
- `npx mdtero-install version`
- canonical manifest: `https://mdtero.com/install/manifest.json`
- canonical install guide: `https://api.mdtero.com/skills/install.md`

## Install routes

- Claude Code: `npx mdtero-install install claude_code`
- Codex: `npx mdtero-install install codex`
- Gemini CLI: `npx mdtero-install install gemini_cli`
- Hermes Agent: `npx mdtero-install install hermes`
- OpenCode: `npx mdtero-install install opencode`
- After install, run `mdtero login` to open `https://mdtero.com/auth` and hand the API key back to your terminal
- Then run `mdtero doctor` to verify that the installed environment can actually see `MDTERO_API_KEY`
- OpenClaw: `clawhub install mdtero`

OpenClaw stays on its dedicated route. Claude Code, Codex, Gemini CLI, Hermes Agent, and OpenCode stay on the npm-first CLI route.

Confirm that the ClawHub route is available in your OpenClaw environment before relying on it. Normal parsing still runs through Mdtero's CLI/API and backend parser. If a paper has to stay local, use the extension or dashboard upload path for the user-provided PDF or file.

`npx mdtero-install install openclaw` is intentionally unsupported.

## Runtime boundary

`mdtero-install` is a Node installer. It writes agent skills and exposes the `mdtero` CLI, but it does not bundle Python dependencies.

The browser extension is also not a Python runtime. It can upload a user-provided PDF/local file or hand browser-context raw data to Mdtero, but it does not include `curl_cffi`, `pyzotero`, or other Python packages. Parsing still happens in the backend.

Local Python tooling is for developer/backend workflows, not the normal public install. That is where local-only Python dependencies such as `curl_cffi` and `pyzotero` belong.

## MCP boundary

Hermes Agent supports MCP through its own `~/.hermes/config.yaml` `mcp_servers` configuration, but Mdtero does not currently expose a maintained public MCP installer flow through `mdtero-install`.

Use the Mdtero skill install first. Add MCP only when a maintained Mdtero MCP server is published and documented as an active public surface.

## Scope

Use this directory for:

- one-page install summaries
- environment-specific setup entry docs
- links out to extension, helper, and skills surfaces

Desktop preview remains a deferred archive / preview surface and is not part of the active extension-and-CLI launch path.
