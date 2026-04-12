# Mdtero Desktop Public Preview

This directory is the public mirror surface for Mdtero desktop preview releases.

The Electron GUI source of truth stays in `JonbinC/mdtero` under `apps/desktop`.

Use this directory for:

- preview release notes
- mirrored preview bundle assets
- public download-facing docs
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

The current preview artifact names are:

- `Mdtero-0.1.0-preview.1-mac-universal.dmg`
- `Mdtero-0.1.0-preview.1-win-x64.exe`
- `mdtero-desktop-preview/` portable preview bundle

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

1. Build the preview bundle in `mdtero` with `npm run package:preview --workspace=@mdtero/desktop`
2. Review the generated bundle locally
3. Mirror the bundle docs or selected assets into this directory
4. Publish the public repo changes to `JonbinC/doi2md`

For installer builds, the upstream desktop host also exposes:

- `npm run package:installer:mac --workspace=@mdtero/desktop`
- `npm run package:installer:win --workspace=@mdtero/desktop`

The upstream GitHub Actions workflow can rebuild the same installer classes for `macOS` and `Windows`.

## Current Boundary

- preview bundle only
- public notes may describe current GUI capabilities such as bilingual shell copy, dual-mode workspace, or local source-API settings
- not a signed production installer
- not the desktop source of truth
