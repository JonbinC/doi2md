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
- After install, run `mdtero login` to open `https://mdtero.com/auth` and hand the API key back to your terminal
- Then run `mdtero doctor` to verify that the installed environment can actually see `MDTERO_API_KEY`
- OpenClaw: `clawhub install mdtero`

OpenClaw stays on its dedicated route. Claude Code, Codex, and Gemini CLI stay on the npm-first CLI route.

Confirm that the ClawHub route is available in your OpenClaw environment before relying on it. If the workflow later needs helper-first local acquisition, local PDF / EPUB intake, or licensed full-text retrieval, install the local `mdtero` helper on the user machine separately.

`npx mdtero-install install openclaw` is intentionally unsupported.

## Scope

Use this directory for:

- one-page install summaries
- environment-specific setup entry docs
- links out to extension, helper, and skills surfaces

Desktop preview remains a deferred archive / preview surface and is not part of the active extension-and-CLI launch path.
