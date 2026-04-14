# Mdtero Desktop Public Preview

This directory is the public mirror surface for Mdtero desktop preview releases.

The Electron GUI source of truth stays in `JonbinC/mdtero` under `apps/desktop`.

Use this directory for:

- preview release notes
- mirrored preview bundle assets
- public download-facing docs
- mirrored installer manifest metadata
- user-facing notes about desktop capabilities that are already implemented upstream

Do not move the desktop app source code here.

## Current Preview Scope

The current preview is the first guided GUI for Mdtero's research workflow.

It is meant to help non-CLI users work through the existing Mdtero pipeline more clearly, not replace the existing website, helper, extension, or CLI.

Current upstream capabilities already reflected by this preview surface:

- dual-mode workspace: `Discovery` and `Notebook`
- project tree plus paper/task views
- Markdown-first reading and report workflow
- bilingual GUI shell: `English / 中文`
- local source enhancement settings for `OpenAlex`, `Elsevier`, `Wiley TDM`, and `Springer OA`
- preview-ready public bundle built from the upstream desktop host

## Current Preview Artifacts

The current preview version is `0.1.0-preview.1`.

The current preview artifact names are:

- `Mdtero-0.1.0-preview.1-mac-universal.dmg` → `desktop/releases/Mdtero-0.1.0-preview.1-mac-universal.dmg`
- `Mdtero-0.1.0-preview.1-win-x64.exe` → `desktop/releases/Mdtero-0.1.0-preview.1-win-x64.exe`

The canonical installer ledger also records `.blockmap` metadata for updater parity, but those files are not part of the user-facing download list in this public preview documentation.

These are preview artifacts only:

- unsigned by default
- not notarized
- no auto-update yet
- suitable for public preview and internal acceptance, not positioned as a final production release

## Product Boundary

The desktop GUI is the workspace and visualization layer.

It does not replace:

- the backend parsing core
- the helper's local runtime responsibilities
- the browser extension's page-side acquisition role
- the CLI's automation-first workflows

The parsing core and account/session logic remain owned by the upstream Mdtero application stack.

## Current Release Path

For the authoritative release order, use `mdtero-frontend/docs/LAUNCH_RUNBOOK.md`.

Operationally, this public mirror depends on the upstream workflow and maintainer commands in `JonbinC/mdtero`:

1. Upstream maintainers may use the GitHub Actions **workflow** `.github/workflows/build-desktop-installers.yml` to build preview installers and upload CI artifacts.
2. Upstream maintainers must **manually** refresh `apps/desktop/installers/manifest.json` and mirror it with `npm run mirror:public-installer-manifest --workspace=@mdtero/desktop` before public docs advertise new installer names.
3. Upstream maintainers must **manually** stage the actual public installer files with `npm run stage:public-installers --workspace=@mdtero/desktop`.
4. Upstream maintainers must **manually** mirror bundle docs or selected assets into this directory.
5. Upstream maintainers must **manually** publish the public repo changes to `JonbinC/doi2md`.

The following upstream commands are the relevant maintainer commands for this public mirror:

- `npm run package:installer:mac --workspace=@mdtero/desktop`
- `npm run package:installer:win --workspace=@mdtero/desktop`
- `npm run mirror:public-installer-manifest --workspace=@mdtero/desktop`
- `npm run stage:public-installers --workspace=@mdtero/desktop`

The mirrored installer ledger lives at `desktop/releases/installer-manifest.json` and is copied from the upstream SSOT file `mdtero-frontend/apps/desktop/installers/manifest.json`.

## Current Boundary

- preview bundle only
- public notes may describe current GUI capabilities such as bilingual shell copy, dual-mode workspace, or local source-API settings
- preview installer classes only, not a production release
- CI build automation does not equal public publication automation
- not the desktop source of truth
