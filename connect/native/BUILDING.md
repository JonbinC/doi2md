# Building the native debug client

The native workflow builds full macOS Apple Silicon, macOS Intel and Windows x64 debug payloads. Linux remains a basic client first. Build artifacts are for debugging: macOS uses ad-hoc signing, Windows installers are unsigned, and real OS acceptance remains pending. This workflow uploads short-lived Actions artifacts; it does not create a GitHub Release or update website downloads.

## Build prerequisites

Use the matching operating system and architecture for every build; `prepare.py` rejects cross-compiling frozen Python resources. Install Python 3.11 with uv, Go 1.22+, Rust stable, and Node 22.19+. Dependency versions come from `uv.lock`, the npm lockfiles and `src-tauri/Cargo.lock`; the freezer is pinned to PyInstaller 6.19.0. Tauri additionally needs the platform build tools (Xcode command line tools on macOS, MSVC on Windows, GTK 3/WebKitGTK 4.1 development packages on Linux).

From the repository root:

```sh
uv sync --frozen --extra connect-full
npm --prefix connect/native ci --ignore-scripts
```

Prepare a full bundle on the appropriate host, choosing one target:

```sh
# Apple Silicon Mac
uv run --extra connect-full --with pyinstaller==6.19.0 python connect/native/prepare.py --target aarch64-apple-darwin --edition full
npm --prefix connect/native run build -- --target aarch64-apple-darwin --bundles app

# Intel Mac
uv run --extra connect-full --with pyinstaller==6.19.0 python connect/native/prepare.py --target x86_64-apple-darwin --edition full
npm --prefix connect/native run build -- --target x86_64-apple-darwin --bundles app

# Windows x64 (PowerShell, cmd or the workflow's bash)
uv run --extra connect-full --with pyinstaller==6.19.0 python connect/native/prepare.py --target x86_64-pc-windows-msvc --edition full
npm --prefix connect/native run build -- --target x86_64-pc-windows-msvc --bundles nsis
```

Preparation freezes the existing public Python bridge and real `connect/app` assets, builds the existing Go Relay, and installs the pinned Pi dependencies into generated runtime resources using `npm ci --ignore-scripts --omit=dev`. Full builds also copy the host Node executable and its complete license notices. If a distribution does not include those notices locally, preparation retrieves `LICENSE` from the fixed official Node GitHub tag matching the detected version. Windows executes npm's JavaScript entry point through Node directly, without constructing a shell command.

Each preparation then launches the actual frozen executable with a temporary anonymous configuration. It checks the served UI and CSP, loopback session, full-mode Node/Pi dependency probe when applicable, parent-requested shutdown and released listener. The smoke environment excludes inherited account keys, provider keys, proxies and Python/Node hooks; keyring reads are disabled for this build check. It performs no login, cloud library request, credential verification or model request. Windows smoke owns a named kill-on-close Job before launching the onefile bootloader; the bridge joins it before opening a listener. Failed Unix smoke processes and descendants are stopped through their separate process group.

The full artifact contains Python, Node, Pi and Relay. Debug testers do not need to install those runtimes separately. Platform libraries, WebView support and working OS credential services still depend on the host operating system.

## Linux basic smoke

For local Linux verification, use `aarch64-unknown-linux-gnu` or `x86_64-unknown-linux-gnu` to match the current host:

```sh
uv run --extra connect-full --with pyinstaller==6.19.0 python connect/native/prepare.py --target aarch64-unknown-linux-gnu --edition basic
npm --prefix connect/native run build -- --debug --target aarch64-unknown-linux-gnu --no-bundle -- --locked
uv run python connect/native/smoke.py --binary connect/native/src-tauri/target/aarch64-unknown-linux-gnu/debug/mdtero-connect-desktop --headless --crash-check
```

Basic resources omit bundled Node/Pi. The keyring package is still included so the bridge can use a supported native credential store when one is available. The Linux basic source CI job does not claim to produce an accepted Linux installer.

The native smoke loads the real WebKit window, downloads a fixed synthetic blob, verifies saved bytes, and removes that file. It then checks both normal exit and forced native-parent termination for bridge process/port cleanup. Its configuration, provider environment and Linux download directory are isolated. It makes no account or paid model request. Omit the target flag during a local Cargo build to use `src-tauri/target/debug/mdtero-connect-desktop` instead.

## Verification and provenance

The build-input tests exercise OS/architecture gating, stable Node version checks, Windows npm argument handling, local license preservation, credential-free smoke environments, rejected startup URLs and real disposable HTTP/process supervision:

```sh
uv run pytest tests_py/test_connect_native_prepare.py -q
```

Local Linux aarch64 basic and full preparations passed the real frozen-binary UI/session/shutdown smoke; the full check also exercised the bundled Node/Pi dependency probe. These checks establish build behavior; they do not establish macOS/Windows installation, keychain, downloads, CARSI or institutional access acceptance. See [DEBUGGING.md](DEBUGGING.md) for the human checks.

For a successful macOS/Windows bundle, run the collector with the same target and edition as preparation:

```sh
uv run python connect/native/collect_artifacts.py --target aarch64-apple-darwin --edition full
```

The collector requires a matching runtime manifest and emits a payload, source provenance, runtime manifest and `SHA256SUMS`. The runtime manifest hashes the bridge and direct runtime files, including Node notices; it deliberately excludes the dependency tree. The final payload checksum covers all shipped bytes, including npm dependencies. Checksums verify integrity against the accompanying metadata; they do not replace release signing or notarization.

Generated `.build`, `dist`, `src-tauri/binaries`, `src-tauri/resources`, npm dependencies and Cargo output are ignored. Commit the source and lockfiles, then use CI artifacts from that exact commit for reviewable provenance.
