# Helper

This directory is for legacy local-acquisition notes and narrow local-file handoffs.

The helper is not the normal public install path. Mdtero's regular product flow is `https://mdtero.com/install.sh` or the dashboard asking the backend to choose the route and run the parser. The browser extension remains a local executor for user PDF/local file upload and browser-context raw data capture.

Dependency boundary:

- `npm install -g mdtero-install@0.1.8` owns the currently published public CLI package.
- `curl -Ls https://mdtero.com/install.sh | sh -s -- --agent <target>` is the preferred one-command bootstrap for CLI package plus agent skill files.
- `npx mdtero-install install <target>` installs agent skill files and is the reviewable skill-only route.
- `mdtero-install` is the Node CLI package and installer/uninstaller for agent skill files.
- The browser extension is JavaScript/browser code and does not bundle `curl_cffi`.
- Local Python/backend tooling may use local-only Python dependencies such as `curl_cffi` and `pyzotero`.

Current migrated content:

- `openclaw/`: OpenClaw-facing install guidance

Not maintained anymore:

- legacy MCP code has been moved to `archive/mcp-legacy/`
