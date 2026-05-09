# Public Install AGENTS.md

## OVERVIEW

Canonical public install contract. The manifest is website-first release truth and must stay mirrored with the active site copy.

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Public manifest | `manifest.json` | Canonical target list and install commands. |
| Installer CLI | `../bin/mdtero-install.mjs` | Reads bundled/fallback manifest. |
| Install docs | `README.md` | Public install instructions. |
| Site mirror | `../../mdtero-frontend/apps/site-next/public/install/manifest.json` | From `mdtero-public/install`, points to the active site copy and must match public manifest. |
| Contract proof | `../tests/public-contract-truth.test.mjs` | Enforces manifest/doc/release truth. |

## CONVENTIONS

- `manifestUrl` points to `https://mdtero.com/install/manifest.json`.
- Claude Code, Codex, Gemini CLI, Hermes Agent, and OpenCode use `curl -Ls https://mdtero.com/install.sh | sh -s -- --agent <target>` as the primary path.
- `npx mdtero-install ...` is a fallback for installing/removing skill files only.
- OpenClaw uses `clawhub install mdtero` and stays separate from install-script targets.
- Account boundary note must preserve: Account/Dashboard is the control plane for API keys, quota, history, diagnostics, and install prompts; the `mdtero` CLI is the unified runtime entry for discovery, parse, translate, task-status, download, and agent-skill workflows.
- Desktop release truth is mirrored from public desktop ledger, not invented here.

## ANTI-PATTERNS

- Do not change target names or install commands without updating tests and site mirror.
- Do not make this manifest diverge from the site manifest.
- Do not promote desktop beyond preview through manifest wording alone.

## VERIFY

```bash
node --test tests/public-contract-truth.test.mjs
node --test tests/mdtero-install.test.mjs
```
