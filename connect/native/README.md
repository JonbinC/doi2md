# Native Connect shell

**Status: native packaging is not shipped.** This branch provides a Python loopback client, with an optional local Pi SDK runtime. No signed/notarized macOS, Windows or Linux Connect installer is available from this work.

## Run the current sources

```sh
uv sync --frozen
uv run mdtero connect --no-browser --port 0 --json
# Open the printed loopback URL locally.
```

Basic mode requires no Node/Pi installation. Full mode uses Node.js **22.19.0 or newer**:

```sh
uv sync --frozen --extra connect-full
npm --prefix connect/agent ci --ignore-scripts
uv run --extra connect-full mdtero connect --full --no-browser --port 0 --json
```

The browser cannot enable full mode or install dependencies. The Python wheel built from this branch includes Pi worker sources and its lockfile, but does not bundle Node or installed npm dependencies. See [the runtime instructions](../agent/README.md) and [verification](../VERIFICATION.md).

Mdtero account authentication uses existing CLI configuration/environment. Separate BYOK defaults to process memory; persistent writes require an explicit, working supported OS keyring. There is no plaintext provider-key fallback. Optional keyring dependency installation does not prove that a usable credential service exists on the operating system.

The Pi child is supervised, cancellable and limited to one approved metadata-only model request. It exposes no model-callable shell/filesystem tools. Those restrictions are not an OS sandbox and do not replace signing, dependency delivery or native lifecycle acceptance.

## Native acceptance still required

- Tauri 2 shell and loopback/WebView lifecycle integration.
- Reuse the Go Relay in `relay/` as a supervised sidecar, with start/stop/restart and upgrade evidence.
- Node/Pi dependency delivery and update integrity; no runtime npm installation triggered by page loads.
- Credential-store behavior on each supported OS, including locked/unavailable stores, key removal and uninstall policy.
- Code signing/notarization, checksums and verified website release manifests.
- Per-OS installation, upgrade, cancellation, shutdown and uninstall evidence.

Nextmdtero website entry, CARSI school/publisher access, complete Zotero checkpoint sync, local MinerU/Voyage execution, full-text Pi evidence and financial hard caps also remain open. Do not advertise a downloadable desktop edition or native support matrix until its artifacts and acceptance evidence exist. Keep PR #10 Draft.
