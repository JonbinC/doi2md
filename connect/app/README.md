# Mdtero Connect — live loopback UI

This UI is served only by `mdtero connect` (Python loopback bridge on `127.0.0.1`). It calls `/connect/v1/*` on the same origin. The Mdtero API key stays in the CLI config / environment and is never sent to the page.

## Run

```sh
# from a checkout with a verified API key already configured
uv run mdtero connect --no-browser --json
# open the printed http://127.0.0.1:<port>/ URL locally
```

## Covered now

- Account library listing via `GET /api/v1/documents`
- Tags catalog / batch preview-apply via `/api/v1/library/tags*` (explicit `dry_run`)
- BibTeX / CSL / Markdown / Markdown ZIP export via `POST /api/v1/library/export`
- Relay transport vs browser diagnostics (article entitlement separate)
- Zotero desktop connector probe on approved `127.0.0.1:23119` only
- Optional Agent status stub (`enabled: false`)

## Not claimed

Signed native installers, CARSI password handling in-cloud, full offline MD+figures, or a shipped Pi/OpenCode agent.
