<div align="center">
  <img src="./extension/src/assets/icon-128.png" alt="Mdtero logo" width="120" />

  # Mdtero Browser Extension

  *The public extension mirror for Mdtero's local capture path.*
</div>

This repository is the public home for the browser extension only.

The active product SSOT lives in [`JonbinC/mdtero`](https://github.com/JonbinC/mdtero):

- website, guide, dashboard, and API docs: `apps/site`
- active extension source of truth: `apps/extension`
- shared client contract: `packages/shared`

This repo stays focused on extension distribution and extension-facing public code.

Mdtero is currently agent-first:

1. Open [mdtero.com/account](https://mdtero.com/account)
2. Create or select an API key
3. Install Mdtero into OpenClaw, Claude Code, Codex, or Gemini CLI

Use this repository when you specifically need the browser extension for local capture from a live paper page.

## This Repo Contains

- the public extension mirror in [`extension`](./extension)
- the mirrored shared contract in [`shared`](./shared)
- the current sideload ZIP for manual install
- public install guides for Codex and OpenClaw

## When To Use The Extension

- you are already reading a supported paper page locally
- publisher-side acquisition must stay on the user machine
- you want the fastest path to a local Markdown package and bundle download

PDF is optional input. The default handoff format remains the Markdown package.

## Repo Boundary

- use this repo for extension packaging, public extension code, and manual sideload distribution
- do not treat this repo as the source of truth for website flows, dashboard UX, or backend behavior
- when extension behavior changes in `JonbinC/mdtero`, sync the same change here in the same round

## Install

1. Download `mdtero-extension-beta.zip` from [mdtero.com/guide](https://mdtero.com/guide), or use the mirrored ZIP in this repository.
2. Unzip it into a stable local folder.
3. Open `edge://extensions` or `chrome://extensions`.
4. Turn on `Developer mode`.
5. Click `Load unpacked` and choose the unzipped folder.
6. Sign in inside Mdtero settings and keep the default API URL unless you are testing locally.
7. Add your own Elsevier API key only when you need enhanced Elsevier retrieval.

## Repo Map

- [`extension`](./extension): extension source, tests, build output, and manifest
- [`shared`](./shared): public client contract used by the extension
- [`codex`](./codex): Codex-facing install guidance
- [`openclaw`](./openclaw): OpenClaw-facing install guidance

## Public Links

- Edge Add-ons: [Mdtero on Microsoft Edge](https://microsoftedge.microsoft.com/addons/detail/mdtero/bgikfidgigjnkgfdhhopojgpckilknic)
- OpenClaw install guide: [`./openclaw/INSTALL.md`](./openclaw/INSTALL.md)
- Codex install guide: [`./codex/INSTALL.md`](./codex/INSTALL.md)

## Local Development

```bash
npm install
npm test
npm run build
```

Build output lives in [`extension/dist`](./extension/dist).

## Notes

- the extension and website are public clients; the production backend stays private
- the extension does not need the website UI open to parse papers
- local helper or extension should handle publisher-side local acquisition when required
- if repo responsibilities ever conflict, `JonbinC/mdtero` wins as product SSOT
