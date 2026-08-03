<div align="center">
  <img src="./extension/src/assets/icon-128.png" alt="Mdtero logo" width="120" />

  # Mdtero

  *Structured Markdown for research workflows.*
</div>

Mdtero turns papers into reusable Markdown packages for reading, translation, project research, and local agents.

Python/uv CLI, TUI, browser extension, and agent skill bundle are maintained as the public client surfaces.

**Languages:** English | [简体中文](./README_CN.md)

## Install

```bash
uv tool install --force --reinstall git+https://github.com/JonbinC/doi2md.git
mdtero setup
mdtero doctor --json
```

During alpha, install from this GitHub repository. If `uv` is unavailable, use the installer:

```bash
curl -Ls https://mdtero.com/install.sh | sh
curl -Ls https://mdtero.com/install.sh | sh -s -- --agent codex
```

The installer supports `uv`, `pipx`, and Python fallbacks. `--agent <target>` installs a local agent skill.

## Use Mdtero

```bash
mdtero discover "thermal energy storage" --limit 5 --interactive
mdtero parse <doi-or-url> --wait --timeout 300 --json
mdtero parse --file paper.pdf --trace --wait --timeout 600 --json
mdtero status <task-id> --wait --timeout 300 --json
mdtero download <task-id> paper_md --output-dir ./mdtero-output --json
mdtero translate <task-id> --to zh-CN --wait --timeout 600 --json
```

`mdtero doctor --json` returns safe auth/dependency/academic/Zotero/project/RAG summaries without echoing credentials.

The CLI is the default path. Desktop installs prepare the local access helper
automatically for campus-network and browser-required routes. Use the browser
extension only for current-page capture or when an existing browser session is
needed; it can hand DOI, URL, PDF, EPUB, HTML, or XML artifacts back to the CLI.

### Choose the surface for your environment

| Environment | Best surface | What it can solve | Boundary |
| --- | --- | --- | --- |
| Campus Windows/macOS with a full browser | Extension + optional local Relay | OA, campus-IP routes, browser login/challenges, entitled closed articles | The user completes visible login or verification. |
| CLI/Agent on a server only | CLI/API | OA, structured APIs, ordinary HTTP, VPN/IP-authorized files, and uploads | No browser session; WAF/login-only closed content needs a file or another desktop. |
| Server Agent plus a separate campus desktop | Server CLI/API + Relay on the desktop; extension as manual fallback | Full authorized browser acquisition on the desktop, then cloud parsing | The extension alone is user-triggered; use Relay when the server must request the article remotely. |
| Server connected to campus VPN without a browser | CLI/API with the VPN or proxy | IP-authorized machine-readable PDF/XML/HTML | VPN supplies network access, not browser cookies or challenge completion. |

In short: a browser is required for browser-bound entitlement; a campus IP or
VPN is sufficient only when the publisher exposes a machine-readable route.
Mdtero never bypasses a paywall or exports browser session material.

## Project Workflow

Use a local Mdtero project when you are handling a paper set:

```bash
mdtero project init --name literature-review
mdtero project import-bib references.bib --json
mdtero project parse --wait --timeout 300 --json
mdtero rag query "What are the strongest findings?" --build-if-needed --json
```

Zotero support is conservative: `mdtero zotero sync` adds Mdtero result notes and tags for matching succeeded items without rewriting Zotero bibliographic metadata.

## Browser And Agents

Use the browser extension as a lightweight fallback for a paper open in your
browser, content accessed through your own session, or a file you want to
upload. The extension and CLI share task history, downloads, and translation.

Install a local agent skill with:

```bash
mdtero agent install --interactive
mdtero mcp briefing --json
```

The briefing provides safe task state, available downloads, citations, and suggested next steps. Keep API keys and other secrets out of prompts, logs, and repositories. For a trusted headless machine, enter a fresh key only at the secure `mdtero setup --api-key --json` prompt.

## Access Boundaries

Mdtero helps process material you are permitted to access. Publisher subscriptions, institutional access, and source-specific credentials remain your responsibility. When a source needs your browser session or a local copy, use the extension or upload the saved file.

Parser and source-selection implementation are service internals, not user configuration. The stable workflow is submit, check status, download, translate, and use the resulting Markdown in a project.

## Product Boundary

Mdtero Account is the control plane for Mdtero API keys, quota, billing, history, and install prompts. Academic source keys stay in local `mdtero config academic` configuration. The CLI-managed local access helper and browser extension remain separate from provider credentials.

## Shared `/api/v1` server contract

The CLI, extension, dashboard, and MCP briefing expose this contract: `/api/v1/route`, `/api/v1/extension/route`, `/api/v1/tasks/parse`, `/api/v1/tasks/upload`, `/api/v1/tasks/{task_id}`, `/api/v1/tasks/{task_id}/download/{artifact}`, `/api/v1/discovery/search`, `/api/v1/tasks/translate`, `/api/v1/projects`, `/api/v1/projects/{project_id}/tasks/{task_id}/import`, `/api/v1/projects/{project_id}/rag/status`, `/api/v1/projects/{project_id}/rag/build`, and `/api/v1/projects/{project_id}/rag/query`.

## Repo Map

The Python package owns the CLI and local workflow; the `extension/` package is the lightweight browser fallback and `nextmdtero/` is the website/dashboard workspace.

## Documentation

- [Mdtero website](https://mdtero.com)
- [Documentation](https://mdtero.com/docs/)
- [Install guide](https://mdtero.com/docs/install.html)

## Development

```bash
uv run --with pytest --with rich --with textual --with httpx --with requests --with curl_cffi --with pyzotero --with fastmcp pytest tests_py -q
npm --prefix extension test
npm --prefix extension run build
```
