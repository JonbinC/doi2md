# Mdtero Connect — source handoff (2026-10-21)

> **HANDOFF / NOT A RELEASE.** This branch preserves the recoverable Connect design prototype and documents the remaining native implementation. It must not be described as a signed macOS/Windows/Linux client or as a completed cloud migration.

## Repository boundaries and refs

- This public repository owns installable clients, Relay, browser extension, distributions and public docs. Do not move private backend or website code here.
- Current base: `doi2md` main `2b1628ceef5b1ab879ec735b7084fc8ce46ecb3c`.
- Backend **PR #43 was merged** at `66d4388176a334ce36474769e0c695ef600f4657`, adding authenticated per-document and bulk tags, tag search, scoped MCP library tools, BibTeX/CSL/Markdown exports and tests. Reuse these contracts; do not reimplement an alternate library database.
- Backend **PR #42**: design-only cloud-first 5 GiB, Connect, CARSI/Zotero/RAG requirements; open at time of this handoff: https://github.com/JonbinC/mdtero-backend/pull/42
- Existing mainline Relay supports campus HTTP transport, optional controlled browser profile, user web login, background service and multi-OS Go release artifacts; see `relay/README.md`.
- Existing website `JonbinC/Nextmdtero` manages user dashboard and official download page; cross-repo design changes belong there.

## What is actually preserved here

- `connect/design/` contains the **offline editable prototype** (HTML/CSS/JS, policy tests and reproducible build script), captured from this conversation's artifact. It uses **synthetic** accounts, quota, institution access, Zotero and papers. It makes **no requests to Mdtero**. Do not ask real users to type keys into the prototype.
- The developer preview screenshots were created locally, but the claimed later Go production implementation source is **not present** in the currently accessible working directory. Do not invent or claim a recovered file. The attached source is a design/interaction starting point, not the claimed working native client.
- The exact portable source has a manifest and reproducibility checks in `connect/design/README.md`. Run `python build.py` and `node --test policy.test.cjs` there.

## Requested product (from user, superseding a pure Relay helper)

One unified **Mdtero Connect** desktop application, with **Library mode** (everyday, minimal) and **Research mode** (optional AI agent), built from shared account/library contracts. Do **not** create two unsynchronized libraries or force users through a terminal.

1. **Library:** Zotero-like three-pane view, collections, user-editable tags (batch add/remove + AND/OR filter), meaningful metadata/provenance, multi-select, duplicate handling, citation/BibTeX/CSL export, MD text and batch ZIP downloads. Explicitly label missing figures; existing backend export's `X-Mdtero-Export: markdown-text-only` must not be marketed as full MD+figures.
2. **Acquisition:** DOI/URL, local PDF/EPUB/XML/HTML, current browser page (authorized Relay or extension), Zotero selected-collection one-way sync. Structured API/publisher XML first; authorized article HTML second; MinerU only when a PDF/scan requires conversion. Parsing always requires explicit estimated-cost confirmation and an idempotency key.
3. **Connections/settings:** Mdtero account login, safe publisher keys, Relay transport vs browser readiness vs **per-article** institution entitlement, CARSI via visible local browser (never collect institution cookies/passwords), Zotero local API, remote MCP host connection and diagnostics.
4. **AI agent:** Optional narrow scientific tools (search, select, compare evidence, retrieve formula/table/figure, add tags, organize, export) through a host-owned permission policy. Model BYOK API and optional provider-authorized OAuth are *different* flows. Do not silently claim ChatGPT subscription OAuth can power commercial Mdtero; check provider eligibility. Assess Pi agent-core vs OpenCode SDK but never expose unrestricted shell/filesystem by default.
5. **Cloud:** 5 GiB logical per-user private MD + protected figures and citation revisions, **not** an instantly enabled new entitlement until backend quota, object-store manifest promotion and PostgreSQL backup/restore are validated. Never call the prototype proof that this is deployed.
6. **Release:** macOS ARM64/Intel, Windows x64, supported Linux x64/ARM64. Build + signed/notarized installer gates, web release manifest updated to actual asset checksums. Never advertise builds that do not exist.

## First implementation PRs — recommended sequence

- **Client PR 1:** Native UI shell + authenticated account/Relay status, read-only library list, clear error states and shared accessible design tokens; no secret in WebView and no arbitrary remote page navigation. Check loopback origin/CSRF if using local HTTP.
- **Client PR 2:** Tag UI + guarded bulk exports + narrow capture tasks using backend #43; real cross-account denial tests.
- **Client PR 3:** Zotero local API read-only collections/changes and item import, deterministic dedup/checkpoints; visible institution login + article verification.
- **Agent PR:** Pi/OpenCode adapter as a bounded optional layer. Approval before writes, paid parse/translation and data upload. Real evidence citations and token cost reporting.
- **Website/backend PRs:** Three-step onboarding and storage promotion/migration after durability gates. This repo cannot deploy those independently.

## Handoff validation matrix

Must be run *after* actual code is implemented: `go test ./...` under `relay/`; `npm --prefix extension test -- --run`; `npm --prefix extension run build`; existing Python tests and backend release gate; desktop browser tests at 1440/768/390/320; real native install/upgrade/uninstall, CARSI and Zotero checks with authorized user sessions; server backup/restore and image survival; supply-chain hashes/signing and cross-account permissions.

**Do not merge this design-only handoff as if it ships native Connect.** Proceed from the extracted source and create follow-on runnable implementation PRs with proof for each finished feature.
