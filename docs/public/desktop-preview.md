# Desktop Preview

Mdtero Desktop is currently published as a public preview installer set.

That means:

- the build is generated from `JonbinC/mdtero/apps/desktop`
- the public repo mirrors preview-facing docs and optional release assets
- the public repo also mirrors the upstream installer ledger at `desktop/releases/installer-manifest.json`
- preview version `0.1.0-preview.1` currently publishes `Mdtero-0.1.0-preview.1-mac-universal.dmg` and `Mdtero-0.1.0-preview.1-win-x64.exe`
- those user-facing installers live at `desktop/releases/Mdtero-0.1.0-preview.1-mac-universal.dmg` and `desktop/releases/Mdtero-0.1.0-preview.1-win-x64.exe`
- signing, notarization, and auto-update are not part of this preview stage
- the canonical upstream ledger may still include `.blockmap` metadata, but the public docs intentionally omit `.blockmap` files from the beginner-facing download list

## Expected Use

- review the GUI
- validate desktop-first research workspace flows
- stage public preview releases without changing backend or site ownership
- verify mirrored installer hashes against the upstream desktop manifest when installers are staged
- keep public docs and guide-facing installer names aligned with `desktop/releases/installer-manifest.json`

## Release Truth

For the exact release order, use `mdtero-frontend/docs/LAUNCH_RUNBOOK.md`.

The current publication contract is:

- `.github/workflows/build-desktop-installers.yml` can automatically build preview installers and upload CI artifacts
- public mirroring, manifest refresh, staged public installers, and public repo publication remain manual maintainer work
- the upstream installer manifest must be refreshed before the site or public docs advertise new installer names
- this preview surface does not imply a signed production release
