from __future__ import annotations

from pathlib import Path

import httpx

from mdtero.agent import detect_targets, install_targets, uninstall_targets
from mdtero.cli import build_parser
from mdtero.client import MdteroClient
from mdtero.config import AcademicKeys, MdteroConfig, ZoteroConfig, load_config, save_config
from mdtero.core import artifacts_from_task_result, paper_from_task, provider_from_task_result
from mdtero.projects import (
    PaperRecord,
    add_paper,
    extract_bib_targets,
    import_bib,
    init_project,
    load_project,
    paper_to_document,
    project_pending_papers,
    project_task_ids,
    remove_paper,
    update_paper_submission,
    update_task,
)
from mdtero.workflow import parse_trace_from_route, status_trace, upload_trace
from mdtero.zotero import paper_from_zotero_item


def test_parser_exposes_next_gen_command_contract():
    parser = build_parser()
    help_text = parser.format_help()
    for command in ["setup", "doctor", "login", "config", "parse", "discover", "project", "parse-bib", "zotero", "translate", "rag", "mcp", "agent", "tui"]:
        assert command in help_text


def test_config_round_trip_keeps_semantic_scholar_local_discover_flag(tmp_path: Path):
    path = tmp_path / "config.json"
    save_config(
        MdteroConfig(
            api_key="key",
            academic=AcademicKeys(semantic_scholar_api_key="s2"),
        ),
        path,
    )

    cfg = load_config(path)

    assert cfg.api_key == "key"
    assert cfg.has_semantic_scholar_key is True


def test_client_falls_back_to_legacy_parse_when_v1_route_is_not_deployed(monkeypatch):
    calls = []

    def fake_request(self, method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path == "/api/v1/route":
            request = httpx.Request(method, "https://api.mdtero.test/api/v1/route")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("not found", request=request, response=response)
        if path == "/api/v1/tasks/parse":
            request = httpx.Request(method, "https://api.mdtero.test/api/v1/tasks/parse")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("not found", request=request, response=response)
        if path == "/tasks/parse":
            return {"task_id": "legacy-task", "status": "queued"}
        raise AssertionError(path)

    monkeypatch.setattr(MdteroClient, "_request", fake_request)
    client = MdteroClient()

    route = client.route("10.1000/demo")
    task = client.parse("10.1000/demo")

    assert route["legacy_fallback"] is True
    assert route["server_entrypoint"] == "/tasks/parse"
    assert task["task_id"] == "legacy-task"
    assert [call[1] for call in calls] == ["/api/v1/route", "/api/v1/tasks/parse", "/tasks/parse"]


def test_project_init_creates_local_project_state(tmp_path: Path):
    target = init_project(tmp_path, name="demo")
    state = load_project(tmp_path)

    assert target.exists()
    assert state.name == "demo"
    assert state.papers == []


def test_project_add_remove_and_task_update(tmp_path: Path):
    init_project(tmp_path, name="demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/demo", task_id="task-1", status="queued"))

    update_task(
        tmp_path,
        {
            "task_id": "task-1",
            "status": "succeeded",
            "result": {
                "preferred_artifact": "paper_md",
                "selected_provider": "mineru_precision",
                "parser_strategy": "mineru_precision_ast",
                "quality": {"reason_code": "ok"},
            },
        },
    )
    state = load_project(tmp_path)

    assert state.papers[0].status == "succeeded"
    assert state.papers[0].artifact == "paper_md"
    assert state.papers[0].reason_code == "ok"
    assert state.papers[0].provider == "mineru_precision"
    assert state.papers[0].parser_strategy == "mineru_precision_ast"
    document = paper_to_document(state.papers[0])
    assert document.provider.provider == "mineru_precision"
    assert document.artifacts[0].key == "paper_md"

    remove_paper(tmp_path, "task-1")
    assert load_project(tmp_path).papers == []


def test_project_queue_submission_refresh_helpers(tmp_path: Path):
    init_project(tmp_path, name="demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/pending", status="pending"))
    add_paper(tmp_path, PaperRecord(input="10.1000/queued", task_id="task-queued", status="queued"))
    add_paper(tmp_path, PaperRecord(input="10.1000/failed", task_id="task-failed", status="failed"))

    state = load_project(tmp_path)
    assert [paper.input for paper in project_pending_papers(state)] == ["10.1000/pending"]
    assert [paper.input for paper in project_pending_papers(state, include_failed=True)] == ["10.1000/pending", "10.1000/failed"]
    assert project_task_ids(state) == ["task-queued", "task-failed"]

    update_paper_submission(
        tmp_path,
        "10.1000/pending",
        {
            "task_id": "task-new",
            "status": "queued",
            "result": {
                "selected_provider": "openalex",
                "parser_strategy": "server_parse",
                "reason_code": "queued",
            },
        },
    )
    updated = load_project(tmp_path).papers[0]

    assert updated.task_id == "task-new"
    assert updated.status == "queued"
    assert updated.provider == "openalex"
    assert updated.parser_strategy == "server_parse"
    assert updated.reason_code == "queued"


def test_zotero_item_maps_to_project_paper():
    paper = paper_from_zotero_item(
        {
            "key": "ABC",
            "data": {
                "title": "A paper",
                "DOI": "10.1000/zotero",
                "url": "https://example.test/paper",
            },
        }
    )

    assert paper is not None
    assert paper.input == "10.1000/zotero"
    assert paper.title == "A paper"
    assert paper.source == "zotero"


def test_bib_targets_import_into_project(tmp_path: Path):
    bib = tmp_path / "refs.bib"
    bib.write_text(
        """
        @article{a, doi={10.1000/demo.one}, title={One}}
        @article{b, url={https://doi.org/10.1000/demo.two}, title={Two}}
        @article{c, url={https://example.test/fulltext}, title={Three}}
        """,
        encoding="utf-8",
    )

    targets = extract_bib_targets(bib.read_text(encoding="utf-8"))
    summary = import_bib(tmp_path, [bib])
    state = load_project(tmp_path)

    assert [target["value"] for target in targets] == [
        "10.1000/demo.one",
        "10.1000/demo.two",
        "https://example.test/fulltext",
    ]
    assert summary["imported_count"] == 3
    assert state.papers[0].source == "bib:refs.bib"


def test_config_round_trip_keeps_zotero_credentials(tmp_path: Path):
    path = tmp_path / "config.json"
    save_config(
        MdteroConfig(
            zotero=ZoteroConfig(library_id="123", library_type="group", api_key="zotero-key"),
        ),
        path,
    )

    cfg = load_config(path)

    assert cfg.zotero.library_id == "123"
    assert cfg.zotero.library_type == "group"
    assert cfg.zotero.api_key == "zotero-key"


def test_core_maps_task_result_to_document_artifacts_and_provider():
    task = {
        "task_id": "task-1",
        "status": "succeeded",
        "result": {
            "selected_provider": "mineru_precision",
            "parser_strategy": "mineru_precision_ast",
            "reason_code": "ok",
            "artifacts": {
                "paper_md": {
                    "filename": "chen2026hydrate.md",
                    "media_type": "text/markdown",
                    "path": "/tmp/chen2026hydrate.md",
                },
                "paper_bundle": {
                    "filename": "chen2026hydrate.zip",
                    "media_type": "application/zip",
                },
            },
        },
    }

    provider = provider_from_task_result(task["result"])
    artifacts = artifacts_from_task_result("task-1", task["result"])
    document = paper_from_task("10.1000/demo", task)

    assert provider.provider == "mineru_precision"
    assert provider.strategy == "mineru_precision_ast"
    assert artifacts[0].kind == "markdown"
    assert artifacts[0].download_url == "/api/v1/tasks/task-1/download/paper_md"
    assert artifacts[1].kind == "zip"
    assert document.input == "10.1000/demo"
    assert document.artifacts[0].filename == "chen2026hydrate.md"


def test_workflow_traces_expose_agent_friendly_steps(tmp_path: Path):
    route = {
        "route_kind": "server",
        "acquisition_mode": "licensed_api",
        "requires_raw_upload": False,
        "action_hint": "Submit to server parse.",
    }
    parse_trace = parse_trace_from_route("10.1000/demo", route, {"task_id": "task-1"}).to_dict()
    upload = upload_trace(tmp_path / "paper.pdf", {"task_id": "task-2"}).to_dict()
    status = status_trace(
        {
            "task_id": "task-1",
            "status": "succeeded",
            "result": {"download_artifacts": [{"artifact": "paper_md"}]},
        }
    ).to_dict()

    assert parse_trace["steps"][0]["name"] == "route"
    assert parse_trace["steps"][1]["name"] == "server_parse"
    assert upload["steps"][0]["metadata"]["filename"] == "paper.pdf"
    assert status["steps"][-1]["name"] == "download_artifacts"


def test_python_agent_installer_writes_packaged_skill_without_npm(tmp_path: Path):
    results = install_targets(["codex"], root=tmp_path)
    skill_path = tmp_path / ".codex" / "skills" / "mdtero" / "SKILL.md"

    assert results[0].target == "codex"
    assert results[0].action == "installed"
    assert skill_path.exists()
    assert "uv tool install mdtero" in skill_path.read_text(encoding="utf-8")


def test_python_agent_installer_detects_and_uninstalls_targets(tmp_path: Path):
    (tmp_path / ".hermes").mkdir()

    detected = detect_targets(tmp_path)
    results = install_targets(root=tmp_path)
    removed = uninstall_targets(["hermes"], root=tmp_path)

    assert [target.name for target in detected] == ["hermes"]
    assert results[0].target == "hermes"
    assert removed[0].action == "removed"
    assert not (tmp_path / ".hermes" / "skills" / "mdtero").exists()
