# mdtero-public AGENTS.md

## OVERVIEW

Public local-install/download surface: browser extension, public install manifest, local-file handoff assets, and agent skill materials.

## STRUCTURE

```text
mdtero-public/
├── extension/  # public browser extension SSOT
├── shared/     # public contract subset used by extension/public code
├── install/    # canonical public install manifest and docs
├── skills/     # agent skill/install bundles
└── docs/       # public product documentation notes
```

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Extension runtime | `extension` | Source, tests, manifest, build output. |
| Extension protocol helpers | `extension/src/lib` | Route execution, browser capture, raw upload, runtime messages. |
| Public install contract | `install/manifest.json` | Mirrored with site manifest; audited by tests. |
| Public shared contracts | `shared/src` | Mirror/subset for public clients. |

## CONVENTIONS

- If users download, install, or run it locally, default here.
- Website/dashboard/backend behavior is not owned here.
- OpenClaw is separate from install-script agent-skill targets and is not maintained in this public repo.
- Generated `extension/dist` is output; source edits belong under `extension/src`.

## ANTI-PATTERNS

- Do not put private backend implementation, dashboard product code, or secret-bearing ops scripts here.
- Do not let archive/MCP legacy content or retired helper-bundle probes become active behavior.
- Do not let public shared contracts drift from frontend/backend truth.
- Do not treat GitHub Releases or public mirror repo as independent release truth.

## COMMANDS

```bash
npm --prefix extension install
npm --prefix extension test -- --run
npm --prefix extension run build
uv run --with pytest python -m pytest tests_py
```

## CHILD GUIDANCE

- `extension/AGENTS.md`: extension source/build/test surface.
- `extension/src/lib/AGENTS.md`: extension protocol helpers.
- `shared/AGENTS.md`: public shared contract subset.
