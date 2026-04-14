# Install

This directory is the umbrella entry point for public installation flows.

Use it for:

- one-page install summaries
- environment-specific setup entry docs
- links out to `extension/`, `helper/`, and `skills/`

## Unified Entry

For agent-style installs, prefer the lightweight install CLI:

```bash
npx mdtero-install show
```

Examples:

```bash
npx mdtero-install install codex
npx mdtero-install install claude_code
npx mdtero-install install gemini_cli
```

OpenClaw remains the special case:

```bash
clawhub install mdtero
```

Account boundary:

- Keyword discovery and API-key management stay in Mdtero Account. Use the agent install for parse, translate, task-status, and download workflows.

Canonical manifest:

- `https://mdtero.com/install/manifest.json`

Manual fallback / helper guide:

- `https://api.mdtero.com/skills/install.md`
