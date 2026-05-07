# mdtero-public AGENTS.md

## OVERVIEW

Public local-install/download surface: browser extension, public install manifest, local-file handoff assets, agent skill materials, and desktop preview mirrors.

## STRUCTURE

```text
mdtero-public/
├── extension/  # public browser extension SSOT
├── shared/     # public contract subset used by extension/public code
├── install/    # canonical public install manifest and docs
├── desktop/    # public desktop preview ledger mirror
├── helper/     # legacy local-file handoff notes/docs
├── skills/     # agent skill/install bundles
├── tests/      # public release/install contract tests
└── archive/    # historical/reference-only assets
```

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Extension runtime | `extension` | Source, tests, manifest, build output. |
| Extension protocol helpers | `extension/src/lib` | Route execution, helper bundle, page capture, runtime messages. |
| Public install contract | `install/manifest.json` | Mirrored with site manifest; audited by tests. |
| Installer CLI | `bin/mdtero-install.mjs` | Uses bundled manifest fallback. |
| Public shared contracts | `shared/src` | Mirror/subset for public clients. |
| Desktop preview ledger | `desktop/releases/installer-manifest.json` | Mirror of frontend desktop installer manifest. |
| Contract tests | `tests/public-contract-truth.test.mjs` | Guards release truth and mirror alignment. |

## CONVENTIONS

- If users download, install, or run it locally, default here.
- Website/dashboard/backend behavior is not owned here.
- OpenClaw is separate from npm-first agent-skill install targets.
- Public desktop is preview/testing unless docs/tests promote it.
- Generated `extension/dist` is output; source edits belong under `extension/src`.

## ANTI-PATTERNS

- Do not put private backend implementation, dashboard product code, or secret-bearing ops scripts here.
- Do not let archive/MCP legacy content become active behavior.
- Do not let public shared contracts drift from frontend/backend truth.
- Do not treat GitHub Releases or public mirror repo as independent release truth.

## COMMANDS

```bash
npm install
npm run test:install
npm run test:public-contract
node --test tests/mdtero-install.test.mjs
node --test tests/public-contract-truth.test.mjs
```

## CHILD GUIDANCE

- `install/AGENTS.md`: manifest and installer contract.
- `desktop/AGENTS.md`: public desktop preview mirror.
- `extension/AGENTS.md`: extension source/build/test surface.
- `extension/src/lib/AGENTS.md`: extension protocol helpers.
- `shared/AGENTS.md`: public shared contract subset.
