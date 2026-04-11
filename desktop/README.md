# Mdtero Desktop Public Preview

This directory is the public mirror surface for Mdtero desktop preview releases.

The Electron GUI source of truth stays in `JonbinC/mdtero` under `apps/desktop`.

Use this directory for:

- preview release notes
- mirrored preview bundle assets
- public download-facing docs

Do not move the desktop app source code here.

## Current Release Path

1. Build the preview bundle in `mdtero` with `npm run package:preview --workspace=@mdtero/desktop`
2. Review the generated bundle locally
3. Mirror the bundle docs or selected assets into this directory
4. Publish the public repo changes to `JonbinC/doi2md`

## Current Boundary

- preview bundle only
- not a signed production installer
- not the desktop source of truth
