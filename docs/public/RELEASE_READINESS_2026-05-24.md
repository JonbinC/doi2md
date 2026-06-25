# Release Readiness - 2026-05-24

This matrix records what is proven by the current worktree and what still needs post-deploy smoke. It is intentionally stricter than a changelog: a row is marked ready only when there is current test, build, or live-smoke evidence.

## Proven Ready

| Area | Evidence |
| --- | --- |
| Public Python/uv CLI as the main runtime | `pyproject.toml` exposes `mdtero`; public release gate passed with `202 passed`; install docs use `uv tool install git+https://github.com/JonbinC/doi2md.git` and exclude npm runtime commands. |
| Setup, doctor, academic keys, and agent-safe diagnostics | CLI contract tests cover setup/doctor/config flows; docs require `mdtero doctor --json`; redaction tests cover Mdtero keys, bearer headers, signed URLs, and token query params. |
| DOI/URL parse, raw upload, status, download, project mode | Public CLI contract tests cover parse/status/download/project flows; live production smoke completed arXiv parse, project refresh, and artifact download. |
| PDF upload through backend document parsing | Production smoke completed PDF upload, backend file fetch, and Markdown download. |
| Discovery | Production smoke completed server OpenAlex discovery; CLI contract covers server OpenAlex discovery. |
| Zotero import and conservative sync | Public CLI tests cover pyzotero mock import/sync; docs state sync writes Mdtero notes/tags only and does not rewrite bibliographic metadata. |
| Server-side RAG | Production smoke completed server project bootstrap, task import, index build, status, and query; CLI/MCP tests cover not-ready and ready paths. |
| FastMCP and agent skill handoff | Public CLI tests cover MCP briefing/tools and Python-based agent install; `mdtero smoke --json` now validates the MCP briefing exposes `agent_briefing`, `server_rag_status`, and `rag_query` after RAG setup; docs and skills no longer require npm for agent skill installation. |
| Browser extension scoped to v1 product | Extension release gate passed with `138 passed`; build passed; extension dist smoke passed; manifest/workspace tests assert no native messaging, no publisher key storage, no old helper UI, no retired publisher-specific action names, v1 task/upload/translate/download paths, and CLI handoff for DOI/URL plus failed local PDF/EPUB uploads. |
| Website/dashboard docs and UI | Nextmdtero release gate passed with `101 passed`; build passed; docs build passed; 11 production route artifacts verified; dashboard tests cover API-key copy dialog, install prompts, RAG/MCP workflow, redaction, extension handoff, and deploy route smoke tooling. |
| Backend `/api/v1` and script cleanup | Backend release gate passed with `248 passed`; script layout tests limit active scripts; old browser bridge, helper runtime, parser-v2 shadow/benchmark scripts, Cloud Run E2E helpers, Wiley TDM one-off probes, and one-off export/demo scripts are removed from runnable locations. `/api/v1/route` and `/api/v1/extension/route` expose `requires_browser_capture` instead of the retired `requires_helper` helper flag. |
| Backend read-only production freshness | `scripts/validation/backend_production_smoke.py --api-base https://api.mdtero.com --json` succeeded on 2026-05-26 with `deployment_state=current`; `/health` and `/client-config` returned 200, and unauthenticated `/diagnostics/translation/providers` returned the expected 401 instead of stale 404. |
| Forgejo manual CI smoke policy | Public, frontend, and backend private preflights now run a Forgejo workflow policy gate that requires `workflow_dispatch`, `runs-on: linux-small`, explicit secret-name listing, and no push/PR triggers before extension/frontend/backend smoke tests run. |

## Requires Post-Deploy Smoke

| Area | Required check |
| --- | --- |
| Deployed website routes | Current production smoke against `https://mdtero.com` still fails only on `/docs/install.html` and `/docs/zh/install.html`: both live docs pages return 200 but miss the latest `evidence_pack.context_markdown` marker while local source/build include it. Deploy the latest `nextmdtero`, then rerun `npm run smoke:routes -- --base-url https://mdtero.com --json`; for another deployment target use `npm run smoke:routes -- --base-url <production-url> --json`. |
| Browser extension interactive flow | Load the built MV3 extension in Chrome/Edge and smoke website OAuth token bridge, current-page parse, PDF/EPUB upload, task polling, translate, and artifact download. Unit tests and dist smoke cover the packaged contract, but browser UI behavior still needs a real browser. |
| Translation provider health | The backend diagnostics route is now deployed: unauthenticated `GET /diagnostics/translation/providers` returns 401, which proves production is no longer on the stale build that returned 404. Operators still need an authenticated diagnostics check or successful translation task to prove at least one provider is healthy before calling translation launch-ready. |
| Deployment and production smoke | After pushing and deploying backend/site/public artifacts, rerun `mdtero smoke --json --timeout 600 --interval 2` with a fresh valid API key and record task ids/results. The workspace test key currently returns `401 missing or invalid credentials` on `/me/usage`, so it cannot prove the live parse/RAG/translate path. |

## Not Public Product Scope

- npm runtime CLI and per-agent npm installers.
- Native browser bridge, native host, and helper-bundle upload workflows.
- Public parser engine selection. Uploaded PDFs use the backend parsing path; internal fallback behavior is service-owned.
- Backend-local copies of the public CLI/TUI/Zotero/RAG/MCP client runtime.
