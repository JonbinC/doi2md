# Connect verification and remaining acceptance

This is evidence for the loopback client on Draft [PR #10](https://github.com/JonbinC/doi2md/pull/10), branch `handoff/connect-research-client-20261021`. It is not a native release certificate. Backend #43 already owns library tags/import/export; these checks exercise the client against that contract without creating another library database.

## Reproduce local checks

Run from the repository root:

```sh
uv sync --frozen
uv run pytest tests_py/test_connect_security.py tests_py/test_connect_bridge.py tests_py/test_connect_zotero_local.py -q
node --check connect/app/api.js
node --check connect/app/app.js
node --test connect/design/policy.test.cjs
uv run python scripts/ci/secret_guard.py
```

Install and run Chromium browser regressions:

```sh
npm --prefix connect ci
npm --prefix connect run test:install
npm --prefix connect test
```

If Chromium is already installed, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to its executable path when running the tests. The suite starts a real loopback bridge with synthetic upstream/providers. To inspect that same fixture manually:

```sh
uv run python connect/tests/serve_fixture.py
# open http://127.0.0.1:18741 locally
```

The fixture is a test tool with synthetic documents and control state, not a production launcher. It deliberately replaces account, Relay and Zotero responses rather than using configured real credentials. The test entry points are [connect.spec.cjs](tests/connect.spec.cjs), [playwright.config.cjs](tests/playwright.config.cjs) and [serve_fixture.py](tests/serve_fixture.py).

Do not infer a passed check from a command appearing in this document; see the recorded results.

## What the checks prove

| Evidence | Coverage | Boundary |
|---|---|---|
| Python bridge/security tests | Loopback binding, HTTP request guards, CSRF and adapter payload semantics; failure handling and Zotero endpoint restrictions | Network and account responses use controlled fixtures; not production authentication |
| Browser regressions through the real local bridge | Live `connect/app` UI, onboarding truthfulness, tag draft/preview/apply behavior, export downloads and connection states | Backend responses are synthetic; no real account, publisher entitlement or desktop install is certified |
| Offline design policy tests | Prototype readiness, quota arithmetic and checkpoint policy examples | `connect/design` is mock-only with `connect-src 'none'`; no production quota or sync implementation |
| Secret guard | Repository checks for prohibited secret patterns | Does not replace runtime credential storage and release audits |
| Real account smoke (separate, requires local credentials) | Account list, tag dry-run/apply and downloaded backend exports | Must be run against an authorized account; cannot be replaced by browser fixtures |
| Native/institution acceptance (outstanding) | Installation/signing, Relay lifecycle, visible CARSI login and article evidence | Requires each supported OS and school/publisher combination |

## Real account smoke

No API key should be pasted into the UI, committed, or recorded in screenshots/test logs.

```sh
# configure the account in the terminal first; restart after configuration changes
uv run mdtero connect --no-browser --port 0 --json
```

Open the printed loopback URL and record the bridge/client version and observations without credentials:

1. Verify that a known document appears. A configured key with a failed list request must stay unverified.
2. Select a small, authorized set. Preview a temporary tag and confirm no write occurs; apply the reviewed preview and confirm the library changes. Preview removal and apply it to restore the original tags.
3. Change the draft or selection after preview and confirm applying requires a new preview.
4. Download BibTeX and CSL JSON, plus single-document Markdown and Markdown ZIP for documents with saved text. Check the downloaded file contents. Markdown exports must remain labeled text-only, without images.
5. Check Relay transport/browser diagnostics independently. A generic entitlement diagnostic must not mark the selected document or every publisher as verified.
6. With Zotero desktop open, list collections and explicitly choose one for metadata import dry-run. Connector reachability, readable collections and import preview are separate observations; do not call this checkpoint synchronization.

## Remaining work and risks

| Area | Still required |
|---|---|
| Website/Dashboard | Connect entry, startup guidance/deep links and eventual verified release manifest in Nextmdtero |
| Native runtime | Tauri shell, supervised Relay sidecar, OS credential storage, signing/notarization, installation and uninstall evidence |
| Zotero | Pagination, durable checkpoints partitioned by source/account, dedupe, deletion sync and desktop-version acceptance |
| CARSI/access | Visible local login, passwords/Cookies kept on-device, and school-by-publisher article evidence; online Relay alone is insufficient |
| Cloud storage | Backend quota enforcement, durable Markdown/private images and tested PostgreSQL backup/restore; no automatic 5 GiB migration claim |
| Optional Agent | Pi/OpenCode runtime, BYOK, approvals, budgets and constrained tools; current status remains disabled |
| Product integration | Backend MCP Reader embedding and website/client/Reader workflows |
| Release | Keep Draft; merge, website support claims and publication require explicit authorization and the relevant acceptance evidence |

The bridge currently loads CLI configuration at startup. After login/setup or key rotation, restart `mdtero connect`; a page refresh cannot reload saved credentials into an existing bridge process.

## Recorded results

| Command/check | Result | Exit code |
|---|---|---|
| `uv sync --frozen` | Completed | 0 |
| `uv run pytest tests_py/test_connect_security.py tests_py/test_connect_bridge.py tests_py/test_connect_zotero_local.py -q` | 29 passed | 0 |
| `node --check connect/app/api.js` | Syntax valid | 0 |
| `node --check connect/app/app.js` | Syntax valid | 0 |
| `node --test connect/design/policy.test.cjs` | 26 passed | 0 |
| `uv run python scripts/ci/secret_guard.py` | Passed | 0 |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/snap/bin/chromium npm --prefix connect test` | 15 passed using installed Chromium | 0 |
| `npm --prefix connect audit --audit-level=moderate` | No vulnerabilities | 0 |
| `uv build` | Built source distribution and wheel; all four packaged UI assets matched the source bytes | 0 |
| Installed wheel: `mdtero connect --help` and loopback static-asset smoke outside the checkout | Passed in a fresh Python 3.14 environment | 0 |
| `uv run pytest tests_py -q` in this three-repository workspace | 433 passed, 1 failed: existing public/site manifest mismatch | 1 |
| `python -m pytest tests_py -q` on an isolated snapshot of the current sources | 433 passed, 1 skipped (no adjacent website checkout) | 0 |

The workspace-wide failure compares `install/manifest.json` with the adjacent Nextmdtero checkout. Those checkouts declare CLI 0.3.4 and 0.3.3 respectively, with an additional account-note difference. The same test fails on the original `5af8492` sources with that website manifest. Neither manifest was changed here. The isolated run used the current source changes and a local Git index for repository-boundary tests, without copying credentials or the adjacent website. Website manifest alignment remains separate work.

The browser regressions cover skip-capable onboarding; missing/invalid credentials; failed-session refresh clearing stale state and recovery; tag drafts, preview/apply/removal and stale-preview invalidation; all four download formats including JSON MIME handling; request guards; independent Relay/Zotero status; and narrow/wide layouts without JavaScript or CSP errors. Their upstream account, Relay and Zotero data remain synthetic.

An authorized real-account browser check also passed library listing, tag preview/apply/removal with the original tags restored, and all four export formats. Markdown and ZIP retained the text-only export label. This verifies those account operations only; it does not certify native installation, complete Zotero synchronization, CARSI access, Agent execution or cloud storage durability.
