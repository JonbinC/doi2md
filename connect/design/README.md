# Mdtero Connect — offline UI source handoff

This directory is an **editable, dependency-free UI scaffold**, intended for the next engineer/Work session. Open `index.html` in a browser. All papers, tags, state changes, login, school status, quota and downloaded BibTeX/CSV are **mock/sample data**; no real API requests are made, and the CSP forbids outbound connections. Do not use real credentials.

## Files

- `index.html` — responsive standalone shell and intentionally visible demo warning.
- `style.css` — shared semantic palette and desktop/tablet/phone layout for sidebar, literature list, metadata/actions inspector, status and setup.
- `app.js` — reconstructed interactive source handoff for three-step onboarding, library selection, tag filter/edit, fake citation exports, CARSI/Zotero capability-state demonstrations and separate Library/Research settings. It is **not** the previously claimed real Go Connect integration; those Go source files were not present in the recoverable local workspace.
- `policy.js` + `policy.test.cjs` — **exact recovered** executable design contract and its original 26 Node policy tests from the October 21 conversation artifact. These are product-state invariants, not production permissions/quota/sync implementations.

The earlier 2026-10-21 fully interactive design artifact remains a conversation attachment (`Mdtero-Connect-v1-design.zip`). The recovered backend/client repository snapshots were used to document handoff boundaries, but are **not duplicated** here. This self-contained page is a smaller, newly authored source-readable UI reference and should not be claimed as byte-identical to the original attachment.

## Local checks

```sh
node --check app.js
node --test policy.test.cjs
# open index.html in a normal browser
```

The live loopback client now lives in [`../app/`](../app/) and is started with `mdtero connect`. Keep this `design/` tree offline (CSP forbids outbound calls) as the interaction reference and policy-test fixture.

When extending further, prefer typed bridge adapters over a second unscoped proxy. The current backend already supports:

- `GET /api/v1/documents` (account library)
- `GET /api/v1/library/tags`, `GET /api/v1/library/tagged-documents`, `GET /api/v1/library/documents/{id}/tags`
- `POST /api/v1/library/tags/batch`, `POST /api/v1/library/export`
- `POST /api/v1/library/import` for bounded, metadata-only import
- Existing Relay login/status/browser capture flows under `relay/`

**Security gates:** no school cookies, OAuth tokens or publisher keys in the webview; local device credentials in native OS secure storage; no untrusted remote HTML as privileged client UI; short-lived local server credentials, loopback origin/CSRF checks; explicit confirmation before paid parsing, upload or write actions. Signed native installers and actual operating-system tests remain outstanding.

See [../HANDOFF.md](../HANDOFF.md) and backend PR [#42](https://github.com/JonbinC/mdtero-backend/pull/42) for the larger product plan. Backend PR [#43](https://github.com/JonbinC/mdtero-backend/pull/43) has already shipped the tag/export server contracts.