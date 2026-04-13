# Desktop Preview

Mdtero Desktop is currently published as a public preview bundle.

That means:

- the build is generated from `JonbinC/mdtero/apps/desktop`
- the public repo mirrors preview-facing docs and optional bundle assets
- the public repo also mirrors the upstream installer ledger at `desktop/releases/installer-manifest.json`
- signing, notarization, and auto-update are not part of this preview stage
- current preview installer targets are macOS universal `dmg` and Windows `exe`

## Local Launch

From the generated preview bundle root:

```bash
npm install
npm run start
```

## Expected Use

- review the GUI
- validate desktop-first research workspace flows
- stage public preview releases without changing backend or site ownership
- verify mirrored installer hashes against the upstream desktop manifest when installers are staged
