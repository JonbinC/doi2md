# Public Desktop Preview AGENTS.md

## OVERVIEW

Public desktop preview mirror. The Electron source and installer manifest generation live in `mdtero-frontend/apps/desktop`.

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Public preview docs | `README.md`, `../docs/public/desktop-preview.md` | Preview posture and install wording. |
| Mirrored ledger | `releases/installer-manifest.json` | Public copy of frontend desktop installer manifest. |
| Upstream SSOT | `../../mdtero-frontend/apps/desktop/installers/manifest.json` | From `mdtero-public/desktop`, points to the frontend desktop manifest; refresh there first. |
| Preview contract test | `../tests/desktop-preview-contract.test.mjs` | Validates mirrored metadata and wording. |

## CONVENTIONS

- Preview/testing surface only unless release docs/tests say otherwise.
- Public mirroring/publication is maintainer work; CI only builds/uploads artifacts.
- Keep installer filenames, hashes, versions, and docs aligned.
- GitHub Release asset download is fallback/mirror behavior, not independent truth.

## ANTI-PATTERNS

- Do not edit this ledger as if it were the upstream source.
- Do not claim notarization, auto-update, or production release status without matching release proof.
- Do not put Electron source here.

## VERIFY

```bash
node --test tests/desktop-preview-contract.test.mjs
node --test tests/release-workflow-contract.test.mjs
```
