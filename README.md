<div align="center">
  <img src="./extension/src/assets/icon-128.png" alt="Mdtero logo" width="120" />

  # Mdtero Public Install Surface

  *Python/uv CLI, TUI, browser extension, and agent skill bundle for paper-to-Markdown workflows.*
</div>

Mdtero turns papers into reusable Markdown research packages.

This repository is the public home for the active launch surfaces:

- Python runtime CLI/TUI package `mdtero`, installed with `uv tool install mdtero`
- browser extension for OAuth login, DOI/current-page parse, PDF/EPUB upload, translation, polling, and download
- packaged agent skill bundle installed by the Python CLI with `mdtero agent install`

The old npm package `mdtero-install` is now only a legacy compatibility installer. It is not the runtime and is no longer required for skill installation.

## Quick Start

```bash
uv tool install mdtero
mdtero setup
mdtero agent install --target codex
```

For a one-command agent setup:

```bash
curl -Ls https://mdtero.com/install.sh | sh -s -- --agent codex
```

The script requires `uv`, installs the Python runtime, then runs `mdtero agent install --target <target>`.

## Agent Targets

```bash
mdtero agent install --target claude_code
mdtero agent install --target codex
mdtero agent install --target gemini_cli
mdtero agent install --target hermes
mdtero agent install --target opencode
mdtero agent install --all
mdtero agent uninstall --target codex
```

If `--target` is omitted, Mdtero detects existing `~/.codex`, `~/.claude`, `~/.gemini`, `~/.hermes`, and `~/.opencode` directories and installs into the detected workspaces.

OpenClaw keeps the dedicated route:

```bash
clawhub install mdtero
```

## Runtime Commands

```bash
mdtero doctor
mdtero login --api-key <key>
mdtero config academic
mdtero project init
mdtero project import-bib references.bib
mdtero project parse --wait
mdtero project refresh
mdtero project download --output-dir ./mdtero-output
mdtero config zotero
mdtero zotero import
mdtero discover "thermochemical energy storage" --limit 5
mdtero parse 10.48550/arXiv.1706.03762
mdtero parse --file paper.pdf
mdtero parse --batch ./papers
mdtero status <task-id>
mdtero download <task-id> paper_md
mdtero translate paper.md --to zh-CN
mdtero rag build --project-id <server-project-id>
mdtero rag query "What are the strongest findings?" --project-id <server-project-id>
mdtero mcp serve
mdtero tui
```

## Product Boundary

Mdtero Account is the control plane for API keys, quota, billing, history, diagnostics, and install prompts. The Python client owns local project state, BibTeX/Zotero import, TUI, MCP context, and agent skill installation. The backend owns parsing, MinerU PDF processing, OpenAlex fallback discovery, LLM translation, task artifacts, and server-side RAG.

The browser extension stays a browser surface. It does not ship Python dependencies such as `curl_cffi`, `pyzotero`, or `fastmcp`; it only handles browser-context capture and user-selected file upload/download.

## Repo Map

- [`src/mdtero`](./src/mdtero): Python CLI/TUI/client package
- [`extension`](./extension): MV3 browser extension source, tests, and build output
- [`install`](./install): website install manifest and install guide
- [`skills`](./skills): legacy skill source mirrored for compatibility
- [`archive`](./archive): retired public surfaces

## Local Development

```bash
uv run --with pytest --with rich --with textual --with httpx --with requests --with curl_cffi --with pyzotero --with fastmcp pytest tests_py -q
uv run --with build python -m build --wheel
npm --prefix extension test
npm --prefix extension run build
```
