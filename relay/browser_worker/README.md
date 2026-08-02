# Authorized Browser Worker

This optional, loopback-only sidecar captures an authorized publisher article
for `mdtero-relay`: it prefers the publisher PDF after the user has authorized
access in the dedicated `Mdtero Access` browser profile, otherwise it can return
sanitized static HTML only for a complete readable article.

It is not a general browser proxy. The Relay only accepts the
publisher-domain-allowlisted `article_html`, `article_pdf`, and
`article_fulltext` recipes, and the worker never returns browser cookies or
profile data. `article_fulltext` is preferred: it returns a verified publisher
PDF when possible, otherwise static article HTML after a full-text guard. It
does not return short errors, HTTP 4xx/5xx pages, or rate-limit pages as HTML.

`article_html` is a static parse fallback for a readable article that has no
usable PDF endpoint. Before it leaves the computer, the worker removes scripts,
forms, frames, event handlers, session-like DOM attributes, and URL
query/fragment values. It is not a page mirror and cannot be used to replay a
browser session elsewhere.

This is the browser-enabled part of the **server plus campus desktop** setup.
Most desktop users should start with the browser extension instead. Enable
this worker when the Agent runs on a separate server and needs the campus
computer to acquire a publisher artifact on its behalf.

Run it only on a machine controlled by the authorized user. The normal
background configuration is an owner-readable file at
`~/.config/mdtero-relay/browser-worker.json`:

```json
{"worker_url":"http://127.0.0.1:8788","token":"a-random-local-token"}
```

Use mode `600` for this file. Relay and this worker read it locally; the token
is not sent to Mdtero's backend. Environment variables remain available for
one-off development runs:

```bash
export MDTERO_BROWSER_WORKER_URL=http://127.0.0.1:8788
export MDTERO_BROWSER_WORKER_TOKEN=<same-random-token>
python3 mdtero_browser_worker.py
```

For a local checkout, install the sidecar once with:

```bash
cd relay/browser_worker
python3 -m venv ~/.local/share/mdtero-relay/browser-venv
~/.local/share/mdtero-relay/browser-venv/bin/pip install -r requirements.txt
~/.local/share/mdtero-relay/browser-venv/bin/playwright install chromium
```

Then start `mdtero_browser_worker.py` under the desktop's launch agent,
systemd user unit, or server process supervisor. Keep the worker bound to
`127.0.0.1`; the native Relay is the only process that should call it.

After starting the worker, verify the local side without revealing its local
configuration:

```bash
mdtero-relay status --json
```

The output contains `local_browser.configured`, `reachable`, and
`session_active`. The account-level `browser` object in the same response only
describes the capabilities advertised to Mdtero; neither object contains a
token, cookie, CDP URL, or profile path.

The first headed launch creates the `Mdtero Access` Chrome profile. The user
controls that dedicated visible profile; when configured for loopback CDP the
worker attaches to it without closing Chrome. A user can complete institutional
login or a publisher challenge once and a later article task can reuse the
resulting lawful session. It returns
`browser_login_required` or `browser_challenge_required` when that has not
happened, and returns a specific unavailable/rate-limit result rather than
parsing a publisher error page as an article.

On Linux, the worker automatically uses an installed Chrome/Chromium binary
when one is available. With no `DISPLAY` or `WAYLAND_DISPLAY` it defaults to
headless mode, which is suitable for open-access pages and non-interactive
server workers; set `MDTERO_BROWSER_HEADLESS=false` when a desktop user needs
to see and complete a login or challenge. If no system browser is installed,
install Playwright's managed Chromium with `playwright install chromium` or set
`MDTERO_BROWSER_EXECUTABLE` explicitly.

Never point it at a regular Chrome profile. The worker can either launch the
dedicated profile itself or attach through a loopback-only CDP endpoint to the
same user-controlled profile; neither mode exports profile data or closes the
user's visible Chrome when attached.

To deliberately open an approved publisher page in the visible dedicated
profile before retrying a task, use the Relay locally:

```bash
mdtero-relay browser-open https://publisher.example/article
```

This action is local-only and returns no cookies, storage, screenshots, or
page content to the Relay or backend. Use it only to complete your own login
or challenge; subsequent task capture remains limited to the fixed article
recipes.

The worker is intentionally single-concurrency so two paper tasks cannot mix
browser state. Artifacts are capped at 30 MiB in this first transport version;
larger assets need a future object-storage handoff rather than a larger Relay
message.
