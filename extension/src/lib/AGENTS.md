# Extension lib AGENTS.md

## OVERVIEW

Protocol and acquisition helper layer for the public extension. These files translate shared/backend contracts into browser/runtime behavior.

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| API calls | `api.ts` | Fetch adapters for backend/public contract surfaces. |
| Route execution | `ssot-route.ts` | Executes backend route plans through extension capabilities. |
| Runtime messages | `runtime.ts` | Extension command/message shaping. |
| Helper bundles | `helper-bundle.ts` | ZIP/manifest packaging for helper-bundle parse flow. |
| Page capture | `page-capture.ts` | Page classification and artifact detection. |
| Capture hints | `bridge-wake.ts` | Publisher URL support detection for current-tab capture hints. |

## CONVENTIONS

- Treat this subtree as adapters/protocol code, not canonical backend policy.
- Preserve backend route-plan semantics; extension executes plans, it does not invent fallback ordering truth.
- Keep helper bundle manifest fields stable with backend parser expectations.
- Keep page-capture classifiers conservative around login/challenge/PDF-shell detection.

## ANTI-PATTERNS

- Do not duplicate `@mdtero/shared` contract definitions locally.
- Do not promote a publisher-specific hack into generic routing policy here.
- Do not bypass tests for background/page-capture/helper-bundle behavior.
- Do not reintroduce native messaging or local helper dependencies into the public extension.

## VERIFY

```bash
npm test --workspace=@mdtero/extension -- --run tests/background.test.ts tests/page-capture.test.ts
```
