<div align="center">
  <img src="./extension/src/assets/icon-128.png" alt="Mdtero logo" width="120" />

  # Mdtero Public Install Surface

  *The public local-client and install surface for Mdtero's current launch path.*
</div>

Mdtero turns papers into reusable Markdown research packages.

This repository is the public home for the two active launch surfaces:

- the low-friction install script and fallback agent-skill installer for Claude Code, Codex, Gemini CLI, Hermes Agent, and OpenCode
- the browser extension for paper pages or local files that should stay in the user's browser session

Mdtero Account is the control plane for API keys, quota, history, diagnostics, and install prompts. The `mdtero` CLI is the unified runtime entry for discovery, parse, translate, task-status, download, and agent-skill workflows.

## Who this is for

This public install surface must work for two readers:

- **Humans** who want one clear path to install, connect an agent, use Mdtero, update, uninstall, and troubleshoot.
- **Agents** that receive a dashboard or documentation handoff and need to execute the right commands without confusing the currently published npm CLI package with future Python-package plans.

If you are human, start with the one-command installer below. If you are an agent, preserve the runtime boundary: the install script installs the currently published npm CLI package, `mdtero-install` owns agent skill files, Account remains the control plane, the `mdtero` CLI remains the runtime entry, and OpenClaw stays on ClawHub.

## Canonical install paths

Use the install script for the local npm CLI package and matching agent skill bundle:

```bash
curl -Ls https://mdtero.com/install.sh | sh -s -- --agent codex
mdtero login
mdtero doctor
```

For a reviewable install, download the script first:

```bash
curl -Ls https://mdtero.com/install.sh -o install-mdtero.sh
sh install-mdtero.sh --agent codex
```

Under the hood, the install script runs `npm install -g mdtero-install@0.1.8`, then `npx --yes mdtero-install install <target>`. The same npm installer remains available for reviewable skill-only updates:

```bash
npx mdtero-install show
npx mdtero-install version
npx mdtero-install install codex        # or claude_code / gemini_cli / hermes / opencode
npx mdtero-install uninstall codex      # removes only the selected agent skill bundle
```

Choose the install target that matches the agent workspace:

- Claude Code: `curl -Ls https://mdtero.com/install.sh | sh -s -- --agent claude_code`
- Codex: `curl -Ls https://mdtero.com/install.sh | sh -s -- --agent codex`
- Gemini CLI: `curl -Ls https://mdtero.com/install.sh | sh -s -- --agent gemini_cli`
- Hermes Agent: `curl -Ls https://mdtero.com/install.sh | sh -s -- --agent hermes`
- OpenCode: `curl -Ls https://mdtero.com/install.sh | sh -s -- --agent opencode`
- OpenClaw keeps the dedicated route: `clawhub install mdtero`

`npm install -g mdtero-install@0.1.8` installs the currently published public CLI package, including the `mdtero` command for login, doctor, parse, status, translate, and download workflows. `npx --yes mdtero-install install <target>` installs the requested agent skill bundle. `mdtero-install show` prints the active public manifest, `mdtero-install version` confirms the packaged installer version, `mdtero login` opens the Mdtero browser handoff, and `mdtero doctor` checks that `MDTERO_API_KEY` is available before an agent tries to parse, translate, inspect task status, or download artifacts.

For headless agents, create a fresh API key in Mdtero Account and copy the dashboard install prompt into the agent. Use `mdtero login` when you are sitting at an interactive terminal; use the dashboard prompt when the agent cannot open a browser.

For OpenClaw, confirm that the dedicated ClawHub route is available in your environment before relying on it. Normal parsing still runs through Mdtero's CLI/API and backend parser. If a paper has to stay local, use the extension or dashboard upload path for the user-provided PDF or file.

`npx mdtero-install install openclaw` is intentionally unsupported.

Claude Code, Codex, Gemini CLI, Hermes Agent, and OpenCode use the install script as the primary path. `npx mdtero-install install <target>` remains available for reinstalling only skill files when the CLI package is already managed elsewhere.

Hermes can load Mdtero as a `SKILL.md` workflow from `~/.hermes/skills/mdtero`. Hermes MCP configuration is a separate surface: Mdtero does not yet publish an active public MCP installer flow through `mdtero-install`.

## What each install gives you

The current public `mdtero` command is exposed by the npm package `mdtero-install@0.1.8`. It calls the hosted Mdtero API for login, doctor, parse, status, translate, and download workflows.

The next Python package direction is an importable Cloud Parse SDK. That SDK should let developers use `from mdtero import Mdtero` to create hosted parse tasks, wait for completion, and download Markdown artifacts. It should not expose the local parser engine or backend routing internals.

The npm package `mdtero-install` is the Node-based public CLI and agent-skill installer. It writes or removes target-specific skill files for Claude Code, Codex, Gemini CLI, Hermes Agent, and OpenCode, and it exposes the current `mdtero` command. Some planned commands may still report "not implemented in the npm CLI yet"; use the supported commands printed by `mdtero --help` until those surfaces ship. The browser extension is a separate browser surface and does not own CLI installation.

## Extension boundary

Use the extension only as a local executor. The backend decides the route plan; the extension follows that plan when a user must upload a PDF/local file or capture browser-context raw data. Parsing, Markdown generation, figure handling, and artifact packaging still happen in the Mdtero backend.

- the extension is not the backend
- the extension is not the normal path for CLI automation
- the extension is a JavaScript browser surface; it does not ship Python packages such as `curl_cffi`
- the extension should preserve user PDF/local file upload; routine DOI/URL parsing should use the built-in CLI/API/backend path

## Release truth

- The website-led install manifest at `https://mdtero.com/install/manifest.json` is the canonical public release seam.
- GitHub Releases and the public [`JonbinC/doi2md`](https://github.com/JonbinC/doi2md) repository only mirror the website-led release chain.
- The current launchability proof for the active launch surfaces is `npm --prefix mdtero-frontend run test:launchability-proof`.
- Desktop preview artifacts remain a deferred archive / preview surface and are not part of the current extension-and-CLI launch path.

## Repo map

- [`extension`](./extension): extension source, tests, build output, and manifest
- [`shared`](./shared): public client contract used by the extension
- [`install`](./install): public install manifest and entry docs
- [`helper/openclaw/INSTALL.md`](./helper/openclaw/INSTALL.md): OpenClaw-specific route
- [`skills`](./skills): agent-specific install notes for install-script targets

## Local development

```bash
npm install
npm run test:install
npm run test:public-contract
```
