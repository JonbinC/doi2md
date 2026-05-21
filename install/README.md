# Install

This directory is the public install contract for Mdtero.

Mdtero Account is the control plane for API keys, quota, billing, history, diagnostics, and install prompts. The runtime CLI is the Python package. Agent skill installation is also handled by the Python CLI, so npm is no longer required for the normal install path.

## Recommended Quick Start

```bash
uv tool install mdtero
mdtero setup
mdtero agent install --target codex
```

For a one-command install:

```bash
curl -Ls https://mdtero.com/install.sh | sh -s -- --agent codex
```

For a reviewable install:

```bash
curl -Ls https://mdtero.com/install.sh -o install-mdtero.sh
sh install-mdtero.sh --agent codex
```

The install script requires `uv`, installs the Python runtime, then runs `mdtero agent install --target <target>`.

## Connect An Agent Workspace

| Agent | Command |
|---|---|
| Claude Code | `mdtero agent install --target claude_code` |
| Codex | `mdtero agent install --target codex` |
| Gemini CLI | `mdtero agent install --target gemini_cli` |
| Hermes Agent | `mdtero agent install --target hermes` |
| OpenCode | `mdtero agent install --target opencode` |
| OpenClaw | `clawhub install mdtero` |

Useful variants:

```bash
mdtero agent install              # auto-detect existing agent directories
mdtero agent install --all
mdtero agent install --target codex --dry-run
mdtero agent uninstall --target codex
```

The legacy npm package `mdtero-install` remains available only as a compatibility path for older prompts. It should not be presented as the default runtime or skill installer.

## Use Mdtero After Setup

```bash
mdtero doctor
mdtero discover "thermochemical energy storage" --limit 5
mdtero parse 10.48550/arXiv.1706.03762
mdtero parse --file paper.pdf
mdtero parse --batch ./papers
mdtero project init
mdtero project import-bib references.bib
mdtero project parse --wait
mdtero project refresh
mdtero project download --output-dir ./mdtero-output
mdtero config zotero
mdtero zotero import --collection <collection-id>
mdtero status <task-id>
mdtero download <task-id> paper_md
mdtero translate paper.md --to zh-CN
mdtero rag build --project-id <server-project-id>
mdtero rag query "What are the strongest findings?" --project-id <server-project-id>
mdtero mcp serve
```

For headless agents, create a fresh API key in Mdtero Account and use:

```bash
mdtero login --api-key <key>
```

## Update Or Uninstall

```bash
uv tool upgrade mdtero
mdtero agent install --target codex
mdtero agent uninstall --target codex
uv tool uninstall mdtero
```

`mdtero agent uninstall <target>` removes only the selected skill bundle. It does not remove API keys, generated Markdown, downloaded papers, Zotero data, local project state, or backend artifacts.

## Troubleshooting

- If `mdtero` is missing, run `uv tool install mdtero`.
- If `uv` is missing, install it from `https://docs.astral.sh/uv/getting-started/installation/`.
- If `mdtero doctor` reports a missing API key, run `mdtero setup` or `mdtero login --api-key <key>`.
- If no agent workspace is detected, pass an explicit `--target`.
- If OpenClaw is needed, use `clawhub install mdtero`; `mdtero agent install --target openclaw` is intentionally unsupported.

## Boundary

The Python runtime owns setup, login, discovery, parse, task polling, download, BibTeX/Zotero import, project state, RAG commands, MCP context, TUI, and agent skill installation.

The browser extension owns browser-context capture, OAuth bridge, user-selected PDF/EPUB upload, translation requests, polling, and artifact download. It does not include Python packages or local parser engines.
