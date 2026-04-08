# Install

This directory is the umbrella entry point for public installation flows.

Use it for:

- one-page install summaries
- environment-specific setup entry docs
- links out to `extension/`, `helper/`, and `skills/`

## Unified Entry

For agent-style installs, prefer the lightweight install CLI:

```bash
npx @mdtero/install show
```

Examples:

```bash
npx @mdtero/install install codex
npx @mdtero/install install claude_code
npx @mdtero/install install gemini_cli
```

OpenClaw remains the special case:

```bash
clawhub install mdtero
```

Canonical manifest:

- `https://mdtero.com/install/manifest.json`
