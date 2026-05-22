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
that Python runtime. The legacy `mdtero-install` npm package is not the runtime and
is not required for skill installation.

Current maintained content:

- `openclaw/`: OpenClaw-facing install guidance for the dedicated ClawHub route.

Retired content:

- legacy MCP code has been moved to `archive/mcp-legacy/`.
