# Connect desktop debugging

The first desktop debugging targets are **macOS Apple Silicon, macOS Intel and Windows x64**. Linux keeps the existing basic loopback client. [The machine-readable matrix](support-matrix.json) describes build targets, not a website support promise or a list of accepted operating systems.

These debugging artifacts from Draft PR #10 have no verified developer signing identity and are not notarized. A green build proves that the selected toolchain produced an artifact; it does not prove installation, credential storage, downloads or native process cleanup on a person's computer. No minimum operating-system version has been accepted yet. There is no signed/notarized Connect release, automatic updater or website download manifest in this work.

## Get an artifact

Open the **Connect native debug artifacts** workflow run for the exact commit under review. Download the artifact matching the computer's CPU, verify `SHA256SUMS` against the payload, and keep its build metadata with any report. GitHub requires sign-in to download Actions artifacts. The repository currently limits artifact retention to **one day**; save a local copy for longer testing. These are not GitHub Releases.

The extracted Actions artifact contains `artifact-index.json` (commit, edition, target, source digest and payload hash), `source-checksums.json`, the packaged runtime manifest and these debugging instructions. On macOS, run `shasum -a 256 -c SHA256SUMS` from that directory. On Windows, compare `Get-FileHash -Algorithm SHA256 <payload.exe>` with the matching line in `SHA256SUMS`. These hashes check integrity within the downloaded artifact; they are not a publisher identity signature.

| Computer | Workflow runner | Rust target | Payload |
|---|---|---|---|
| Apple Silicon Mac | `macos-14` | `aarch64-apple-darwin` | `.app` inside `.tar.gz` |
| Intel Mac | `macos-15-intel` | `x86_64-apple-darwin` | `.app` inside `.tar.gz` |
| Windows x64 | `windows-2022` | `x86_64-pc-windows-msvc` | NSIS setup `.exe` |
| Linux x64 | `ubuntu-22.04` | Source verification | Basic CLI plus browser; no native artifact |

The Mac tar archive preserves executable permissions inside the application bundle. Extract it before opening the `.app`. macOS debugging bundles may use an ad-hoc signature so Apple Silicon can run their code; this does not authenticate the developer or provide notarization. Gatekeeper may refuse the build, and Windows may show an unrecognized-publisher warning. Record the exact result. Do not disable system-wide operating-system protections to make a test pass.

Windows uses the system WebView2 runtime; installation may need a network connection to obtain the runtime if it is absent. This is not an offline installer acceptance claim. Use a normal user account for the first test and record any request for elevation.

## Account and provider setup

The desktop window uses the same Python loopback bridge and account configuration as `mdtero connect`. From the native **Connect** menu, choose **登录 Mdtero 账户…** to open the system browser. The existing callback/state flow verifies the account before saving; **取消登录** closes its listener. Successful login restarts the bridge, clears session BYOK and cancels active Pi requests. End-to-end native login acceptance on macOS/Windows is still pending. Existing CLI configuration can also be reused:

```sh
uv sync --frozen
uv run mdtero setup
```

The full macOS/Windows native bundle includes Python bridge, Go Relay and the pinned Node/Pi runtime. Preparation runs the frozen bridge, requests its bundled UI/session, and checks shutdown. Collection rejects a mismatched target/edition/commit or missing runtime inputs. These checks do not run the installed application; the end-user launch test must be on a machine without development toolchains. Account authentication still uses the existing CLI account-storage contract; OS-keyring BYOK is a separate setting.

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
| Pi | In full mode preview a small selection, approve one request, then test cancellation and timeout. Confirm selection/question/model/budget edits require another preview. Record separately whether this used a synthetic server or a real provider. |
| Relay | Check process startup/diagnostics, explicit start/stop/restart behavior and process exit. Transport online does not imply a usable browser or article entitlement. |
| Lifecycle | Close all windows, reopen, kill the desktop parent unexpectedly, and restart. Inspect for orphaned bridge/Relay/Pi processes and stale listening ports. Repeated launch must not hide failures. |
| Install/uninstall | Test fresh install, upgrade and uninstall. Record whether app data and credential entries remain; do not silently delete user data to make uninstall look complete. |

Zotero needs separate real-desktop/version coverage for collection import. Pagination, stable checkpoints, dedupe and deletion synchronization remain open. CARSI needs a visible local login and school-by-publisher evidence; a browser fixture is not institutional access acceptance. Signing, notarization, supported OS minimums, automatic updates and website integration remain open.

## Linux basic client

```sh
uv sync --frozen
uv run mdtero connect --no-browser --port 0 --json
# Open the printed loopback URL in a local browser.
```

This mode covers library, tags, exports, local provider configuration and connection diagnostics without Node/Pi. Source users can opt into [full mode](../agent/README.md) when its dependencies and an OS credential service are available, but Linux native packaging is not part of the first debugging matrix.

## Report a failure

Include the acceptance-record fields, exact steps, expected/observed behavior, sanitized error text and whether restarting reproduced it. Distinguish the native window from the loopback page opened in an ordinary browser. Do not attach your configuration directory, OS credential store, full environment dump, Relay pairing token or provider request headers.

Build logs, checksums and synthetic tests stay separate from human acceptance. Keep PR #10 Draft until remaining evidence is reviewed; this workflow neither merges the PR nor publishes a release.

Runner names and architecture come from [GitHub's runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners). Packaging follows Tauri's [macOS application bundle](https://v2.tauri.app/distribute/macos-application-bundle/), [macOS signing](https://v2.tauri.app/distribute/sign/macos/), [Windows installer](https://v2.tauri.app/distribute/windows-installer/) and [external binary](https://v2.tauri.app/develop/sidecar/) documentation.
