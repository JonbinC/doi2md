---
name: mdtero
description: Use when the user needs DOI/URL/file papers turned into structured Markdown for reading, optional translation, project research, RAG, or agent workflows.
license: MIT
compatibility: Requires network access to api.mdtero.com, the Python mdtero CLI (uv/pip), and a Mdtero API key from https://mdtero.com/dashboard. Optional Elsevier/OpenAlex/Semantic Scholar keys stay in local mdtero config.
metadata:
  homepage: https://mdtero.com
  repository: https://github.com/JonbinC/doi2md
  install: npx skills add JonbinC/doi2md
  discovery: https://mdtero.com/.well-known/agent-skills/index.json
---

# Mdtero

DOI/URL/file → structured Markdown package → optional `translate` / RAG. Prefer full-text Markdown; inspect `quality_label` before citing.

## Activate before cloud parse

Unauthenticated cloud parse is rejected. The guest path is a **free Mdtero account** (monthly free-plan parse quota — currently **10**). Guide the user through this before inventing anonymous API calls:

1. Open https://mdtero.com/auth?from=skill (email or OAuth; invite code optional)
2. In https://mdtero.com/dashboard create an API key (one-time secret)
3. Install the Python runtime if `mdtero` is missing: `uv tool install --upgrade mdtero`
4. Run `mdtero setup` (workstation) or `mdtero setup --api-key --json` (headless); paste the key only at the secure prompt — never into chat or shell history
5. Confirm with `mdtero doctor --json-compact` until `authenticated: true`
6. Run the first parse below (arXiv DOI is a safe smoke input)

In China, if PyPI is slow use the mirror command from `https://mdtero.com/install/manifest.json`.

## Install (preferred)

```bash
npx skills add JonbinC/doi2md
# or: npx skills add https://mdtero.com/agent-skills
uv tool install --upgrade mdtero
mdtero setup
mdtero doctor --json-compact
```

Refresh this skill into a detected agent workspace with `mdtero agent install --interactive` (targets: `codex`, `claude_code`, `cursor`, `gemini_cli`, `hermes`, `opencode`, `trae`, `workbuddy`).

## First parse

```bash
mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json
mdtero parse --file paper.pdf --trace --wait --timeout 600 --json
mdtero parse --batch ./papers --wait --timeout 300 --json
```

After download, inspect `quality_label` / `.low_quality.md` before citing. Prefer `xml`/`html`/`epub` sources over `abstract_only`.

## Agent rules

- Run `mdtero doctor --json-compact` (or `--json`) before parse/translate/RAG/MCP work; do not treat setup as complete until it reports `authenticated: true` and returns safe `next_commands` without echoing secrets
- Prefer `--json-compact` on `parse` / `status` / `discover` when feeding LLM context; use full `--json` only when debugging
- Follow returned `next_commands`, `reason_code`, `action_hint`, and `preferred_artifact`
- For RAG answers, use `evidence_pack.context_markdown`, `source_nodes`, and `citations` as the grounded evidence surface; treat `answer` as an extractive summary
- Paste one-time API secrets only into secure CLI prompts, never into shell commands, MCP output, logs, or chat

## Deeper guides

- Setup, auth, and academic keys: `references/setup.md`
- CLI / project / discover / translate commands: `references/cli-workflow.md`
- MCP tools and dashboard handoff: `references/mcp-workflow.md`
- Literature-review playbook: `references/literature-review.md`

## Verification

- Installation is incomplete until `mdtero doctor --json` reports `authenticated: true`
- If `mdtero` is missing or imports a top-level `service` package, repair with `uv tool install --force --reinstall mdtero` or `curl -Ls https://mdtero.com/install.sh | sh`
- On task failure, report `reason_code` and the server action hint before retrying
