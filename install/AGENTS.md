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
- Claude Code, Codex, and Gemini CLI use `npx mdtero-install ...`.
- OpenClaw uses `clawhub install mdtero` and stays separate from npm-first targets.
- Account boundary note must preserve: discovery/API-key management stay in Mdtero Account.
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
