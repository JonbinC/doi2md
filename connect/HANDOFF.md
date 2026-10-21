# Mdtero Connect — source handoff (2026-10-21)

> **Draft [PR #10](https://github.com/JonbinC/doi2md/pull/10) — not a signed desktop release.** Continue on `handoff/connect-research-client-20261021`. The runnable client is the loopback UI and Python bridge, with an optional local Pi runtime in full mode. A Tauri debug shell and Mac/Windows artifact workflow now wrap this same client; see [native debugging](native/DEBUGGING.md). Website integration, native human acceptance and institutional access acceptance remain separate work.

## Repository boundaries

- This public repository owns installable clients, Relay, extension, distributions and public docs. Do not copy private backend or website implementation here.
- Backend **PR #43 is merged** (`66d4388…`) and owns library tags, tag search, metadata import, scoped MCP tools and BibTeX/CSL/Markdown exports. Reuse those contracts; do not build another library database.
- Backend **PR #42** is a design-only cloud-first RFC, not evidence of implemented cloud storage.
- `JonbinC/Nextmdtero` owns website/Dashboard publication. This PR does not deploy that site.
- Existing Relay transport and Go release artifacts remain under `relay/`; see [its README](../relay/README.md).

## Runnable sources

| Path | Role |
|---|---|
| `connect/design/` | Offline prototype with mock data, CSP `connect-src 'none'` and 26 policy tests |
| `connect/app/` | Live UI: onboarding, library, local discovery, BYOK and optional Pi research; same-origin `/connect/v1/*` requests |
| `src/mdtero/connect/` | Loopback bridge, library adapters, provider credentials, supervised Agent runtime, Zotero client, Relay diagnostics and CLI |
| `connect/agent/` | Pinned Pi SDK adapter, dependency lockfile, license notice and real-SDK tests with synthetic HTTP |
| `connect/VERIFICATION.md` | Reproducible checks, recorded results and acceptance gaps |
| `connect/native/README.md` | Native packaging boundary; no signed installer is shipped here |

### Basic client

```sh
uv sync --frozen
# Configure the Mdtero account in the terminal if needed:
uv run mdtero setup
uv run mdtero connect --no-browser --port 0 --json
# Open the printed loopback URL locally; stop with Ctrl+C.
```

Basic mode does not require Node or the Pi SDK. Account secrets stay in the existing CLI configuration/environment and never return to the page. Restart the bridge after terminal login or saved-account configuration changes; refreshing the page does not reload the account configuration.

### Optional full mode

With Node.js **22.19.0 or newer**:

```sh
uv sync --frozen --extra connect-full
npm --prefix connect/agent ci --ignore-scripts
uv run --extra connect-full mdtero connect --full --no-browser --port 0 --json
```

The Python extra makes OS keyring support an explicit dependency; it cannot create or unlock an OS credential service. Session-only keys also work in full mode. The page never installs Node packages or enables full mode itself. See [the runtime README](agent/README.md) for installation from a locally built wheel and runtime details.

Select 1–10 account-library documents, enter a question, select an AI provider and a model from the pinned SDK's catalog, and preview the request. The preview freezes the selected metadata and the 128–4,096 output-token limit. A short-lived, single-use approval permits one model request; cancellation and a 90-second timeout stop the supervised child. Changing the selection, question, model or budget requires a new preview.

Only document ID, title, authors, year, venue and DOI are included. This is **metadata-only research**: the model has not read the full text, figures or abstracts. Pi exposes no model-callable tools, shell or filesystem access and does not discover local skills, extensions, project instructions or auth files. The SDK is trusted local code, not an OS sandbox. The token/request limit is not a dollar-denominated financial hard cap.

## BYOK and capability boundaries

| Service category | Provider IDs | What the local key currently enables |
|---|---|---|
| Discovery | `openalex` | Existing local OpenAlex discovery; no cloud fallback on the Connect search route |
| Parsing | `mineru` | Credential storage only; does not change cloud parsing credentials |
| Retrieval | `voyage` | Credential storage only; does not change cloud RAG credentials |
| AI | `openai`, `anthropic`, `google`, `openrouter` | Explicitly approved requests in the optional local Pi runtime |

Session storage is the default and is cleared when the bridge stops. Persistent storage is an explicit OS-keyring choice; unavailable, locked, plaintext/file and unsupported backends cannot silently become a plaintext fallback. Existing environment keys and legacy local OpenAlex configuration remain compatible. The provider status reports the effective source without returning key fragments or fingerprints. Saving never marks a key as verified.

OpenAlex's explicit key check uses a fixed, free single-entity lookup with the key in a Bearer header. MinerU, Voyage and AI checks are configuration-only: no parsing, embedding, reranking or generation is submitted for diagnosis. Search results are metadata and are not automatically added to the account library. See [verification](VERIFICATION.md) for provider documentation and test boundaries.

## Existing client behavior

- Three-step onboarding, account-library verification and distinct configured/verified states.
- Tag drafts survive redraws. Preview explicitly sends `dry_run: true`; applying the reviewed selection sends `false`. Draft/selection changes invalidate the preview.
- Backend #43 provides BibTeX, CSL JSON, Markdown and Markdown ZIP. Markdown exports remain text-only, without images.
- Relay transport, browser capability and entitlement remain independent diagnostics. An online Relay is not evidence of full-text access.
- Zotero has explicit collection selection and metadata-only import preview. Connector reachability is not full synchronization.

Bridge guards apply to the new provider/research routes too: loopback-only binding, Host/Origin validation, CSRF for POST, same-origin UI requests, secret-free status/errors and fixed Zotero `http://127.0.0.1:23119`. Newly entered provider keys do not enter `config.json`, prompts, browser persistence or process argv; Pi receives only its selected AI key over stdin.

## Reproduce checks

```sh
uv run pytest tests_py/test_connect_*.py -q
node --check connect/app/api.js
node --check connect/app/app.js
node --test connect/design/policy.test.cjs
npm --prefix connect/agent test
npm --prefix connect ci
npm --prefix connect run test:install
npm --prefix connect test
uv run python scripts/ci/secret_guard.py
```

The browser fixture replaces upstream account/Relay/Zotero/provider services. Node tests use the actual pinned Pi SDK with a synthetic HTTP model server. Neither is a private-provider-key or paid-model acceptance test. Detailed commands and recorded exit codes are in [VERIFICATION.md](VERIFICATION.md).

## Remaining work

1. Nextmdtero website/Dashboard Connect entry, launch guidance/deep links and an eventual verified release manifest.
2. macOS/Windows Tauri debug artifacts and human acceptance; supported-OS Relay lifecycle/upgrade, credentials, signed/notarized installers and install/upgrade/uninstall evidence. Shell, bundled Python/Node/Pi and explicitly approved HTTP-only Relay controls now exist. The client Relay precheck is not an atomic cross-computer lease.
3. Zotero pagination, stable source/account checkpoints, dedupe, deletion synchronization and real desktop/version acceptance.
4. Visible local CARSI login, passwords/Cookies kept on-device, and school-by-publisher full-text acceptance.
5. Pi full-text evidence/tools, production model-provider acceptance, financial hard caps, OS sandboxing and durable run history. Pi is the selected Agent implementation; no OpenCode runtime ships here.
6. Actual local MinerU/Voyage consumers or explicit backend per-user BYOK contracts. Storing a key does not add those contracts.
7. Backend 5 GiB Markdown/private-image quota, durable object storage and tested PostgreSQL backup/restore.
8. Backend MCP Reader embedding and product-level website/client/Reader integration.

**Keep PR #10 Draft.** Reviewable local sources and passing tests do not authorize merge, publication, website support-matrix changes or native release claims.
