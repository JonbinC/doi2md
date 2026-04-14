<div align="center">
  <img src="./extension/src/assets/icon-128.png" alt="Mdtero logo" width="120" />

  # Mdtero Public Surface

  *The public local-client and install surface for Mdtero.*
</div>

This repository is the public home for Mdtero's user-side installables.

This repo is now the intended SSOT for the browser extension and the wider public install surface.

The frontend repo may keep a compatibility mirror under `mdtero-frontend/apps/extension`, but long-lived extension changes should start here.

The product and backend SSOT still live in separate private repos:

- frontend product repo: `JonbinC/mdtero`
- backend parsing repo: `JonbinC/mdtero-backend`

This repo stays focused on what users install or run locally.

Mdtero turns papers into reusable Markdown research packages.

Keyword discovery and API-key management stay in Mdtero Account. Use the agent install for parse, translate, task-status, and download workflows.

Use this repository when you specifically need public local capture, helper setup, or public install guidance.

## Unified Agent Install

The public npm entry for agent-side setup is:

```bash
npx mdtero-install show
```

Direct install examples:

```bash
npx mdtero-install install codex
npx mdtero-install install claude_code
npx mdtero-install install gemini_cli
```

OpenClaw keeps the dedicated route:

```bash
clawhub install mdtero
```

## This Repo Contains

- the public extension code in [`extension`](./extension)
- desktop preview release notes and mirrored bundles in [`desktop`](./desktop)
- helper-facing public assets in [`helper`](./helper)
- skill-facing public assets in [`skills`](./skills)
- public install entry points in [`install`](./install)
- shared client contract in [`shared`](./shared)
- public docs in [`docs/public`](./docs/public)
- archived legacy assets in [`archive`](./archive)

## When To Use The Extension

- you are already reading a supported paper page locally
- the paper page needs to stay on your own machine
- you want a quick path to `paper.md`, figures, and a reusable bundle
- you already have a local PDF or EPUB and want to keep the same package flow
- local PDF intake currently defaults to `GROBID`; `Docling` and `MinerU` remain selectable fallbacks

PDF is optional input. The default handoff format remains the Markdown package.

## Desktop Preview

The desktop GUI source of truth stays in `JonbinC/mdtero` under `apps/desktop`.

This public repo only carries the public preview release surface:

- mirrored preview bundle docs
- lightweight release notes
- public download-facing structure for desktop previews
- mirrored installer manifest metadata for staged preview installers
- capability notes for features already shipped from the upstream desktop SSOT, such as bilingual shell copy and local source-API settings

Do not move the actual Electron source of truth here.

Current preview positioning:

- dual-mode research workspace: `Discovery` and `Notebook`
- bilingual GUI shell: `English / 中文`
- local source enhancement settings for `OpenAlex`, `Elsevier`, `Wiley TDM`, and `Springer OA`
- current preview artifact classes: `mac universal dmg`, `win x64 exe`, and a portable preview bundle

See [`desktop/README.md`](./desktop/README.md) for the current preview scope and artifact notes.

## Repo Boundary

- use this repo for public extension packaging, desktop preview mirroring, helper/setup assets, and user-side install guidance
- do not treat this repo as the source of truth for dashboard UX or backend implementation
- if something is meant to be downloaded, installed, or run by end users locally, default it here
- legacy MCP code is archived and is not an actively maintained surface

## Install

1. Install Mdtero from the Chrome Web Store or Edge Add-ons.
2. Sign in inside Mdtero settings and keep the default API URL unless you are testing locally.
3. Open the article locally or start from your own PDF/EPUB when needed.
4. Use manual unpacked loading only for development or review builds.

## Repo Map

- [`extension`](./extension): extension source, tests, build output, and manifest
- [`desktop`](./desktop): desktop preview release docs and mirrored preview bundles
- [`helper`](./helper): helper-facing public assets and MCP/runtime utilities
- [`archive`](./archive): deprecated or historical public assets kept only for reference
- [`skills`](./skills): public skill-facing install guidance
- [`install`](./install): top-level install entry docs
- [`shared`](./shared): public client contract used by local clients
- [`docs/public`](./docs/public): stable public-facing docs

## Public Links

- Chrome Web Store: [Mdtero on Google Chrome](https://chromewebstore.google.com/detail/mdtero/knpihhcooldgedbklgjghebijcpejibp)
- Edge Add-ons: [Mdtero on Microsoft Edge](https://microsoftedge.microsoft.com/addons/detail/mdtero/bgikfidgigjnkgfdhhopojgpckilknic)
- Product guide: [mdtero.com/guide](https://mdtero.com/guide)
- OpenClaw install guide: [`./helper/openclaw/INSTALL.md`](./helper/openclaw/INSTALL.md)
- Codex install guide: [`./skills/codex/INSTALL.md`](./skills/codex/INSTALL.md)

## Local Development

```bash
npm install
npm test
npm run build
```

Build output lives in [`extension/dist`](./extension/dist).

Desktop preview mirror docs live in [`desktop`](./desktop).

## Notes

- the extension and website are public clients; the production backend stays private
- the extension does not need the website UI open to parse papers
- local helper or extension should handle publisher-side local acquisition when required
- permissions stay scoped to local downloads, supported paper tabs, native helper messaging, and the supported publisher/API host list
- for the local helper, download the installer, inspect it locally, then run it
- if repo responsibilities ever conflict, frontend/backend SSOT wins over this public packaging repo
