---
name: mdtero
description: Use when Mdtero should be available inside an agent workspace for scientific paper parsing, translation, task-status checks, and backend-run Markdown workflows.
---

# Mdtero

## Quick Start

1. Start from `https://mdtero.com/account`
2. Create or select an API key
3. Install Mdtero into the agent workspace
4. Run `mdtero login` (or `mdtero login --api-key <key>` when the environment needs manual setup)
5. Run `mdtero doctor` to verify that the key is available before parse, translate, status, or download work
6. Restart the agent shell if it does not automatically read `.env`

## Setup Rules

- `MDTERO_API_KEY` is required before normal parse and translation work
- normal DOI/URL parsing should use the installed CLI/API and Mdtero backend parser
- the browser extension is only needed for user PDF/local file upload or browser-context raw data capture
- keep user-provided files and licensed browser-context capture on the user's own machine when required

## Output Rule

- prefer Markdown first
- treat PDF as optional input or optional fallback output
- use fallback bundles only when the workflow truly needs them

## Helpful Public Entry Points

- install overview: `https://mdtero.com/install/manifest.json`
- install guide: `https://api.mdtero.com/skills/install.md`

## Verification Rule

- do not treat installation as complete until `mdtero doctor` shows that the shell or configured env file can see `MDTERO_API_KEY`
- after verification, continue with the normal Mdtero workflow from the installed environment
