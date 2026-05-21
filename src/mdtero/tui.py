from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static

from .config import load_config
from .projects import ensure_project


class MdteroTui(App):
    CSS = """
    Screen { background: #f7f7f4; color: #1d2525; }
    #panel { padding: 2 4; border: solid #668c7a; }
    """

    def compose(self) -> ComposeResult:
        cfg = load_config()
        project = ensure_project(Path.cwd())
        yield Header(show_clock=True)
        yield Static(
            "\n".join(
                [
                    "Mdtero Project Dashboard",
                    "",
                    f"Project: {project.name} ({len(project.papers)} papers)",
                    f"API: {cfg.api_base_url}",
                    f"Login: {'configured' if cfg.api_key else 'missing'}",
                    f"Semantic Scholar: {'local discover enabled' if cfg.has_semantic_scholar_key else 'server OpenAlex fallback'}",
                    "",
                    "Commands: setup, parse, discover, project, zotero, rag, mcp, agent",
                ]
            ),
            id="panel",
        )
        yield Footer()
