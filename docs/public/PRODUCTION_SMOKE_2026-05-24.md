# Production Smoke - 2026-05-24

Scope: public `mdtero` CLI against `https://api.mdtero.com`, using the local repository checkout with `uv run --project` so the smoke directory remains the command working directory. Secrets were supplied through process environment only and are not written here.

## Environment

- CLI version: `mdtero 0.2.0a9`
- API base: `https://api.mdtero.com`
- Smoke directory: `/tmp/mdtero-smoke-RLNBZR`
- Public PDF fixture: arXiv `1706.03762` PDF downloaded from `https://arxiv.org/pdf/1706.03762.pdf`

## Passed

- `mdtero doctor --json` completed against production.
- `mdtero discover "retrieval augmented generation scientific papers" --limit 2 --json` returned `source=openalex_server`, `provider=openalex`, `items=2`.
- `mdtero project init --name smoke --json` created a local project with `.mdtero/project.json`.
- `mdtero parse 10.48550/arXiv.1706.03762 --json` created task `2a57f571-afb3-468b-8470-65305b156cd3`.
- `mdtero status 2a57f571-afb3-468b-8470-65305b156cd3 --wait --timeout 300 --json` completed with `status=succeeded`, `stage=completed`, `reason_code=task_succeeded`.
- `mdtero download ... paper_md` and `paper_bundle` returned downloaded paths for `vaswani2017attention.md` and `vaswani2017attention.zip`.
- `mdtero parse --file attention.pdf --json` created PDF task `185f3ee9-5764-480a-b87e-939321aeb27a`.
- `mdtero status 185f3ee9-5764-480a-b87e-939321aeb27a --wait --timeout 420 --json` completed with `status=succeeded`, `stage=completed`, `reason_code=task_succeeded`.
- PDF quality reported `provider=mineru_precision`, `selected_pdf_provider=mineru_precision`, `url_fetch_used=true`, `external_upload_used=false`, `mineru_configured=true`, `provider_state=done`, `markdown_status=usable`.
- `mdtero download 185f3ee9-5764-480a-b87e-939321aeb27a paper_md --output-dir ./pdf-out --json` downloaded `pdf-out/attention-2.md`.
- `mdtero rag build --json` created/bound server project `10` and completed with `status=succeeded`, `reason_code=indexed`, `embedding_model=voyage-4`, `chunk_count=42`, `embedded_count=42`.
- `mdtero rag status --json` reported `status=ready`, `reason_code=indexed`, `pending_embedding_count=0`.
- `mdtero rag query "What is the main contribution of attention models?" --build-if-needed --json` completed with `status=succeeded`, `reason_code=rag_query_succeeded`, `match_count=5`, `citations=5`, `matches=5`, and an extractive answer.
- `mdtero mcp briefing --json` returned server RAG ready state and MCP tools including `agent_briefing`, `server_rag_status`, and `rag_query`.
- `mdtero agent detect --json` returned 5 targets and detected local `codex`, `claude_code`, and `hermes` workspaces.

## Latest ArXiv + Voyage RAG Re-Smoke

Run directory: `/tmp/mdtero-live-smoke-Y5UD11`. The API key was supplied only through `MDTERO_API_KEY` in the process environment and was not written to this repository or to this report.

Future re-smokes can use the packaged command instead of replaying the manual command sequence:

```bash
MDTERO_API_KEY=<fresh-key> mdtero smoke --json --timeout 600 --interval 2
```

For repo-checkout testing without installing the wheel, run the same command through `uv run --project /path/to/doi2md mdtero smoke --json --timeout 600 --interval 2` from an empty temporary directory.

- `uv run --project repos/public mdtero --version` returned `mdtero 0.2.0a9`.
- `mdtero doctor --json` returned `status=ok`; before project init it correctly reported `project.initialized=false` and next commands for `mdtero project init` and `mdtero parse ... --trace --wait --timeout 300 --json`.
- `mdtero project init --name live-smoke --json` created `/tmp/mdtero-live-smoke-Y5UD11/.mdtero/project.json`.
- `mdtero parse 10.48550/arXiv.1706.03762 --wait --timeout 300 --json` completed with task `394965d4-fef7-4ccb-8503-99d482894cfe`, `status=succeeded`, `stage=completed`, `reason_code=task_succeeded`, `route_kind=source_first`, and `provider_id=arxiv`.
- `mdtero project refresh --wait --timeout 300 --json` refreshed 1 succeeded task.
- `mdtero project download --output-dir ./out --json` downloaded `out/vaswani2017attention.zip`.
- `mdtero rag build --json` created and bound server project `13`, imported 1 task, and returned `status=succeeded`, `reason_code=indexed`, `document_count=1`, `chunk_count=39`, `embedded_count=39`, and `embedding_model=voyage-4`.
- `mdtero rag status --json` returned `status=ready`, `reason_code=indexed`, `pending_embedding_count=0`, and next commands for `mdtero rag query "<question>" --build-if-needed --json` and `mdtero mcp serve`.
- `mdtero rag query "What is the core contribution of this paper?" --build-if-needed --json` returned `status=succeeded`, `reason_code=rag_query_succeeded`, `citation_count=5`, `match_count=5`, and an extractive answer grounded in the Transformer paper.

This re-smoke proves the current public CLI can complete the arXiv source-first parse, artifact download, server-project bootstrap, task import, backend Voyage embedding build, RAG status, and RAG query path against production.

## Failed / Needs Operator Fix

- `mdtero translate <parse-task-id> --to zh-CN --json` successfully created task `b2a1cc21-5af5-4e04-b4b4-fa88acd8ce7a`, but final status was `failed` with `reason_code=translation_provider_chain_failed`.
- The production task error summary was: `codex: translation_provider_auth_failed; mimo: translation_provider_auth_failed; claude_code: translation_provider_auth_failed; local_legacy: translation_provider_rate_limited`.
- The returned action hint correctly says operators need to refresh provider API keys, restore quota, or disable the failing provider before retrying.

## Notes

- Use `mdtero smoke --json --timeout 600 --interval 2` for future CLI production smoke tests after installing the public package. Use `uv run --project /path/to/doi2md mdtero smoke --json --timeout 600 --interval 2` when testing from a repository checkout and running from a temporary project directory. `uv --directory /path/to/doi2md run mdtero ...` changes the command working directory to the repo and can place downloaded artifacts under the repo.
- This smoke proves the production CLI path for discovery, DOI parsing, PDF upload with MinerU URL API, artifact download, server-side Voyage RAG, MCP briefing, and agent detection. It does not prove browser-extension interactive login or Chrome/Edge upload UI; those still need browser-level smoke.

## Repository Gates Re-run After Cleanup

- Backend: latest release gate passed with `241 passed` across public assets, deploy assets, v1 API, usage/tasks, translation, script layout, source connectivity, parser policy, route acceptance, PDF upload proof, backend production smoke tooling, public route-contract cleanup, and parser pipeline surfaces.
- Backend secret guard: passed; no tracked `.env.yaml`, private keys, or signed temporary URL tokens were found.
- Public CLI: latest release gate passed with `196 passed` for `tests_py`; `python3 -m compileall -q src/mdtero` passed; `python3 scripts/ci/secret_guard.py` passed.
- Public package build: `uv build` produced `mdtero-0.2.0a9` sdist and wheel; installing the wheel in a temporary venv and running `mdtero --version` returned `mdtero 0.2.0a9`.
- Public extension: latest release gate passed with `141 passed` for the full extension test suite; `npm run build` passed and refreshed `extension/dist`; `python3 scripts/ci/extension_dist_smoke.py` passed for the packaged MV3 bundle. The popup/background tests prove CLI handoff commands for failed local PDF/EPUB uploads, and the dist smoke now rejects retired publisher-specific action names.
- Website/dashboard: latest release gate passed with `99 passed`; `npm run build` passed and verified 11 production route artifacts. The deploy route smoke command is `npm run smoke:routes -- --base-url <production-url> --json`.
- Website deploy workflow now runs route smoke against both the Vercel deployment URL and `https://mdtero.com` after deploy, so missing markers such as `/docs/install.html` without `evidence_pack.context_markdown` fail the deploy job instead of slipping through as a stale production build.
- `git diff --check` passed in backend, public, and nextmdtero.

## Cleanup State

- Public extension internal API naming now uses raw artifact upload (`createRawUploadTask`, `RawUploadTaskRequest`) while still posting to `/api/v1/tasks/upload`.
- Backend route acceptance now uses `publisher_html_raw_upload`; old helper-bundle and browser-bridge execution modes are retired from the release gate and removed from the active extension action contract.
- Retired backend validation scripts, parser-v2 shadow/benchmark entrypoints, and old one-off deploy scripts have been removed from runnable script locations.

## Production Deploy Smoke Recheck - 2026-05-24 UTC

This recheck used current worktree smoke tools against the live domains without writing secrets to the repository.

### Website Routes

Command:

```bash
npm run smoke:routes -- --base-url https://mdtero.com --json
```

Result: failed with `reason_code=site_route_smoke_failed` because `/docs/install.html` returned HTTP 200 but missed the expected `evidence_pack.context_markdown` marker. The other checked routes passed: `/`, `/auth`, `/dashboard`, `/install`, and `/admin`.

Local source and local production build do include `evidence_pack.context_markdown` in `docs/install.md` and `dist/docs/install.html`, so this is a production deployment freshness issue rather than a source/build failure. Deploy the latest `nextmdtero` build, then rerun the same route smoke command.

### Backend Public Health

- `GET https://api.mdtero.com/health` returned `200` with `status=ok`.
- `GET https://api.mdtero.com/client-config` returned `200` with the public skills manifest/install URLs.
- `GET https://api.mdtero.com/diagnostics/translation/providers` returned `404`, which indicates production backend has not yet deployed the current diagnostics router. Current backend deploy smoke now requires this unauthenticated route to return `401`; `404` is treated as a stale backend build.

### CLI/API Auth Smoke

The local checkout reports `mdtero 0.2.0a9`; `mdtero doctor --json` shows `curl_cffi`, FastMCP, and pyzotero are installed. The only local Mdtero key found in the workspace secrets has an `mdt_live` prefix but production rejects it:

- `GET https://api.mdtero.com/me/usage` returned `401` with `missing or invalid credentials`.
- `mdtero smoke --json --timeout 600 --interval 2` failed at discovery/parse because the same key was not accepted by production.

The CLI smoke now classifies production `401` responses as `authentication_required` and returns `mdtero setup --api-key <key>`, `mdtero doctor --json`, and `mdtero smoke --json --timeout 600 --interval 2` as recovery commands instead of mislabeling the run as a parser failure.
