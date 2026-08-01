# Authorized Browser Worker

This optional, loopback-only sidecar adds two narrowly scoped capabilities to
`mdtero-relay`: capture an authenticated publisher article as HTML, or download
its publisher PDF after the user has authorized access in the dedicated
`Mdtero Access` browser profile.

It is not a general browser proxy. The Relay only accepts the `article_html`
and `article_pdf` recipes, both are publisher-domain allowlisted, and the
worker never returns browser cookies or profile data.

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

The first headed launch creates the `Mdtero Access` Chrome profile. The user
must complete institutional login and any publisher challenge themselves in
that profile. The worker returns `browser_login_required` or
`browser_challenge_required` when that has not happened.

The worker is intentionally single-concurrency so two paper tasks cannot mix
browser state. Artifacts are capped at 30 MiB in this first transport version;
larger assets need a future object-storage handoff rather than a larger Relay
message.
