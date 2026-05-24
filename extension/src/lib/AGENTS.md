# Extension lib AGENTS.md

## OVERVIEW

Protocol and browser acquisition layer for the public extension. These files translate shared/backend contracts into browser/runtime behavior.

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| API calls | `api.ts` | Fetch adapters for backend/public contract surfaces. |
| Route execution | `ssot-route.ts` | Executes backend route plans through extension capabilities. |
| Runtime messages | `runtime.ts` | Extension command/message shaping. |
| Raw fulltext upload | `api.ts` + `ssot-route.ts` | Browser-captured HTML/XML/EPUB/PDF artifacts upload through `/api/v1/tasks/upload`. |
| Page capture | `page-capture.ts` | Page classification and artifact detection. |

## CONVENTIONS

- Treat this subtree as adapters/protocol code, not canonical backend policy.
- Preserve backend route-plan semantics; extension executes plans, it does not invent fallback ordering truth.
- Captured HTML/XML/EPUB/PDF should upload as raw artifacts through `/api/v1/tasks/upload`; avoid adding local helper or native messaging detours.
- Keep page-capture classifiers conservative around login/challenge/PDF-shell detection.

## ANTI-PATTERNS

- Do not duplicate `@mdtero/shared` contract definitions locally.
- Do not promote a publisher-specific hack into generic routing policy here.
- Do not bypass tests for background/page-capture/raw-upload behavior.
- Do not reintroduce native messaging, local helper dependencies, or publisher API key storage into the public extension.

## VERIFY

```bash
npm test --workspace=@mdtero/extension -- --run tests/background.test.ts tests/page-capture.test.ts
```
