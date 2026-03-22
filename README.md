<div align="center">
  <img src="./extension/src/assets/icon-128.png" alt="Mdtero logo" width="120" />

  # Mdtero Browser Extension

  *The secondary Mdtero entry path for local paper capture during beta.*
</div>

Mdtero is currently agent-first:

1. Open [mdtero.com/account](https://mdtero.com/account)
2. Create or select an API key
3. Install Mdtero into OpenClaw, Claude Code, Codex, or Gemini CLI

Use this repository when you specifically need the browser extension for local capture from a live paper page.

## This Repo Contains

- the browser extension source in [`extension`](./extension)
- the current sideload ZIP
- public install guides for Codex and OpenClaw

## When To Use The Extension

- you are already reading a supported paper page locally
- publisher-side acquisition must stay on the user machine
- you want the fastest path to a local Markdown package and bundle download

PDF is optional input. The default handoff format remains the Markdown package.

## Install

1. Download `mdtero-extension-beta.zip` from [mdtero.com/guide](https://mdtero.com/guide), or build it here.
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
