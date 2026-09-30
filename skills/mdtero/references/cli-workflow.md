# CLI workflow

## Projects

- initialize: `mdtero project init`
- inspect: `mdtero project status --json` or `mdtero project list --json`
- queue: `mdtero project add <doi-or-url> --json`, `mdtero project remove <doi-or-url-or-task-id> --json`
- BibTeX: `mdtero project import-bib references.bib --json`
- Zotero: `mdtero config zotero`, then `mdtero zotero import --json`; sync notes/tags with `mdtero zotero sync`
- parse queue: `mdtero project parse --wait --timeout 300 --json`
- refresh: `mdtero project refresh --wait --timeout 300 --json`
- download: `mdtero project download --output-dir ./mdtero-output --json`

## Parse / translate / download

- DOI/URL: `mdtero parse <doi-or-url> --trace --wait --timeout 300 --json`
- Quote shell metacharacters: `mdtero parse '10.1016/S0260-8774(02)00304-7' --trace --wait --timeout 300 --json`
- Local file: `mdtero parse --file <paper.pdf|paper.html|paper.xml|paper.epub> --trace --wait --timeout 600 --json`
- Directory batch: `mdtero parse --batch ./papers --wait --timeout 300 --json`
- DOI list batch: `mdtero parse-batch dois.txt --wait --download paper_md --output-dir ./mdtero-output --json`
- Poll: `mdtero status <task-id> --wait --timeout 300 --json`
- Download Markdown: `mdtero download <task-id> paper_md --output-dir <dir> --json` (metadata filenames; `.low_quality.md` for low-confidence; updates `manifest.csv`)
- Translate: `mdtero translate <parse-task-id> --to zh-CN --wait --timeout 600 --json` or `mdtero translate <paper.md> --to zh-CN --wait --timeout 600 --json`

When the backend route plan includes a fetchable HTML/XML/EPUB/PDF source, the CLI may acquire it locally with `curl_cffi` and upload automatically. Inspect `client_acquisition` in `--trace` JSON.

## Discover

- `mdtero discover "<query>" --json` (unquoted multi-word queries also work)
- Interactive add: `mdtero discover "<query>" --limit 5 --interactive` (`n`/`p` page, `r <query>` refine, numbers select, `a` add page; `--source local|server` to force)
- Scripted add: `mdtero discover "<query>" --limit 5 --add --select 1,3 --json`
- Paging: `mdtero discover "<query>" --limit 5 --page 2 --json`

## RAG

- One-command bootstrap: `mdtero rag query "What are the strongest findings?" --build-if-needed --json`
- Explicit recovery: `mdtero rag build --wait --json`, `mdtero project ingest --json`, `mdtero project create-server --json`, `mdtero project link --server-project-id <id> --json`

## Continuation contract

`mdtero parse`, `mdtero project parse`, `mdtero status`, and `mdtero project refresh` JSON include `next_commands`, `quality_label`, and sometimes `quality_warning`. Follow those before inventing a new path. Prefer returned `preferred_artifact` on success; report `reason_code` / `action_hint` / `quality_label` on failure.

## Capture boundaries

- Keep user-provided files and licensed browser-context capture on the user's machine when required
- Use the browser extension only for browser-context capture and user-triggered upload/download
- Extension-to-CLI handoff: if extension capture is blocked by a publisher challenge, campus-network/session-bound access, or a user-saved file workflow, continue with `mdtero parse <doi-or-url> --trace --wait --timeout 300 --json` or `mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json`; after a successful parse, continue with `mdtero rag query "<question>" --build-if-needed --json`, `mdtero mcp briefing --json`, and `mdtero mcp serve`; preserve `client_acquisition`, raw upload status, `reason_code`, `action_hint`, `next_commands`, and the MCP server startup contract
- `mdtero parse`, `mdtero project parse`, `mdtero status`, and `mdtero project refresh` JSON responses include `next_commands`, `quality_label`, and sometimes `quality_warning`; follow those returned commands before inventing a new continuation
