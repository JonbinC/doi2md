# Mdtero Connect — live loopback UI

The Python bridge serves this UI on `127.0.0.1` or `::1`. Browser requests use same-origin `/connect/v1/*`; the Mdtero account API key stays in CLI configuration/environment and never returns to the page. [Connect v0.1.0-preview.1](https://github.com/JonbinC/doi2md/releases/tag/connect-v0.1.0-preview.1) is a public unsigned desktop preview, not a signed release.

## Run

```sh
uv sync --frozen
# Configure the Mdtero account in the terminal when needed:
uv run mdtero setup
uv run mdtero connect --no-browser --port 0 --json
# Open the printed http://127.0.0.1:<port>/ URL locally.
```

Use the bridge, rather than `file://` or an unrelated web server. Basic mode needs no Node/Pi installation. After terminal login or saved-account configuration changes, stop and restart the bridge. Provider keys changed in this UI take effect in the running process.

The Tauri debug shell serves the same UI. Its **Connect → 登录 Mdtero 账户…** menu opens the system browser; successful login reconnects the bridge, clears session BYOK and cancels active research. **Connect → 打开导出文件夹** opens `Downloads/Mdtero Connect`. Check [native debugging status](../native/DEBUGGING.md) for the exact artifact commit and outstanding per-computer acceptance.

For optional Pi research, install Node.js **22.19.0 or newer**, then:

```sh
uv sync --frozen --extra connect-full
npm --prefix connect/agent ci --ignore-scripts
uv run --extra connect-full mdtero connect --full --no-browser --port 0 --json
```

The Python extra supplies keyring support; an available OS credential service is still required for persistent key storage. Full mode can also use session keys. Dependencies are installed explicitly, never by opening the page. See [the Pi runtime README](../agent/README.md).

## Use the client

1. Follow the three optional onboarding steps. A configured account key becomes verified only after an account-library request succeeds.
2. List/filter account documents, edit tags, preview changes and apply the reviewed selection. All batch writes send an explicit `dry_run` value; editing a draft or selection requires a fresh preview.
3. Download BibTeX, CSL JSON, Markdown or Markdown ZIP using backend #43. Markdown is text-only, without images.
4. Expand **用 OpenAlex 找文献** under the Library to search directly from this computer. Discovery results are metadata and are not automatically saved to the account library.
5. Open **Settings** for separate OpenAlex, MinerU, Voyage and AI provider keys. Saving a key does not start a provider request.
6. Open **Connections** for bundled Relay controls, independent transport/browser/entitlement diagnostics, and Zotero collection preview.
7. In full mode, select 1–10 library documents and preview a Pi question, provider, catalog model and output-token limit. Explicit approval makes one model request. Changes invalidate the preview; running requests can be cancelled and time out after 90 seconds. Reloading the page can recover the current running request and its cancel action; completed history is not durable.

Pi receives only selected document ID, title, authors, year, venue and DOI. It cannot claim to have read full text or abstracts. It has no tools, model-callable shell/filesystem access or local resource discovery. Results are plain text. The 128–4,096 output-token cap does not guarantee a dollar budget, and the installed SDK is trusted local code rather than an OS sandbox.

## BYOK

| Purpose | Providers | Current consumer |
|---|---|---|
| Discovery | OpenAlex | Local search through the existing discovery implementation; this route does not fall back to the cloud |
| Parsing | MinerU | Credential storage only; cloud parse is unchanged |
| Retrieval | Voyage AI | Credential storage only; cloud RAG is unchanged |
| AI | OpenAI, Anthropic, Google AI/Gemini, OpenRouter | Optional local Pi research |

Keys default to session memory, cleared when Connect stops. OS credential storage requires an explicit choice and a supported working backend; there is no plaintext-file fallback. Environment keys and legacy OpenAlex configuration remain readable. Status shows source/configured/verification states and never returns a saved key or its fragments. Entering a provider key does not change the Mdtero account key.

Saving does not make network requests or verify credentials. OpenAlex's explicit check performs one fixed free singleton lookup using a Bearer header. Other provider checks report configuration only and do not submit paid/usage-consuming work. Form fields clear after submission and keys are not persisted in browser storage.

## Managed Relay and local connections

The native debug bundle includes a supervised Go Relay. In **Connections**, check the current-page permission to carry Mdtero document HTTP requests through this computer, then explicitly start or restart it. A local account key is required. Startup fails closed when another Relay is already online or cloud status cannot be checked. The client-side precheck is not an atomic lease across computers.

The UI distinguishes its managed process from cloud transport, browser readiness and article entitlement. Refreshing restores the running-process state, while permission remains unchecked after a page reload. Stop is available for an owned running process without granting transport permission again. Closing the client stops its owned child; it does not control an existing external Relay or install a background service. This managed mode keeps the institution browser disabled. A running process or online transport does not prove full-text access.

Plain `mdtero connect` has no trusted bundled Relay resource directory, so its managed start/restart controls are unavailable; diagnostics remain usable. Per-OS real-account startup, crash cleanup and upgrade acceptance are still required. Zotero uses fixed `127.0.0.1:23119`, explicit collection selection and metadata-only import preview; reachability is not checkpoint synchronization.

## Verify and inspect gaps

```sh
uv sync --frozen --extra connect-full
uv run --extra connect-full pytest tests_py/test_connect_*.py -q
npm --prefix connect/agent ci --ignore-scripts
npm --prefix connect/agent test
npm --prefix connect ci
npm --prefix connect run test:install
npm --prefix connect test
```

See [recorded verification and remaining acceptance](../VERIFICATION.md). The real loopback browser fixture has synthetic upstream data; Pi SDK tests use a local fake HTTP model server. Neither spends model credits or certifies a real provider, native installer or institution's full-text access. The [offline design prototype](../design/README.md) remains mock-only.

Signed native installers, per-OS native/Relay human acceptance, complete Zotero synchronization, visible CARSI login, cloud 5 GiB durability, full offline Markdown/figures, full-text Pi tools and financial hard caps remain incomplete. The exact platform build results and limits are in [verification](../VERIFICATION.md). Institution passwords and Cookies must remain on-device.
