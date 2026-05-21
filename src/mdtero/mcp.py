from __future__ import annotations

from pathlib import Path

from .projects import load_project, paper_to_document, project_documents


def serve_project_context(project_root: Path | None = None) -> None:
    try:
        from fastmcp import FastMCP
    except Exception as exc:  # pragma: no cover - optional runtime import
        raise RuntimeError("FastMCP is required for `mdtero mcp serve`. Install with `uv tool install mdtero`.") from exc

    root = project_root or Path.cwd()
    mcp = FastMCP("mdtero")

    @mcp.tool
    def project_status() -> dict:
        state = load_project(root)
        return {
            "name": state.name,
            "paper_count": len(state.papers),
            "papers": [document.to_dict() for document in project_documents(root)],
        }

    @mcp.tool
    def paper_context(input_or_task_id: str) -> dict:
        state = load_project(root)
        for paper in state.papers:
            if paper.input == input_or_task_id or paper.task_id == input_or_task_id:
                return paper_to_document(paper).to_dict()
        return {"error": "paper_not_found", "input_or_task_id": input_or_task_id}

    mcp.run()
