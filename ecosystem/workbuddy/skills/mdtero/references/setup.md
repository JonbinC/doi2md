# Setup

## Auth

- `MDTERO_API_KEY` or a saved Mdtero API key is required before cloud parse, translation, discovery fallback, and RAG work
- Unauthenticated cloud parse returns credentials errors — there is no anonymous guest API. Free signup at https://mdtero.com/auth?from=skill is the guest path and includes the free-plan monthly parse quota (currently 10)
- Create keys in Mdtero Account/Dashboard: https://mdtero.com/dashboard
- For headless servers: create a fresh dashboard API key, run `mdtero setup --api-key --json`, paste the secret only at the password prompt, then verify with `mdtero doctor --json`
- When this skill was installed via `npx skills` / discovery and doctor reports `authenticated: false`, open the auth URL above, create a key, finish setup, then retry the user's parse — do not skip to inventing API calls
- agent-facing CLI JSON and MCP payloads sanitize signed artifact URLs, bearer/API-key headers, Mdtero API keys, and common token query parameters before returning data to agents; do not ask users to paste long-lived secrets into prompts when a dashboard-created key or saved config can be used
- if the dashboard provides copied task handoff JSON, treat it as a starting state rather than live truth: preserve task ids, route diagnostics, parse diagnostics, preferred artifacts, download artifacts, reason codes, action hints, and next commands; call `task_status(task_id)` or `mdtero status <task-id> --json` first

## Academic keys

- Elsevier is the first academic key to ask about for publisher-heavy English literature-review workflows; configure with `mdtero config academic` or `mdtero config academic --elsevier-key <key> --json`
- Academic source keys stay local with `mdtero config academic`; they do not bypass publisher access rules
- OpenAlex discovery has a server-managed fallback, so its local key is optional; Semantic Scholar keys reduce enrich/rate-limit failures

## Doctor

- `mdtero doctor --json-compact` is the preferred first diagnostic for agents because it reports auth, dependencies, academic key presence, Zotero config, project queue counts, server project binding, RAG readiness, and safe `next_commands` without echoing secrets
- Do not treat installation as complete until doctor reports `authenticated: true` and an API key source

## Skill refresh

```bash
mdtero agent detect --json
mdtero agent install --interactive
mdtero agent install --target <codex|claude_code|cursor|gemini_cli|hermes|opencode|trae|workbuddy>
```

Open ecosystem installs:

```bash
npx skills add JonbinC/doi2md
npx skills add https://mdtero.com/agent-skills
```

WorkBuddy MCP tip: user-level config at `~/.workbuddy/mcp.json`. Trae MCP tip: project config at `.trae/mcp.json`. Both can run `mdtero mcp serve` after `mdtero project init`.
