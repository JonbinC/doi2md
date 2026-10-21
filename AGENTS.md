# doi2md AGENTS.md

## OVERVIEW

Public local-install/download surface: Python CLI/TUI, browser extension, campus Relay, install manifest, local-file handoff assets, and agent skill materials. Website/dashboard code belongs in `JonbinC/Nextmdtero`; backend runtime belongs in `JonbinC/mdtero-backend`.

## STRUCTURE

```text
doi2md/
├── src/mdtero/ # public Python CLI/TUI and packaged agent skills
├── relay/      # campus HTTP transport and optional authorized browser worker
├── extension/  # public browser extension SSOT
├── shared/     # public contract subset used by extension/public code
├── install/    # canonical public install manifest and docs
├── skills/     # agent skill/install bundles
└── docs/       # public product documentation notes
```

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Public CLI/TUI | `src/mdtero` | Python runtime, project state, local agent installation. |
| Campus Relay | `relay` | Native relay, browser worker, and their tests. |
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
- Do not commit private CI mirrors, internal hostnames, secret-manager operator scripts, or dated production smoke ledgers.
- Do not let archive/MCP legacy content or retired helper-bundle probes become active behavior.
- Do not let public shared contracts drift from frontend/backend truth.
- Do not treat GitHub Releases or public mirror repo as independent release truth.
- Do not commit `relay/dist/` binaries; publish them through GitHub Releases.

## COMMANDS

```bash
npm --prefix extension install
npm --prefix extension test -- --run
npm --prefix extension run build
uv run --with pytest python -m pytest tests_py
```

## Cloud Agent setup

- Use the repository's Python lockfile with `uv sync --frozen`, run `npm ci` in `extension/`, and run `go mod download` in `relay/`. Extension CI uses Node 22; the Relay module targets Go 1.22. Check the selected Cloud Agent image instead of assuming these tools are preinstalled.
- Install Python venv support (`python3-venv` on Debian/Ubuntu) when the image cannot run `python3 -m venv`; the CI wheel smoke uses it. `uv sync` manages its own environment.
- No resident dev server is needed for CLI, extension, or Relay verification. Check `uv run mdtero --version` and `uv run mdtero project init` in a disposable directory. Run `uv run pytest tests_py -q`, `npm --prefix extension test -- --run`, `npm --prefix extension run build`, and `go test ./...` from `relay/` as the relevant gates.

## CHILD GUIDANCE

- `extension/AGENTS.md`: extension source/build/test surface.
- `extension/src/lib/AGENTS.md`: extension protocol helpers.
- `shared/AGENTS.md`: public shared contract subset.
