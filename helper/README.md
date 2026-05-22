# Helper

This directory is retained only for narrow compatibility notes that do not fit the
active Python CLI, browser extension, or agent skill surfaces.

Mdtero's normal public path is now:

```bash
uv tool install git+https://github.com/JonbinC/doi2md.git
mdtero setup
mdtero agent install --target <target>
```

The install script at `https://mdtero.com/install.sh` is a bootstrap wrapper around
that Python runtime. Agent skill installation is handled by `mdtero agent install`.

Current maintained content:

- `openclaw/`: OpenClaw-facing install guidance for the dedicated ClawHub route.

Retired content has been removed from the active repository once the Python
runtime owns the maintained replacement.
