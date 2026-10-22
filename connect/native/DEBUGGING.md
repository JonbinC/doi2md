# Connect desktop preview debugging

The public preview targets are **macOS Apple Silicon, macOS Intel and Windows x64**. Linux keeps the basic CLI/browser client and has no native installer. [The machine-readable matrix](support-matrix.json) describes available preview builds; OS acceptance remains a separate status.

These unsigned debugging artifacts are published as **Connect v0.1.0-preview.1**. macOS bundles use an ad-hoc signature, not a verified developer identity or notarization; Windows installers have no Authenticode signature. A successful build and archive audit verify the artifact and its checksums. They do not prove installation, credential storage, downloads, account login or process cleanup on a person's computer. No minimum operating-system version has been accepted. There is no automatic updater.

## Get an artifact

Download the platform payloads from the durable [Connect v0.1.0 preview release](https://github.com/JonbinC/doi2md/releases/tag/connect-v0.1.0-preview.1). Verify `SHA256SUMS` before opening the payload and keep its build metadata with any report. The binaries were built from source commit `bf7d719836bc9da6dccd0a77c1cf6a632b347626`; the original Actions artifacts are short-lived. The release includes checksums and build provenance for the Apple Silicon DMG, plus artifact indexes for the Actions-built payloads.

The extracted Actions artifact contains `artifact-index.json` (commit, edition, target, source digest and payload hash), `source-checksums.json`, the packaged runtime manifest and these debugging instructions. On macOS, run `shasum -a 256 -c SHA256SUMS` from that directory. On Windows, compare `Get-FileHash -Algorithm SHA256 <payload.exe>` with the matching line in `SHA256SUMS`. These hashes check integrity within the downloaded artifact; they are not a publisher identity signature.

| Computer | Build host | Rust target | Payload |
|---|---|---|---|
| Apple Silicon Mac | Mac mini · macOS 27.0.1 | `aarch64-apple-darwin` | [DMG installer](https://github.com/JonbinC/doi2md/releases/download/connect-v0.1.0-preview.1/mdtero-connect-debug-aarch64-apple-darwin.dmg) · [previous `.app` archive](https://github.com/JonbinC/doi2md/releases/download/connect-v0.1.0-preview.1/mdtero-connect-debug-aarch64-apple-darwin.tar.gz) |
| Intel Mac | `macos-15-intel` | `x86_64-apple-darwin` | [`.app` inside `.tar.gz`](https://github.com/JonbinC/doi2md/releases/download/connect-v0.1.0-preview.1/mdtero-connect-debug-x86_64-apple-darwin.tar.gz) |
| Windows x64 | `windows-2022` | `x86_64-pc-windows-msvc` | [NSIS setup `.exe`](https://github.com/JonbinC/doi2md/releases/download/connect-v0.1.0-preview.1/mdtero-connect-debug-x86_64-pc-windows-msvc-setup.exe) |
| Linux x64 | `ubuntu-22.04` | Source verification | Basic CLI plus browser; no native artifact |

### Recorded artifact status

Checked on **2026-10-22 UTC**. The Apple Silicon DMG was built on a Mac mini from source commit `bf7d719836bc9da6dccd0a77c1cf6a632b347626`; `hdiutil verify`, app code-signature verification and the bundled-runtime smoke passed. The Intel Mac and Windows assets came from successful full-bundle jobs in [Actions run 39720709023](https://github.com/JonbinC/doi2md/actions/runs/39720709023). Real-machine account, credential, download and lifecycle acceptance remains pending.

| Target / source | Recorded result | Debug artifact |
|---|---|---|
| Apple Silicon DMG, `bf7d7198` | Mac mini, macOS 27.0.1 / Xcode 26.6; DMG and ad-hoc app signature verified; notarization not performed; human acceptance pending | [DMG installer](https://github.com/JonbinC/doi2md/releases/download/connect-v0.1.0-preview.1/mdtero-connect-debug-aarch64-apple-darwin.dmg) · [Build provenance](https://github.com/JonbinC/doi2md/releases/download/connect-v0.1.0-preview.1/mdtero-connect-debug-aarch64-apple-darwin.provenance.json) · SHA256 `a6b0bab4ca6425e671be8bdb5157456d542ecf64ca196082cd303825a99cff64` |
| Apple Silicon, `bf7d7198` | Full build and static archive audit passed; ad-hoc signature only | [Preview payload](https://github.com/JonbinC/doi2md/releases/download/connect-v0.1.0-preview.1/mdtero-connect-debug-aarch64-apple-darwin.tar.gz) · SHA256 `3e904b8fd9e3fd24871699286408d38b7acc000a5872378e690102102adec80e` |
| Intel Mac, `bf7d7198` | Full build and static archive audit passed; ad-hoc signature only | [Preview payload](https://github.com/JonbinC/doi2md/releases/download/connect-v0.1.0-preview.1/mdtero-connect-debug-x86_64-apple-darwin.tar.gz) · SHA256 `fef599b0a12fe6ba51d65c956e0db23dc4ce98086ce2faf9d69c7dab7a94b8c2` |
| Windows x64, `bf7d7198` | Full build and static archive audit passed; unsigned installer | [Preview payload](https://github.com/JonbinC/doi2md/releases/download/connect-v0.1.0-preview.1/mdtero-connect-debug-x86_64-pc-windows-msvc-setup.exe) · SHA256 `a68c26aa98a6d4b80c7676d1e85913103c94ce4753804e0e07b443fe94bdebde` |

The Mac DMG contains a `.app` signed ad hoc so Apple Silicon can run its code; it does not authenticate the developer or provide notarization. The previous Mac tar archive preserves executable permissions inside the app bundle and must be extracted before opening. Gatekeeper may refuse either build, and Windows may show an unrecognized-publisher warning. Record the exact result. Do not disable system-wide operating-system protections to make a test pass.

Windows uses the system WebView2 runtime; installation may need a network connection to obtain the runtime if it is absent. This is not an offline installer acceptance claim. Use a normal user account for the first test and record any request for elevation.

## Account and provider setup

The desktop window uses the same Python loopback bridge and account configuration as `mdtero connect`. From the native **Connect** menu, choose **登录 Mdtero 账户…** to open the system browser. The existing callback/state flow verifies the account before saving; **取消登录** closes its listener. Successful login restarts the bridge, clears session BYOK and cancels active Pi requests. End-to-end native login acceptance on macOS/Windows is still pending. Existing CLI configuration can also be reused:

```sh
uv sync --frozen
uv run mdtero setup
```

The full native build configuration bundles the Python bridge, Go Relay and pinned Node/Pi runtime. Preparation runs the frozen bridge, requests its bundled UI/session, and checks shutdown before collection. Collection rejects a mismatched target/edition/commit or missing runtime inputs. A Windows build must first pass those checks before its installer can be offered for debugging. These checks do not run the installed application; the end-user launch test must be on a machine without development toolchains. Account authentication still uses the existing CLI account-storage contract; OS-keyring BYOK is a separate setting.

Exports are saved under **Downloads / Mdtero Connect** with a unique prefix. Use **Connect → 打开导出文件夹** to find them.

In Connections, explicitly allow this computer to carry the account's document HTTP requests before starting or restarting its bundled Relay. Stop remains available after a page reload; permission is not saved in the browser. Closing Connect stops only its owned child. An existing online Relay or unavailable cloud status blocks startup. This precheck has a race if two computers start simultaneously; it is not an atomic server lease. The institution browser remains disabled, existing services are not controlled, and no service is installed. A running process is shown separately from cloud transport and full-text entitlement.

BYOK belongs to the local client: OpenAlex for discovery, MinerU for parsing, Voyage for retrieval, and a separate AI provider for Pi. Keys default to session memory. Explicit persistence requires a supported, working OS credential service; failure must remain visible and cannot create a plaintext fallback. MinerU and Voyage currently store credentials only. Pi handles approved metadata-only questions and has no model-callable shell or filesystem tools. It has not read paper full text. Real model calls require a provider key and may incur provider usage.

Do not put account/provider keys, institution passwords or Cookies in screenshots, logs or issue text. Diagnostic status should report availability and source without key fragments. Report an unexpected secret exposure privately and remove it from any artifact before sharing.

## Per-computer acceptance record

For each target, record the commit, artifact checksum, OS version, CPU architecture, WebView version, test date and which tests below passed or failed. Keep account identity and keys out of the record. All rows are initially **pending**; automation and browser fixtures do not fill this record.

| Area | Procedure and expected evidence |
|---|---|
| Launch | Open from an extracted/downloaded artifact under a standard user. Record startup, missing-runtime and OS trust prompts. Confirm no Python, Node or Go installation is needed for the native process. |
| Account login | Start the native system-browser login, complete the account callback, confirm local verification and library access. Exercise cancellation, timeout, browser-launch failure and close/reopen. This remains pending until exercised in a real native build. |
| Library | Verify the account, load the real document list, filter tags, preview an explicit `dry_run: true`, apply the reviewed change and restore the test tag. |
| Downloads | Export BibTeX, CSL JSON, Markdown and Markdown ZIP. Check saved filenames and bytes from the WebView; Markdown stays text-only. An HTTP response alone does not prove a native download works. |
| Provider credentials | Use session storage, close/reopen and confirm removal. Explicitly save to the OS store, restart, load, remove and restart again. Exercise locked and unavailable stores without plaintext fallback. |
| Pi | In full mode preview a small selection, approve one request, then test cancellation, timeout and reload recovery. Confirm selection/question/model/budget edits require another preview. Missing model credentials should lead to Settings; missing dependencies should show their own readiness reason. Record separately whether this used a synthetic server or a real provider. |
| Relay | Confirm initial permission is unchecked and page load does not start a process. Explicitly permit/start, uncheck and confirm restart is disabled, then permit/restart. Reload: recover the owned running process with permission unchecked; stop must still work. Check external-online and unavailable-cloud startup rejection. Inspect owned-process exit separately from cloud transport and article entitlement. |
| Lifecycle | Close all windows, reopen, kill the desktop parent unexpectedly, and restart. Inspect for orphaned bridge/Relay/Pi processes and stale listening ports. Repeated launch must not hide failures. |
| Install/uninstall | Test fresh install, upgrade and uninstall. Record whether app data and credential entries remain; do not silently delete user data to make uninstall look complete. |

Zotero needs separate real-desktop/version coverage for collection import. Pagination, stable checkpoints, dedupe and deletion synchronization remain open. CARSI needs a visible local login and school-by-publisher evidence; a browser fixture is not institutional access acceptance. Developer identity signing, notarization, supported OS minimums and automatic updates remain open.

## Linux basic client

```sh
uv sync --frozen
uv run mdtero connect --no-browser --port 0 --json
# Open the printed loopback URL in a local browser.
```

This mode covers library, tags, exports, local provider configuration and connection diagnostics without Node/Pi. Source users can opt into [full mode](../agent/README.md) when its dependencies and an OS credential service are available, but Linux native packaging is not part of the first debugging matrix.

## Report a failure

Include the acceptance-record fields, exact steps, expected/observed behavior, sanitized error text and whether restarting reproduced it. Distinguish the native window from the loopback page opened in an ordinary browser. Do not attach your configuration directory, OS credential store, full environment dump, Relay pairing token or provider request headers.

| Observation | Useful evidence / next check |
|---|---|
| Managed Relay unavailable | Confirm this is a native bundle with its trusted runtime resources. Plain CLI mode offers diagnostics; the page cannot choose another executable or install a service. |
| Relay startup blocked | Record the safe reason code and independent transport diagnostic. An external online Relay or unknown cloud state blocks startup; do not kill unrelated processes. |
| Pi not ready | Record `reason_code`, dependency availability, supported Node/SDK versions and any allowlisted probe stage/code/integer exit. A missing provider key and a missing SDK require different fixes; do not attach raw subprocess output or environment. |
| Build failed before an artifact exists | Record the failing job step. Source-test failure, frozen dependency failure, app build failure and artifact-upload timeout are different outcomes. An older artifact keeps its own commit identity. |
| Export response succeeded but no file appears | Check `Downloads/Mdtero Connect` through the native menu and record the actual WebView result. HTTP bytes alone do not establish a native download. |

Build logs, checksums and synthetic tests stay separate from per-computer acceptance. Report any install warning or failure with the asset's commit and checksum; do not attach account/provider secrets or an environment dump.

Runner names and architecture come from [GitHub's runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners). Packaging follows Tauri's [macOS application bundle](https://v2.tauri.app/distribute/macos-application-bundle/), [macOS signing](https://v2.tauri.app/distribute/sign/macos/), [Windows installer](https://v2.tauri.app/distribute/windows-installer/) and [external binary](https://v2.tauri.app/develop/sidecar/) documentation.
