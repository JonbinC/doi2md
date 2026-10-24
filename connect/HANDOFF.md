# Mdtero Connect — source handoff (updated 2026-10-22)

> **Public unsigned desktop preview.** [PR #10](https://github.com/JonbinC/doi2md/pull/10) is merged. Connect v0.1.0-preview.1 has durable [Mac and Windows debug downloads](https://github.com/JonbinC/doi2md/releases/tag/connect-v0.1.0-preview.1); the release page also documents Linux's basic CLI/browser setup. The Nextmdtero download entry is being published separately. The Tauri shell wraps the same loopback UI and Python bridge, with an optional local Pi runtime in full mode. Per-computer installation, account login and institutional access acceptance remain pending; see [native debugging](native/DEBUGGING.md).

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
| `src/mdtero/connect/` | Loopback bridge, library adapters, provider credentials, supervised Pi and Relay runtimes, native account login, Zotero client, diagnostics and CLI |
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

The desktop debug shell uses the same client. Its Connect menu offers account login in the system browser, cancellation/reconnection, and the export folder (`Downloads/Mdtero Connect`). Successful login restarts the bridge, clears session BYOK and cancels active research. Native Mac/Windows account-login and installation acceptance remain pending. [Debugging status](native/DEBUGGING.md#recorded-artifact-status) identifies which exact commits have artifacts; an older successful Mac artifact does not certify current Windows delivery.

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
- Connect's local full-text path stores artifacts on this computer and parses them in-process. If IEEE's rendered page is only an abstract/access shell, it now tries the publisher's fixed `stampPDF` URL in the same visible browser and locally parses a verified PDF. This does not call or replace the backend's IEEE OA worker. The parser is currently declared only in the optional `parse` extra (Python 3.12+), while native full builds use Python 3.11 and install `connect-full` only; packaged full-text availability remains unverified and the worker cannot be retired on this evidence.
- Connections can explicitly start, stop or restart the native bundle's owned HTTP-only Relay. Startup/restart requires current-page transport permission, a local account key and a confirmed cloud-offline precheck. Reload restores the owned-process state without saving permission. Plain CLI mode has no bundled Relay resource path and offers diagnostics only.
- The native client supervises the same Go `mdtero-relay` runtime shipped for standalone use; its loopback UI/bridge, local full-text parser and Relay's cloud transport remain separate permission and data paths. The remaining duplicate acquisition policy is mostly in Python compatibility fetch vs Go fetch and the Connect vs Relay publisher adapters. A safer next unification step is shared request/result fixtures and parity tests for host allowlists, redirects, size limits, credential stripping and IEEE PDF candidates; browser profiles, cookies and account-key scopes must stay separate.
- Relay process, cloud transport, browser capability and entitlement remain independent observations. The managed browser stays disabled, existing external Relays are not controlled, and no background service is installed. An online Relay is not evidence of full-text access; the client-side precheck is not an atomic cross-computer lease.
- Zotero has explicit collection selection and metadata-only import preview. Connector reachability is not full synchronization.

Bridge guards apply to provider, research and Relay control routes: loopback-only binding, Host/Origin validation, CSRF for POST, same-origin UI requests, secret-free status/errors and fixed Zotero `http://127.0.0.1:23119`. Newly entered provider keys do not enter `config.json`, prompts, browser persistence or process argv; Pi receives only its selected AI key over stdin. The owned Relay receives account credentials through its sanitized child environment; its temporary browser-off policy contains no key.

## Reproduce checks

```sh
uv sync --frozen --extra connect-full
uv run --extra connect-full pytest tests_py/test_connect_*.py -q
node --check connect/app/api.js
node --check connect/app/app.js
node --test connect/design/policy.test.cjs
npm --prefix connect/agent ci --ignore-scripts
npm --prefix connect/agent test
npm --prefix connect ci
npm --prefix connect run test:install
npm --prefix connect test
uv run --extra connect-full python scripts/ci/secret_guard.py
```

The browser fixture uses real UI/bridge security and real provider/Agent approval logic while replacing upstream account/Relay/Zotero/provider services and model execution. Relay UI coverage simulates the process boundary; separate runtime tests exercise supervised children. Node tests use the actual pinned Pi SDK with a synthetic HTTP model server. Neither is a private-provider-key or paid-model acceptance test. Detailed commands, recorded exit codes and platform CI failures are in [VERIFICATION.md](VERIFICATION.md).

## Remaining work

1. Keep the Nextmdtero Connect download entry aligned with this preview release and add dashboard deep links and a machine-verified release manifest.
2. Complete per-OS installation, native account login, downloads, Relay lifecycle/upgrade, credential-store and uninstall acceptance. Mac and Windows full bundles are published with hashes; Tauri, bundled Python/Node/Pi and explicitly approved HTTP-only Relay controls are implemented. Developer identity signing, notarization and a machine-verified website release manifest remain open.
3. Zotero pagination, stable source/account checkpoints, dedupe, deletion synchronization and real desktop/version acceptance.
4. Visible local CARSI login, passwords/Cookies kept on-device, and school-by-publisher full-text acceptance.
5. Pi full-text evidence/tools, production model-provider acceptance, financial hard caps, OS sandboxing and durable run history. Pi is the selected Agent implementation; no OpenCode runtime ships here.
6. Actual local MinerU/Voyage consumers or explicit backend per-user BYOK contracts. Storing a key does not add those contracts.
7. Backend 5 GiB Markdown/private-image quota, durable object storage and tested PostgreSQL backup/restore.
8. Backend MCP Reader embedding and product-level website/client/Reader integration.

PR #10 is merged and this preview is published. Do not describe these unsigned artifacts as a signed desktop release or completed per-OS acceptance.
