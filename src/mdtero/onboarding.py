from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import MdteroConfig


ACADEMIC_OPTIONS: list[dict[str, str]] = [
    {
        "index": "1",
        "label": "Elsevier key",
        "url": "https://dev.elsevier.com/apikey/manage",
        "field": "elsevier_api_key",
        "prompt": "Elsevier API key",
    },
    {
        "index": "2",
        "label": "Wiley TDM",
        "url": "https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining",
        "field": "wiley_tdm_token",
        "prompt": "Wiley TDM token",
    },
    {
        "index": "3",
        "label": "Semantic Scholar API Key",
        "url": "https://www.semanticscholar.org/product/api#api-key-form",
        "field": "semantic_scholar_api_key",
        "prompt": "Semantic Scholar API key",
    },
]


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
        "next_commands": [
            "mdtero discover \"<topic>\" --limit 5 --json",
            "mdtero config academic --json",
            "mdtero smoke --json",
            "mdtero mcp briefing --json",
        ],
        "next_command_groups": build_next_step_command_groups(),
    }


def build_onboarding_checklist(
    *,
    authenticated: bool,
    headless: bool,
    academic: dict[str, Any],
    agent_status: list[dict[str, Any]],
    agent_detection_skipped: bool,
) -> list[dict[str, Any]]:
    configured_academic = academic.get("configured") if isinstance(academic.get("configured"), dict) else {}
    has_semantic_scholar = bool(configured_academic.get("semantic_scholar_api_key"))
    detected_agents = [item for item in agent_status if item.get("detected")]
    installed_agents = [item for item in detected_agents if item.get("installed")]
    return [
        {
            "id": "auth",
            "title": "Authenticate",
            "status": "complete" if authenticated else "needs_action",
            "primary_command": "mdtero doctor --json" if authenticated else ("mdtero setup --api-key --json" if headless else "mdtero setup"),
            "action_hint": "Browser OAuth is preferred on workstations; API-key setup is for trusted headless servers and agents.",
        },
        {
            "id": "academic_keys",
            "title": "Optional academic resource keys",
            "status": "enhanced" if any(configured_academic.values()) else "optional",
            "primary_command": "mdtero config academic",
            "action_hint": "Configure Elsevier, Wiley TDM, or Semantic Scholar keys only when you have them. Without Semantic Scholar, discovery uses server OpenAlex.",
            "links": academic.get("application_links", {}),
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
                "mdtero parse --file paper.pdf --trace --wait --timeout 300 --json",
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
            "title": "Build backend Voyage RAG",
            "status": "ready_after_parse",
            "primary_command": "mdtero rag query \"<question>\" --build-if-needed --json",
            "secondary_commands": ["mdtero rag build --json", "mdtero rag status --json"],
            "action_hint": "Voyage runs on the Mdtero backend; no local RAG provider key is required.",
        },
        {
            "id": "mcp",
            "title": "Expose context to local agents",
            "status": "ready",
            "primary_command": "mdtero mcp briefing --json",
            "secondary_commands": ["mdtero mcp serve"],
            "action_hint": "FastMCP tools expose project status, parse/download/translation commands, server RAG status, and rag_query(question).",
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
                "mdtero parse 10.48550/arXiv.1706.03762 --wait --timeout 300 --json",
                "mdtero parse https://example.org/open-paper --trace --wait --timeout 300 --json",
                "mdtero parse --file paper.pdf --trace --wait --timeout 300 --json",
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
                "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 300 --json",
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
                "mdtero rag build --json",
                "mdtero rag status --json",
                "mdtero rag query \"What are the key claims and methods?\" --build-if-needed --json",
                "mdtero mcp briefing --json",
                "mdtero mcp serve",
                "mdtero agent install --interactive",
                "mdtero tui",
            ],
        ),
    ]
    return [{"title": title, "commands": commands} for title, commands in sections]
