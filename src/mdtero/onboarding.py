from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import MdteroConfig


ACADEMIC_OPTIONS: list[dict[str, str]] = [
    {
        "index": "1",
        "label": "Elsevier key (recommended first for publisher-heavy literature)",
        "url": "https://dev.elsevier.com/apikey/manage",
        "field": "elsevier_api_key",
        "prompt": "Elsevier API key",
        "hint": "Improves ScienceDirect/Elsevier routing when the user has valid Elsevier API access or institutional entitlement; it does not bypass publisher access rules.",
    },
    {
        "index": "2",
        "label": "Wiley TDM",
        "url": "https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining",
        "field": "wiley_tdm_token",
        "prompt": "Wiley TDM token",
        "hint": "Use when the user's Wiley access includes TDM rights.",
    },
    {
        "index": "3",
        "label": "Semantic Scholar API Key",
        "url": "https://www.semanticscholar.org/product/api#api-key-form",
        "field": "semantic_scholar_api_key",
        "prompt": "Semantic Scholar API key",
        "hint": "Improves local discovery; without it, discovery uses the backend OpenAlex fallback.",
    },
]


ONE_COMMAND_RAG_BOOTSTRAP = 'mdtero rag query "What are the strongest findings?" --build-if-needed --json'
GENERIC_RAG_QUERY_COMMAND = 'mdtero rag query "<question>" --build-if-needed --json'


def build_input_route_contract() -> dict[str, Any]:
    """Canonical local input routes shared by setup JSON, TUI, extension, and agents."""
    return {
        "schema_version": "2026-05-27",
        "goal": "choose_shortest_markdown_path",
        "server_apis": {
            "route": "/api/v1/route",
            "parse": "/api/v1/tasks/parse",
            "upload": "/api/v1/tasks/upload",
            "status": "/api/v1/tasks/{task_id}",
            "download": "/api/v1/tasks/{task_id}/download/{artifact}",
            "project_import": "/api/v1/projects/{project_id}/tasks/{task_id}/import",
            "rag_build": "/api/v1/projects/{project_id}/rag/build",
            "rag_query": "/api/v1/projects/{project_id}/rag/query",
        },
        "routes": [
            {
                "id": "doi_or_url",
                "label": "DOI or URL",
                "status": "fast_smoke",
                "best_for": ["DOI", "arXiv", "EuropePMC XML", "open HTML/XML URL"],
                "primary_command": "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json",
                "next_commands": [
                    "mdtero status <task-id> --wait --timeout 300 --json",
                    "mdtero download <task-id> paper_md --output-dir ./mdtero-output --json",
                ],
                "evidence_fields": ["route", "client_acquisition", "reason_code", "action_hint", "download_artifacts"],
                "action_hint": "Use this for a single DOI or URL when the backend route can recognize the source. Keep trace JSON for agents.",
            },
            {
                "id": "file_upload",
                "label": "PDF / EPUB / XML / HTML file",
                "status": "upload",
                "best_for": ["local PDF", "local EPUB", "saved XML", "saved HTML"],
                "primary_command": "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json",
                "next_commands": [
                    "mdtero status <task-id> --wait --timeout 600 --json",
                    "mdtero download <task-id> paper_bundle --output-dir ./mdtero-output --json",
                ],
                "evidence_fields": ["selected_provider", "parser_strategy", "reason_code", "download_artifacts"],
                "action_hint": "Use direct upload for local user files. PDFs are handled by the backend; EPUB/XML/HTML bypass browser capture when already saved.",
            },
            {
                "id": "browser_extension_handoff",
                "label": "Browser extension handoff",
                "status": "manual_capture",
                "best_for": ["website OAuth", "campus network", "logged-in browser session", "publisher challenge", "human-selected PDF/EPUB"],
                "primary_command": "mdtero parse <doi-or-current-page-url> --trace --wait --timeout 300 --json",
                "next_commands": [
                    "mdtero parse --file <saved-browser-artifact.pdf|epub|html|xml> --trace --wait --timeout 600 --json",
                    "mdtero mcp briefing --json",
                ],
                "evidence_fields": ["client_acquisition", "reason_code", "action_hint", "next_commands"],
                "action_hint": "Start in the extension when browser state matters, then hand the DOI, URL, or saved artifact back to the CLI/MCP path.",
            },
            {
                "id": "rag_mcp_after_parse",
                "label": "RAG / MCP after parse",
                "status": "after_parse",
                "best_for": ["completed Markdown", "project synthesis", "local agent context", "citation-preserving answers"],
                "primary_command": ONE_COMMAND_RAG_BOOTSTRAP,
                "next_commands": [
                    "mdtero project ingest --json",
                    ONE_COMMAND_RAG_BOOTSTRAP,
                    "mdtero rag status --json",
                    "mdtero rag build --wait --json",
                    GENERIC_RAG_QUERY_COMMAND,
                    "mdtero mcp briefing --json",
                    "mdtero mcp serve",
                ],
                "evidence_fields": ["answer", "citations", "source_nodes", "evidence_pack.context_markdown", "citation_contract"],
                "action_hint": "Use the one-command bootstrap query after succeeded Markdown artifacts; it can bind/import/build backend RAG before handing the same local project context to FastMCP.",
            },
        ],
        "separate_smoke_required": ["pdf_upload", "epub_upload", "browser_extension_mv3"],
    }


def build_academic_onboarding_summary(cfg: MdteroConfig, *, path: Path, saved: bool) -> dict[str, Any]:
    configured = {
        "elsevier_api_key": bool((cfg.academic.elsevier_api_key or "").strip()),
        "wiley_tdm_token": bool((cfg.academic.wiley_tdm_token or "").strip()),
        "semantic_scholar_api_key": bool((cfg.academic.semantic_scholar_api_key or "").strip()),
    }
    discover_source = "local_semantic_scholar" if configured["semantic_scholar_api_key"] else "server_openalex"
    discover_hint = (
        "Semantic Scholar is configured; discovery tries the local Semantic Scholar API first and falls back to server OpenAlex when needed."
        if configured["semantic_scholar_api_key"]
        else "Semantic Scholar is not configured; discovery uses the server OpenAlex fallback."
    )
    return {
        "status": "saved" if saved else "current",
        "config_path": str(path),
        "configured": configured,
        "discover_source": discover_source,
        "discover_behavior": {
            "semantic_scholar": "local_first" if configured["semantic_scholar_api_key"] else "not_configured",
            "fallback": "server_openalex",
            "action_hint": discover_hint,
        },
        "application_links": {
            str(option["field"]): option["url"] for option in ACADEMIC_OPTIONS
        },
        "recommended_order": ["elsevier_api_key", "semantic_scholar_api_key", "wiley_tdm_token"],
        "priority_hints": {
            str(option["field"]): option["hint"] for option in ACADEMIC_OPTIONS
        },
        "elsevier_guidance": {
            "status": "configured" if configured["elsevier_api_key"] else "recommended",
            "action_hint": (
                "Elsevier is configured. Keep using `mdtero doctor --json` and parse trace output to confirm the selected route for each paper."
                if configured["elsevier_api_key"]
                else "For English literature-review work, configure an Elsevier key first when the user has ScienceDirect/Elsevier access. It improves publisher routing but does not bypass licensed-access requirements."
            ),
            "configure_command": "mdtero config academic --elsevier-key <key> --json",
        },
        "next_commands": [
            "mdtero discover \"<topic>\" --limit 5 --json",
            "mdtero config academic --json",
            "mdtero smoke --json",
            "mdtero mcp briefing --json",
        ],
        "input_routes": build_input_route_contract(),
        "next_command_groups": build_next_step_command_groups(),
    }


def build_onboarding_checklist(
    *,
    authenticated: bool,
    headless: bool,
    academic: dict[str, Any],
    dependencies: dict[str, Any] | None = None,
    agent_status: list[dict[str, Any]],
    agent_detection_skipped: bool,
) -> list[dict[str, Any]]:
    configured_academic = academic.get("configured") if isinstance(academic.get("configured"), dict) else {}
    has_semantic_scholar = bool(configured_academic.get("semantic_scholar_api_key"))
    detected_agents = [item for item in agent_status if item.get("detected")]
    installed_agents = [item for item in detected_agents if item.get("installed")]
    dependencies = dependencies or {}
    dependency_ready = bool(dependencies.get("ready"))
    missing_dependencies = [str(value) for value in dependencies.get("missing") or []]
    return [
        {
            "id": "auth",
            "title": "Authenticate",
            "status": "complete" if authenticated else "needs_action",
            "primary_command": "mdtero doctor --json" if authenticated else ("mdtero setup --api-key --json" if headless else "mdtero setup"),
            "action_hint": "Browser OAuth is preferred on workstations; API-key setup is for trusted headless servers and agents.",
        },
        {
            "id": "local_dependencies",
            "title": "Local capture, Zotero, and MCP dependencies",
            "status": "ready" if dependency_ready else "needs_install",
            "primary_command": "mdtero doctor --json" if dependency_ready else "uv tool install --force --reinstall git+https://github.com/JonbinC/doi2md.git",
            "action_hint": (
                "curl_cffi, FastMCP, and pyzotero are importable; local acquisition, MCP, and Zotero workflows are available."
                if dependency_ready
                else "Missing dependency modules: " + ", ".join(missing_dependencies or ["unknown"]) + ". Reinstall or upgrade the Python/uv Mdtero client before relying on local capture, MCP, or Zotero."
            ),
            "required_modules": ["curl_cffi.requests", "fastmcp", "pyzotero"],
        },
        {
            "id": "academic_keys",
            "title": "Academic source keys (Elsevier first)",
            "status": "elsevier_ready" if configured_academic.get("elsevier_api_key") else ("partial" if any(configured_academic.values()) else "recommended"),
            "primary_command": "mdtero config academic",
            "action_hint": "For publisher-heavy literature reviews, ask whether the user can provide an Elsevier API key and configure it first. Academic keys stay local; without Semantic Scholar, discovery uses server OpenAlex.",
            "links": academic.get("application_links", {}),
            "recommended_order": academic.get("recommended_order", ["elsevier_api_key", "semantic_scholar_api_key", "wiley_tdm_token"]),
            "elsevier_guidance": academic.get("elsevier_guidance", {}),
        },
        {
            "id": "discovery",
            "title": "Discover papers",
            "status": "local_semantic_scholar" if has_semantic_scholar else "server_openalex",
            "primary_command": "mdtero discover \"<topic>\" --limit 5 --interactive",
            "action_hint": "Use space-bar multi-select in interactive discovery, or `--add --select 1,3 --json` for agent-safe project intake.",
        },
        {
            "id": "project",
            "title": "Create a local project",
            "status": "recommended",
            "primary_command": "mdtero project init --name literature-review",
            "action_hint": "Project mode tracks DOI/file queues, task ids, downloads, Zotero imports, server RAG binding, and MCP context.",
        },
        {
            "id": "parse",
            "title": "Parse DOI, URL, PDF, EPUB, XML, or HTML",
            "status": "ready",
            "primary_command": "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json",
            "secondary_commands": [
                "mdtero parse --file paper.pdf --trace --wait --timeout 600 --json",
                "mdtero parse --batch ./papers --wait --timeout 300 --json",
                "mdtero project parse --wait --timeout 300 --json",
            ],
            "action_hint": "Use trace output to preserve route, client_acquisition, raw upload, reason_code, action_hint, and download_artifacts for agents.",
        },
        {
            "id": "zotero",
            "title": "Connect Zotero",
            "status": "optional",
            "primary_command": "mdtero config zotero",
            "secondary_commands": ["mdtero zotero import --limit 20", "mdtero zotero sync"],
            "action_hint": "Import is read-first project intake; sync should be run deliberately after reviewing local project state.",
        },
        {
            "id": "rag",
            "title": "Build backend RAG",
            "status": "ready_after_parse",
            "primary_command": ONE_COMMAND_RAG_BOOTSTRAP,
            "secondary_commands": [GENERIC_RAG_QUERY_COMMAND, "mdtero rag status --json", "mdtero rag build --wait --json"],
            "action_hint": "RAG runs on the Mdtero backend; no local RAG provider key or manual server project id is required.",
        },
        {
            "id": "mcp",
            "title": "Expose context to local agents",
            "status": "ready",
            "primary_command": "mdtero mcp briefing --json",
            "secondary_commands": ["mdtero mcp serve"],
            "action_hint": "FastMCP tools expose project status, parse/download/translation commands, server RAG status, waited server_rag_build, and rag_query(question).",
        },
        {
            "id": "agent_skills",
            "title": "Install local agent skills",
            "status": "skipped_headless" if agent_detection_skipped else ("installed" if installed_agents and len(installed_agents) == len(detected_agents) else "needs_selection" if detected_agents else "not_detected"),
            "primary_command": "mdtero agent install --interactive",
            "secondary_commands": ["mdtero agent detect --json"],
            "action_hint": "Use space to multi-select detected Codex, Claude, Gemini, Hermes, or OpenCode workspaces.",
        },
    ]


def build_next_step_command_groups() -> list[dict[str, Any]]:
    sections = [
        (
            "Verify this workstation",
            [
                "mdtero doctor --json",
                "mdtero config academic --json",
                "mdtero agent detect --json",
            ],
        ),
        (
            "One-shot launch smoke",
            [
                "mdtero smoke --json",
                "mdtero smoke --doi 10.48550/arXiv.1706.03762 --wait --timeout 300 --json",
                "mdtero mcp briefing --json",
            ],
        ),
        (
            "Start a local project",
            [
                "mdtero project init --name literature-review",
                "mdtero discover \"graph neural networks\" --limit 5 --interactive",
                "mdtero discover \"graph neural networks\" --limit 5 --add --select 1,3 --json",
                "mdtero project import-bib references.bib",
            ],
        ),
        (
            "Parse papers and files",
            [
                "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json",
                "mdtero parse https://example.org/open-paper --trace --wait --timeout 300 --json",
                "mdtero parse --file paper.pdf --trace --wait --timeout 600 --json",
                "mdtero parse --batch ./papers --wait --timeout 300 --json",
                "mdtero project parse --wait --timeout 300 --json",
                "mdtero project refresh --wait --timeout 300 --json",
                "mdtero project download --output-dir ./mdtero-output --json",
            ],
        ),
        (
            "Browser extension handoff",
            [
                "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
                "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json",
                "mdtero status <task-id> --wait --timeout 300 --json",
                "mdtero download <task-id> paper_md --output-dir ./mdtero-output --json",
                "mdtero project ingest --json",
                "mdtero rag query \"<question>\" --build-if-needed --json",
                "mdtero mcp briefing --json",
            ],
        ),
        (
            "Translate completed Markdown",
            [
                "mdtero translate <parse-task-id> --to zh-CN --wait --timeout 600 --json",
                "mdtero translate paper.md --to zh-CN --wait --timeout 600 --json",
                "mdtero download <translation-task-id> translated_md --output-dir ./mdtero-output --json",
            ],
        ),
        (
            "Zotero",
            [
                "mdtero config zotero",
                "mdtero zotero import --limit 20",
                "mdtero zotero sync",
            ],
        ),
        (
            "Server RAG and local agents",
            [
                ONE_COMMAND_RAG_BOOTSTRAP,
                "mdtero rag status --json",
                "mdtero rag build --wait --json",
                GENERIC_RAG_QUERY_COMMAND,
                "mdtero mcp briefing --json",
                "mdtero mcp serve",
                "mdtero agent install --interactive",
                "mdtero tui",
            ],
        ),
    ]
    return [{"title": title, "commands": commands} for title, commands in sections]
