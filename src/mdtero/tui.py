from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static

from .agent import detect_targets
from .config import MdteroConfig, load_config
from .mcp import build_agent_commands, build_rag_context
from .projects import ProjectState, ensure_project


def build_dashboard_model(
    *,
    project_root: Path | None = None,
    config: MdteroConfig | None = None,
    agent_root: Path | None = None,
) -> dict[str, Any]:
    root = project_root or Path.cwd()
    cfg = config or load_config()
    project = ensure_project(root)
    agents = detect_targets(agent_root)
    pending = [paper for paper in project.papers if paper.status in {"pending", "created"} and not paper.task_id]
    running = [paper for paper in project.papers if paper.task_id and paper.status not in {"succeeded", "failed"}]
    succeeded = [paper for paper in project.papers if paper.status == "succeeded"]
    failed = [paper for paper in project.papers if paper.status == "failed"]
    rag = build_rag_context(root)
    commands = build_agent_commands(root)["commands"]
    return {
        "account": {
            "api_base_url": cfg.api_base_url,
            "authenticated": bool(cfg.api_key),
            "auth_hint": "mdtero login --api-key <key>" if not cfg.api_key else "mdtero doctor",
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
            "detected": [agent.name for agent in agents],
            "labels": [agent.label for agent in agents],
            "install_command": "mdtero agent install" if agents else "mdtero agent install --target codex",
        },
        "commands": commands,
        "next_steps": _next_steps(cfg, project, rag, commands),
    }


def render_dashboard_text(model: dict[str, Any]) -> Group:
    return Group(
        _account_panel(model),
        _project_panel(model),
        _rag_panel(model),
        _integration_panel(model),
        _next_steps_panel(model),
    )


class MdteroTui(App):
    CSS = """
    Screen { background: #f7f7f4; color: #1d2525; }
    #dashboard { padding: 1 2; }
    """

    def compose(self) -> ComposeResult:
        model = build_dashboard_model(project_root=Path.cwd())
        yield Header(show_clock=True)
        yield Static(render_dashboard_text(model), id="dashboard")
        yield Footer()


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
                "artifact": paper.artifact,
            }
            for paper in project.papers[-6:]
        ],
    }


def _next_steps(cfg: MdteroConfig, project: ProjectState, rag: dict[str, Any], commands: dict[str, str]) -> list[str]:
    if not cfg.api_key:
        return ["mdtero login --api-key <key>", "mdtero doctor"]
    if not project.papers:
        return ["mdtero project add 10.48550/arXiv.1706.03762", "mdtero project parse --wait"]
    if project.papers and any(paper.status in {"pending", "created"} and not paper.task_id for paper in project.papers):
        return [commands["parse_pending"], commands["refresh"]]
    if not project.server_project_id:
        return ["mdtero project create-server", "mdtero project ingest"]
    if rag.get("ready_for_ingest_count", 0) > 0:
        return ["mdtero project ingest", "mdtero rag build", "mdtero rag query \"<question>\""]
    return ["mdtero discover \"your topic\"", "mdtero parse <doi-or-url>"]


def _account_panel(model: dict[str, Any]) -> Panel:
    account = model["account"]
    academic = model["academic"]
    table = Table.grid(expand=True)
    table.add_column(ratio=1)
    table.add_column(ratio=2)
    table.add_row("API", account["api_base_url"])
    table.add_row("Auth", "configured" if account["authenticated"] else f"missing - {account['auth_hint']}")
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
    table = Table.grid(expand=True)
    table.add_column(ratio=1)
    table.add_column(ratio=2)
    table.add_row("Ready", "yes" if rag["ready"] else "no")
    table.add_row("Reason", rag["reason_code"])
    table.add_row("Ready for ingest", str(rag["ready_for_ingest_count"]))
    table.add_row("MCP", "mdtero mcp serve")
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
    table.add_row("Agent install", agents["install_command"])
    return Panel(table, title="Integrations", border_style="yellow")


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
