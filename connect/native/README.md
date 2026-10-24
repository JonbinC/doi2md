# Native Connect shell

**Status: public unsigned desktop preview.** The Tauri 2 shell starts the bundled Python loopback bridge, restricts its window to that bridge, and stops its managed processes on exit. macOS Apple Silicon has a full DMG; Intel Mac currently has a full `.tar.gz` app bundle; Windows x64 has a full installer, all with Node/Pi. [Download them from the Connect v0.1.0 preview release](https://github.com/JonbinC/doi2md/releases/tag/connect-v0.1.0-preview.1). Linux has the basic CLI/browser client and no native installer.

See [debug downloads and per-computer acceptance](DEBUGGING.md), [build instructions](BUILDING.md) and the [build matrix](support-matrix.json). The desktop assets are published for debugging; per-OS installation, account login, credentials and lifecycle acceptance remains pending.

The native **Connect** menu opens account login in the system browser, cancels login, reconnects the bridge and opens the export folder (`Downloads/Mdtero Connect`). Successful login restarts the bridge; this clears session BYOK and cancels active Pi requests. Account login reuses the existing CLI callback/state and account-storage contract. Separate provider BYOK may use a supported OS credential service.

Go Relay is included and starts only after explicit permission in Connections. The bridge manages only its own child, checks for an existing cloud Relay before starting, and stops its child on close. This mode carries HTTP traffic with the institution browser disabled; it does not install a background service. There is no remote Tauri IPC, runtime dependency installation or automatic updater.

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

Local HTML/PDF full-text parsing is a separate capability from the Pi full edition. The native bridge currently freezes Python 3.11, while the optional private `mdtero-parser` requires Python 3.12 or newer and is not part of the public `connect-full` extra. Native runtime manifests now record the frozen-build Python version, parser module detection and compatibility status; the artifact collector rejects missing or contradictory declarations. A compatible build environment is only a preflight signal, not proof that the parser is inside the frozen executable. Keep local full-text parsing release-gated until a frozen import smoke and authorized HTML/PDF fixtures pass.

## Native acceptance still required

- macOS/Windows real-machine window, download, OAuth and lifecycle acceptance. Linux WebKit smoke does not certify them.
- Supported-OS Relay start/stop/restart, crash cleanup and upgrade acceptance. A client-side precheck cannot atomically prevent two computers connecting at the same time.
- Node/Pi delivery on clean machines and update integrity. Builds bundle locked dependencies; page loads never run npm.
- Credential-store behavior on each supported OS, including locked/unavailable stores, key removal and uninstall policy.
- Code signing/notarization, checksums and verified website release manifests.
- Per-OS installation, upgrade, cancellation, shutdown and uninstall evidence.

The Nextmdtero homepage now points users to this preview. CARSI school/publisher acceptance, complete Zotero checkpoint sync, local MinerU/Voyage execution, full-text Pi evidence and financial hard caps remain open. Do not advertise a signed desktop edition or accepted per-OS support.
