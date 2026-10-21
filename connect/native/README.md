# Native Connect shell

**Status: native debug builds, not a signed release.** The Tauri 2 shell starts the bundled Python loopback bridge, restricts its window to that bridge, and stops its managed processes on exit. macOS Apple Silicon, macOS Intel and Windows x64 target the full edition with bundled Node/Pi. Linux retains the basic CLI/browser client; a Linux native build is a development smoke target.

See [debug downloads and per-computer acceptance](DEBUGGING.md), [build instructions](BUILDING.md) and the [build matrix](support-matrix.json). The workflow uploads expiring Actions artifacts, without publishing a GitHub Release or changing the website support matrix. Per-OS human acceptance remains pending.

The native **Connect** menu opens account login in the system browser, cancels login, reconnects the bridge and opens the export folder (`Downloads/Mdtero Connect`). Successful login restarts the bridge; this clears session BYOK and cancels active Pi requests. Account login reuses the existing CLI callback/state and account-storage contract. Separate provider BYOK may use a supported OS credential service.

Go Relay is included in the native runtime but is **not started by the shell** in this slice. Relay start/stop/restart supervision is still open. There is no remote Tauri IPC, runtime dependency installation or automatic updater.

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

- macOS/Windows real-machine window, download, OAuth and lifecycle acceptance. Linux WebKit smoke does not certify them.
- Reuse the Go Relay in `relay/` as a supervised sidecar, with start/stop/restart and upgrade evidence.
- Node/Pi delivery on clean machines and update integrity. Builds bundle locked dependencies; page loads never run npm.
- Credential-store behavior on each supported OS, including locked/unavailable stores, key removal and uninstall policy.
- Code signing/notarization, checksums and verified website release manifests.
- Per-OS installation, upgrade, cancellation, shutdown and uninstall evidence.

Nextmdtero website entry, CARSI school/publisher access, complete Zotero checkpoint sync, local MinerU/Voyage execution, full-text Pi evidence and financial hard caps also remain open. Do not advertise a signed desktop edition or accepted native support matrix. Keep PR #10 Draft.
