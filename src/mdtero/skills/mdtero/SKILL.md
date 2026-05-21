---
name: mdtero
description: Use when Mdtero should be available inside an agent workspace for scientific paper parsing, translation, task-status checks, Zotero/BibTeX project import, RAG, MCP, and backend-run Markdown workflows.
---

# Mdtero

## Quick Start

1. Install the Python runtime with `uv tool install mdtero`
2. Run `mdtero setup`
3. Use `mdtero login --api-key <key>` when the environment is headless
4. Run `mdtero doctor` before parse, translate, status, download, Zotero, RAG, or MCP work

## Setup Rules

- `MDTERO_API_KEY` or a saved Mdtero API key is required before cloud parse, translation, discovery fallback, and RAG work
- normal DOI/URL parsing should use the installed `mdtero` CLI and Mdtero backend parser
- local PDF/EPUB/XML/HTML files should be uploaded with `mdtero parse --file <path>`
- keep user-provided files and licensed browser-context capture on the user's own machine when required
- use the browser extension only for browser-context capture and user-triggered upload/download flows

## CLI Workflow

- initialize a project: `mdtero project init`
- import a BibTeX file: `mdtero project import-bib references.bib`
- import Zotero items: `mdtero config zotero`, then `mdtero zotero import`
- submit a project queue: `mdtero project parse --wait`
- refresh project tasks: `mdtero project refresh`
- download project Markdown: `mdtero project download --output-dir ./mdtero-output`
- parse a DOI/URL: `mdtero parse <doi-or-url>`
- parse a local paper file: `mdtero parse --file <paper.pdf|paper.html|paper.xml|paper.epub>`
- parse a directory of files: `mdtero parse --batch ./papers`
- search discovery: `mdtero discover "<query>"`
- poll status: `mdtero status <task-id>`
- download Markdown: `mdtero download <task-id> paper_md --output-dir <dir>`
- translate Markdown: `mdtero translate <paper.md> --to zh-CN`
- build server project RAG: `mdtero rag build --project-id <server-project-id>`
- query server project RAG: `mdtero rag query "<question>" --project-id <server-project-id>`
- serve project MCP context: `mdtero mcp serve`

The CLI talks to `https://api.mdtero.com` by default. Use `MDTERO_API_URL` only for staging or local verification.

## Output Rule

- prefer Markdown first
- treat PDF as input, not as the normal output
- use fallback bundles only when the workflow truly needs image or asset files
- keep task ids, `reason_code`, and download artifact names visible in handoffs

## Verification Rule

- do not treat installation as complete until `mdtero doctor` reports an API key source
- if `mdtero` is missing, install the Python runtime with `uv tool install mdtero`
- if a task fails, report `reason_code` and the server action hint before retrying
