# Public Shared AGENTS.md

## OVERVIEW

Public shared contract subset used by extension/public code. Mirror/adaptation layer, not an independent product contract authority.

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Public exports | `src/index.ts` | Shared package barrel. |
| API contract subset | `src/api-contract.ts` | Public TS shapes consumed by extension. |
| Package config | `package.json` | Local package consumed by extension via file dependency. |
| Frontend contract source | `../../mdtero-frontend/packages/shared` | From `mdtero-public/shared`, points to the broader frontend-facing contract layer. |
| Backend schema source | `../../mdtero-backend/service/schemas.py` | From `mdtero-public/shared`, points to backend HTTP model truth. |

## CONVENTIONS

- Keep public shared shapes aligned with frontend shared and backend schemas.
- Expose only public-safe contract surfaces.
- Treat public shared as a package boundary for extension consumers.

## ANTI-PATTERNS

- Do not add backend-private fields just because they exist server-side.
- Do not fork contract names or enum values from the frontend/backend source surfaces.
- Do not make extension-only implementation details part of the shared contract.

## VERIFY

```bash
node --test tests/public-contract-truth.test.mjs
npm test --workspace=@mdtero/extension
```
