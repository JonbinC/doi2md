# Connect verification and remaining acceptance

Evidence for the loopback client on Draft [PR #10](https://github.com/JonbinC/doi2md/pull/10), branch `handoff/connect-research-client-20261021`. Backend #43 owns library tags/import/export; the client reuses those contracts. The current work adds local BYOK, OpenAlex discovery and optional metadata-only Pi research. This is not a native release certificate.

## Reproduce local checks

Run from the repository root:

```sh
uv sync --frozen
uv run pytest tests_py/test_connect_*.py -q
node --check connect/app/api.js
node --check connect/app/app.js
node --test connect/design/policy.test.cjs
uv run python scripts/ci/secret_guard.py
```

With Node.js **22.19.0 or newer**, install the pinned Pi SDK and run its tests:

```sh
npm --prefix connect/agent ci --ignore-scripts
npm --prefix connect/agent test
```

Install/run Chromium browser regressions:

```sh
npm --prefix connect ci
npm --prefix connect run test:install
npm --prefix connect test
```

When Chromium is already installed, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to its executable path. To inspect the synthetic fixture manually:

```sh
uv run python connect/tests/serve_fixture.py
# Open http://127.0.0.1:18741 locally.
```

This fixture is not a production launcher. It uses the real loopback bridge, ProviderStore and AgentRuntime approval controls, but replaces account/Relay/Zotero, provider HTTP, Pi dependency discovery and model execution. Its provider store is isolated from real environment keys and the local OS keyring. Test entry points are [connect.spec.cjs](tests/connect.spec.cjs), [playwright.config.cjs](tests/playwright.config.cjs) and [serve_fixture.py](tests/serve_fixture.py).

Do not infer a passed check from a command appearing in this document; recorded results are below.

## What the checks prove

| Evidence | Coverage | Boundary |
|---|---|---|
| Python bridge/security tests | Loopback binding, Host/Origin/CSRF, library payload semantics, new provider/research routes and Zotero endpoint restrictions | Controlled account/network responses; not production authentication |
| Provider tests | Session/OS/environment/legacy precedence, trusted-keyring allowlist, no plaintext fallback or key echo, explicit free OpenAlex check, verification invalidation and shutdown cleanup | Fake OS backend and synthetic OpenAlex responses; not real OS-keyring or provider acceptance |
| Python Agent tests | Account-owned selection, frozen/single-use approval, basic/full separation, concurrency, secret-safe subprocess input/output, cancellation and timeout | Model execution/dependency fixtures; no paid generation |
| Pi Node tests | Actual pinned SDK lifecycle, one request/output-token cap, absent tools, ignored project resources, no auth/session files, no retry, cancellation and sanitized errors | Local synthetic HTTP model server; real provider credentials/billing are not tested |
| Browser regressions | Real live UI/bridge, onboarding, library operations, BYOK forms, discovery, approval invalidation, research output and cancellation, narrow/wide layouts | Synthetic upstream/provider/Agent responses; does not certify real full-text analysis |
| Offline design policy tests | Prototype readiness, quota arithmetic and checkpoint examples | Mock-only `connect/design`, CSP `connect-src 'none'`; no production quota/sync implementation |
| Secret guard | Repository checks for prohibited secret patterns | Does not replace runtime credential storage or release audits |
| Real account smoke | Library list, reviewed temporary-tag apply/removal and backend exports | Separate authorized account check; baseline evidence does not validate new BYOK or Pi execution |
| Native/institution acceptance | Installation/signing, Relay lifecycle, visible CARSI login and article evidence | Outstanding for each supported OS and school/publisher combination |

## Run and inspect the real client

```sh
# Configure account authentication in the terminal first if needed.
uv run mdtero setup
uv run mdtero connect --no-browser --port 0 --json
```

No account key belongs in the page, committed files, screenshots or test logs. Restart the bridge after changing terminal/saved account configuration. In the library:

1. Confirm a known document appears. Configured credentials with a failed list request must remain unverified.
2. Preview a temporary tag, confirm no write occurs, then apply the reviewed preview. Preview removal and apply it to restore original tags.
3. Change draft/selection after preview; applying must require a new preview.
4. Download BibTeX, CSL JSON, single-document Markdown and Markdown ZIP. Inspect downloaded contents; Markdown/ZIP must retain the text-only label without images.
5. Inspect Relay transport/browser diagnostics independently. Generic entitlement diagnostics cannot verify a selected document or all publishers.
6. With Zotero open, explicitly choose a collection for metadata import dry-run. Reachability, listing and preview are separate observations; this is not checkpoint synchronization.

### BYOK checks

Connections supports seven providers in four categories: OpenAlex discovery; MinerU parsing; Voyage retrieval; and OpenAI/Anthropic/Google/OpenRouter AI.

- Session keys disappear when Connect stops. Explicit OS persistence requires a trusted working OS keyring; failures cannot produce a plaintext fallback. `connect-full` adds the optional Python keyring dependency, not an OS credential service.
- Status reports configured/source/verification without key fragments or fingerprints. Saving must not make provider requests or mark a key verified. Environment and legacy OpenAlex config can reappear after clearing a session override; clearing does not erase those external sources.
- OpenAlex's explicit check uses a fixed singleton endpoint with a Bearer header, no redirects and no environment proxy. Single-entity retrieval is free according to [OpenAlex example costs](https://developers.openalex.org/access/example-costs/); [authentication documentation](https://developers.openalex.org/how-to-use-the-api/rate-limits-and-authentication) supports Bearer keys. A network/probe failure is distinct from a proven invalid key.
- MinerU/Voyage/AI checks remain configuration-only. No supported free authentication probe is implemented here; diagnostic buttons must not submit parsing, embeddings, reranking or generation. [MinerU's documented tasks](https://mineru.net/apiManage/docs) consume parsing quota; [Voyage pricing](https://docs.voyageai.com/docs/pricing) is usage-based.
- A deliberate OpenAlex search uses the existing local discovery implementation and can consume the provider's search budget. This route does not fall back to the cloud, and results are metadata, not automatically imported documents.
- MinerU/Voyage are `credential_only`: no local consumer or cloud per-user BYOK contract is added. Their saved keys do not change cloud parse/RAG credentials.

No private provider key or paid-model smoke was run for this iteration. Automated provider checks use synthetic responses.

### Optional Pi acceptance

```sh
uv sync --frozen --extra connect-full
npm --prefix connect/agent ci --ignore-scripts
uv run --extra connect-full mdtero connect --full --no-browser --port 0 --json
```

Use Node.js 22.19.0 or newer. In Connections configure an AI key locally, then select 1–10 account-library documents. Preview the question, provider, pinned-catalog model, exact selected metadata and 128–4,096 output-token limit. Review the transfer before approving. Approval is short-lived and single-use; changes require a new preview. A run permits one model request, supports cancellation and stops after 90 seconds.

The payload contains only ID, title, authors, year, venue and DOI. It does not include full text, abstracts, images, tags, unselected documents or institution credentials. Answers cannot be treated as full-text reading or validated findings. Pi has no model-callable tools, shell/filesystem access or ambient resource discovery; installed SDK/dependencies remain trusted code rather than an OS sandbox. Output tokens and request count are bounded, but a dollar-denominated financial hard cap is not implemented. Real paid-model acceptance requires deliberate separate testing; opening full mode is not evidence that a provider key works.

The implementation uses pinned `@earendil-works/pi-coding-agent@1.3.0`. Pi is the current Agent choice; no OpenCode runtime is included. See [runtime details and primary SDK sources](agent/README.md).

## Remaining work and risks

| Area | Still required |
|---|---|
| Website/Dashboard | Connect entry, startup guidance/deep links and verified release manifest in Nextmdtero |
| Native runtime | Mac/Windows debug builds and human acceptance; supported-OS Relay lifecycle, credentials, signing/notarization and installation/uninstall evidence. Tauri shell, bundled dependencies and explicit HTTP-only Relay controls now exist. |
| Zotero | Pagination, stable source/account checkpoints, dedupe, deletion sync and desktop-version acceptance |
| CARSI/access | Visible local login, passwords/Cookies kept on-device, school/publisher article evidence; online Relay is insufficient |
| MinerU/Voyage BYOK | Actual local adapters or explicit backend per-user credentials/consumption contracts; saved local keys do not change cloud jobs |
| Pi research | Full-text evidence/tools, real provider acceptance, financial hard caps, OS sandboxing and durable history; current research is metadata-only |
| Cloud storage | Backend quota enforcement, durable Markdown/private images and tested PostgreSQL backup/restore; no automatic 5 GiB migration claim |
| Product integration | Backend MCP Reader embedding and website/client/Reader workflows |
| Release | Keep Draft; merge, publication and website support claims require explicit authorization and relevant acceptance evidence |

## Native debug iteration

The native shell reuses the same loopback API and backend #43. Mac Apple Silicon, Mac Intel and Windows x64 target full debug artifacts; Linux remains basic first. See [native build instructions](native/BUILDING.md), [artifact/acceptance instructions](native/DEBUGGING.md) and [the machine-readable build matrix](native/support-matrix.json). No release, merge or website support claim is made.

| Command/check | Result | Exit code |
|---|---|---|
| `uv sync --frozen --extra connect-full` | Completed | 0 |
| `uv run --extra connect-full pytest tests_py/test_connect_*.py -q` | 258 passed, 2 Windows kernel integration tests skipped on Linux | 0 |
| `uv run --extra connect-full pytest tests_py/test_cli_contract.py -k login -q` | 14 passed | 0 |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/snap/bin/chromium npm --prefix connect test` | 33 passed, including mobile navigation and Relay permission/lifecycle UI | 0 |
| `npm --prefix connect/agent test` | 14 passed, pinned SDK with synthetic transport | 0 |
| `node --test connect/design/policy.test.cjs` | 26 passed, offline policy only | 0 |
| `node --check connect/app/api.js` and `node --check connect/app/app.js` | Passed | 0 |
| `uv run --extra connect-full --with pyinstaller==6.19.0 python connect/native/prepare.py --target aarch64-unknown-linux-gnu --edition basic` | Real frozen UI/CSP/session and shutdown smoke | 0 |
| Same preparation with `--edition full` | Also checked bundled Node 22.23.1 / Pi 1.3.0 dependencies | 0 |
| `cargo test --locked --manifest-path connect/native/src-tauri/Cargo.toml --lib` | 4 navigation, handshake and export-path policy tests | 0 |
| `npm --prefix connect/native run build -- --debug --no-bundle -- --locked` | Actual Linux aarch64 Tauri CLI build | 0 |
| Native binary `--smoke-test` under Xvfb | Real WebKit loaded loopback UI; exit released bridge port | 0 |
| `uv run python connect/native/smoke.py --binary connect/native/src-tauri/target/debug/mdtero-connect-desktop --headless --crash-check` | Real WebKit synthetic download bytes matched; normal exit and native-parent SIGKILL both stopped bridge PID/port | 0 |
| `cargo fmt --manifest-path connect/native/src-tauri/Cargo.toml -- --check` | Passed | 0 |
| `uv run --extra connect-full python scripts/ci/secret_guard.py` after adding new sources to Git index | Passed | 0 |
| `git diff --check` | Passed | 0 |
| Isolated full `python -m pytest tests_py -q` with source overlay and Git index | 658 passed, 4 skipped (adjacent website absent; two Windows kernel tests; ignored native Go binary absent) | 0 |

The isolated full-suite snapshot preceded the final three directory-lock retry tests. Those were included in the final focused Connect suite above; the bundled Go probe ran locally with prepared resources. The pre-existing adjacent-site manifest mismatch remains as recorded below; no install manifest was changed.

These are Linux build and synthetic-service results. No current real paid AI, MinerU or Voyage request was made. They do not establish Mac/Windows installation, OS credential prompts, real account browser login, Zotero/CARSI depth or signed distribution. The native workflow must produce artifacts for the exact reviewed commit; every platform's human acceptance remains pending.

The first Mac ARM job on `280a3933` produced a full `.app` artifact. Windows exposed a test-only file-URL/path conversion error, fixed with `fileURLToPath`. Mac Intel exposed HTTP-listener startup timeouts. The shared loopback listener now skips stdlib reverse DNS, with fault-injection tests proving both bridge and OAuth callback start with DNS unavailable. Final per-platform rebuild results must be checked separately; the first ARM artifact does not certify a later commit. Artifact retention is limited to one day by the repository.

The next client slice adds explicit HTTP-only Relay supervision (28 runtime tests) and frozen Windows external-process DLL-path handling (9 tests). Relay starts only after current-page permission and an explicit cloud-offline precheck. Its temporary browser-off policy contains no account key; only the owned Go child receives account credentials in its environment. The precheck is not an atomic lease across computers. Browser reload restores owned-process state without restoring permission. No real cloud Relay was started for these tests.

Authorized real-account checks through the live bridge passed document listing, tags, explicit tag dry-run and nonempty BibTeX/CSL/Markdown/ZIP responses. The Markdown formats retained `markdown-text-only`. No tags were applied or removed in this check, no Relay was started, and no provider/model request was made. This HTTP evidence does not replace native WebView download or account-login acceptance.

Windows `f0d617b3` passed Python/Pi source tests but its frozen dependency probe failed. Rebuilds now sanitize the external-program DLL search path following [PyInstaller's Windows guidance](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#launching-external-programs-from-the-frozen-application), emit only allowlisted dependency failure codes and wait for all Windows Job descendants before deleting temporary files. The prior failure's root cause remains unconfirmed until the frozen Windows rebuild succeeds.

Windows `05abe13d` caught a transient directory-lock failure in the diagnostic test before freezing. Cleanup now retries briefly after confirmed process exit and preserves the safe original phase if deletion still fails. Focused preparation checks: `uv run --extra connect-full pytest tests_py/test_connect_native_prepare.py -q` — 45 passed, 1 Windows-only skip, exit 0. The latest local full frozen preparation and actual WebKit download/parent-crash smoke both passed again, exit 0.

The repository Extension CI also encountered newly published Vitest advisories. Its test dependencies were patched from 4.1.11 to 4.1.12 without changing extension runtime sources. `npm --prefix extension audit --audit-level=moderate`, extension tests (210 passed) and build all exited 0.

## Previous BYOK/Pi iteration: 77bd331

| Command/check | Result | Exit code |
|---|---|---|
| `uv run pytest tests_py/test_connect_providers.py -q` | 62 passed | 0 |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/snap/bin/chromium npm --prefix connect test` | 27 passed; original flows plus BYOK/discovery/Pi and reload recovery | 0 |
| `node --check connect/tests/connect.spec.cjs` | Syntax valid | 0 |
| `uv run python -m py_compile connect/tests/serve_fixture.py` | Syntax valid | 0 |
| `uv run python -m compileall -q src/mdtero/connect/providers.py` | Syntax valid | 0 |
| `uv run python scripts/ci/secret_guard.py` | Passed | 0 |
| `git diff --check` | Passed | 0 |

Additional checks on the current sources:

| Command/check | Result | Exit code |
|---|---|---|
| `uv sync --frozen --extra connect-full` | Completed | 0 |
| `uv run pytest tests_py/test_connect_*.py -q` | 119 passed | 0 |
| `npm --prefix connect/agent test` | 14 passed with real pinned Pi SDK and synthetic HTTP model transport | 0 |
| `node --test connect/design/policy.test.cjs` | 26 passed; offline policy only | 0 |
| App JS and Pi worker `node --check` | Syntax valid | 0 |
| `npm --prefix connect/agent audit --audit-level=moderate` | No vulnerabilities | 0 |
| `python -m pytest tests_py -q` on an isolated current-source snapshot with a Git index | 523 passed, 1 skipped without adjacent website checkout | 0 |
| `uv build` and packaged-asset comparison | UI plus five Pi runtime files match source; SDK dependencies/tests excluded from wheel | 0 |
| Installed wheel outside checkout: full-mode loopback, SDK catalog and credential-free status | SDK 1.3.0 detected; correctly not ready without AI key | 0 |

Current BYOK/Pi acceptance uses synthetic credentials and model/provider transport. No real paid model, MinerU parsing, or Voyage embedding/rerank request was made. OS credential behavior is covered with controlled backends; supported-OS interactive acceptance is still outstanding. Historical results below do not replace these current checks.

## Previous baseline: a1d6104

These results were recorded for `a1d6104033808df0d9fba26433e2651afe322f05`, before BYOK/Pi work:

| Command/check | Result | Exit code |
|---|---|---|
| `uv sync --frozen` | Completed | 0 |
| `uv run pytest tests_py/test_connect_security.py tests_py/test_connect_bridge.py tests_py/test_connect_zotero_local.py -q` | 29 passed | 0 |
| `node --check connect/app/api.js` and `node --check connect/app/app.js` | Syntax valid | 0 |
| `node --test connect/design/policy.test.cjs` | 26 passed | 0 |
| `uv run python scripts/ci/secret_guard.py` | Passed | 0 |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/snap/bin/chromium npm --prefix connect test` | 15 passed | 0 |
| `npm --prefix connect audit --audit-level=moderate` | No vulnerabilities | 0 |
| `uv build` | Built sdist/wheel; four packaged UI assets matched source | 0 |
| Installed-wheel CLI help/static-asset smoke outside checkout | Passed in a fresh Python 3.14 environment | 0 |
| `uv run pytest tests_py -q` in this three-repository workspace | 433 passed, 1 existing public/site manifest failure | 1 |
| `python -m pytest tests_py -q` on an isolated source snapshot | 433 passed, 1 skipped without adjacent website | 0 |

The baseline workspace failure compares this repository's CLI 0.3.4 install manifest with the adjacent Nextmdtero checkout's 0.3.3 manifest and an account-note difference. It also failed on original `5af8492` sources. Neither manifest was changed by that work; website alignment remains separate.

The baseline authorized real-account smoke passed listing, tag preview/apply/removal with original tags restored, and four export formats retaining text-only labels. It does not certify current BYOK/provider execution, Pi, native installation, complete Zotero synchronization, CARSI or cloud storage durability.
