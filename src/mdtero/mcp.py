from __future__ import annotations

from pathlib import Path
from typing import Any

from .projects import load_project, paper_to_document, project_documents


def build_project_status(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path.cwd()
    state = load_project(root)
    succeeded = [paper for paper in state.papers if paper.status == "succeeded" and paper.task_id]
    pending = [paper for paper in state.papers if paper.status in {"pending", "created"} and not paper.task_id]
    failed = [paper for paper in state.papers if paper.status == "failed"]
    return {
        "name": state.name,
        "server_project_id": state.server_project_id,
        "paper_count": len(state.papers),
        "ready_for_ingest_count": len(succeeded),
        "pending_count": len(pending),
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
        "parse_pending": "mdtero project parse --wait",
        "refresh": "mdtero project refresh --wait",
        "download_markdown": "mdtero project download --output-dir ./mdtero-output",
        "serve_mcp": "mdtero mcp serve",
    }
    if state.server_project_id:
        commands["ingest_for_rag"] = "mdtero project ingest"
        commands["rag_build"] = "mdtero rag build"
        commands["rag_query"] = "mdtero rag query \"<question>\""
    else:
        commands["create_server_project"] = "mdtero project create-server"
        commands["bind_server_project"] = "mdtero project link --server-project-id <id>"
    return {
        "project": state.name,
        "server_project_id": state.server_project_id,
        "commands": commands,
        "workflow": [
            "mdtero project parse --wait",
            "mdtero project refresh --wait",
            "mdtero project create-server" if not state.server_project_id else "mdtero project ingest",
            "mdtero rag build",
            "mdtero rag query \"<question>\"",
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


def _paper_commands(paper: Any) -> list[str]:
    if paper.status in {"pending", "created"} and not paper.task_id:
        return ["mdtero project parse --wait"]
    if paper.task_id and paper.status not in {"succeeded", "failed"}:
        return [f"mdtero status {paper.task_id} --wait", "mdtero project refresh --wait"]
    if paper.task_id and paper.status == "succeeded":
        return [f"mdtero download {paper.task_id} {paper.artifact or 'paper_md'} --output-dir ./mdtero-output", "mdtero project ingest"]
    if paper.status == "failed":
        return ["mdtero project parse --include-failed --wait"]
    return []


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
    def agent_commands() -> dict:
        return build_agent_commands(root)

    mcp.run()
