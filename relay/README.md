# mdtero-relay

Standalone campus-network relay for Mdtero. Install this on a school/office machine so cloud agents can fetch publisher URLs through your campus IP.

## Optional: authorized local browser

If the same user has lawful institutional access in a local browser but a
publisher challenges automated requests, Relay can optionally use a separate
`Mdtero Access` Chrome profile. This is a **user-bound article capture**, not a
browser proxy: it accepts only `article_html` and `article_pdf` for approved
publisher domains and returns no cookies, credentials, browser storage, or
screenshots. It cannot grant access that the local user does not already have.

See [`browser_worker/README.md`](browser_worker/README.md). The local worker is
advertised to the backend as `browser_fetch`; it can only be scheduled by that
same Mdtero account's tasks.

When a publisher needs a manual institution login or browser challenge, open
the article URL locally with `mdtero-relay browser-open <publisher-url>`,
complete that step in the visible **Mdtero Access** profile, then retry the
task. The browser session remains local and is reused by later eligible tasks.

## One-line install

**macOS / Linux**

```bash
curl -fsSL https://mdtero.com/relay | bash
```

With API key:

```bash
curl -fsSL https://mdtero.com/relay | bash -s -- --api-key mdt_xxx
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
2. Save your API key (if provided)
3. Register a background service (launchd on macOS, login task on Windows)
4. Start relaying automatically on login

## Commands

```bash
mdtero-relay install [--api-key <key>] [--label <name>]
mdtero-relay serve [--label <name>]
mdtero-relay status
mdtero-relay login [--browser] [--api-key <key>]
mdtero-relay browser-open <publisher-url>
mdtero-relay uninstall
mdtero-relay version
```

`mdtero-relay login` opens the same Mdtero web OAuth flow as the CLI. After you sign in on mdtero.com, a dedicated **Campus Relay** API key is issued to this machine automatically.

## How it works

```text
Campus machine (mdtero-relay)
  └─ WebSocket ─► api.mdtero.com/api/v1/relay/ws
Cloud agent / backend
  └─ POST /api/v1/relay/fetch { "url": "https://doi.org/..." }
       └─ forwarded to campus machine ─► publisher site
```

## Release

Forgejo/GitHub workflow: `public/.forgejo/workflows/release-relay.yml`

```bash
# Tag-driven release
git tag relay/v0.1.0
git push origin relay/v0.1.0

# Manual release
# Forgejo: run "Release Campus Relay" with version 0.1.0
```

Local publish to nextmdtero static assets:

```bash
cd public/relay
bash scripts/build-release.sh
MDTERO_SITE_ROOT=/path/to/nextmdtero bash scripts/publish-site-assets.sh 0.1.0
```

Required Forgejo secrets/vars for automatic site publish:

- `NEXTMDTERO_REPO_TOKEN` — push access to site repo
- `NEXTMDTERO_REPO` — e.g. `mdtero/nextmdtero`
- optional `FORGEJO_TOKEN` — attach binaries to Forgejo release

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
GOOS=windows GOARCH=amd64 go build -o dist/mdtero-relay-windows-amd64.exe ./cmd/mdtero-relay
```

## Relation to `mdtero relay serve`

The Python CLI still includes `mdtero relay serve` for developers and existing users. **`mdtero-relay` is the recommended install for campus machines** — smaller, native, and auto-starts as a service.

Both clients speak the same backend protocol.

## Configuration

Config file:

- macOS/Linux: `~/.config/mdtero-relay/config.json`
- Windows: `%APPDATA%\mdtero-relay\config.json`

Environment overrides:

- `MDTERO_API_KEY`
- `MDTERO_API_URL` (default `https://api.mdtero.com`)

## Logs

- macOS: `~/Library/Logs/mdtero-relay.log`
- Windows: `%LOCALAPPDATA%\mdtero-relay\relay.log`
