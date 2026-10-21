# Mdtero Connect — live loopback UI

This UI is served only by `mdtero connect` (Python loopback bridge on `127.0.0.1`). It calls `/connect/v1/*` on the same origin. The Mdtero API key stays in the CLI config / environment and is never sent to the page.

## Run

```sh
# from a checkout with a locally configured API key
uv sync --frozen
uv run mdtero connect --no-browser --json
# open the printed http://127.0.0.1:<port>/ URL locally
```

The page must be served by this bridge, not opened with `file://` or an unrelated web server. Use `--port 0` for an available local port. Configure the account with `mdtero login` / `mdtero setup` in a terminal. After changing saved configuration, stop and restart the bridge before refreshing the page; the bridge loads configuration when it starts.

## Three-step start

1. Configure the local account and check that the account-library request succeeds. Merely finding a key never marks remote authentication as verified.
2. Review literature access and continue with available documents. This page does not collect publisher/model keys or verify publisher entitlement.
3. Check optional Relay/Zotero connections and inspect Agent availability. Moving between steps does not turn on a connection or complete an authorization.

## Covered now

- Account library listing via `GET /api/v1/documents`
- Tags catalog / batch preview-apply via `/api/v1/library/tags*` (explicit `dry_run`); drafts survive redraws, and edits/selection changes require a new preview before applying
- BibTeX / CSL / Markdown / Markdown ZIP export via `POST /api/v1/library/export`
- Relay transport vs browser diagnostics; entitlement results are diagnostics, not proof that the selected paper is readable
- Zotero desktop connector probe and explicit collection selection on approved `127.0.0.1:23119` only; import preview is metadata-only with `dry_run: true`
- Optional Agent status stub (`enabled: false`)

## Not claimed

Website/Dashboard integration, signed native installers, complete Zotero synchronization, a visible CARSI login/entitlement workflow, cloud 5 GiB durability, full offline Markdown+figures, or a shipped Pi/OpenCode agent. Institution passwords and Cookies must remain on-device.

See [verification and remaining acceptance work](../VERIFICATION.md). The offline [design prototype](../design/README.md) uses mock data; its policy tests do not verify the live backend, native installation or institutional access.
