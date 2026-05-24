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
            "auth_hint": "mdtero setup --api-key <key>" if not cfg.is_authenticated else "mdtero doctor --json",
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
            "recommended_next_commands": briefing["recommended_next_commands"],
        },
        "handoff": handoff,
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
        Columns([_operator_panel(model), _shortcuts_panel(model)], equal=True, expand=True),
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
    payload["server_status"] = server_status.get("status")
    payload["server_reason_code"] = server_status.get("reason_code")
    payload["server_summary"] = summary
    payload["ready"] = server_status.get("status") == "ready"
    if server_status.get("reason_code"):
        payload["reason_code"] = str(server_status["reason_code"])
    return payload


def _next_steps(cfg: MdteroConfig, project: ProjectState, rag: dict[str, Any], commands: dict[str, str]) -> list[str]:
    rag_build_command = commands.get("rag_build") or commands.get("bootstrap_rag") or "mdtero rag build --json"
    if not cfg.is_authenticated:
        return ["mdtero setup --api-key <key>", "mdtero doctor --json"]
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
    elif rag.get("server_error_type"):
        table.add_row("Server RAG", f"unavailable ({rag.get('server_error_type')})")
    table.add_row("MCP briefing", mcp["briefing_command"])
    table.add_row("MCP server", mcp["serve_command"])
    table.add_row("Agent briefing", mcp["primary_tool"])
    return Panel(table, title="RAG & MCP", border_style="magenta")


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


def _shortcuts_panel(model: dict[str, Any]) -> Panel:
    table = Table("Key", "Action", "Command", expand=True)
    for item in model.get("shortcuts") or []:
        table.add_row(str(item.get("key") or "-"), str(item.get("label") or "-"), str(item.get("command") or "-"))
    return Panel(table, title="Shortcuts", border_style="cyan")


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
