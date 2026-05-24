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

## Failed / Needs Operator Fix

- `mdtero translate <parse-task-id> --to zh-CN --json` successfully created task `b2a1cc21-5af5-4e04-b4b4-fa88acd8ce7a`, but final status was `failed` with `reason_code=translation_provider_chain_failed`.
- The production task error summary was: `codex: translation_provider_auth_failed; mimo: translation_provider_auth_failed; claude_code: translation_provider_auth_failed; local_legacy: translation_provider_rate_limited`.
- The returned action hint correctly says operators need to refresh provider API keys, restore quota, or disable the failing provider before retrying.

## Notes

- Use `uv run --project /path/to/doi2md mdtero ...` for future smoke tests when the command should run from a temporary project directory. `uv --directory /path/to/doi2md run mdtero ...` changes the command working directory to the repo and can place downloaded artifacts under the repo.
- This smoke proves the production CLI path for discovery, DOI parsing, PDF upload with MinerU URL API, artifact download, server-side Voyage RAG, MCP briefing, and agent detection. It does not prove browser-extension interactive login or Chrome/Edge upload UI; those still need browser-level smoke.
