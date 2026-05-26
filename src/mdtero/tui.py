from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static

from .agent import detect_target_status
from .client import MdteroClient
from .config import MdteroConfig, load_config
from .mcp import build_agent_briefing, build_agent_commands, build_rag_context
from .projects import ProjectState, ensure_project

WORKSTATION_SETUP_COMMAND = "mdtero setup"
HEADLESS_SETUP_COMMAND = "mdtero setup --api-key"


def build_dashboard_model(
    *,
    project_root: Path | None = None,
    config: MdteroConfig | None = None,
    agent_root: Path | None = None,
    rag_status_fetcher: Any | None = None,
) -> dict[str, Any]:
    root = project_root or Path.cwd()
    cfg = config or load_config()
    project = ensure_project(root)
    agent_status = detect_target_status(agent_root)
    detected_agents = [agent for agent in agent_status if agent.detected]
    installed_agents = [agent for agent in agent_status if agent.installed]
    pending_agent_installs = [agent for agent in agent_status if agent.detected and not agent.installed]
    pending = [paper for paper in project.papers if paper.status in {"pending", "created"} and not paper.task_id]
    running = [paper for paper in project.papers if paper.task_id and paper.status not in {"succeeded", "failed"}]
    succeeded = [paper for paper in project.papers if paper.status == "succeeded"]
    failed = [paper for paper in project.papers if paper.status == "failed"]
    rag = _tui_rag_payload(build_rag_context(root), project.server_project_id, rag_status_fetcher=rag_status_fetcher)
    commands = build_agent_commands(root)["commands"]
    briefing = build_agent_briefing(root, rag_status_fetcher=rag_status_fetcher, config=cfg, agent_root=agent_root)
    next_steps = _next_steps(cfg, project, rag, commands)
    command_palette = _command_palette_payload(
        cfg=cfg,
        project=project,
        rag=rag,
        commands=commands,
        next_steps=next_steps,
    )
    extension_handoff = _extension_handoff_payload(commands)
    launch_bundle = _launch_bundle_payload(
        cfg=cfg,
        project=project,
        rag=rag,
        commands=commands,
        next_steps=next_steps,
        extension_handoff=extension_handoff,
    )
    handoff = {
        "ready_artifacts": briefing["ready_artifacts"],
        "blocked_items": briefing["blocked_items"],
        "active_items": briefing["active_items"],
        "recommended_next_commands": briefing["recommended_next_commands"],
    }
    return {
        "health": _health_payload(
            cfg=cfg,
            project=project,
            rag=rag,
            detected_agents=detected_agents,
            installed_agents=installed_agents,
            pending_agent_installs=pending_agent_installs,
            handoff=handoff,
            next_steps=next_steps,
        ),
        "account": {
            "api_base_url": cfg.api_base_url,
            "authenticated": cfg.is_authenticated,
            "auth_source": cfg.api_key_source,
            "auth_hint": WORKSTATION_SETUP_COMMAND if not cfg.is_authenticated else "mdtero doctor --json",
        },
        "academic": {
            "elsevier": bool(cfg.academic.elsevier_api_key),
            "wiley_tdm": bool(cfg.academic.wiley_tdm_token),
            "semantic_scholar": bool(cfg.academic.semantic_scholar_api_key),
            "discover_source": "local Semantic Scholar" if cfg.has_semantic_scholar_key else "server OpenAlex",
            "configure_command": "mdtero config academic",
        },
        "project": _project_payload(project, pending=pending, running=running, succeeded=succeeded, failed=failed),
        "rag": rag,
        "zotero": {
            "configured": bool(cfg.zotero.library_id and cfg.zotero.api_key),
            "library_id": cfg.zotero.library_id,
            "library_type": cfg.zotero.library_type,
            "commands": ["mdtero config zotero", "mdtero zotero import", "mdtero zotero sync"],
        },
        "agents": {
            "detected": [agent.target for agent in detected_agents],
            "labels": [agent.label for agent in detected_agents],
            "detected_count": len(detected_agents),
            "installed_count": len(installed_agents),
            "pending_install_count": len(pending_agent_installs),
            "pending_install_labels": [agent.label for agent in pending_agent_installs],
            "status": [
                {
                    "target": agent.target,
                    "label": agent.label,
                    "detected": agent.detected,
                    "installed": agent.installed,
                    "skill_path": agent.skill_path,
                    "install_command": agent.install_command,
                    "selection_index": agent.selection_index,
                }
                for agent in agent_status
            ],
            "detect_command": commands["agent_detect"],
            "install_command": commands["agent_install"],
            "fallback_install_command": "mdtero agent install --target codex --json",
            "interactive_hint": "Use spaces to multi-select detected workspaces in `mdtero agent install --interactive`.",
        },
        "mcp": {
            "briefing_command": commands["mcp_briefing"],
            "serve_command": commands["serve_mcp"],
            "primary_tool": "agent_briefing",
            "tools": briefing["mcp_tools"],
            "task_tools": _mcp_task_tools_payload(briefing["mcp_tools"]),
            "tool_plan": _mcp_tool_plan_payload(briefing.get("mcp_tool_plan") or []),
            "recommended_next_commands": briefing["recommended_next_commands"],
        },
        "extension_handoff": extension_handoff,
        "launch_bundle": launch_bundle,
        "handoff": handoff,
        "command_palette": command_palette,
        "commands": commands,
        "next_steps": next_steps,
        "operator_summary": _operator_summary(
            cfg=cfg,
            project=project,
            rag=rag,
            handoff=handoff,
            detected_agents=detected_agents,
            installed_agents=installed_agents,
        ),
        "shortcuts": _shortcuts_payload(commands),
    }


def render_dashboard_text(model: dict[str, Any]) -> Group:
    return Group(
        _hero_panel(model),
        Columns([_account_panel(model), _project_panel(model)], equal=True, expand=True),
        Columns([_rag_panel(model), _integration_panel(model)], equal=True, expand=True),
        _mcp_tool_plan_panel(model),
        _command_palette_panel(model),
        _launch_bundle_panel(model),
        Columns([_operator_panel(model), _extension_handoff_panel(model)], equal=True, expand=True),
        _shortcuts_panel(model),
        _handoff_panel(model),
        _next_steps_panel(model),
    )


class MdteroTui(App):
    BINDINGS = [
        ("r", "refresh_dashboard", "Refresh"),
        ("d", "doctor", "Doctor"),
        ("p", "parse_pending", "Parse"),
        ("g", "rag_status", "RAG"),
        ("m", "mcp_briefing", "MCP"),
        ("q", "quit", "Quit"),
    ]

    CSS = """
    Screen { background: #fcf7f1; color: #2f1a12; }
    #dashboard { padding: 1 2; }
    """

    def __init__(self, *, project_root: Path | None = None) -> None:
        super().__init__()
        self.project_root = project_root or Path.cwd()

    def _build_renderable(self) -> Group:
        return render_dashboard_text(build_dashboard_model(project_root=self.project_root))

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(self._build_renderable(), id="dashboard")
        yield Footer()

    def action_refresh_dashboard(self) -> None:
        self.query_one("#dashboard", Static).update(self._build_renderable())
        self.notify("Dashboard refreshed")

    def action_doctor(self) -> None:
        self.notify("mdtero doctor --json")

    def action_parse_pending(self) -> None:
        self.notify("mdtero project parse --wait --timeout 300 --json")

    def action_rag_status(self) -> None:
        self.notify("mdtero rag status --json")

    def action_mcp_briefing(self) -> None:
        self.notify("mdtero mcp briefing --json")


def _project_payload(
    project: ProjectState,
    *,
    pending: list[Any],
    running: list[Any],
    succeeded: list[Any],
    failed: list[Any],
) -> dict[str, Any]:
    return {
        "name": project.name,
        "server_project_id": project.server_project_id,
        "paper_count": len(project.papers),
        "pending_count": len(pending),
        "running_count": len(running),
        "succeeded_count": len(succeeded),
        "failed_count": len(failed),
        "recent": [
            {
                "input": paper.input,
                "task_id": paper.task_id,
                "status": paper.status,
                "reason_code": paper.reason_code,
                "action_hint": paper.action_hint,
                "artifact": paper.artifact,
                "translation_attempts": paper.translation_attempts,
            }
            for paper in project.papers[-6:]
        ],
    }


def _tui_rag_payload(local_rag: dict[str, Any], server_project_id: str | None, *, rag_status_fetcher: Any | None = None) -> dict[str, Any]:
    payload = dict(local_rag)
    if not server_project_id:
        return payload
    fetcher = rag_status_fetcher
    if fetcher is None:
        fetcher = MdteroClient().rag_status
    try:
        server_status = fetcher(server_project_id)
    except Exception as exc:
        payload["server_status"] = "unavailable"
        payload["server_reason_code"] = "server_rag_status_unavailable"
        payload["server_error_type"] = exc.__class__.__name__
        return payload
    summary = server_status.get("summary") if isinstance(server_status.get("summary"), dict) else {}
    next_commands = [str(command).strip() for command in server_status.get("next_commands") or [] if str(command).strip()]
    payload["server_status"] = server_status.get("status")
    payload["server_reason_code"] = server_status.get("reason_code")
    payload["server_summary"] = summary
    payload["ready"] = server_status.get("status") == "ready"
    if server_status.get("reason_code"):
        payload["reason_code"] = str(server_status["reason_code"])
    for key in ["selected_provider", "provider_state", "provider_configured", "voyage_configured"]:
        if key in server_status:
            payload[key] = server_status.get(key)
    payload["embedding_model"] = server_status.get("embedding_model") or summary.get("embedding_model")
    if server_status.get("action_hint"):
        payload["action_hint"] = str(server_status["action_hint"])
    if next_commands:
        payload["next_commands"] = next_commands
    payload["server_agent_summary"] = {
        "status": payload.get("server_status"),
        "reason_code": payload.get("server_reason_code"),
        "selected_provider": payload.get("selected_provider"),
        "provider_state": payload.get("provider_state"),
        "provider_configured": payload.get("provider_configured", payload.get("voyage_configured")),
        "embedding_model": payload.get("embedding_model"),
        "embedded_count": summary.get("embedded_count", 0),
        "chunk_count": summary.get("chunk_count", 0),
        "pending_embedding_count": summary.get("pending_embedding_count", 0),
    }
    return payload


def _next_steps(cfg: MdteroConfig, project: ProjectState, rag: dict[str, Any], commands: dict[str, str]) -> list[str]:
    rag_build_command = commands.get("rag_build") or commands.get("bootstrap_rag") or "mdtero rag build --json"
    if not cfg.is_authenticated:
        return [WORKSTATION_SETUP_COMMAND, "mdtero doctor --json", HEADLESS_SETUP_COMMAND]
    if not project.papers:
        return ["mdtero project add 10.48550/arXiv.1706.03762 --json", commands["parse_pending"]]
    if project.papers and any(paper.status in {"pending", "created"} and not paper.task_id for paper in project.papers):
        return [commands["parse_pending"], commands["refresh"]]
    if not project.server_project_id:
        return [commands["bootstrap_rag"], "mdtero rag status --json", "mdtero rag query \"<question>\" --build-if-needed --json"]
    if rag.get("server_status") == "ready":
        return ["mdtero rag status --json", "mdtero rag query \"<question>\" --build-if-needed --json", commands["mcp_briefing"], commands["serve_mcp"]]
    if rag.get("server_status") in {"not_ready", "partial"}:
        return ["mdtero rag status --json", rag_build_command, "mdtero rag query \"<question>\" --build-if-needed --json"]
    if rag.get("ready_for_ingest_count", 0) > 0:
        return [rag_build_command, "mdtero rag status --json", "mdtero rag query \"<question>\" --build-if-needed --json"]
    return ["mdtero discover \"your topic\" --json", "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json"]


def _health_payload(
    *,
    cfg: MdteroConfig,
    project: ProjectState,
    rag: dict[str, Any],
    detected_agents: list[Any],
    installed_agents: list[Any],
    pending_agent_installs: list[Any],
    handoff: dict[str, Any],
    next_steps: list[str],
) -> dict[str, Any]:
    ready_artifacts = handoff.get("ready_artifacts") or []
    blocked_items = handoff.get("blocked_items") or []
    active_items = handoff.get("active_items") or []
    primary_next_command = next_steps[0] if next_steps else "mdtero doctor --json"

    if not cfg.is_authenticated:
        status = "needs_auth"
        headline = "Needs login"
        detail = "Authenticate before parse, translation, discovery fallback, RAG, or MCP."
    elif blocked_items:
        status = "needs_attention"
        headline = "Needs attention"
        detail = f"{len(blocked_items)} failed item(s) need status review or retry."
    elif not project.papers:
        status = "empty_project"
        headline = "Ready to start"
        detail = "Add a DOI, run discovery, import BibTeX, or connect Zotero."
    elif rag.get("server_status") == "ready":
        status = "ready"
        headline = "Project RAG ready"
        detail = "Server-side Voyage RAG is ready for queries and MCP agent context."
    elif ready_artifacts:
        status = "results_ready"
        headline = "Results ready"
        detail = f"{len(ready_artifacts)} parsed artifact(s) can be downloaded or ingested into RAG."
    elif active_items:
        status = "working"
        headline = "Work in progress"
        detail = f"{len(active_items)} active or queued item(s) need parse/refresh."
    else:
        status = "configured"
        headline = "Configured"
        detail = "Run the next command to continue the project workflow."

    return {
        "status": status,
        "headline": headline,
        "detail": detail,
        "primary_next_command": primary_next_command,
        "cards": [
            {"label": "Account", "value": "ok" if cfg.is_authenticated else "login required"},
            {"label": "Project", "value": f"{len(project.papers)} papers"},
            {"label": "RAG", "value": str(rag.get("server_status") or rag.get("reason_code") or "local")},
            {"label": "Agents", "value": f"{len(installed_agents)}/{len(detected_agents)} installed" if detected_agents else "none detected"},
        ],
        "counts": {
            "ready_artifacts": len(ready_artifacts),
            "blocked_items": len(blocked_items),
            "active_items": len(active_items),
            "pending_agent_installs": len(pending_agent_installs),
        },
    }


def _operator_summary(
    *,
    cfg: MdteroConfig,
    project: ProjectState,
    rag: dict[str, Any],
    handoff: dict[str, Any],
    detected_agents: list[Any],
    installed_agents: list[Any],
) -> list[dict[str, str]]:
    ready_artifacts = handoff.get("ready_artifacts") or []
    blocked_items = handoff.get("blocked_items") or []
    active_items = handoff.get("active_items") or []
    rows: list[dict[str, str]] = []

    rows.append(
        {
            "area": "Account",
            "state": "ready" if cfg.is_authenticated else "missing",
            "detail": cfg.api_key_source if cfg.is_authenticated else "run mdtero setup",
        }
    )
    rows.append(
        {
            "area": "Project",
            "state": "ready" if project.papers else "empty",
            "detail": f"{len(project.papers)} paper(s), {len(active_items)} active, {len(blocked_items)} blocked",
        }
    )
    rows.append(
        {
            "area": "Artifacts",
            "state": "ready" if ready_artifacts else "none",
            "detail": f"{len(ready_artifacts)} downloadable result(s)",
        }
    )
    rows.append(
        {
            "area": "RAG",
            "state": str(rag.get("server_status") or rag.get("reason_code") or "local"),
            "detail": f"{rag.get('ready_for_ingest_count', 0)} local result(s) ready for ingest",
        }
    )
    rows.append(
        {
            "area": "Agents",
            "state": "ready" if detected_agents and len(installed_agents) == len(detected_agents) else "setup",
            "detail": f"{len(installed_agents)}/{len(detected_agents)} detected skill(s) installed",
        }
    )
    return rows


def _shortcuts_payload(commands: dict[str, str]) -> list[dict[str, str]]:
    return [
        {"key": "r", "label": "refresh", "action": "refresh_dashboard", "command": "reload dashboard state"},
        {"key": "d", "label": "doctor", "action": "doctor", "command": "mdtero doctor --json"},
        {"key": "p", "label": "parse", "action": "parse_pending", "command": commands.get("parse_pending", "mdtero project parse --wait --timeout 300 --json")},
        {"key": "g", "label": "rag", "action": "rag_status", "command": commands.get("rag_status", "mdtero rag status --json")},
        {"key": "m", "label": "mcp", "action": "mcp_briefing", "command": commands.get("mcp_briefing", "mdtero mcp briefing --json")},
        {"key": "q", "label": "quit", "action": "quit", "command": "close TUI"},
    ]


def _mcp_task_tools_payload(tool_names: list[str]) -> list[dict[str, str]]:
    labels = {
        "submit_parse": "Submit DOI/URL parse and optionally wait for completion",
        "task_status": "Poll task status and sync local project state",
        "download_artifact": "Download preferred Markdown/ZIP/translation artifact for a task",
        "request_translation": "Translate parse task or Markdown with provider-attempt diagnostics",
        "rag_query": "Bootstrap/query server-side Voyage RAG with evidence pack",
    }
    return [
        {"tool": name, "purpose": labels[name]}
        for name in labels
        if name in tool_names
    ]


def _mcp_tool_plan_payload(plan: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in plan:
        if not isinstance(item, dict):
            continue
        failure_fields = item.get("failure_fields")
        if not isinstance(failure_fields, list):
            failure_fields = []
        rows.append({
            "step": str(item.get("step") or "-"),
            "tool": str(item.get("tool") or "-"),
            "when": str(item.get("when") or "-")[:140],
            "arguments": item.get("arguments") if isinstance(item.get("arguments"), dict) else {},
            "success_signal": str(item.get("success_signal") or "")[:140],
            "failure_fields": [str(field) for field in failure_fields if str(field).strip()],
            "next_commands": [str(command) for command in item.get("next_commands") or [] if str(command).strip()],
        })
    return rows


def _extension_handoff_payload(commands: dict[str, str]) -> dict[str, Any]:
    command_plan = _extension_handoff_commands(commands)
    return {
        "browser_scope": [
            "website OAuth login",
            "current-page parse from an already-open article",
            "PDF/EPUB upload",
            "task polling, translation, and download",
        ],
        "cli_scope": [
            "curl_cffi route acquisition for planned HTML/XML/EPUB/PDF sources",
            "raw artifact upload with --trace client_acquisition details",
            "project queue/status/download/RAG/MCP commands for local agents",
        ],
        "handoff_triggers": [
            "publisher challenge or JavaScript verification page",
            "campus-network or logged-in browser state needs manual confirmation",
            "extension capture cannot access the current tab or direct download URL",
        ],
        "commands": command_plan,
        "primary_commands": command_plan[:2],
        "visible_fields": ["client_acquisition", "reason_code", "action_hint", "download_artifacts", "next_commands"],
    }


def _extension_handoff_commands(commands: dict[str, str]) -> list[str]:
    return [
        commands.get("extension_handoff_url") or commands.get("parse_doi_or_url") or "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
        commands.get("extension_handoff_file") or commands.get("parse_file") or "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 300 --json",
        "mdtero status <task-id> --wait --timeout 300 --json",
        "mdtero download <task-id> paper_md --output-dir ./mdtero-output --json",
        commands.get("mcp_briefing") or "mdtero mcp briefing --json",
    ]


def _launch_bundle_payload(
    *,
    cfg: MdteroConfig,
    project: ProjectState,
    rag: dict[str, Any],
    commands: dict[str, str],
    next_steps: list[str],
    extension_handoff: dict[str, Any],
) -> dict[str, Any]:
    setup_commands = [
        commands.get("doctor") or "mdtero doctor --json",
        commands.get("setup") or WORKSTATION_SETUP_COMMAND,
        commands.get("login_api_key") or HEADLESS_SETUP_COMMAND,
        commands.get("agent_detect") or "mdtero agent detect --json",
        commands.get("agent_install") or "mdtero agent install --interactive",
    ]
    parse_commands = [
        commands.get("discover") or 'mdtero discover "your topic" --json',
        commands.get("parse_doi_or_url") or "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
        commands.get("parse_file") or "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 300 --json",
        commands.get("parse_batch") or "mdtero parse --batch ./papers --wait --timeout 300 --json",
    ]
    project_commands = [
        commands.get("project_init_named") or commands.get("project_init") or "mdtero project init --name literature-review",
        commands.get("parse_pending") or "mdtero project parse --wait --timeout 300 --json",
        commands.get("refresh") or "mdtero project refresh --wait --timeout 300 --json",
        commands.get("download_markdown") or "mdtero project download --output-dir ./mdtero-output --json",
        commands.get("zotero_import") or "mdtero zotero import --json",
        commands.get("zotero_sync") or "mdtero zotero sync --json",
    ]
    rag_commands = _dedupe_commands([
        "mdtero project ingest --json" if project.server_project_id else "mdtero rag build --json",
        *(rag.get("next_commands") if isinstance(rag.get("next_commands"), list) else []),
        commands.get("rag_status") or "mdtero rag status --json",
        commands.get("rag_build") or commands.get("bootstrap_rag") or "mdtero rag build --json",
        commands.get("rag_query") or 'mdtero rag query "<question>" --build-if-needed --json',
        commands.get("mcp_briefing") or "mdtero mcp briefing --json",
        commands.get("serve_mcp") or "mdtero mcp serve",
    ])
    groups = [
        {
            "label": "Setup",
            "purpose": "Authenticate, verify the local runtime, and install agent skills when a workspace is detected.",
            "commands": _dedupe_commands(setup_commands if not cfg.is_authenticated else [setup_commands[0], *setup_commands[3:]]),
        },
        {
            "label": "Parse",
            "purpose": "Submit one DOI/URL, local file, or batch directory with traceable task status.",
            "commands": _dedupe_commands(parse_commands),
        },
        {
            "label": "Project",
            "purpose": "Manage the local library, refresh task state, download artifacts, and sync Zotero metadata/results.",
            "commands": _dedupe_commands(project_commands),
        },
        {
            "label": "RAG + MCP",
            "purpose": "Create or reuse the server Voyage RAG project, query grounded evidence, then brief local FastMCP agents.",
            "commands": rag_commands,
        },
        {
            "label": "Extension handoff",
            "purpose": "Recover from publisher challenges, campus sessions, or browser-saved files without losing reason_code/action_hint.",
            "commands": _dedupe_commands([str(command) for command in extension_handoff.get("commands") or []]),
        },
    ]
    return {
        "copy_hint": "Copy one group into a terminal or agent prompt; commands are ordered and JSON-first where possible.",
        "primary_group": "Setup" if not cfg.is_authenticated else ("RAG + MCP" if project.papers else "Parse"),
        "next_commands": _dedupe_commands(next_steps),
        "groups": groups,
    }


def _dedupe_commands(commands: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for command in commands:
        value = str(command or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _command_palette_payload(
    *,
    cfg: MdteroConfig,
    project: ProjectState,
    rag: dict[str, Any],
    commands: dict[str, str],
    next_steps: list[str],
) -> list[dict[str, Any]]:
    next_step_set = set(next_steps)
    rag_build_command = commands.get("rag_build") or commands.get("bootstrap_rag") or "mdtero rag build --json"
    rows = [
        {
            "area": "Setup",
            "use": "Authenticate this workstation with browser OAuth" if not cfg.is_authenticated else "Verify local runtime",
            "command": commands.get("setup") if not cfg.is_authenticated else commands.get("doctor"),
        },
        {"area": "Discover", "use": "Find papers and add selections", "command": commands.get("discover")},
        {"area": "Parse", "use": "Single DOI or URL", "command": commands.get("parse_doi_or_url")},
        {"area": "Parse", "use": "Single local PDF/EPUB/XML/HTML", "command": commands.get("parse_file")},
        {"area": "Parse", "use": "Batch upload local files", "command": commands.get("parse_batch")},
        {"area": "Extension", "use": "Handoff challenged page or saved file to CLI", "command": commands.get("extension_handoff_url")},
        {"area": "Extension", "use": "Upload a browser-saved PDF/EPUB/XML/HTML", "command": commands.get("extension_handoff_file")},
        {"area": "Project", "use": "Parse pending queue", "command": commands.get("parse_pending")},
        {"area": "Project", "use": "Refresh task statuses", "command": commands.get("refresh")},
        {"area": "Project", "use": "Download ready Markdown/ZIP", "command": commands.get("download_markdown")},
        {"area": "Zotero", "use": "Import Zotero metadata", "command": commands.get("zotero_import")},
        {"area": "Zotero", "use": "Sync Mdtero results back", "command": commands.get("zotero_sync")},
        {"area": "RAG", "use": "Create/bind/import/build Voyage index", "command": rag_build_command},
        {"area": "RAG", "use": "Check server RAG readiness", "command": commands.get("rag_status")},
        {"area": "RAG", "use": "Ask grounded project question", "command": commands.get("rag_query")},
        {"area": "MCP", "use": "Tool: submit_parse(input_value)", "command": "submit_parse"},
        {"area": "MCP", "use": "Tool: task_status(task_id)", "command": "task_status"},
        {"area": "MCP", "use": "Tool: download_artifact(task_id)", "command": "download_artifact"},
        {"area": "MCP", "use": "Tool: request_translation(task_id_or_markdown_path)", "command": "request_translation"},
        {"area": "MCP", "use": "One-shot agent context", "command": commands.get("mcp_briefing")},
        {"area": "MCP", "use": "Serve FastMCP tools", "command": commands.get("serve_mcp")},
        {"area": "Agents", "use": "Detect local workspaces", "command": commands.get("agent_detect")},
        {"area": "Agents", "use": "Install selected skills", "command": commands.get("agent_install")},
    ]
    if not cfg.is_authenticated:
        rows.insert(1, {"area": "Setup", "use": "Headless or remote shell fallback", "command": commands.get("login_api_key") or HEADLESS_SETUP_COMMAND})
    if not project.papers:
        rows.insert(1, {"area": "Project", "use": "Initialize or rename project", "command": commands.get("project_init_named") or commands.get("project_init")})
    if rag.get("ready_for_ingest_count", 0) > 0 or project.server_project_id:
        rows.insert(11, {"area": "RAG", "use": "Import succeeded tasks", "command": commands.get("ingest_for_rag") or "mdtero project ingest --json"})

    palette: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        command = str(row.get("command") or "").strip()
        seen_key = (str(row.get("area") or ""), command)
        if not command or seen_key in seen:
            continue
        seen.add(seen_key)
        palette.append({**row, "command": command, "is_next": command in next_step_set})
    return palette


def _hero_panel(model: dict[str, Any]) -> Panel:
    health = model["health"]
    grid = Table.grid(expand=True)
    grid.add_column(ratio=2)
    grid.add_column(ratio=3)
    grid.add_row(Text(str(health["headline"]), style="bold"), str(health["detail"]))
    grid.add_row("Primary next command", str(health["primary_next_command"]))
    grid.add_row("Status code", str(health["status"]))

    cards = Table.grid(expand=True)
    cards.add_column(ratio=1)
    cards.add_column(ratio=1)
    cards.add_column(ratio=1)
    cards.add_column(ratio=1)
    card_values = [f"{item['label']}: {item['value']}" for item in health.get("cards", [])]
    while len(card_values) < 4:
        card_values.append("")
    cards.add_row(*card_values[:4])
    return Panel(Group(grid, cards), title="Mdtero Control Console", border_style="yellow")


def _account_panel(model: dict[str, Any]) -> Panel:
    account = model["account"]
    academic = model["academic"]
    table = Table.grid(expand=True)
    table.add_column(ratio=1)
    table.add_column(ratio=2)
    table.add_row("API", account["api_base_url"])
    table.add_row("Auth", f"configured ({account['auth_source']})" if account["authenticated"] else f"missing - {account['auth_hint']}")
    table.add_row("Discover", academic["discover_source"])
    table.add_row("Academic keys", _key_summary(academic))
    return Panel(table, title="Account & Discovery", border_style="green")


def _project_panel(model: dict[str, Any]) -> Panel:
    project = model["project"]
    table = Table("Metric", "Value", expand=True)
    table.add_row("Project", project["name"])
    table.add_row("Server project", project["server_project_id"] or "not linked")
    table.add_row("Queue", f"{project['paper_count']} total / {project['pending_count']} pending / {project['running_count']} running")
    table.add_row("Results", f"{project['succeeded_count']} succeeded / {project['failed_count']} failed")
    for item in project["recent"]:
        table.add_row(str(item["status"]), str(item["input"])[:80])
    return Panel(table, title="Project", border_style="cyan")


def _rag_panel(model: dict[str, Any]) -> Panel:
    rag = model["rag"]
    mcp = model["mcp"]
    table = Table.grid(expand=True)
    table.add_column(ratio=1)
    table.add_column(ratio=2)
    table.add_row("Ready", "yes" if rag["ready"] else "no")
    table.add_row("Reason", rag["reason_code"])
    table.add_row("Ready for ingest", str(rag["ready_for_ingest_count"]))
    if rag.get("server_status"):
        table.add_row("Server RAG", f"{rag.get('server_status')} ({rag.get('server_reason_code')})")
        summary = rag.get("server_summary") if isinstance(rag.get("server_summary"), dict) else {}
        table.add_row("Embeddings", f"{summary.get('embedded_count', 0)}/{summary.get('chunk_count', 0)} chunks")
        provider = rag.get("selected_provider") or "server"
        provider_state = rag.get("provider_state") or ("configured" if rag.get("provider_configured") else "unknown")
        table.add_row("Provider", f"{provider} / {provider_state}")
        if rag.get("embedding_model"):
            table.add_row("Model", str(rag.get("embedding_model")))
        if rag.get("action_hint"):
            table.add_row("Hint", str(rag.get("action_hint"))[:120])
        next_commands = rag.get("next_commands") if isinstance(rag.get("next_commands"), list) else []
        if next_commands:
            table.add_row("Next", str(next_commands[0])[:120])
    elif rag.get("server_error_type"):
        table.add_row("Server RAG", f"unavailable ({rag.get('server_error_type')})")
    table.add_row("MCP briefing", mcp["briefing_command"])
    table.add_row("MCP server", mcp["serve_command"])
    table.add_row("Agent briefing", mcp["primary_tool"])
    task_tools = mcp.get("task_tools") if isinstance(mcp.get("task_tools"), list) else []
    if task_tools:
        table.add_row("MCP tools", ", ".join(str(item.get("tool")) for item in task_tools))
    tool_plan = mcp.get("tool_plan") if isinstance(mcp.get("tool_plan"), list) else []
    if tool_plan:
        table.add_row("MCP plan", f"{len(tool_plan)} steps from agent_briefing")
    return Panel(table, title="RAG & MCP", border_style="magenta")


def _mcp_tool_plan_panel(model: dict[str, Any]) -> Panel:
    mcp = model["mcp"]
    plan = mcp.get("tool_plan") if isinstance(mcp.get("tool_plan"), list) else []
    table = Table("Step", "Tool", "When", "Failure fields", expand=True)
    if not plan:
        table.add_row("brief", "agent_briefing", "Run mdtero mcp briefing --json to load the agent playbook", "reason_code, action_hint, next_commands")
    for item in plan[:8]:
        fields = item.get("failure_fields") if isinstance(item.get("failure_fields"), list) else []
        field_text = ", ".join(str(field) for field in fields[:5])
        table.add_row(
            str(item.get("step") or "-"),
            str(item.get("tool") or "-"),
            str(item.get("when") or "-")[:100],
            field_text or "-",
        )
    return Panel(table, title="MCP Tool Plan", border_style="magenta")


def _integration_panel(model: dict[str, Any]) -> Panel:
    zotero = model["zotero"]
    agents = model["agents"]
    table = Table.grid(expand=True)
    table.add_column(ratio=1)
    table.add_column(ratio=2)
    table.add_row("Zotero", "configured" if zotero["configured"] else "not configured")
    table.add_row("Zotero library", str(zotero["library_id"] or "-"))
    table.add_row("Agents", ", ".join(agents["labels"]) if agents["labels"] else "none detected")
    table.add_row("Agent skills", f"{agents['installed_count']} installed / {agents['pending_install_count']} pending")
    if agents["pending_install_labels"]:
        table.add_row("Pending", ", ".join(agents["pending_install_labels"]))
    table.add_row("Agent detect", agents["detect_command"])
    table.add_row("Agent install", agents["install_command"])
    return Panel(table, title="Integrations", border_style="yellow")


def _handoff_panel(model: dict[str, Any]) -> Panel:
    handoff = model["handoff"]
    table = Table("State", "Item", "Next", expand=True)
    ready = handoff.get("ready_artifacts") or []
    blocked = handoff.get("blocked_items") or []
    active = handoff.get("active_items") or []
    if not ready and not blocked and not active:
        table.add_row("empty", "No papers in the local project yet", "mdtero discover \"<topic>\" --interactive")
    for item in ready[:3]:
        table.add_row("ready", _brief_item_label(item), str(item.get("download_command") or "mdtero project download --output-dir ./mdtero-output --json"))
    for item in blocked[:3]:
        table.add_row("blocked", _brief_item_label(item), _blocked_next_hint(item))
    for item in active[:3]:
        commands = item.get("recommended_commands") if isinstance(item.get("recommended_commands"), list) else []
        table.add_row("active", _brief_item_label(item), str(commands[0] if commands else "mdtero project refresh --wait --timeout 300 --json"))
    commands = handoff.get("recommended_next_commands") or []
    if commands:
        table.add_row("agent", "Follow agent_briefing next_commands", str(commands[0]))
    return Panel(table, title="Agent Handoff", border_style="blue")


def _operator_panel(model: dict[str, Any]) -> Panel:
    table = Table("Area", "State", "Detail", expand=True)
    for item in model.get("operator_summary") or []:
        table.add_row(str(item.get("area") or "-"), str(item.get("state") or "-"), str(item.get("detail") or "-"))
    return Panel(table, title="Operator Summary", border_style="green")


def _extension_handoff_panel(model: dict[str, Any]) -> Panel:
    handoff = model["extension_handoff"]
    table = Table("Mode", "Details", expand=True)
    table.add_row("Extension", "; ".join(handoff["browser_scope"][:4]))
    table.add_row("CLI", "; ".join(handoff["cli_scope"][:3]))
    table.add_row("Switch when", "; ".join(handoff["handoff_triggers"][:3]))
    table.add_row("URL command", str(handoff["commands"][0]))
    table.add_row("File command", str(handoff["commands"][1]))
    table.add_row("Follow-up", "; ".join(str(command) for command in handoff["commands"][2:5]))
    table.add_row("Agent fields", ", ".join(handoff["visible_fields"]))
    return Panel(table, title="Extension to CLI", border_style="yellow")


def _shortcuts_panel(model: dict[str, Any]) -> Panel:
    table = Table("Key", "Action", "Command", expand=True)
    for item in model.get("shortcuts") or []:
        table.add_row(str(item.get("key") or "-"), str(item.get("label") or "-"), str(item.get("command") or "-"))
    return Panel(table, title="Shortcuts", border_style="cyan")


def _command_palette_panel(model: dict[str, Any]) -> Panel:
    table = Table("Area", "Use", "Command", expand=True)
    for item in model.get("command_palette") or []:
        style = "bold yellow" if item.get("is_next") else ""
        table.add_row(
            str(item.get("area") or "-"),
            str(item.get("use") or "-"),
            str(item.get("command") or "-"),
            style=style,
        )
    return Panel(table, title="Command Palette", border_style="white")


def _launch_bundle_panel(model: dict[str, Any]) -> Panel:
    bundle = model.get("launch_bundle") if isinstance(model.get("launch_bundle"), dict) else {}
    groups = bundle.get("groups") if isinstance(bundle.get("groups"), list) else []
    table = Table("Group", "Purpose", "Commands", expand=True)
    for group in groups:
        if not isinstance(group, dict):
            continue
        commands = group.get("commands") if isinstance(group.get("commands"), list) else []
        command_text = "\n".join(str(command) for command in commands[:6])
        table.add_row(str(group.get("label") or "-"), str(group.get("purpose") or "-")[:110], command_text or "-")
    hint = Table.grid(expand=True)
    hint.add_column(ratio=1)
    hint.add_row(str(bundle.get("copy_hint") or "Copy a command group into your terminal or agent prompt."))
    hint.add_row(f"Primary group: {bundle.get('primary_group') or '-'}")
    return Panel(Group(hint, table), title="Launch Bundles", border_style="yellow")


def _brief_item_label(item: dict[str, Any]) -> str:
    title = str(item.get("title") or "").strip()
    task_id = str(item.get("task_id") or "").strip()
    input_value = str(item.get("input") or "").strip()
    label = title or task_id or input_value or "paper"
    if task_id and task_id not in label:
        label = f"{label} ({task_id})"
    return label[:90]


def _blocked_next_hint(item: dict[str, Any]) -> str:
    hint = str(item.get("action_hint") or item.get("reason_code") or "check mdtero status").strip()
    attempts = item.get("translation_attempts")
    if isinstance(attempts, list) and attempts:
        provider_bits = []
        for attempt in attempts[:3]:
            if not isinstance(attempt, dict):
                continue
            provider = str(attempt.get("provider") or "provider").strip()
            reason = str(attempt.get("reason_code") or attempt.get("provider_error_code") or "failed").strip()
            provider_bits.append(f"{provider}:{reason}")
        if provider_bits:
            hint = f"{hint} ({'; '.join(provider_bits)})"
    return hint[:120]


def _next_steps_panel(model: dict[str, Any]) -> Panel:
    text = Text()
    for index, command in enumerate(model["next_steps"], start=1):
        text.append(f"{index}. ", style="bold")
        text.append(command)
        text.append("\n")
    return Panel(text, title="Next Commands", border_style="white")


def _key_summary(academic: dict[str, Any]) -> str:
    parts = [
        f"Elsevier {'ok' if academic['elsevier'] else 'optional'}",
        f"Wiley {'ok' if academic['wiley_tdm'] else 'optional'}",
        f"Semantic Scholar {'ok' if academic['semantic_scholar'] else 'optional'}",
    ]
    return " / ".join(parts)
