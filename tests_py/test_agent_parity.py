from __future__ import annotations

from pathlib import Path

from mdtero.agent_output import compact_agent_payload, summarize_markdown_paper
from mdtero.agent import TARGETS, install_targets
from mdtero.mcp import MCP_TOOLS, discover_for_agent, paper_summary_for_agent


def test_compact_agent_payload_keeps_handoff_fields():
    payload = {
        "task_id": "t1",
        "status": "succeeded",
        "quality_label": "full_text_good",
        "reason_code": "task_succeeded",
        "action_hint": "download paper_md",
        "next_commands": ["mdtero download t1 paper_md"],
        "preferred_artifact": "paper_md",
        "noise": {"huge": "x" * 1000},
        "result": {
            "quality": {
                "coverage_score": 0.9,
                "structure_score": 0.8,
                "fidelity_score": 0.85,
                "section_count": 8,
            }
        },
    }
    compact = compact_agent_payload(payload)
    assert compact["schema"] == "mdtero.agent.v1"
    assert compact["compact"] is True
    assert compact["task_id"] == "t1"
    assert compact["quality_label"] == "full_text_good"
    assert "noise" not in compact
    assert compact["quality_summary"]["coverage_score"] == 0.9


def test_paper_summary_builds_section_index_and_range(tmp_path: Path):
    markdown = """---
title: Example Paper
doi: 10.1000/example
---

# Example Paper

## Introduction

Hello world.

## Methods

Details.
"""
    summary = summarize_markdown_paper(markdown, source="memory", range_spec="1:4")
    assert summary["title"] == "Example Paper"
    assert summary["front_matter"]["doi"] == "10.1000/example"
    assert any(item["title"] == "Introduction" for item in summary["sections"])
    assert summary["range"] == {"start": 1, "end": 4}
    assert "Example Paper" in (summary["excerpt"] or "")


def test_cursor_agent_target_installs(tmp_path: Path):
    assert "cursor" in TARGETS
    (tmp_path / ".cursor").mkdir()
    results = install_targets(["cursor"], root=tmp_path, dry_run=False)
    assert results[0].target == "cursor"
    assert (tmp_path / ".cursor" / "skills" / "mdtero" / "SKILL.md").exists()


def test_mcp_tool_catalog_includes_discover_and_paper_summary():
    assert "discover" in MCP_TOOLS
    assert "paper_summary" in MCP_TOOLS


def test_paper_summary_for_agent_reads_file(tmp_path: Path):
    path = tmp_path / "paper.md"
    path.write_text("# Title\n\n## A\n\nbody\n", encoding="utf-8")
    payload = paper_summary_for_agent(str(path), tmp_path, compact=True)
    assert payload["status"] == "ok"
    assert payload["title"] == "Title"


def test_discover_for_agent_requires_query():
    payload = discover_for_agent("", compact=True)
    assert payload["reason_code"] == "discover_query_required"
