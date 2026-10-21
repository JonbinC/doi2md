# Mdtero Connect — source handoff (2026-10-21)

> **WIP on PR #10 — not a signed desktop release.** This branch now includes a runnable loopback Connect bridge wired to backend library/tags/export contracts, plus the offline design prototype. Do not describe it as notarized macOS/Windows/Linux installers or a completed 5 GiB cloud migration.

## Repository boundaries and refs

- This public repository owns installable clients, Relay, browser extension, distributions and public docs. Do not move private backend or website code here.
- Backend **PR #43 was merged** (`66d4388…`), adding authenticated tags, tag search, scoped MCP library tools, BibTeX/CSL/Markdown exports. **Reuse these contracts; do not reimplement an alternate library database.**
- Backend **PR #42**: design-only cloud-first RFC (may still be open).
- Existing mainline Relay supports campus HTTP transport and multi-OS Go release artifacts; see `relay/README.md`.
- Website `JonbinC/Nextmdtero` owns dashboard/download-page publication.

## What is in this branch

| Path | Role |
|---|---|
| `connect/design/` | Offline editable prototype (mock data, CSP `connect-src 'none'`). Keep for UX reference + 26 policy tests. |
| `connect/app/` | **Live UI** served only by the loopback bridge. Talks to `/connect/v1/*` on the same origin. |
| `src/mdtero/connect/` | Python bridge, library adapters, Zotero loopback client, Relay diagnostics, CLI (`mdtero connect`). |
| `connect/native/README.md` | Native packaging plan; interim entry is `mdtero connect`. |

### Runnable slice (verify locally)

```sh
uv sync --frozen
uv run pytest tests_py/test_connect_security.py tests_py/test_connect_bridge.py tests_py/test_connect_zotero_local.py -q
node --check connect/app/api.js && node --check connect/app/app.js
node --test connect/design/policy.test.cjs
# with a real API key already configured:
uv run mdtero connect --no-browser --json
```

Security gates already enforced in the bridge:

- Bind host must be `127.0.0.1` or `::1`
- Host / Origin checks for API routes
- CSRF required for POST
- Zotero uses fixed `http://127.0.0.1:23119` only (no user-supplied base URL)
- API key never returned to the UI

## Product direction (unchanged)

One unified **Mdtero Connect** desktop application, with **Library mode** (everyday) and optional **Research mode** (AI agent), sharing account/library contracts. Do not create two unsynchronized libraries.

## Remaining work (not claimed done)

1. Tauri 2 shell + signed/notarized installers + website manifest checksums
2. Hardened Zotero collection sync checkpoints / dedupe against every desktop build
3. Visible CARSI institution login + per-article entitlement UX beyond the probe button
4. Optional Agent (Pi/OpenCode) with approvals and BYOK — currently `enabled: false`
5. Cloud 5 GiB MD+figures durability (backend/ops), not a Connect-only flag flip

## First implementation sequence (status)

- **Client PR 1 (this PR, in progress):** loopback UI shell + authenticated library list + Relay diagnostics + clear unauthenticated state
- **Client PR 2 (this PR, in progress):** tag preview/apply + guarded bulk exports through backend #43
- **Client PR 3 (partial):** Zotero loopback probe/collections/import dry-run; full checkpoint sync still open
- **Agent PR:** status stub only
- **Website/backend:** out of scope for this repo’s deploy path

**Do not merge as if it ships signed native Connect.** Keep draft until tests pass and reviewers accept the loopback bridge as the interim client.
