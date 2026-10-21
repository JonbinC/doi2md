# Native Connect shell

**Status: interim.** The runnable native entry in this PR is:

```sh
mdtero connect
```

That starts a loopback-only HTTP bridge and opens the Connect UI. API keys remain in the existing Mdtero CLI config / OS environment.

## Planned packaging (not shipped here)

- Tauri 2 shell embedding the Connect UI
- Go Relay as a supervised sidecar (reuse `relay/`)
- OS credential storage, code signing / notarization, and per-OS install/upgrade/uninstall evidence

Do not advertise macOS/Windows/Linux installers until those gates exist with checksums on the website release manifest.
