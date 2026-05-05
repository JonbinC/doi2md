<div align="center">
  <img src="./extension/src/assets/icon-128.png" alt="Mdtero logo" width="120" />

  # Mdtero Public Install Surface

  *The public local-client and install surface for Mdtero's current launch path.*
</div>

Mdtero turns papers into reusable Markdown research packages.

This repository is the public home for the two active launch surfaces:

- the npm-first installer CLI for Claude Code, Codex, Gemini CLI, Hermes Agent, and OpenCode
- the browser extension for paper pages or local files that should stay in the user's browser session

Keyword discovery and API-key management stay in Mdtero Account.

## Canonical install paths

Use the npm-first installer when Mdtero should run inside an agent or terminal workspace:

```bash
npx mdtero-install show
npx mdtero-install version
npx mdtero-install install codex        # or claude_code / gemini_cli / hermes / opencode
mdtero login                            # browser handoff for an interactive terminal
mdtero doctor                           # confirms MDTERO_API_KEY is visible to the CLI
```

Choose the install target that matches the agent workspace:

- Claude Code: `npx mdtero-install install claude_code`
- Codex: `npx mdtero-install install codex`
- Gemini CLI: `npx mdtero-install install gemini_cli`
- Hermes Agent: `npx mdtero-install install hermes`
- OpenCode: `npx mdtero-install install opencode`
- OpenClaw keeps the dedicated route: `clawhub install mdtero`

`mdtero-install show` prints the active public manifest, `mdtero-install version` confirms the packaged installer version, `mdtero login` opens the Mdtero browser handoff, and `mdtero doctor` checks that `MDTERO_API_KEY` is available before an agent tries to parse, translate, inspect task status, or download artifacts.

For headless agents, create a fresh API key in Mdtero Account and copy the dashboard install prompt into the agent. Use `mdtero login` when you are sitting at an interactive terminal; use the dashboard prompt when the agent cannot open a browser.

For OpenClaw, confirm that the dedicated ClawHub route is available in your environment before relying on it. Normal parsing still runs through Mdtero's CLI/API and backend parser. If a paper has to stay local, use the extension or dashboard upload path for the user-provided PDF or file.

`npx mdtero-install install openclaw` is intentionally unsupported.

Claude Code, Codex, Gemini CLI, Hermes Agent, and OpenCode stay on the npm-first install path via `npx mdtero-install install <target>`.

Hermes can load Mdtero as a `SKILL.md` workflow from `~/.hermes/skills/mdtero`. Hermes MCP configuration is a separate surface: Mdtero does not yet publish an active public MCP installer flow through `mdtero-install`.

## What each install gives you

The npm CLI is a Node package. It installs the `mdtero-install` and `mdtero` commands plus the agent skill files; it does not bundle Python packages such as `curl_cffi` or `pyzotero`.

Local Python tooling is a developer/backend concern, not the normal product install. Dependencies such as `curl_cffi` and `pyzotero` belong to that local backend tooling, not to the npm CLI or browser extension.

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
- [`skills`](./skills): agent-specific install notes for npm-first skill targets

## Local development

```bash
npm install
npm test
npm run build
npm run test:install
npm run test:public-contract
```
