<div align="center">
  <img src="./extension/src/assets/icon-128.png" alt="Mdtero logo" width="120" />

  # Mdtero Public Install Surface

  *The public local-client and install surface for Mdtero's current launch path.*
</div>

Mdtero turns papers into reusable Markdown research packages.

This repository is the public home for the two active launch surfaces:

- the browser extension for local browser capture when a live paper page must stay on the user's machine
- the npm-first installer CLI for Claude Code, Codex, and Gemini CLI

Keyword discovery and API-key management stay in Mdtero Account.

## Canonical install paths

- Inspect the public contract: `npx mdtero-install show`
- Check the packaged installer version: `npx mdtero-install version`
- Install for Claude Code: `npx mdtero-install install claude_code`
- Install for Codex: `npx mdtero-install install codex`
- Install for Gemini CLI: `npx mdtero-install install gemini_cli`
- Then run browser login from the installed CLI: `mdtero login`
- Verify the environment with `mdtero doctor`
- OpenClaw keeps the dedicated route: `clawhub install mdtero`

For OpenClaw, confirm that the dedicated ClawHub route is available in your environment before relying on it. If the workflow later needs helper-first local acquisition, local PDF / EPUB intake, or licensed full-text retrieval, install the local `mdtero` helper on the user machine separately.

`npx mdtero-install install openclaw` is intentionally unsupported.

Claude Code, Codex, and Gemini CLI stay on the npm-first install path via `npx mdtero-install install <target>`.

## Extension boundary

Use the extension when you are already reading a supported paper page locally, when a local PDF / EPUB should stay on your own machine, or when you want helper-first local capture before downloading Markdown and handing translation off.

- the extension is not the backend
- the extension is not the normal path for CLI automation
- the extension is the helper-first local capture surface when the user is already in the browser or already has a local paper file

## Release truth

- The website-led install manifest at `https://mdtero.com/install/manifest.json` is the canonical public release seam.
- GitHub Releases and the public `doi2md` repository only mirror the website-led release chain.
- The current launchability proof for the active launch surfaces is `npm --prefix mdtero-frontend run test:launchability-proof`.
- Desktop preview artifacts remain a deferred archive / preview surface and are not part of the current extension-and-CLI launch path.

## Repo map

- [`extension`](./extension): extension source, tests, build output, and manifest
- [`shared`](./shared): public client contract used by the extension
- [`install`](./install): public install manifest and entry docs
- [`helper/openclaw/INSTALL.md`](./helper/openclaw/INSTALL.md): OpenClaw-specific route

## Local development

```bash
npm install
npm test
npm run build
npm run test:install
npm run test:public-contract
```
