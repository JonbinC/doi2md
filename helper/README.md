# Helper

This directory is for legacy local-acquisition notes and narrow local-file handoffs.

The helper is not the normal public install path. Mdtero's regular product flow is the npm CLI or dashboard asking the backend to choose the route and run the parser. The browser extension remains a local executor for user PDF/local file upload and browser-context raw data capture.

Dependency boundary:

- `uv tool install mdtero` owns the Python runtime CLI and local Python dependencies.
- `mdtero bootstrap --agent <target>` and `mdtero setup --agent <target>` are the preferred one-command bootstrap after the uv runtime is installed; they delegate only agent skill files to `npx mdtero-install install <target>`.
- `mdtero-install` is a Node installer/uninstaller for agent skill files; it does not own the Python runtime CLI.
- The browser extension is JavaScript/browser code and does not bundle `curl_cffi`.
- Local Python/backend tooling may use local-only Python dependencies such as `curl_cffi` and `pyzotero`.

Current migrated content:

- `openclaw/`: OpenClaw-facing install guidance

Not maintained anymore:

- legacy MCP code has been moved to `archive/mcp-legacy/`
