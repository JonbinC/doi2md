# Public Extension AGENTS.md

## OVERVIEW

Public browser extension source, tests, manifest, and build output. This is the extension SSOT for the local public install surface.

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Extension manifest | `manifest.json` | Runtime/content/background permissions and host scope. |
| Background orchestration | `src/background.ts` | High-impact control flow. |
| Page/content bridge | `src/content.ts` | Page-side capture/auth bridge. |
| Protocol helpers | `src/lib` | Route execution, helper bundle, browser bridge, API client. |
| Tests | `tests` | Dense extension coverage. |
| Build config | `esbuild.config.mjs` | Produces `dist`. |

## CONVENTIONS

- Public extension code consumes public/shared contracts and backend route plans.
- Publisher-side local acquisition should stay on the user machine when required.
- Permissions stay scoped to local downloads, supported paper tabs, native helper messaging, and supported publisher/API hosts.
- Mirror changes to frontend compatibility surface only when local compatibility needs it.
- Treat `dist` as generated build output.

## ANTI-PATTERNS

- Do not add website/dashboard UX here.
- Do not embed backend-private provider logic or credentials.
- Do not define new shared contract truth in extension-only code when shared/backend contracts exist.

## COMMANDS

```bash
npm run build --workspace=@mdtero/extension
npm test --workspace=@mdtero/extension
```
