---
name: mdtero
description: Use when Mdtero should be available inside an agent workspace for scientific paper parsing, translation, task-status checks, and helper-first local acquisition workflows.
---

# Mdtero

## Quick Start

1. Start from `https://mdtero.com/account`
2. Create or select an API key
3. Keep Mdtero inside the agent for parse, translate, status, and download workflows

## Setup Rules

- `MDTERO_API_KEY` is required before normal parse and translation work
- the local helper `mdtero` is the preferred path for local acquisition
- the browser extension is only needed when a supported live paper page must be captured in the browser
- for Elsevier and ScienceDirect, keep acquisition on the user's own machine

## Output Rule

- prefer Markdown first
- treat PDF as optional input or optional fallback output
- use fallback bundles only when the workflow truly needs them

## Helpful Public Entry Points

- install overview: `https://mdtero.com/install/manifest.json`
- helper installer: `https://api.mdtero.com/helpers/install_mdtero_helper.sh`
- install guide: `https://api.mdtero.com/skills/install.md`
