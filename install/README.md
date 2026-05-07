# Install

This directory is the umbrella entry point for the current Mdtero public install surface.

Keyword discovery and API-key management stay in Mdtero Account.

## Who this page is for

This page is both a human install guide and an agent handoff contract.

- **Humans** should be able to copy the quick-start, connect their agent, run Mdtero, update, uninstall, and recover from PATH issues.
- **Agents** should be able to read the same page and act safely: install only the selected skill bundle, never claim npm owns the Python runtime, never delete user papers or Markdown, and keep OpenClaw on ClawHub.

The short version: humans run `uv tool install mdtero` and then `mdtero bootstrap --agent <target>`; agents preserve the boundary that `uv` owns the runtime and `mdtero-install` owns only skill files.

## Inspect the canonical public contract

- `npx mdtero-install show`
- `npx mdtero-install version`
- `npx mdtero-install uninstall <target>`
- canonical manifest: `https://mdtero.com/install/manifest.json`
- canonical install guide: `https://api.mdtero.com/skills/install.md`

## Recommended quick start

Install the local runtime with `uv`, then connect the current agent workspace with the Python bootstrap command:

```bash
uv tool install mdtero                  # installs the Python CLI runtime and local deps
mdtero bootstrap --agent codex          # or claude_code / gemini_cli / hermes / opencode
mdtero login                            # interactive browser handoff
mdtero doctor                           # verifies MDTERO_API_KEY is visible
```

Use `mdtero setup --agent <target>` for the same behavior under the setup verb. Use `--dry-run` to preview the skill install command without writing files:

```bash
mdtero bootstrap --agent codex --dry-run
```

## Connect an agent workspace

Choose the target that matches the agent workspace:

| Agent | Command |
|---|---|
| Claude Code | `mdtero bootstrap --agent claude_code` |
| Codex | `mdtero bootstrap --agent codex` |
| Gemini CLI | `mdtero bootstrap --agent gemini_cli` |
| Hermes Agent | `mdtero bootstrap --agent hermes` |
| OpenCode | `mdtero bootstrap --agent opencode` |
| OpenClaw | `clawhub install mdtero` |

The bootstrap command is the user-facing entry point. Internally, it keeps the Python runtime managed by `uv` and delegates only the agent skill files to npm:

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

`uv tool install mdtero` installs the Python CLI runtime in an isolated environment with local dependencies such as `curl_cffi` and `pyzotero`. For a one-command product bootstrap after the runtime exists, run `mdtero bootstrap --agent <target>` or `mdtero setup --agent <target>`; the Python runtime remains managed by `uv`, and the command only delegates agent skill files to `npx mdtero-install install <target>`. `mdtero-install show` prints the canonical public manifest. `mdtero-install version` confirms the package/manifest version. `mdtero-install install <target>` writes only the Mdtero skill bundle for the chosen agent. `mdtero-install uninstall <target>` removes only that selected agent skill bundle; it does not remove the Python runtime, API keys, generated Markdown, downloaded papers, or user project data. For an interactive terminal, run `mdtero login` after install to open `https://mdtero.com/auth` and hand the API key back to your terminal. Then run `mdtero doctor` to verify that the installed environment can actually see `MDTERO_API_KEY`.

For a headless agent, create a fresh API key in Mdtero Account and copy the prepared install prompt from the dashboard into the agent you trust. Use that prompt instead of browser login when the agent cannot open a browser or when you want one auditable setup message.

OpenClaw stays on its dedicated route. Claude Code, Codex, Gemini CLI, Hermes Agent, and OpenCode stay on the npm-first agent-skill route after the `uv` CLI runtime is installed.

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

Runtime and skill files have separate owners:

```bash
uv tool upgrade mdtero                  # update the Python runtime
uv tool uninstall mdtero                # remove the Python runtime
npx mdtero-install install codex        # update/reinstall one agent skill bundle
npx mdtero-install uninstall codex      # remove only that agent skill bundle
```

`mdtero-install uninstall <target>` does not remove the Python runtime, API keys, generated Markdown, downloaded papers, or user project data. OpenClaw stays on `clawhub install mdtero`; do not use npm or `mdtero bootstrap --agent openclaw` for OpenClaw.

## Troubleshooting

- If `mdtero` is missing, run `uv tool install mdtero`.
- If `mdtero version` prints an npm-style version such as `0.1.7`, your shell is hitting a stale npm shim. Run `which -a mdtero`, put the uv tool path first, or remove the stale shim after backing it up.
- If `mdtero bootstrap --agent <target>` says `npx` is missing, install Node/npm only for the agent skill bundle route. This does not affect the uv-managed Python runtime.
- If `mdtero doctor` cannot see `MDTERO_API_KEY`, run `mdtero login` again or paste a fresh key from Mdtero Account into the runtime environment.

## Runtime boundary

`mdtero` is a Python CLI runtime installed with `uv tool install mdtero`. That runtime package declares Python dependencies such as `curl_cffi` and `pyzotero` so users do not depend on system Python shims.

The planned Python import API is a Cloud Parse SDK. It should expose `from mdtero import Mdtero` for hosted parse tasks, task polling, and Markdown artifact download. It should not expose local parser internals as the public package contract.

`mdtero-install` is a Node installer for agent skills. It writes workflow files for the selected agent target; it does not own the Python runtime.

The Python runtime should own the canonical `mdtero` command. If `which -a mdtero` shows both a Python runtime and an npm shim, put the Python runtime first or remove/rename the stale shim after backing it up. The symptom of the wrong command is an npm-style version such as `0.1.7` or a message that `discover` is "not implemented in the npm CLI yet".

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
