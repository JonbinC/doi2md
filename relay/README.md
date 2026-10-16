# mdtero-relay

Standalone campus-network relay for Mdtero. Install this on a school/office machine so cloud agents can fetch publisher URLs through your campus IP.

## Choose your setup

| Your setup | What to install | What it covers |
| --- | --- | --- |
| Campus desktop | Mdtero CLI (Relay is prepared automatically) | Campus HTTP and an isolated authorized browser profile are available to cloud Agents. The extension remains a lightweight current-tab fallback. |
| Server only | Mdtero CLI/API key | OA, publisher APIs, normal HTTP, and uploads. There is no browser session on the server. |
| Server plus campus desktop | CLI on the server, Relay on the campus computer | Recommended for user-authorized closed or bot-protected publisher content. The Agent stays in the cloud; the desktop performs acquisition. |
| Server plus campus lightweight board (ARMv7/ARM64, no display) | `mdtero-relay` with `--local-browser headless` on the campus board | Campus HTTP plus optional headless Chromium for IP-authorized / open pages. Interactive institution login still needs a desktop browser or the extension. |
| Server plus campus VPN | CLI/API key and VPN/proxy | IP-authorized machine-readable sources. A VPN alone does not supply browser cookies or a user login. |

For the third setup, install Relay on the computer that already has the
institutional browser access. It connects outward to Mdtero, so the server
does not need an inbound port, public IP, or SSH tunnel. The cloud Agent sends
an approved article request; Relay returns only a verified PDF or sanitized
static article HTML for parsing.

## Authorized local browser

If the same user has lawful institutional access in a local browser but a
publisher challenges automated requests, Relay uses a separate
`Mdtero Access` Chrome profile. This is a **user-bound article capture**, not a
browser proxy: it accepts only `article_html`, `article_pdf`, and
`article_fulltext` for approved
publisher domains and returns no cookies, credentials, browser storage, or
screenshots. It cannot grant access that the local user does not already have.

The native Relay always provides campus-network HTTP fetch. On a supported
desktop install, the CLI packages and starts the browser worker automatically
(using an installed Chrome/Edge or a managed Playwright Chromium). Browser
capture is advertised to the backend as `browser_fetch` / `browser_fulltext`.
`mdtero-relay status` reports whether the worker is configured and reachable
without showing its token, profile path, or CDP endpoint.

Ordinary headless API servers still skip the worker by default. Campus boards
without a display can opt in with `--local-browser headless` so Relay starts a
loopback Chromium worker. That mode covers IP-authorized and open pages; it
cannot invent an institution login or pass a visible challenge. Official
release artifacts include `linux-armv7` (GOARM=7). Playwright does not ship an
ARMv7 browser, so those boards need a system Chromium package such as
`chromium` / `chromium-browser`.

When a publisher needs a manual institution login or browser challenge, open
the article URL locally with `mdtero-relay browser-open <publisher-url>`,
complete that step in the visible **Mdtero Access** profile, then retry the
task. `article_fulltext` prefers a verified publisher PDF and otherwise returns
sanitized static article HTML. The browser session remains local and is reused
by later eligible tasks. The extension remains available when a user wants to
capture the page already open in their ordinary browser.

## One-line install

**macOS / Linux**

```bash
curl -fsSL https://mdtero.com/relay | bash
```

With API key:

```bash
curl -fsSL https://mdtero.com/relay | bash -s -- --api-key mdt_xxx
```

Campus ARMv7 / headless board with Chromium:

```bash
sudo apt-get install -y chromium   # or chromium-browser
curl -fsSL https://mdtero.com/relay | bash -s -- --api-key mdt_xxx --local-browser headless
```

**Windows (PowerShell)**

```powershell
irm https://mdtero.com/relay.ps1 | iex
```

With API key:

```powershell
$env:MDTERO_API_KEY="mdt_xxx"; irm https://mdtero.com/relay.ps1 | iex
```

The installer will:

1. Download a native `mdtero-relay` binary
2. Open the Mdtero sign-in page when no API key was supplied, or save the key
   provided by an automated install
3. Register a background service (launchd on macOS, systemd user service on Linux, login task on Windows)
4. Start relaying automatically on login

For a normal campus computer, use the no-key command and finish the browser
sign-in. Linux desktops and servers use a per-user systemd service when
available; on minimal images without systemd, keep `mdtero-relay serve` under
the host's process supervisor. For a headless install, pass `--api-key` from a secret manager or run
`mdtero-relay login --browser=false` interactively; do not put the key in a
shell history or a checked-in script. Add `--local-browser headless` only when
the campus board should also run the Chromium capture worker.

## Commands

```bash
mdtero-relay install [--api-key <key>] [--browser=false] [--local-browser auto|headless|off] [--label <name>]
mdtero-relay serve [--label <name>]
mdtero-relay status [--json]
mdtero-relay login [--browser] [--api-key <key>]
mdtero-relay browser-open <publisher-url>
mdtero-relay uninstall
mdtero-relay version
```

`mdtero-relay login` opens the same Mdtero web OAuth flow as the CLI. After you sign in on mdtero.com, a dedicated **Campus Relay** API key is issued to this machine automatically.

## How it works

```text
Campus machine (mdtero-relay)
  ├─ POST /api/v1/relay/ticket ─► api.mdtero.com (API key stays at origin)
  └─ WebSocket ─► returned Cloudflare Worker `ws_url` + short-lived ticket
Cloud agent / backend
  └─ POST /api/v1/relay/fetch { "url": "https://doi.org/..." }
       └─ forwarded to campus machine ─► publisher site
```

## Release

GitHub Actions workflow: `.github/workflows/release-relay.yml`

```bash
# Tag-driven release. Pushing relay/v* runs Release Campus Relay.
git tag relay/v0.1.8
git push origin relay/v0.1.8

# Manual release
# GitHub: run "Release Campus Relay" with the desired version
```

Relay binaries are published through GitHub Releases (`relay/v*`). Do not commit
`relay/dist/` archives into this repository.

Optional local copy into a website static-assets tree:

```bash
cd relay
bash scripts/build-release.sh
MDTERO_SITE_ROOT=/path/to/website-repo bash scripts/publish-site-assets.sh 0.1.8
```

## Build from source

```bash
cd relay
go mod tidy
go build -o mdtero-relay ./cmd/mdtero-relay
./mdtero-relay install --api-key mdt_xxx
```

Cross-compile examples:

```bash
GOOS=darwin GOARCH=arm64 go build -o dist/mdtero-relay-darwin-arm64 ./cmd/mdtero-relay
GOOS=darwin GOARCH=amd64 go build -o dist/mdtero-relay-darwin-amd64 ./cmd/mdtero-relay
GOOS=linux GOARCH=arm GOARM=7 go build -o dist/mdtero-relay-linux-armv7 ./cmd/mdtero-relay
GOOS=windows GOARCH=amd64 go build -o dist/mdtero-relay-windows-amd64.exe ./cmd/mdtero-relay
```

## Relation to `mdtero relay serve`

The Python CLI still includes `mdtero relay serve` for developers and existing users. **`mdtero-relay` is the recommended install for campus machines** — smaller, native, and auto-starts as a service.

Both clients speak the same backend protocol. The Python CLI and native Relay
prefer the ticket/Worker path and fall back to the origin WebSocket only when
the gateway is unavailable.

## Configuration

Config file:

- macOS/Linux: `~/.config/mdtero-relay/config.json`
- Windows: `%APPDATA%\mdtero-relay\config.json`

Environment overrides:

- `MDTERO_API_KEY`
- `MDTERO_API_URL` (default `https://api.mdtero.com`)

## Logs

- macOS: `~/Library/Logs/mdtero-relay.log`
- Linux: `${XDG_STATE_HOME:-~/.local/state}/mdtero-relay/relay.log`
- Windows: `%LOCALAPPDATA%\mdtero-relay\relay.log`
