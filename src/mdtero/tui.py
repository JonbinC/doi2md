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
from .config import MdteroConfig, config_path, load_config
from .mcp import build_agent_briefing, build_agent_commands, build_rag_context
from .onboarding import GENERIC_RAG_QUERY_COMMAND, ONE_COMMAND_RAG_BOOTSTRAP, build_academic_onboarding_summary, build_input_route_contract
from .projects import ProjectState, ensure_project, project_rag_local_coverage
from .rag_contract import ensure_rag_contract

WORKSTATION_SETUP_COMMAND = "mdtero setup"
HEADLESS_SETUP_COMMAND = "mdtero setup --api-key --json"


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
    local_rag_coverage = project_rag_local_coverage(project)
    rag = _tui_rag_payload(build_rag_context(root), project.server_project_id, rag_status_fetcher=rag_status_fetcher)
    rag.setdefault("local_rag_coverage", local_rag_coverage)
    commands = build_agent_commands(root)["commands"]
    briefing = build_agent_briefing(root, rag_status_fetcher=rag_status_fetcher, config=cfg, agent_root=agent_root)
    dashboard_setup_handoff = _dashboard_setup_handoff_payload(briefing.get("dashboard_setup_handoff_json"))
    onboarding_checklist = briefing.get("onboarding_checklist") or []
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
    launch_summary = _launch_summary_payload(
        cfg=cfg,
        project=project,
        rag=rag,
        detected_agent_count=len(detected_agents),
        installed_agent_count=len(installed_agents),
        launch_bundle=launch_bundle,
        next_steps=next_steps,
    )
    input_routes = build_input_route_contract()
    handoff = {
        "ready_artifacts": briefing["ready_artifacts"],
        "blocked_items": briefing["blocked_items"],
        "active_items": briefing["active_items"],
        "recommended_next_commands": briefing["recommended_next_commands"],
    }
    mcp_payload = {
        "briefing_command": commands["mcp_briefing"],
        "serve_command": commands["serve_mcp"],
        "primary_tool": "agent_briefing",
        "dashboard_setup_handoff_json": dashboard_setup_handoff,
        "server": briefing.get("mcp_server"),
        "tools": briefing["mcp_tools"],
        "task_tools": _mcp_task_tools_payload(briefing["mcp_tools"]),
        "tool_plan": _mcp_tool_plan_payload(briefing.get("mcp_tool_plan") or []),
        "agent_playbook": _agent_playbook_payload(briefing.get("agent_playbook") or {}),
        "recommended_next_commands": briefing["recommended_next_commands"],
    }
    agent_workflow = _agent_workflow_payload(
        cfg=cfg,
        project=project,
        rag=rag,
        handoff=handoff,
        mcp=mcp_payload,
        launch_summary=launch_summary,
        next_steps=next_steps,
    )
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
            "discover_source": "server OpenAlex",
            "configure_command": "mdtero config academic",
            "application_links": build_academic_onboarding_summary(cfg, path=config_path(), saved=False)["application_links"],
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
        "mcp": mcp_payload,
        "agent_workflow": agent_workflow,
        "extension_handoff": extension_handoff,
        "dashboard_setup_handoff_json": dashboard_setup_handoff,
        "input_routes": input_routes,
        "onboarding_checklist": onboarding_checklist,
        "launch_summary": launch_summary,
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
        _agent_workflow_panel(model),
        _onboarding_panel(model),
        _dashboard_setup_handoff_panel(model),
        Columns([_account_panel(model), _project_panel(model)], equal=True, expand=True),
        Columns([_rag_panel(model), _integration_panel(model)], equal=True, expand=True),
        _agent_playbook_panel(model),
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
    ensure_rag_contract(server_status)
    citation_contract = server_status.get("citation_contract") if isinstance(server_status.get("citation_contract"), dict) else {}
    if citation_contract:
        payload["citation_contract"] = citation_contract
        required_fields = citation_contract.get("required_for_final_answer") if isinstance(citation_contract.get("required_for_final_answer"), list) else []
        if required_fields:
            payload["citation_rule"] = f"Final answers preserve {', '.join(str(field) for field in required_fields)}"
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
    rag_build_command = commands.get("rag_build") or commands.get("bootstrap_rag") or "mdtero rag build --wait --json"
    rag_query_command = commands.get("rag_query") or GENERIC_RAG_QUERY_COMMAND
    if not cfg.is_authenticated:
        return [WORKSTATION_SETUP_COMMAND, "mdtero doctor --json", HEADLESS_SETUP_COMMAND]
    if not project.papers:
        return ["mdtero project add 10.48550/arXiv.1706.03762 --json", commands["parse_pending"]]
    if project.papers and any(paper.status in {"pending", "created"} and not paper.task_id for paper in project.papers):
        return [commands["parse_pending"], commands["refresh"]]
    if not project.server_project_id:
        return [ONE_COMMAND_RAG_BOOTSTRAP, "mdtero rag status --json", rag_build_command]
    if rag.get("server_status") == "ready":
        return ["mdtero rag status --json", rag_query_command, commands["mcp_briefing"], commands["serve_mcp"]]
    if rag.get("server_status") in {"not_ready", "partial"}:
        return [ONE_COMMAND_RAG_BOOTSTRAP, "mdtero rag status --json", rag_build_command]
    if rag.get("ready_for_ingest_count", 0) > 0:
        return [ONE_COMMAND_RAG_BOOTSTRAP, "mdtero rag status --json", rag_build_command]
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
        detail = "Server-side RAG is ready for queries and MCP agent context."
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


def _agent_workflow_payload(
    *,
    cfg: MdteroConfig,
    project: ProjectState,
    rag: dict[str, Any],
    handoff: dict[str, Any],
    mcp: dict[str, Any],
    launch_summary: dict[str, Any],
    next_steps: list[str],
) -> dict[str, Any]:
    playbook = mcp.get("agent_playbook") if isinstance(mcp.get("agent_playbook"), dict) else {}
    first_action = playbook.get("first_action") if isinstance(playbook.get("first_action"), dict) else {}
    coverage = rag.get("local_rag_coverage") if isinstance(rag.get("local_rag_coverage"), dict) else {}
    blocked_items = handoff.get("blocked_items") if isinstance(handoff.get("blocked_items"), list) else []
    active_items = handoff.get("active_items") if isinstance(handoff.get("active_items"), list) else []
    ready_artifacts = handoff.get("ready_artifacts") if isinstance(handoff.get("ready_artifacts"), list) else []
    action = _agent_workflow_first_action(
        cfg=cfg,
        project=project,
        rag=rag,
        handoff=handoff,
        mcp=mcp,
        playbook_first_action=first_action,
        next_steps=next_steps,
    )
    if not cfg.is_authenticated:
        phase = "authenticate"
        objective = "Authenticate before handing parse, RAG, or MCP work to an agent."
    elif blocked_items:
        phase = "resolve_blocked_items"
        objective = "Inspect blocked parse or translation items before retrying downstream RAG."
    elif active_items:
        phase = "refresh_or_wait"
        objective = "Refresh or wait for active project tasks, then download ready artifacts."
    elif not project.papers:
        phase = "add_sources"
        objective = "Add papers through discovery, DOI/URL parse, file upload, BibTeX, or Zotero import."
    else:
        phase = str(playbook.get("current_phase") or launch_summary.get("primary_path") or "inspect_project")
        objective = str(playbook.get("objective") or _agent_workflow_objective(project, rag, handoff))
    return {
        "mode": "mcp_tools_first",
        "phase": phase,
        "objective": objective,
        "first_action": {
            "tool": action["tool"],
            "command": action["command"],
            "reason_code": action["reason_code"],
        },
        "fallback_commands": _dedupe_commands([action["command"], *next_steps, "mdtero mcp briefing --json", "mdtero mcp serve"]),
        "state_summary": {
            "project": project.name,
            "papers": len(project.papers),
            "ready_artifacts": len(ready_artifacts),
            "active_items": len(active_items),
            "blocked_items": len(blocked_items),
            "rag_ready_for_ingest": int(coverage.get("ready_for_ingest_count") or rag.get("ready_for_ingest_count") or 0),
            "rag_blocked": int(coverage.get("blocked_count") or 0),
            "server_rag": str(rag.get("server_status") or rag.get("reason_code") or "not_linked"),
        },
        "blocking_items": [_agent_workflow_blocker(item) for item in blocked_items[:3]],
        "rag_coverage": {
            "ready_for_ingest_count": int(coverage.get("ready_for_ingest_count") or 0),
            "blocked_count": int(coverage.get("blocked_count") or 0),
            "pending_count": int(coverage.get("pending_count") or 0),
            "failed_count": int(coverage.get("failed_count") or 0),
            "blocked_reasons": _coverage_reason_counts(coverage.get("blocked") if isinstance(coverage.get("blocked"), list) else []),
        },
        "preserve_fields": [
            "task_id",
            "reason_code",
            "action_hint",
            "next_commands",
            "download_artifacts",
            "citation_contract",
            "citations",
            "source_nodes",
            "evidence_pack.context_markdown",
        ],
        "stop_condition": "Stop and report reason_code/action_hint when the first tool or command returns a failed or blocked state.",
    }


def _agent_workflow_first_action(
    *,
    cfg: MdteroConfig,
    project: ProjectState,
    rag: dict[str, Any],
    handoff: dict[str, Any],
    mcp: dict[str, Any],
    playbook_first_action: dict[str, Any],
    next_steps: list[str],
) -> dict[str, str]:
    blocked_items = handoff.get("blocked_items") if isinstance(handoff.get("blocked_items"), list) else []
    active_items = handoff.get("active_items") if isinstance(handoff.get("active_items"), list) else []
    commands = mcp.get("recommended_next_commands") if isinstance(mcp.get("recommended_next_commands"), list) else []
    fallback_command = str(playbook_first_action.get("command") or (next_steps[0] if next_steps else "mdtero mcp briefing --json"))
    fallback_tool = str(playbook_first_action.get("tool") or mcp.get("primary_tool") or "agent_briefing")
    fallback_reason = str(playbook_first_action.get("reason_code") or rag.get("reason_code") or "inspect_state")

    if not cfg.is_authenticated:
        return {
            "tool": "agent_commands",
            "command": _first_command(commands, next_steps, contains="setup") or "mdtero setup --api-key --json",
            "reason_code": "authentication_required",
        }
    if blocked_items:
        return {
            "tool": "task_status",
            "command": _first_command(commands, next_steps, contains="--include-failed") or "mdtero project parse --include-failed --wait --timeout 300 --json",
            "reason_code": str(blocked_items[0].get("reason_code") or "blocked_items_present") if isinstance(blocked_items[0], dict) else "blocked_items_present",
        }
    if active_items:
        return {
            "tool": "task_status",
            "command": _first_command(commands, next_steps, contains="project refresh") or "mdtero project refresh --wait --timeout 300 --json",
            "reason_code": "active_items_present",
        }
    if not project.papers:
        return {
            "tool": "project_add",
            "command": _first_command(commands, next_steps, contains="project add") or _first_command(commands, next_steps, contains="discover") or "mdtero project add <doi-or-url> --json",
            "reason_code": "project_has_no_papers",
        }
    return {"tool": fallback_tool, "command": fallback_command, "reason_code": fallback_reason}


def _first_command(*groups: list[Any], contains: str) -> str | None:
    for group in groups:
        for command in group:
            text = str(command)
            if contains in text:
                return text
    return None


def _agent_workflow_objective(project: ProjectState, rag: dict[str, Any], handoff: dict[str, Any]) -> str:
    if not project.papers:
        return "Add papers through discovery, DOI/URL parse, file upload, BibTeX, or Zotero import."
    if handoff.get("blocked_items"):
        return "Inspect blocked parse or translation items before retrying downstream RAG."
    if handoff.get("active_items"):
        return "Refresh or wait for active project tasks, then download ready artifacts."
    if rag.get("server_status") == "ready":
        return "Ask grounded RAG questions and preserve citations plus source_nodes in final answers."
    if rag.get("ready_for_ingest_count", 0) > 0 or (rag.get("local_rag_coverage") or {}).get("ready_for_ingest_count", 0) > 0:
        return "Import succeeded artifacts, build server-side RAG, then query through CLI or MCP."
    return "Parse at least one paper successfully before starting RAG."


def _agent_workflow_blocker(item: dict[str, Any]) -> dict[str, str]:
    return {
        "item": _brief_item_label(item),
        "reason_code": str(item.get("reason_code") or "unknown"),
        "action_hint": _blocked_next_hint(item),
    }


def _coverage_reason_counts(items: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        reason = str(item.get("reason_code") or "unknown")
        counts[reason] = counts.get(reason, 0) + 1
    return counts


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
        "rag_query": "Bootstrap/query server-side RAG with evidence pack",
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


def _agent_playbook_payload(playbook: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(playbook, dict):
        playbook = {}
    first_action = playbook.get("first_action") if isinstance(playbook.get("first_action"), dict) else {}
    steps = playbook.get("ordered_steps") if isinstance(playbook.get("ordered_steps"), list) else []
    return {
        "version": str(playbook.get("version") or ""),
        "mode": str(playbook.get("mode") or ""),
        "current_phase": str(playbook.get("current_phase") or "unknown"),
        "objective": str(playbook.get("objective") or ""),
        "first_action": {
            "tool": str(first_action.get("tool") or "agent_briefing"),
            "command": str(first_action.get("command") or "mdtero mcp briefing --json"),
            "reason_code": str(first_action.get("reason_code") or ""),
        },
        "ordered_steps": [
            {
                "step": str(step.get("step") or ""),
                "tool": str(step.get("tool") or ""),
                "required": bool(step.get("required")),
                "command_fallback": str(step.get("command_fallback") or ""),
                "failure_fields": [str(field) for field in step.get("failure_fields") or []],
            }
            for step in steps
            if isinstance(step, dict)
        ][:8],
        "stop_conditions": [str(item) for item in playbook.get("stop_conditions") or []][:3],
        "preserve_fields": [str(item) for item in playbook.get("preserve_fields") or []],
        "guardrails": [str(item) for item in playbook.get("guardrails") or []][:4],
    }


def _dashboard_setup_handoff_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}
    auth_boundary = payload.get("auth_boundary") if isinstance(payload.get("auth_boundary"), dict) else {}
    api_key = payload.get("api_key") if isinstance(payload.get("api_key"), dict) else {}
    command_blocks = payload.get("command_blocks") if isinstance(payload.get("command_blocks"), dict) else {}
    mcp = payload.get("mcp") if isinstance(payload.get("mcp"), dict) else {}
    rag = payload.get("rag") if isinstance(payload.get("rag"), dict) else {}
    next_commands = payload.get("next_commands") if isinstance(payload.get("next_commands"), list) else []
    return {
        "source": str(payload.get("source") or "dashboard_api_key_dialog"),
        "purpose": str(payload.get("purpose") or "Continue CLI and MCP setup without exposing the one-time API key secret."),
        "first_cli_command": str(payload.get("first_cli_command") or HEADLESS_SETUP_COMMAND),
        "auth_boundary": {
            "workstation": str(auth_boundary.get("workstation") or "Use browser OAuth with `mdtero setup` on a normal workstation."),
            "headless": str(auth_boundary.get("headless") or "Use `mdtero setup --api-key --json` only on trusted headless shells."),
            "secret_transport": str(auth_boundary.get("secret_transport") or "Paste the full secret only into the secure CLI prompt."),
            "dashboard_secret_retention": str(auth_boundary.get("dashboard_secret_retention") or "The full secret is shown once and may remain only in the current page session for install prompts until refresh or explicit clear. Persistent dashboard lists show only the prefix identifier."),
        },
        "api_key": {
            "full_secret_shown_once": bool(api_key.get("full_secret_shown_once", True)),
            "full_secret_included": bool(api_key.get("full_secret_included", False)),
            "copy_secret_action": str(api_key.get("copy_secret_action") or "Use the dashboard Copy secret button, then paste only into the secure CLI prompt."),
            "prefix_identifier_field": str(api_key.get("prefix_identifier_field") or "api_key.prefix_identifier"),
        },
        "next_commands": [str(command) for command in next_commands if str(command).strip()],
        "command_blocks": {str(key): str(value) for key, value in command_blocks.items()},
        "mcp": {
            "first_tool": str(mcp.get("first_tool") or "agent_briefing"),
            "startup_order": [str(command) for command in mcp.get("startup_order") or [] if str(command).strip()],
            "expected_tools": [str(tool) for tool in mcp.get("expected_tools") or [] if str(tool).strip()],
        },
        "rag": {
            "owner": str(rag.get("owner") or "backend_rag"),
            "local_rag_provider_key_required": bool(rag.get("local_rag_provider_key_required", False)),
            "primary_command": str(rag.get("primary_command") or ONE_COMMAND_RAG_BOOTSTRAP),
            "fallback_commands": [str(command) for command in rag.get("fallback_commands") or [] if str(command).strip()],
        },
        "redaction_policy": str(payload.get("redaction_policy") or "Do not print Mdtero API keys, provider keys, bearer tokens, signed URLs, storage tokens, or Infisical tokens."),
        "agent_instruction": str(payload.get("agent_instruction") or "Run doctor first, preserve reason_code/action_hint, and paste the API key only into the secure setup prompt."),
    }


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
        "primary_commands": [
            commands.get("extension_handoff_url") or commands.get("parse_doi_or_url") or "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
            commands.get("extension_handoff_file") or commands.get("parse_file") or "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json",
        ],
        "visible_fields": ["task_id", "selected_provider", "parser_strategy", "client_acquisition", "parse_outcome", "reason_code", "action_hint", "preferred_artifact", "download_artifacts", "next_commands"],
    }


def _extension_handoff_commands(commands: dict[str, str]) -> list[str]:
    return [
        commands.get("config_academic") or "mdtero config academic",
        commands.get("discover_interactive") or "mdtero discover \"<topic>\" --limit 5 --interactive",
        commands.get("discover_add_selected") or "mdtero discover \"<topic>\" --limit 5 --add --select 1,3 --json",
        commands.get("extension_handoff_url") or commands.get("parse_doi_or_url") or "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
        commands.get("extension_handoff_file") or commands.get("parse_file") or "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json",
        "mdtero status <task-id> --wait --timeout 300 --json",
        "mdtero download <task-id> paper_md --output-dir ./mdtero-output --json",
        "mdtero project ingest --json",
        "mdtero project refresh --wait --timeout 300 --json",
        ONE_COMMAND_RAG_BOOTSTRAP,
        "mdtero rag status --json",
        "mdtero rag build --wait --json",
        GENERIC_RAG_QUERY_COMMAND,
        commands.get("mcp_briefing") or "mdtero mcp briefing --json",
        commands.get("serve_mcp") or "mdtero mcp serve",
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
        commands.get("mcp_briefing") or "mdtero mcp briefing --json",
        commands.get("agent_detect") or "mdtero agent detect --json",
        commands.get("agent_install") or "mdtero agent install --interactive",
    ]
    parse_commands = [
        commands.get("discover") or 'mdtero discover "your topic" --json',
        commands.get("parse_doi_or_url") or "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
        commands.get("parse_file") or "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json",
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
        "mdtero project ingest --json",
        ONE_COMMAND_RAG_BOOTSTRAP,
        *(rag.get("next_commands") if isinstance(rag.get("next_commands"), list) else []),
        commands.get("rag_status") or "mdtero rag status --json",
        commands.get("rag_query") or GENERIC_RAG_QUERY_COMMAND,
        commands.get("rag_build") or commands.get("bootstrap_rag") or "mdtero rag build --wait --json",
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
            "purpose": "Create or reuse the server RAG project, query grounded evidence, then brief local FastMCP agents.",
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


def _launch_summary_payload(
    *,
    cfg: MdteroConfig,
    project: ProjectState,
    rag: dict[str, Any],
    detected_agent_count: int,
    installed_agent_count: int,
    launch_bundle: dict[str, Any],
    next_steps: list[str],
) -> dict[str, Any]:
    checks = [
        {
            "id": "auth",
            "label": "Auth",
            "ready": cfg.is_authenticated,
            "detail": cfg.api_key_source if cfg.is_authenticated else "run mdtero setup",
        },
        {
            "id": "project",
            "label": "Project",
            "ready": bool(project.papers),
            "detail": f"{len(project.papers)} paper(s)" if project.papers else "add DOI, file, BibTeX, or Zotero items",
        },
        {
            "id": "results",
            "label": "Parsed results",
            "ready": any(paper.status == "succeeded" for paper in project.papers),
            "detail": f"{sum(1 for paper in project.papers if paper.status == 'succeeded')} succeeded",
        },
        {
            "id": "rag",
            "label": "Backend RAG",
            "ready": bool(rag.get("server_status") == "ready" or (project.server_project_id and rag.get("ready"))),
            "detail": str(rag.get("server_status") or rag.get("reason_code") or "not linked"),
        },
        {
            "id": "agents",
            "label": "Agent skills",
            "ready": bool(detected_agent_count and installed_agent_count >= detected_agent_count),
            "detail": f"{installed_agent_count}/{detected_agent_count} installed" if detected_agent_count else "no workspace detected",
        },
    ]
    ready_count = sum(1 for item in checks if item["ready"])
    total_count = len(checks)
    blocked = [item for item in checks if not item["ready"]]
    primary_group = str(launch_bundle.get("primary_group") or "Setup")
    if not cfg.is_authenticated:
        primary_path = "authenticate"
    elif not project.papers:
        primary_path = "discover_or_parse"
    elif not any(paper.status == "succeeded" for paper in project.papers):
        primary_path = "parse_queue"
    elif rag.get("server_status") == "ready":
        primary_path = "query_rag_or_serve_mcp"
    else:
        primary_path = "build_rag"
    return {
        "readiness_score": round(ready_count / total_count, 2),
        "ready_count": ready_count,
        "total_count": total_count,
        "primary_path": primary_path,
        "primary_group": primary_group,
        "primary_next_command": next_steps[0] if next_steps else "mdtero doctor --json",
        "blocked_checks": blocked,
        "checks": checks,
        "recommended_flow": _dedupe_commands([
            "mdtero setup" if not cfg.is_authenticated else "mdtero doctor --json",
            *(next_steps[:3]),
            "mdtero mcp briefing --json",
        ]),
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
    rag_build_command = commands.get("rag_build") or commands.get("bootstrap_rag") or "mdtero rag build --wait --json"
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
        {"area": "RAG", "use": "One-command backend RAG bootstrap and query", "command": ONE_COMMAND_RAG_BOOTSTRAP},
        {"area": "RAG", "use": "Explicit recovery build when bootstrap query is not enough", "command": rag_build_command},
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
    launch = model.get("launch_summary") if isinstance(model.get("launch_summary"), dict) else {}
    grid = Table.grid(expand=True)
    grid.add_column(ratio=2)
    grid.add_column(ratio=3)
    grid.add_row(Text(str(health["headline"]), style="bold"), str(health["detail"]))
    grid.add_row("Primary next command", str(health["primary_next_command"]))
    grid.add_row("Status code", str(health["status"]))
    if launch:
        grid.add_row("Launch path", str(launch.get("primary_path") or "-"))
        grid.add_row("Readiness", f"{launch.get('ready_count', 0)}/{launch.get('total_count', 0)} checks ({launch.get('readiness_score', 0):.0%})")
        blocked = launch.get("blocked_checks") if isinstance(launch.get("blocked_checks"), list) else []
        if blocked:
            grid.add_row("Needs", ", ".join(str(item.get("label") or item.get("id") or "-") for item in blocked[:4]))

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


def _agent_workflow_panel(model: dict[str, Any]) -> Panel:
    workflow = model.get("agent_workflow") if isinstance(model.get("agent_workflow"), dict) else {}
    first_action = workflow.get("first_action") if isinstance(workflow.get("first_action"), dict) else {}
    state = workflow.get("state_summary") if isinstance(workflow.get("state_summary"), dict) else {}
    coverage = workflow.get("rag_coverage") if isinstance(workflow.get("rag_coverage"), dict) else {}
    blockers = workflow.get("blocking_items") if isinstance(workflow.get("blocking_items"), list) else []

    top = Table.grid(expand=True)
    top.add_column(ratio=1)
    top.add_column(ratio=2)
    top.add_row("Phase", str(workflow.get("phase") or "inspect_project"))
    top.add_row("Objective", str(workflow.get("objective") or "Run mdtero mcp briefing --json first."))
    top.add_row("First MCP tool", str(first_action.get("tool") or "agent_briefing"))
    top.add_row("Command fallback", str(first_action.get("command") or "mdtero mcp briefing --json"))
    top.add_row("Stop condition", str(workflow.get("stop_condition") or "Preserve failure fields and report blocked state.")[:140])

    status = Table("Signal", "Value", expand=True)
    status.add_row("Project", f"{state.get('project') or '-'} · {state.get('papers', 0)} paper(s)")
    status.add_row("Work queue", f"{state.get('ready_artifacts', 0)} ready / {state.get('active_items', 0)} active / {state.get('blocked_items', 0)} blocked")
    status.add_row("RAG coverage", f"{coverage.get('ready_for_ingest_count', 0)} ready / {coverage.get('blocked_count', 0)} blocked")
    status.add_row("Server RAG", str(state.get("server_rag") or "not_linked"))
    reasons = coverage.get("blocked_reasons") if isinstance(coverage.get("blocked_reasons"), dict) else {}
    if reasons:
        status.add_row("Blocked reasons", ", ".join(f"{key}:{value}" for key, value in reasons.items()))

    blocked = Table("Blocked item", "Reason", "Next", expand=True)
    if blockers:
        for item in blockers:
            if not isinstance(item, dict):
                continue
            blocked.add_row(str(item.get("item") or "-"), str(item.get("reason_code") or "-"), str(item.get("action_hint") or "-")[:110])
    else:
        blocked.add_row("none", "-", "Continue with the first action above")

    preserve = workflow.get("preserve_fields") if isinstance(workflow.get("preserve_fields"), list) else []
    footer = Table.grid(expand=True)
    footer.add_column(ratio=1)
    footer.add_row("Preserve: " + ", ".join(str(field) for field in preserve[:8]))
    return Panel(Group(top, status, blocked, footer), title="Agent Workflow", border_style="bright_blue")


def _onboarding_panel(model: dict[str, Any]) -> Panel:
    table = Table("Step", "Status", "Primary command", expand=True)
    checklist = model.get("onboarding_checklist") if isinstance(model.get("onboarding_checklist"), list) else []
    for item in checklist:
        if not isinstance(item, dict):
            continue
        table.add_row(
            str(item.get("title") or item.get("id") or "-"),
            str(item.get("status") or "-"),
            str(item.get("primary_command") or "-"),
        )
    if not checklist:
        table.add_row("Setup", "unknown", "mdtero setup --json")
    return Panel(table, title="Onboarding Checklist", border_style="magenta")


def _dashboard_setup_handoff_panel(model: dict[str, Any]) -> Panel:
    handoff = model.get("dashboard_setup_handoff_json") if isinstance(model.get("dashboard_setup_handoff_json"), dict) else {}
    api_key = handoff.get("api_key") if isinstance(handoff.get("api_key"), dict) else {}
    auth_boundary = handoff.get("auth_boundary") if isinstance(handoff.get("auth_boundary"), dict) else {}
    rag = handoff.get("rag") if isinstance(handoff.get("rag"), dict) else {}
    mcp = handoff.get("mcp") if isinstance(handoff.get("mcp"), dict) else {}
    table = Table("Area", "Contract", expand=True)
    table.add_row("Source", str(handoff.get("source") or "dashboard_api_key_dialog"))
    table.add_row("First CLI command", str(handoff.get("first_cli_command") or HEADLESS_SETUP_COMMAND))
    table.add_row("Secret boundary", "full_secret_included=false; paste the one-time API key only into the secure CLI prompt")
    table.add_row("Dashboard retention", str(auth_boundary.get("dashboard_secret_retention") or "full secret shown once, prefix kept after close")[:140])
    table.add_row("Copy action", str(api_key.get("copy_secret_action") or "Copy secret in dashboard, paste only into mdtero setup prompt")[:140])
    table.add_row("Backend RAG", f"{rag.get('owner') or 'backend_rag'}; local provider key required: {rag.get('local_rag_provider_key_required', False)}")
    table.add_row("MCP first tool", str(mcp.get("first_tool") or "agent_briefing"))
    next_commands = handoff.get("next_commands") if isinstance(handoff.get("next_commands"), list) else []
    if next_commands:
        table.add_row("Next", str(next_commands[0])[:140])
    return Panel(table, title="Dashboard Setup Handoff", border_style="green")


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
        if rag.get("citation_rule"):
            table.add_row("Evidence rule", str(rag.get("citation_rule"))[:120])
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


def _agent_playbook_panel(model: dict[str, Any]) -> Panel:
    playbook = model["mcp"].get("agent_playbook") if isinstance(model.get("mcp"), dict) else {}
    if not isinstance(playbook, dict):
        playbook = {}
    first_action = playbook.get("first_action") if isinstance(playbook.get("first_action"), dict) else {}
    table = Table("Field", "Value", expand=True)
    table.add_row("Phase", str(playbook.get("current_phase") or "unknown"))
    table.add_row("Mode", str(playbook.get("mode") or "mcp_tools_first"))
    table.add_row("First tool", str(first_action.get("tool") or "agent_briefing"))
    table.add_row("First command", str(first_action.get("command") or "mdtero mcp briefing --json")[:120])
    steps = playbook.get("ordered_steps") if isinstance(playbook.get("ordered_steps"), list) else []
    if steps:
        compact = []
        for step in steps[:5]:
            if not isinstance(step, dict):
                continue
            marker = "*" if step.get("required") else "optional"
            compact.append(f"{step.get('step')}:{step.get('tool')} ({marker})")
        table.add_row("Ordered steps", " -> ".join(compact))
    preserve = playbook.get("preserve_fields") if isinstance(playbook.get("preserve_fields"), list) else []
    if preserve:
        important = [field for field in preserve if field in {"reason_code", "action_hint", "next_commands", "citation_contract", "citations", "source_nodes", "evidence_pack.context_markdown"}]
        table.add_row("Preserve", ", ".join(important[:8]))
    stop_conditions = playbook.get("stop_conditions") if isinstance(playbook.get("stop_conditions"), list) else []
    if stop_conditions:
        table.add_row("Stop when", str(stop_conditions[0])[:140])
    guardrails = playbook.get("guardrails") if isinstance(playbook.get("guardrails"), list) else []
    if guardrails:
        table.add_row("Guardrail", str(guardrails[-1])[:140])
    return Panel(table, title="Agent Playbook", border_style="cyan")


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
    ]
    return " / ".join(parts)
