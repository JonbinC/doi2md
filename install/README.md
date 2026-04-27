# Install

This directory is the umbrella entry point for the current Mdtero public install surface.

Keyword discovery and API-key management stay in Mdtero Account.

## Inspect the canonical public contract

- `npx mdtero-install show`
- `npx mdtero-install version`
- canonical manifest: `https://mdtero.com/install/manifest.json`
- canonical install guide: `https://api.mdtero.com/skills/install.md`

## Active install routes

- Claude Code: `npx mdtero-install install claude_code`
- Codex: `npx mdtero-install install codex`
- Gemini CLI: `npx mdtero-install install gemini_cli`
- OpenClaw: `clawhub install mdtero`

OpenClaw stays on its dedicated route. Claude Code, Codex, and Gemini CLI stay on the npm-first CLI route.

`npx mdtero-install install openclaw` is intentionally unsupported.

## Scope

Use this directory for:

- one-page install summaries
- environment-specific setup entry docs
- links out to extension, helper, and skills surfaces

Desktop preview remains a deferred archive / preview surface and is not part of the active extension-and-CLI launch path.
