# Install

This directory is the umbrella entry point for the current Mdtero public install surface.

Keyword discovery and API-key management stay in Mdtero Account.

## Who this page is for

This page is both a human install guide and an agent handoff contract.

- **Humans** should be able to copy the quick-start, connect their agent, run Mdtero, update, uninstall, and recover from PATH issues.
- **Agents** should be able to read the same page and act safely: install only the selected public CLI package and skill bundle, never claim the unpublished uv/PyPI route is currently available, never delete user papers or Markdown, and keep OpenClaw on ClawHub.

The short version: humans run one install script for their agent; the script installs the currently published `mdtero-install@0.1.8` npm CLI package and then installs the matching skill bundle. Agents preserve the boundary that npm owns the current public CLI package while the uv/PyPI route is not available.

## Inspect the canonical public contract

- `npx mdtero-install show`
- `npx mdtero-install version`
- `npx mdtero-install uninstall <target>`
- one-command installer: `https://mdtero.com/install.sh`
- canonical manifest: `https://mdtero.com/install/manifest.json`
- canonical install guide: `https://api.mdtero.com/skills/install.md`

## Recommended quick start

Install Mdtero and connect the current agent workspace with one command:

```bash
curl -Ls https://mdtero.com/install.sh | sh -s -- --agent codex
```

For a reviewable install, download the script first:

```bash
curl -Ls https://mdtero.com/install.sh -o install-mdtero.sh
sh install-mdtero.sh --agent codex
```

After install, sign in and verify the runtime:

```bash
mdtero login
mdtero doctor
```

## Connect an agent workspace

Choose the target that matches the agent workspace:

| Agent | Command |
|---|---|
| Claude Code | `curl -Ls https://mdtero.com/install.sh \| sh -s -- --agent claude_code` |
| Codex | `curl -Ls https://mdtero.com/install.sh \| sh -s -- --agent codex` |
| Gemini CLI | `curl -Ls https://mdtero.com/install.sh \| sh -s -- --agent gemini_cli` |
| Hermes Agent | `curl -Ls https://mdtero.com/install.sh \| sh -s -- --agent hermes` |
| OpenCode | `curl -Ls https://mdtero.com/install.sh \| sh -s -- --agent opencode` |
| OpenClaw | `clawhub install mdtero` |

The install script is the user-facing entry point. Internally, it installs the current public CLI package with `npm install -g mdtero-install@0.1.8`, then runs `npx --yes mdtero-install install <target>`. The npm installer remains available as an advanced skill-only path:

```bash
npx mdtero-install show
npx mdtero-install version
npx mdtero-install install claude_code
npx mdtero-install install codex        # or claude_code / gemini_cli / hermes / opencode
npx mdtero-install install gemini_cli
npx mdtero-install install hermes
npx mdtero-install install opencode
npx mdtero-install uninstall codex      # removes only the selected agent skill bundle
```

`npm install -g mdtero-install@0.1.8` installs the currently published public CLI package, including the `mdtero` command. `npx --yes mdtero-install install <target>` installs the chosen agent skill bundle. `mdtero-install show` prints the canonical public manifest. `mdtero-install version` confirms the package/manifest version. `mdtero-install install <target>` writes only the Mdtero skill bundle for the chosen agent. `mdtero-install uninstall <target>` removes only that selected agent skill bundle; it does not remove API keys, generated Markdown, downloaded papers, or user project data. For an interactive terminal, run `mdtero login` after install to open `https://mdtero.com/auth` and hand the API key back to your terminal. Then run `mdtero doctor` to verify that the installed environment can actually see `MDTERO_API_KEY`.

For a headless agent, create a fresh API key in Mdtero Account and copy the prepared install prompt from the dashboard into the agent you trust. Use that prompt instead of browser login when the agent cannot open a browser or when you want one auditable setup message.

OpenClaw stays on its dedicated route. Claude Code, Codex, Gemini CLI, Hermes Agent, and OpenCode use the install script as the primary route; `npx mdtero-install install <target>` remains the reviewable skill-bundle route.

Confirm that the ClawHub route is available in your OpenClaw environment before relying on it. Normal parsing still runs through Mdtero's CLI/API and backend parser. If a paper has to stay local, use the extension or dashboard upload path for the user-provided PDF or file.

For headless OpenClaw, use the dashboard install prompt so the agent receives the ClawHub route, API key, and Account boundary in one message.

`npx mdtero-install install openclaw` is intentionally unsupported.

## Use Mdtero after setup

After `mdtero doctor` confirms the API key is visible, use the runtime CLI for normal work:

```bash
mdtero discover "thermochemical energy storage" --limit 5
mdtero parse 10.48550/arXiv.1706.03762
mdtero status <task-id>
mdtero download <task-id> paper_md --output paper.md
```

For local-user-only content, use direct files or Zotero attachments rather than browser automation:

```bash
mdtero parse-files paper.pdf
mdtero zotero import --library-id <id> --library-type user --api-key <zotero-key> --json
```

## Update or uninstall

CLI package and skill files have separate update commands:

```bash
npm install -g mdtero-install@0.1.8     # install/update the current public CLI package
npm uninstall -g mdtero-install         # remove the current public CLI package
npx mdtero-install install codex        # update/reinstall one agent skill bundle
npx mdtero-install uninstall codex      # remove only that agent skill bundle
```

`mdtero-install uninstall <target>` does not remove the CLI package, API keys, generated Markdown, downloaded papers, or user project data. OpenClaw stays on `clawhub install mdtero`; do not use `mdtero bootstrap --agent openclaw` for OpenClaw.

## Troubleshooting

- If `mdtero` is missing, rerun `curl -Ls https://mdtero.com/install.sh | sh -s -- --agent <target>` or install the CLI package directly with `npm install -g mdtero-install@0.1.8`.
- If `mdtero version` prints `0.1.8`, your shell is using the expected current npm CLI package.
- If `npx mdtero-install install <target>` says `npx` is missing, install Node/npm and rerun the installer.
- If `mdtero doctor` cannot see `MDTERO_API_KEY`, run `mdtero login` again or paste a fresh key from Mdtero Account into the runtime environment.

## Runtime boundary

`mdtero` is currently exposed by the npm package `mdtero-install@0.1.8`. The public npm package supports login, doctor, parse, status, translate, and download workflows through the hosted Mdtero API.

The planned Python import API is a Cloud Parse SDK. It should expose `from mdtero import Mdtero` for hosted parse tasks, task polling, and Markdown artifact download. It should not expose local parser internals as the public package contract.

`mdtero-install` is a Node installer for the public CLI and agent skills. It writes workflow files for the selected agent target and exposes the current `mdtero` command.

The future Python package direction should not be advertised as the current install path until it is published. Today, an npm-style version such as `0.1.8` is expected; a message that `discover` is "not implemented in the npm CLI yet" means that specific command has not shipped in the npm CLI, not that the installation failed.

The browser extension is also not a Python runtime. It can upload a user-provided PDF/local file or hand browser-context raw data to Mdtero, but it does not include `curl_cffi`, `pyzotero`, or other Python packages. Parsing still happens in the backend.

The public GitHub repository for the CLI/install surface is [`JonbinC/doi2md`](https://github.com/JonbinC/doi2md). GitHub Releases mirror website-led release artifacts; they are not the release source of truth.

## MCP boundary

Hermes Agent supports MCP through its own `~/.hermes/config.yaml` `mcp_servers` configuration, but Mdtero does not currently expose a maintained public MCP installer flow through `mdtero-install`.

Use the Mdtero skill install first. Add MCP only when a maintained Mdtero MCP server is published and documented as an active public surface.

## Scope

Use this directory for:

- one-page install summaries
- environment-specific setup entry docs
- links out to extension, helper, and skills surfaces

Desktop preview remains a deferred archive / preview surface and is not part of the active extension-and-CLI launch path.
