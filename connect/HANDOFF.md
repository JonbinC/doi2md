# Mdtero Connect — source handoff (2026-10-21)

> **Draft [PR #10](https://github.com/JonbinC/doi2md/pull/10) — not a signed desktop release.** Continue on `handoff/connect-research-client-20261021`. The runnable client is the loopback UI and bridge; native packaging, website integration and institutional access acceptance remain separate work.

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
| `connect/app/` | **Live UI** with three-step onboarding, library operations and connection diagnostics. Served by the loopback bridge; talks to `/connect/v1/*` on the same origin. |
| `src/mdtero/connect/` | Python bridge, library adapters, Zotero loopback client, Relay diagnostics, CLI (`mdtero connect`). |
| `connect/VERIFICATION.md` | Reproducible checks, evidence boundaries and outstanding acceptance work. |
| `connect/native/README.md` | Native packaging plan; interim entry is `mdtero connect`. |

### Runnable slice (verify locally)

```sh
uv sync --frozen
uv run pytest tests_py/test_connect_security.py tests_py/test_connect_bridge.py tests_py/test_connect_zotero_local.py -q
node --check connect/app/api.js && node --check connect/app/app.js
node --test connect/design/policy.test.cjs
uv run python scripts/ci/secret_guard.py
# with a real API key already configured:
uv run mdtero connect --no-browser --json
```

See [verification](VERIFICATION.md) for browser regression commands and the distinction between synthetic fixtures and real account/desktop acceptance. An API key must be configured in the CLI, never in this page. Restart `mdtero connect` after changing saved configuration; refreshing the page does not reload the bridge's CLI configuration.

### Live client behavior

- Three-step onboarding carries the offline prototype's visual design into the live app. It explains account setup, literature access and optional device/AI connections without simulated registration or invented verification.
- Configured credentials and a successful account-library request are separate states. A present key is not proof of server authentication, publisher access or cloud storage durability.
- Tag drafts survive redraws. Adding or removing tags first makes an explicit `dry_run: true` preview; applying the reviewed selection sends `dry_run: false`. Selection or draft changes invalidate the previous preview.
- BibTeX, CSL JSON, single-document Markdown and Markdown ZIP use backend #43. Markdown is text-only, without images; JSON downloads remain downloadable bytes.
- Relay transport, browser capability and entitlement diagnostics are separate. A diagnostic without an article identifier/full-text evidence cannot certify the selected paper or every publisher.
- Zotero offers explicit collection selection and metadata-only import preview. Connector reachability does not mean collection listing or complete synchronization works.
- Agent stays disabled. The UI does not claim a verified AI connection from opening the onboarding step.

Security gates already enforced in the bridge:

- Bind host must be `127.0.0.1` or `::1`
- Host / Origin checks for API routes
- CSRF required for POST
- Zotero uses fixed `http://127.0.0.1:23119` only (no user-supplied base URL)
- API key never returned to the UI

## Product direction (unchanged)

One unified **Mdtero Connect** desktop application, with **Library mode** (everyday) and optional **Research mode** (AI agent), sharing account/library contracts. Do not create two unsynchronized libraries.

## Remaining work (not claimed done)

1. Nextmdtero website/Dashboard Connect entry, launch guidance and eventual verified release manifest; no signed desktop download is available from this work.
2. Tauri 2 shell, Relay sidecar supervision, OS credential storage, signed/notarized installers and uninstall evidence.
3. Zotero pagination, stable source/account checkpoints, dedupe and deletion synchronization; desktop/version acceptance remains required.
4. Visible local CARSI login, passwords/Cookies kept on-device, and school-by-publisher full-text acceptance. Generic Relay diagnostics do not replace it.
5. Optional Agent (Pi/OpenCode), BYOK, approvals, budgets and tool isolation — currently `enabled: false`.
6. Cloud 5 GiB Markdown/private-image quota, durable object storage and PostgreSQL backup/restore (backend/ops), not a Connect-only flag flip.
7. Embedding the backend MCP Reader, plus product-level website/client/Reader integration.

## First implementation sequence (status)

- **Client (this Draft PR):** three-step onboarding, loopback UI, account-library verification and separate connection diagnostics.
- **Library (this Draft PR):** reviewed tag preview/apply and guarded exports through backend #43; no alternate library database.
- **Zotero (partial):** loopback probe, collection selection and metadata import dry-run; full checkpoint sync still open.
- **Agent PR:** status stub only
- **Website/backend:** out of scope for this repo’s deploy path

**Keep PR #10 Draft.** Passing tests makes this client reviewable; merge, publication, website support-matrix changes and native release claims still need explicit authorization and their own evidence.
