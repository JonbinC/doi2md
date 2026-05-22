from __future__ import annotations

from pathlib import Path
from typing import Any

from .client import MdteroClient
from .config import MdteroConfig, load_config
from .projects import load_project, paper_to_document, project_documents


def build_project_status(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path.cwd()
    state = load_project(root)
    succeeded = [paper for paper in state.papers if paper.status == "succeeded" and paper.task_id]
    pending = [paper for paper in state.papers if paper.status in {"pending", "created"} and not paper.task_id]
    running = [paper for paper in state.papers if paper.task_id and paper.status not in {"succeeded", "failed"}]
    failed = [paper for paper in state.papers if paper.status == "failed"]
    return {
        "name": state.name,
        "server_project_id": state.server_project_id,
        "paper_count": len(state.papers),
        "ready_for_ingest_count": len(succeeded),
        "pending_count": len(pending),
        "running_count": len(running),
        "failed_count": len(failed),
        "papers": [document.to_dict() for document in project_documents(root)],
        "next_actions": build_agent_commands(root),
    }


def build_paper_context(input_or_task_id: str, project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path.cwd()
    state = load_project(root)
    for paper in state.papers:
        if paper.input == input_or_task_id or paper.task_id == input_or_task_id:
            payload = paper_to_document(paper).to_dict()
            payload["recommended_commands"] = _paper_commands(paper)
            return payload
    return {"error": "paper_not_found", "input_or_task_id": input_or_task_id}


def build_agent_commands(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path.cwd()
    state = load_project(root)
    commands: dict[str, Any] = {
        "doctor": "mdtero doctor",
        "parse_pending": "mdtero project parse --wait --json",
        "refresh": "mdtero project refresh --wait --json",
        "download_markdown": "mdtero project download --output-dir ./mdtero-output --json",
        "serve_mcp": "mdtero mcp serve",
    }
    if state.server_project_id:
        commands["ingest_for_rag"] = "mdtero project ingest --json"
        commands["rag_status"] = "mdtero rag status --json"
        commands["rag_build"] = "mdtero rag build --json"
        commands["rag_query"] = "mdtero rag query \"<question>\" --json"
    else:
        commands["bootstrap_rag"] = "mdtero rag build --json"
        commands["create_server_project"] = "mdtero project create-server --json"
        commands["bind_server_project"] = "mdtero project link --server-project-id <id>"
    return {
        "project": state.name,
        "server_project_id": state.server_project_id,
        "commands": commands,
        "workflow": [
            commands["parse_pending"],
            commands["refresh"],
            commands["bootstrap_rag"] if not state.server_project_id else commands["ingest_for_rag"],
            "mdtero rag status --json",
            "mdtero rag query \"<question>\" --json",
        ],
    }


def build_rag_context(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path.cwd()
    state = load_project(root)
    succeeded = [paper for paper in state.papers if paper.status == "succeeded" and paper.task_id]
    return {
        "project": state.name,
        "server_project_id": state.server_project_id,
        "ready": bool(state.server_project_id and succeeded),
        "ready_for_ingest_count": len(succeeded),
        "reason_code": "ready" if state.server_project_id and succeeded else "server_project_not_linked" if not state.server_project_id else "no_succeeded_tasks",
        "commands": build_agent_commands(root)["commands"],
    }


def build_server_rag_status(project_root: Path | None = None, *, fetcher: Any | None = None) -> dict[str, Any]:
    root = project_root or Path.cwd()
    state = load_project(root)
    local_ready = sum(1 for paper in state.papers if paper.status == "succeeded" and paper.task_id)
    commands = build_agent_commands(root)["commands"]
    if not state.server_project_id:
        return {
            "status": "not_ready",
            "reason_code": "server_project_not_linked",
            "project": state.name,
            "server_project_id": None,
            "local_ready_for_ingest_count": local_ready,
            "local_paper_count": len(state.papers),
            "action_hint": "Run `mdtero rag build --json` to create and bind a server project, import succeeded parse tasks, and start server-side Voyage RAG.",
            "next_commands": [commands["bootstrap_rag"], commands["parse_pending"], commands["refresh"]],
        }

    try:
        status = (fetcher or MdteroClient().rag_status)(state.server_project_id)
    except Exception as exc:
        return {
            "status": "unavailable",
            "reason_code": "server_rag_status_unavailable",
            "project": state.name,
            "server_project_id": state.server_project_id,
            "local_ready_for_ingest_count": local_ready,
            "local_paper_count": len(state.papers),
            "error_type": exc.__class__.__name__,
            "next_commands": [commands["ingest_for_rag"], "mdtero rag status --json", commands["rag_build"]],
        }

    summary = status.get("summary") if isinstance(status.get("summary"), dict) else {}
    server_status = str(status.get("status") or "unknown")
    reason_code = str(status.get("reason_code") or "unknown")
    next_commands = ["mdtero rag status --json"]
    if server_status == "ready" or reason_code == "indexed":
        next_commands.extend([commands["rag_query"], "mdtero mcp serve"])
    elif local_ready > 0:
        next_commands.extend([commands["ingest_for_rag"], commands["rag_build"], commands["rag_query"]])
    else:
        next_commands.extend([commands["parse_pending"], commands["refresh"], commands["ingest_for_rag"]])

    status.setdefault("project", state.name)
    status.setdefault("server_project_id", state.server_project_id)
    status.setdefault("local_ready_for_ingest_count", local_ready)
    status.setdefault("local_paper_count", len(state.papers))
    status["next_commands"] = next_commands
    status["agent_summary"] = {
        "status": server_status,
        "reason_code": reason_code,
        "embedded_count": summary.get("embedded_count", 0),
        "chunk_count": summary.get("chunk_count", 0),
        "pending_embedding_count": summary.get("pending_embedding_count", 0),
    }
    return status


def build_agent_briefing(project_root: Path | None = None, *, rag_status_fetcher: Any | None = None, config: MdteroConfig | None = None) -> dict[str, Any]:
    root = project_root or Path.cwd()
    state = load_project(root)
    config = config or load_config()
    commands = build_agent_commands(root)["commands"]
    server_rag = build_server_rag_status(root, fetcher=rag_status_fetcher)

    pending = [paper for paper in state.papers if paper.status in {"pending", "created"} and not paper.task_id]
    running = [paper for paper in state.papers if paper.task_id and paper.status not in {"succeeded", "failed"}]
    succeeded = [paper for paper in state.papers if paper.status == "succeeded" and paper.task_id]
    failed = [paper for paper in state.papers if paper.status == "failed"]

    next_commands: list[str] = []
    if not config.is_authenticated:
        next_commands.extend(["mdtero login --api-key <key>", "mdtero doctor"])
    if not state.papers:
        next_commands.extend([
            "mdtero discover \"<topic>\" --interactive",
            "mdtero project add <doi-or-url> --json",
            "mdtero parse <doi-or-url> --json",
        ])
    if pending:
        next_commands.append(commands["parse_pending"])
    if running:
        next_commands.append(commands["refresh"])
    if failed:
        next_commands.append("mdtero project parse --include-failed --wait --json")
    if succeeded:
        next_commands.append(commands["download_markdown"])
    next_commands.extend(str(command) for command in server_rag.get("next_commands", []) if command)
    next_commands.append(commands["serve_mcp"])

    return {
        "project": {
            "name": state.name,
            "root": str(root.resolve()),
            "server_project_id": state.server_project_id,
            "paper_count": len(state.papers),
        },
        "account": {
            "authenticated": config.is_authenticated,
            "api_key_source": config.api_key_source,
            "api_base_url": config.api_base_url,
            "action_hint": "Run `mdtero doctor` before cloud parse, translation, discovery fallback, or RAG." if config.is_authenticated else "Authenticate before cloud parse, translation, discovery fallback, or RAG.",
            "next_commands": ["mdtero doctor"] if config.is_authenticated else ["mdtero login --api-key <key>", "mdtero doctor"],
        },
        "health": {
            "pending_count": len(pending),
            "running_count": len(running),
            "succeeded_count": len(succeeded),
            "failed_count": len(failed),
            "ready_for_ingest_count": len(succeeded),
            "rag_status": server_rag.get("status"),
            "rag_reason_code": server_rag.get("reason_code"),
        },
        "ready_artifacts": [_paper_agent_summary(paper, include_download=True) for paper in succeeded[:20]],
        "blocked_items": [_paper_agent_summary(paper, include_download=False) for paper in failed[:20]],
        "active_items": [_paper_agent_summary(paper, include_download=False) for paper in [*pending, *running][:20]],
        "rag": {
            "server_project_id": server_rag.get("server_project_id"),
            "status": server_rag.get("status"),
            "reason_code": server_rag.get("reason_code"),
            "agent_summary": server_rag.get("agent_summary"),
            "action_hint": server_rag.get("action_hint"),
            "next_commands": server_rag.get("next_commands", []),
        },
        "recommended_next_commands": _dedupe_commands(next_commands),
        "mcp_tools": [
            "agent_briefing",
            "project_status",
            "paper_context",
            "rag_context",
            "server_rag_status",
            "agent_commands",
        ],
    }


def _paper_commands(paper: Any) -> list[str]:
    if paper.status in {"pending", "created"} and not paper.task_id:
        return ["mdtero project parse --wait --json"]
    if paper.task_id and paper.status not in {"succeeded", "failed"}:
        return [f"mdtero status {paper.task_id} --wait --json", "mdtero project refresh --wait --json"]
    if paper.task_id and paper.status == "succeeded":
        return [f"mdtero download {paper.task_id} {paper.artifact or 'paper_md'} --output-dir ./mdtero-output --json", "mdtero project ingest --json"]
    if paper.status == "failed":
        return ["mdtero project parse --include-failed --wait --json"]
    return []


def _paper_agent_summary(paper: Any, *, include_download: bool) -> dict[str, Any]:
    payload = {
        "input": paper.input,
        "title": paper.title,
        "doi": paper.doi,
        "task_id": paper.task_id,
        "status": paper.status,
        "reason_code": paper.reason_code,
        "artifact": paper.artifact,
        "provider": paper.provider,
        "parser_strategy": paper.parser_strategy,
        "source": paper.source,
        "recommended_commands": _paper_commands(paper),
    }
    if include_download and paper.task_id:
        payload["download_command"] = f"mdtero download {paper.task_id} {paper.artifact or 'paper_md'} --output-dir ./mdtero-output --json"
    return payload


def _dedupe_commands(commands: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for command in commands:
        cleaned = str(command or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def serve_project_context(project_root: Path | None = None) -> None:
    try:
        from fastmcp import FastMCP
    except Exception as exc:  # pragma: no cover - optional runtime import
        raise RuntimeError("FastMCP is required for `mdtero mcp serve`. Install with `uv tool install mdtero`.") from exc

    root = project_root or Path.cwd()
    mcp = FastMCP("mdtero")

    @mcp.tool
    def project_status() -> dict:
        return build_project_status(root)

    @mcp.tool
    def paper_context(input_or_task_id: str) -> dict:
        return build_paper_context(input_or_task_id, root)

    @mcp.tool
    def rag_context() -> dict:
        return build_rag_context(root)

    @mcp.tool
    def server_rag_status() -> dict:
        return build_server_rag_status(root)

    @mcp.tool
    def agent_briefing() -> dict:
        return build_agent_briefing(root)

    @mcp.tool
    def agent_commands() -> dict:
        return build_agent_commands(root)

    mcp.run()
