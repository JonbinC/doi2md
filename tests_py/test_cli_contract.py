from __future__ import annotations

import importlib.util
import json
import shlex
import subprocess
import tomllib
import urllib.parse
from pathlib import Path

import httpx
import pytest
from rich.console import Console

from mdtero.acquisition import AcquiredArtifact, AcquisitionError, acquire_from_route, should_acquire_locally
from mdtero.agent import default_interactive_targets, detect_target_status, detect_targets, install_targets, parse_agent_selection, uninstall_targets
from mdtero.auth import WebLoginResult, build_cli_login_url, run_web_login
from mdtero.cli import API_KEY_PROMPT_SENTINEL, build_parser, _add_discovery_results_to_project, cmd_config_academic, _parse_academic_selection, _parse_result_selection
from mdtero.client import DiscoveryError, MdteroApiError, MdteroClient, _semantic_scholar_parse_url, translation_source_path_from_task
from mdtero.config import AcademicKeys, MdteroConfig, ZoteroConfig, load_config, save_config
from mdtero.mcp import add_project_item_for_agent, build_agent_briefing, build_agent_commands, build_paper_context, build_project_bridge, build_project_status, build_rag_context, build_server_rag_for_agent, build_server_rag_status, download_artifact_for_agent, ingest_project_for_agent, initialize_project_for_agent, query_server_rag, request_translation_for_agent, serve_project_context, submit_parse_for_agent, task_status_for_agent
from mdtero.core import artifacts_from_task_result, paper_from_task, provider_from_task_result
from mdtero.tui import MdteroTui, build_dashboard_model, render_dashboard_text
from mdtero.projects import (
    PaperRecord,
    add_paper,
    bind_server_project,
    extract_bib_targets,
    import_bib,
    init_project,
    load_project,
    paper_from_submission,
    paper_to_document,
    project_pending_papers,
    project_task_ids,
    remove_paper,
    update_paper_submission,
    update_task,
)
from mdtero.rag_contract import ensure_rag_contract
from mdtero.workflow import parse_trace_from_route, status_trace, upload_trace
from mdtero.zotero import build_sync_note, paper_from_zotero_item, sync_project_to_zotero


def load_python_script(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def mock_doctor_remote_auth_ok(monkeypatch):
    from mdtero import cli

    monkeypatch.setattr(
        cli,
        "_doctor_remote_auth",
        lambda cfg: {"status": "ok", "email": "user@example.com", "wallet_balance_display": "$0.00"}
        if cfg.is_authenticated
        else {
            "status": "missing",
            "action_hint": "Run `mdtero setup` for browser OAuth, or `mdtero setup --api-key --json` for headless environments.",
            "next_commands": ["mdtero setup", "mdtero setup --api-key --json"],
        },
    )


CLI_COMMAND_PLACEHOLDERS = {
    "<artifact>": "paper_md",
    "<directory>": "./papers",
    "<doi-or-url>": "10.48550/arXiv.1706.03762",
    "<doi-or-current-page-url>": "10.48550/arXiv.1706.03762",
    "<id>": "42",
    "<name>": "demo",
    "<paper.pdf|paper.epub|paper.html|paper.xml>": "paper.pdf",
    "<paper.pdf|paper.html|paper.xml|paper.epub>": "paper.pdf",
    "<path>": "paper.pdf",
    "<parse-task-id>": "parse-task-123",
    "<question>": "What is indexed?",
    "<refs.bib>": "refs.bib",
    "<saved-browser-artifact.pdf|epub|html|xml>": "paper.pdf",
    "<target>": "codex",
    "<task-id>": "task-123",
    "<task-id-or-paper.md>": "task-123",
    "<task-id-or-markdown-file>": "task-123",
    "<topic>": "thermal storage",
    "<translation-task-id>": "translation-task-123",
}


def assert_agent_cli_command_parses(command: str) -> None:
    rendered = command.strip()
    assert rendered.startswith("mdtero "), rendered
    for placeholder, value in CLI_COMMAND_PLACEHOLDERS.items():
        rendered = rendered.replace(placeholder, value)
    parser = build_parser()
    parser.parse_args(shlex.split(rendered)[1:])


def assert_command_list_parses(commands: list[str]) -> None:
    for command in commands:
        if command.strip().startswith("mdtero "):
            assert_agent_cli_command_parses(command)


def assert_dashboard_model_commands_parse(model: dict) -> None:
    assert_command_list_parses(model.get("next_steps") or [])
    assert_command_list_parses(model.get("extension_handoff", {}).get("commands") or [])
    assert_command_list_parses(model.get("extension_handoff", {}).get("primary_commands") or [])
    assert_command_list_parses(model.get("handoff", {}).get("recommended_next_commands") or [])
    assert_command_list_parses(model.get("mcp", {}).get("recommended_next_commands") or [])
    assert_command_list_parses(model.get("dashboard_setup_handoff_json", {}).get("next_commands") or [])

    command_values = list((model.get("commands") or {}).values())
    assert_command_list_parses([str(command) for command in command_values])

    for item in model.get("shortcuts") or []:
        if isinstance(item, dict):
            assert_command_list_parses([str(item.get("command") or "")])

    for item in model.get("command_palette") or []:
        if isinstance(item, dict):
            assert_command_list_parses([str(item.get("command") or "")])

    for group in model.get("launch_bundle", {}).get("groups") or []:
        if isinstance(group, dict):
            assert_command_list_parses([str(command) for command in group.get("commands") or []])


def assert_onboarding_payload_commands_parse(payload: dict) -> None:
    assert_command_list_parses([str(command) for command in payload.get("next_commands") or []])
    for group in payload.get("next_command_groups") or []:
        if isinstance(group, dict):
            assert_command_list_parses([str(command) for command in group.get("commands") or []])
    for item in payload.get("onboarding_checklist") or []:
        if not isinstance(item, dict):
            continue
        assert_command_list_parses([str(item.get("primary_command") or "")])
        assert_command_list_parses([str(command) for command in item.get("secondary_commands") or []])
    input_routes = payload.get("input_routes") if isinstance(payload.get("input_routes"), dict) else {}
    for route in input_routes.get("routes") or []:
        if not isinstance(route, dict):
            continue
        assert_command_list_parses([str(route.get("primary_command") or "")])
        assert_command_list_parses([str(command) for command in route.get("next_commands") or []])


def test_parser_exposes_next_gen_command_contract():
    parser = build_parser()
    help_text = parser.format_help()
    for command in ["setup", "doctor", "login", "smoke", "config", "parse", "discover", "project", "parse-bib", "zotero", "translate", "rag", "mcp", "agent", "tui"]:
        assert command in help_text


def test_smoke_parser_accepts_deploy_ready_options():
    parser = build_parser()

    args = parser.parse_args([
        "smoke",
        "--api-base",
        "https://staging.example.test",
        "--workdir",
        "/tmp/mdtero-smoke",
        "--doi",
        "10.48550/arXiv.1706.03762",
        "--query",
        "rag papers",
        "--question",
        "What is indexed?",
        "--translate-to",
        "zh-CN",
        "--wait",
        "--timeout",
        "5",
        "--interval",
        "0.5",
        "--skip-download",
        "--json",
    ])

    assert args.command == "smoke"
    assert args.api_base == "https://staging.example.test"
    assert args.workdir == Path("/tmp/mdtero-smoke")
    assert args.timeout == 5
    assert args.interval == 0.5
    assert args.wait is True
    assert args.translate_to == "zh-CN"
    assert args.skip_download is True
    assert args.json is True


def test_setup_accepts_headless_api_key_argument():
    parser = build_parser()

    args = parser.parse_args(["setup", "--api-key", "mdt_live_demo"])

    assert args.api_key == "mdt_live_demo"

    prompt_args = parser.parse_args(["setup", "--api-key"])
    assert prompt_args.api_key == API_KEY_PROMPT_SENTINEL

    json_args = parser.parse_args(["setup", "--api-key", "mdt_live_demo", "--json"])
    assert json_args.api_key == "mdt_live_demo"
    assert json_args.json is True


def test_login_accepts_web_login_flags():
    parser = build_parser()

    args = parser.parse_args(["login", "--no-browser", "--timeout", "12"])

    assert args.no_browser is True
    assert args.timeout == 12

    keyed = parser.parse_args(["login", "--api-key", "mdt_live_demo"])
    assert keyed.api_key == "mdt_live_demo"
    prompted = parser.parse_args(["login", "--api-key"])
    assert prompted.api_key == API_KEY_PROMPT_SENTINEL


def test_smoke_reports_missing_auth_without_network(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv("MDTERO_API_KEY", raising=False)

    def should_not_touch_network(*args, **kwargs):  # pragma: no cover - failure guard
        raise AssertionError("smoke should not create a client without auth")

    monkeypatch.setattr(MdteroClient, "discover", should_not_touch_network)

    args = type(
        "Args",
        (),
        {
            "api_base": None,
            "workdir": tmp_path / "smoke",
            "doi": "10.48550/arXiv.1706.03762",
            "query": "rag papers",
            "limit": 3,
            "question": "What is indexed?",
            "project_id": None,
            "skip_discovery": False,
            "skip_download": False,
            "skip_translate": False,
            "skip_rag": False,
            "timeout": 5,
            "interval": 0.5,
            "translate_to": "zh-CN",
            "json": True,
        },
    )()

    assert cli.cmd_smoke(args) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "not_ready"
    assert payload["reason_code"] == "auth_missing"
    assert payload["next_commands"] == ["mdtero login", "mdtero login --api-key", "mdtero doctor --json"]
    assert payload["steps"] == []


def test_smoke_runs_discover_parse_download_and_rag(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    save_config(MdteroConfig(api_key="mdt_live_test"))
    calls = []

    def fake_discover(self, query, *, limit=10):
        calls.append(("discover", query, limit))
        return {"source": "openalex_server", "items": [{"title": "RAG Paper", "doi": "10.1000/rag"}]}

    def fake_parse_with_route(self, input_value):
        calls.append(("parse", input_value))
        return (
            {"route_kind": "source_first", "acquisition_mode": "native_source_adapter"},
            {"task_id": "task-1", "status": "queued", "selected_provider": "arxiv_native"},
            None,
        )

    def fake_wait(self, task_id, *, interval=2.0, timeout=600.0):
        calls.append(("wait", task_id, interval, timeout))
        return {
            "task_id": task_id,
            "status": "succeeded",
            "result": {
                "preferred_artifact": "paper_md",
                "download_artifacts": [{"artifact": "paper_md", "filename": "paper.md"}],
                "quality": {"provider": "arxiv_native", "parser_strategy": "html_arxiv"},
            },
        }

    def fake_download(self, task_id, artifact, output_dir):
        calls.append(("download", task_id, artifact, output_dir.name))
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / ("paper_CN.md" if artifact == "translated_md" else "paper.md")
        path.write_text("# Paper\n", encoding="utf-8")
        return path

    def fake_translate_task(self, task_id, *, target_language="zh-CN", artifact="paper_md"):
        calls.append(("translate", task_id, target_language, artifact))
        return {"task_id": "translate-1", "status": "queued"}

    def fake_create_project(self, name, *, description=None):
        calls.append(("create_project", name, description))
        return {"id": 42, "name": name}

    def fake_import_task(self, project_id, task_id):
        calls.append(("import", project_id, task_id))
        return {"document_id": "doc-1", "import_status": "imported"}

    def fake_rag_build(self, project_id):
        calls.append(("rag_build", project_id))
        return {"status": "queued", "reason_code": "rag_build_queued"}

    def fake_rag_status(self, project_id):
        calls.append(("rag_status", project_id))
        return {"status": "ready", "reason_code": "indexed", "summary": {"embedded_count": 1, "chunk_count": 1}}

    def fake_rag_query(self, project_id, question):
        calls.append(("rag_query", project_id, question))
        return {"answer": "Ready.", "matches": [{"document_id": "doc-1", "snippet": "Ready evidence."}]}

    def fake_briefing(root):
        calls.append(("mcp_briefing", Path(root).name))
        return {
            "project": {"initialized": True, "name": "mdtero-smoke"},
            "health": {"rag_reason_code": "indexed"},
            "project_bridge": {"status": "bound", "server_project": {"id": "42"}},
            "rag": {"reason_code": "indexed", "agent_summary": {"readiness_status": "ready"}},
            "mcp_tools": ["agent_briefing", "server_rag_status", "server_rag_build", "rag_query"],
            "mcp_tool_plan": [{"tool": "agent_briefing", "step": "inspect_project"}],
            "recommended_next_commands": ["mdtero rag status --json", "mdtero mcp serve"],
        }

    monkeypatch.setattr(MdteroClient, "discover", fake_discover)
    monkeypatch.setattr(MdteroClient, "parse_with_route", fake_parse_with_route)
    monkeypatch.setattr(MdteroClient, "wait", fake_wait)
    monkeypatch.setattr(MdteroClient, "download", fake_download)
    monkeypatch.setattr(MdteroClient, "translate_task", fake_translate_task)
    monkeypatch.setattr(MdteroClient, "create_project", fake_create_project)
    monkeypatch.setattr(MdteroClient, "import_task_to_project", fake_import_task)
    monkeypatch.setattr(MdteroClient, "rag_build", fake_rag_build)
    monkeypatch.setattr(MdteroClient, "rag_status", fake_rag_status)
    monkeypatch.setattr(MdteroClient, "rag_query", fake_rag_query)
    monkeypatch.setattr("mdtero.mcp.build_agent_briefing", fake_briefing)

    args = type(
        "Args",
        (),
        {
            "api_base": "https://api.mdtero.test",
            "workdir": tmp_path / "smoke",
            "doi": "10.48550/arXiv.1706.03762",
            "query": "rag papers",
            "limit": 3,
            "question": "What is indexed?",
            "project_id": None,
            "skip_discovery": False,
            "skip_download": False,
            "skip_translate": False,
            "skip_rag": False,
            "timeout": 5,
            "interval": 0.5,
            "translate_to": "zh-CN",
            "json": True,
        },
    )()

    assert cli.cmd_smoke(args) == 0
    payload = json.loads(capsys.readouterr().out)
    state = load_project(tmp_path / "smoke")

    assert payload["status"] == "succeeded"
    assert payload["reason_code"] == "smoke_succeeded"
    assert payload["api_base_url"] == "https://api.mdtero.test"
    assert payload["task_ids"] == ["task-1"]
    assert payload["translation_task_ids"] == ["translate-1"]
    assert payload["server_project_id"] == "42"
    coverage = payload["coverage_contract"]
    assert coverage["schema_version"] == "2026-05-27"
    assert coverage["goal"] == "production_cli_smoke"
    assert coverage["covered_by_this_command"] == [
        "auth_config_presence",
        "server_openalex_or_local_semantic_scholar_discovery",
        "doi_or_url_route_parse_status",
        "artifact_download",
        "translation_task",
        "server_voyage_rag_build_query",
        "mcp_agent_briefing_contract",
    ]
    assert {item["id"] for item in coverage["requires_separate_smoke"]} == {
        "pdf_mineru_urlapi",
        "epub_upload",
        "browser_extension_mv3",
    }
    assert coverage["skipped_by_flags"] == []
    assert "mdtero parse --file <paper.pdf> --trace --wait --timeout 5 --json" in coverage["post_success_next_commands"]
    assert coverage["artifact_expectations"]["parse"] == ["paper_md", "paper_bundle"]
    assert "selected_provider" in coverage["evidence_fields"]
    assert "client_acquisition" in coverage["evidence_fields"]
    assert [step["name"] for step in payload["steps"]] == ["discover", "parse", "download", "translate", "rag", "mcp_briefing"]
    assert payload["steps"][1]["selected_provider"] == "arxiv_native"
    assert payload["steps"][3]["target_language"] == "zh-CN"
    assert payload["steps"][4]["query"]["answer"] == "Ready."
    assert payload["steps"][5]["mcp_tools"] == ["agent_briefing", "server_rag_status", "server_rag_build", "rag_query"]
    assert payload["steps"][5]["reason_code"] == "indexed"
    assert payload["downloaded_paths"][0].endswith("paper.md")
    assert payload["translated_paths"][0].endswith("paper_CN.md")
    assert state.server_project_id == "42"
    assert calls == [
        ("discover", "rag papers", 3),
        ("parse", "10.48550/arXiv.1706.03762"),
        ("wait", "task-1", 0.5, 5.0),
        ("download", "task-1", "paper_md", "downloads"),
        ("translate", "task-1", "zh-CN", "paper_md"),
        ("wait", "translate-1", 0.5, 5.0),
        ("download", "translate-1", "translated_md", "translations"),
        ("create_project", "mdtero-smoke", "Mdtero local project: mdtero-smoke"),
        ("import", "42", "task-1"),
        ("rag_build", "42"),
        ("rag_status", "42"),
        ("rag_query", "42", "What is indexed?"),
        ("mcp_briefing", "smoke"),
    ]


def test_smoke_can_skip_discovery_download_and_rag(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    save_config(MdteroConfig(api_key="mdt_live_test"))

    def fake_parse_with_route(self, input_value):
        return ({"route_kind": "server"}, {"task_id": "task-1", "status": "queued"}, None)

    def fake_wait(self, task_id, *, interval=2.0, timeout=600.0):
        return {"task_id": task_id, "status": "succeeded", "result": {"preferred_artifact": "paper_md"}}

    monkeypatch.setattr(MdteroClient, "parse_with_route", fake_parse_with_route)
    monkeypatch.setattr(MdteroClient, "wait", fake_wait)

    args = type(
        "Args",
        (),
        {
            "api_base": None,
            "workdir": tmp_path / "smoke",
            "doi": "10.48550/arXiv.1706.03762",
            "query": "rag papers",
            "limit": 3,
            "question": "What is indexed?",
            "project_id": None,
            "skip_discovery": True,
            "skip_download": True,
            "skip_translate": True,
            "skip_rag": True,
            "timeout": 5,
            "interval": 0.5,
            "translate_to": "zh-CN",
            "json": True,
        },
    )()

    assert cli.cmd_smoke(args) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "succeeded"
    assert payload["coverage_contract"]["covered_by_this_command"] == [
        "auth_config_presence",
        "discovery_skipped",
        "doi_or_url_route_parse_status",
        "artifact_download_skipped",
        "translation_skipped",
        "rag_skipped",
        "mcp_briefing_skipped",
    ]
    assert payload["coverage_contract"]["skipped_by_flags"] == ["discovery", "artifact_download", "translation", "rag", "mcp_briefing"]
    assert [step["status"] for step in payload["steps"]] == ["skipped", "succeeded", "skipped", "skipped", "skipped", "skipped"]
    assert [step["reason_code"] for step in payload["steps"] if step["status"] == "skipped"] == ["skipped", "skipped", "skipped", "skipped", "rag_skipped"]


def test_smoke_fails_when_mcp_briefing_missing_agent_tools(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    save_config(MdteroConfig(api_key="mdt_live_test"))

    def fake_parse_with_route(self, input_value):
        return ({"route_kind": "source_first"}, {"task_id": "task-1", "status": "queued"}, None)

    def fake_wait(self, task_id, *, interval=2.0, timeout=600.0):
        return {"task_id": task_id, "status": "succeeded", "result": {"preferred_artifact": "paper_md"}}

    def fake_create_project(self, name, *, description=None):
        return {"id": 42, "name": name}

    def fake_import_task(self, project_id, task_id):
        return {"document_id": "doc-1", "import_status": "imported"}

    def fake_briefing(root):
        return {"project": {"initialized": True}, "mcp_tools": ["agent_briefing", "server_rag_status", "server_rag_build"]}

    monkeypatch.setattr(MdteroClient, "parse_with_route", fake_parse_with_route)
    monkeypatch.setattr(MdteroClient, "wait", fake_wait)
    monkeypatch.setattr(MdteroClient, "create_project", fake_create_project)
    monkeypatch.setattr(MdteroClient, "import_task_to_project", fake_import_task)
    monkeypatch.setattr(MdteroClient, "rag_build", lambda self, project_id: {"status": "queued"})
    monkeypatch.setattr(MdteroClient, "rag_status", lambda self, project_id: {"status": "ready", "reason_code": "indexed"})
    monkeypatch.setattr(MdteroClient, "rag_query", lambda self, project_id, question: {"answer": "Ready", "matches": []})
    monkeypatch.setattr("mdtero.mcp.build_agent_briefing", fake_briefing)

    args = type(
        "Args",
        (),
        {
            "api_base": None,
            "workdir": tmp_path / "smoke",
            "doi": "10.48550/arXiv.1706.03762",
            "query": "rag papers",
            "limit": 3,
            "question": "What is indexed?",
            "project_id": None,
            "skip_discovery": True,
            "skip_download": True,
            "skip_translate": True,
            "skip_rag": False,
            "timeout": 5,
            "interval": 0.5,
            "translate_to": "zh-CN",
            "json": True,
        },
    )()

    assert cli.cmd_smoke(args) == 1
    payload = json.loads(capsys.readouterr().out)
    mcp_step = next(step for step in payload["steps"] if step["name"] == "mcp_briefing")

    assert payload["primary_failure"]["step"] == "mcp_briefing"
    assert mcp_step["status"] == "failed"
    assert mcp_step["reason_code"].startswith("mcp_briefing_missing_tools")
    assert mcp_step["next_commands"] == ["mdtero mcp briefing --json", "mdtero rag status --json", "mdtero mcp serve"]
    assert "agent_briefing, server_rag_status, server_rag_build, and rag_query" in mcp_step["action_hint"]


def test_smoke_classifies_live_401_as_authentication_required(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    save_config(MdteroConfig(api_key="mdt_live_invalid"))

    def fake_parse_with_route(self, input_value):
        raise MdteroApiError(
            {
                "status": "failed",
                "error_code": "authentication_required",
                "reason_code": "authentication_required",
                "status_code": 401,
                "method": "POST",
                "path": "/api/v1/route",
                "detail": {"detail": "missing or invalid credentials"},
            }
        )

    monkeypatch.setattr(MdteroClient, "parse_with_route", fake_parse_with_route)

    args = type(
        "Args",
        (),
        {
            "api_base": "https://api.mdtero.test",
            "workdir": tmp_path / "smoke",
            "doi": "10.48550/arXiv.1706.03762",
            "query": "rag papers",
            "limit": 3,
            "question": "What is indexed?",
            "project_id": None,
            "skip_discovery": True,
            "skip_download": True,
            "skip_translate": True,
            "skip_rag": True,
            "timeout": 5,
            "interval": 0.5,
            "translate_to": "zh-CN",
            "json": True,
        },
    )()

    assert cli.cmd_smoke(args) == 1
    payload = json.loads(capsys.readouterr().out)
    parse_step = next(step for step in payload["steps"] if step["name"] == "parse")

    assert parse_step["reason_code"] == "authentication_required"
    assert parse_step["error_code"] == "authentication_required"
    assert parse_step["http_status"] == 401
    assert parse_step["next_commands"] == [
        "mdtero setup --api-key --json",
        "mdtero doctor --json",
        "mdtero smoke --json --timeout 600 --interval 2",
    ]
    assert "Production auth failed" in parse_step["action_hint"]


def test_smoke_preserves_discovery_error_payload(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    save_config(MdteroConfig(api_key="mdt_live_invalid"))

    def fake_discover(self, query, *, limit=10):
        raise DiscoveryError(
            {
                "status": "failed",
                "error_code": "authentication_required",
                "reason_code": "authentication_required",
                "status_code": 401,
                "source": "openalex_server",
                "message": "missing or invalid credentials",
                "action_hint": "Run `mdtero setup --api-key --json` and verify with `mdtero doctor --json` before server OpenAlex discovery.",
                "next_commands": ["mdtero setup --api-key --json", "mdtero doctor --json", "mdtero discover \"<topic>\" --json"],
            }
        )

    monkeypatch.setattr(MdteroClient, "discover", fake_discover)

    args = type(
        "Args",
        (),
        {
            "api_base": "https://api.mdtero.test",
            "workdir": tmp_path / "smoke",
            "doi": "10.48550/arXiv.1706.03762",
            "query": "rag papers",
            "limit": 3,
            "question": "What is indexed?",
            "project_id": None,
            "skip_discovery": False,
            "skip_download": True,
            "skip_translate": True,
            "skip_rag": True,
            "timeout": 5,
            "interval": 0.5,
            "translate_to": "zh-CN",
            "json": True,
        },
    )()

    assert cli.cmd_smoke(args) == 1
    payload = json.loads(capsys.readouterr().out)
    discover_step = next(step for step in payload["steps"] if step["name"] == "discover")

    assert discover_step["reason_code"] == "authentication_required"
    assert discover_step["error_code"] == "authentication_required"
    assert discover_step["http_status"] == 401
    assert discover_step["message"] == "missing or invalid credentials"
    assert discover_step["next_commands"] == ["mdtero setup --api-key --json", "mdtero doctor --json", "mdtero discover \"<topic>\" --json"]
    assert payload["primary_failure"] == {
        "step": "discover",
        "reason_code": "authentication_required",
        "action_hint": "Run `mdtero setup --api-key --json` and verify with `mdtero doctor --json` before server OpenAlex discovery.",
    }
    assert payload["next_commands"][:2] == ["mdtero setup --api-key --json", "mdtero doctor --json"]


def test_smoke_surfaces_translation_provider_failures(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    save_config(MdteroConfig(api_key="mdt_live_test"))

    def fake_parse_with_route(self, input_value):
        return ({"route_kind": "source_first"}, {"task_id": "task-1", "status": "queued"}, None)

    def fake_wait(self, task_id, *, interval=2.0, timeout=600.0):
        if task_id == "task-1":
            return {
                "task_id": "task-1",
                "status": "succeeded",
                "result": {"preferred_artifact": "paper_md", "artifacts": {"paper_md": {"path": "/server/task-1/paper.md"}}},
            }
        return {
            "task_id": "translate-1",
            "status": "failed",
            "task_kind": "translate",
            "reason_code": "translation_provider_chain_failed",
            "error_code": "translation_provider_chain_failed",
            "result": {
                "reason_code": "translation_provider_chain_failed",
                "translation_attempts": [
                    {"provider": "codex", "reason_code": "translation_provider_auth_failed", "provider_status_code": 401}
                ],
            },
        }

    def fake_download(self, task_id, artifact, output_dir):
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "paper.md"
        path.write_text("# Paper\n", encoding="utf-8")
        return path

    def fake_translate_task(self, task_id, *, target_language="zh-CN", artifact="paper_md"):
        return {"task_id": "translate-1", "status": "queued"}

    monkeypatch.setattr(MdteroClient, "parse_with_route", fake_parse_with_route)
    monkeypatch.setattr(MdteroClient, "wait", fake_wait)
    monkeypatch.setattr(MdteroClient, "download", fake_download)
    monkeypatch.setattr(MdteroClient, "translate_task", fake_translate_task)

    args = type(
        "Args",
        (),
        {
            "api_base": None,
            "workdir": tmp_path / "smoke",
            "doi": "10.48550/arXiv.1706.03762",
            "query": "rag papers",
            "limit": 3,
            "question": "What is indexed?",
            "project_id": None,
            "skip_discovery": True,
            "skip_download": False,
            "skip_translate": False,
            "skip_rag": True,
            "timeout": 5,
            "interval": 0.5,
            "translate_to": "zh-CN",
            "json": True,
        },
    )()

    assert cli.cmd_smoke(args) == 1
    payload = json.loads(capsys.readouterr().out)
    translate_step = next(step for step in payload["steps"] if step["name"] == "translate")

    assert payload["status"] == "failed"
    assert payload["reason_code"] == "smoke_failed"
    assert payload["primary_failure"] == {
        "step": "translate",
        "reason_code": "translation_provider_chain_failed",
        "action_hint": "Check backend translation provider diagnostics, quota, and API keys, then rerun `mdtero smoke --json`.",
    }
    assert payload["failed_steps"] == [
        {
            "name": "translate",
            "reason_code": "translation_provider_chain_failed",
            "action_hint": "Check backend translation provider diagnostics, quota, and API keys, then rerun `mdtero smoke --json`.",
            "next_commands": [
                "mdtero status <translation-task-id> --json",
                "mdtero translate <task-id-or-paper.md> --to zh-CN --wait --timeout 600 --json",
                "mdtero smoke --skip-translate --json",
            ],
            "task_id": "translate-1",
        }
    ]
    assert payload["next_commands"][:3] == [
        "mdtero status <translation-task-id> --json",
        "mdtero translate <task-id-or-paper.md> --to zh-CN --wait --timeout 600 --json",
        "mdtero smoke --skip-translate --json",
    ]
    assert "Smoke failed at `translate` with `translation_provider_chain_failed`" in payload["action_hint"]
    assert translate_step["status"] == "failed"
    assert translate_step["reason_code"] == "translation_provider_chain_failed"
    assert translate_step["result"]["final_task"]["translation_attempts"][0]["reason_code"] == "translation_provider_auth_failed"


def test_wait_commands_accept_timeout_and_interval_flags():
    parser = build_parser()

    parse_args = parser.parse_args(["parse", "10.1000/demo", "--wait", "--timeout", "5", "--interval", "0.5"])
    status_args = parser.parse_args(["status", "task-1", "--wait", "--timeout", "7", "--interval", "1.5"])
    project_parse_args = parser.parse_args(["project", "parse", "--wait", "--timeout", "9", "--interval", "2.5"])
    project_refresh_args = parser.parse_args(["project", "refresh", "--wait", "--timeout", "11", "--interval", "3.5"])
    translate_args = parser.parse_args(["translate", "parse-1", "--wait", "--timeout", "13", "--interval", "4.5"])
    rag_build_args = parser.parse_args(["rag", "build", "--wait", "--timeout", "15", "--interval", "1.25"])
    rag_query_args = parser.parse_args(["rag", "query", "What changed?", "--build-if-needed", "--timeout", "17", "--interval", "2"])

    assert parse_args.timeout == 5
    assert parse_args.interval == 0.5
    assert status_args.timeout == 7
    assert status_args.interval == 1.5
    assert project_parse_args.timeout == 9
    assert project_parse_args.interval == 2.5
    assert project_refresh_args.timeout == 11
    assert project_refresh_args.interval == 3.5
    assert translate_args.timeout == 13
    assert translate_args.interval == 4.5
    assert rag_build_args.wait is True
    assert rag_build_args.timeout == 15
    assert rag_build_args.interval == 1.25
    assert rag_query_args.timeout == 17
    assert rag_query_args.interval == 2


def test_rag_query_accepts_build_if_needed_flag():
    parser = build_parser()

    args = parser.parse_args(["rag", "query", "What changed?", "--build-if-needed", "--json"])

    assert args.question == "What changed?"
    assert args.build_if_needed is True
    assert args.json is True


def test_cli_login_url_carries_loopback_callback_and_state():
    url = build_cli_login_url("https://mdtero.example/", callback_url="http://127.0.0.1:4173/callback", state="state-1")
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)

    assert url.startswith("https://mdtero.example/auth?")
    assert query["cli_callback"] == ["http://127.0.0.1:4173/callback"]
    assert query["cli_state"] == ["state-1"]


def test_web_login_loopback_accepts_site_callback():
    opened_urls: list[str] = []

    def fake_open(url: str):
        opened_urls.append(url)
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        preflight = httpx.options(
            query["cli_callback"][0],
            headers={
                "Origin": "https://mdtero.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
            timeout=5,
        )
        assert preflight.status_code == 204
        assert preflight.headers["access-control-allow-origin"] == "https://mdtero.com"
        response = httpx.post(
            query["cli_callback"][0],
            headers={"Origin": "https://mdtero.com"},
            json={"state": query["cli_state"][0], "apiKey": "mdt_live_web", "prefix": "mdt_live"},
            timeout=5,
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "https://mdtero.com"
        return True

    result = run_web_login("https://mdtero.example", timeout_seconds=5, open_browser=fake_open)

    assert opened_urls
    assert result.api_key == "mdt_live_web"
    assert result.prefix == "mdt_live"


def test_login_command_saves_web_callback_key(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))

    def fake_run_web_login(site_base_url, *, timeout_seconds, open_browser=None):
        assert site_base_url == "https://mdtero.com"
        assert timeout_seconds == 7
        assert open_browser is None
        return WebLoginResult(api_key="mdt_live_saved", prefix="mdt_live")

    monkeypatch.setattr(cli, "run_web_login", fake_run_web_login)

    assert cli.cmd_login(type("Args", (), {"api_key": None, "timeout": 7, "no_browser": False})()) == 0
    cfg = load_config()

    assert cfg.api_key == "mdt_live_saved"
    assert "Saved web login API key" in capsys.readouterr().out


def test_login_no_browser_explains_loopback_and_headless_api_key(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))

    def fake_run_web_login(site_base_url, *, timeout_seconds, open_browser=None):
        assert site_base_url == "https://mdtero.com"
        assert timeout_seconds == 7
        assert open_browser is not None
        open_browser("https://mdtero.com/auth?cli_callback=http%3A%2F%2F127.0.0.1%3A4173%2Fcallback")
        return WebLoginResult(api_key="mdt_live_saved", prefix="mdt_live")

    monkeypatch.setattr(cli, "run_web_login", fake_run_web_login)

    assert cli.cmd_login(type("Args", (), {"api_key": None, "timeout": 7, "no_browser": True})()) == 0
    output = capsys.readouterr().out

    assert "loopback web-login URL" in output
    assert "mdtero setup --api-key --json" in output
    assert "127.0.0.1" in output
    assert "https://mdtero.com/auth?cli_callback=" in output


def test_login_rejects_blank_api_key(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))

    assert cli.cmd_login(type("Args", (), {"api_key": "   ", "timeout": 7, "no_browser": False})()) == 2
    output = capsys.readouterr().out
    cfg = load_config()

    assert "API key cannot be empty" in output
    assert cfg.api_key is None


def test_login_prompts_for_api_key_when_flag_omits_value(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: "mdt_live_prompted")
    monkeypatch.setattr(cli, "run_web_login", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("API-key login should not run browser OAuth")))

    assert cli.cmd_login(type("Args", (), {"api_key": API_KEY_PROMPT_SENTINEL, "timeout": 7, "no_browser": False})()) == 0
    output = capsys.readouterr().out
    cfg = load_config()

    assert cfg.api_key == "mdt_live_prompted"
    assert "Saved API key" in output


def test_login_rejects_blank_prompted_api_key(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: "   ")
    monkeypatch.setattr(cli, "run_web_login", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("blank API-key login should not run browser OAuth")))

    assert cli.cmd_login(type("Args", (), {"api_key": API_KEY_PROMPT_SENTINEL, "timeout": 7, "no_browser": False})()) == 2
    output = capsys.readouterr().out
    cfg = load_config()

    assert "API key cannot be empty" in output
    assert cfg.api_key is None


def test_doctor_accepts_api_key_from_environment(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MDTERO_API_KEY", "mdt_live_env")
    mock_doctor_remote_auth_ok(monkeypatch)

    assert cli.cmd_doctor(type("Args", (), {})()) == 0
    output = capsys.readouterr().out

    assert "API key" in output
    assert "MDTERO_API_KEY" in output


def test_doctor_reports_local_dependency_and_optional_integration_state(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    mock_doctor_remote_auth_ok(monkeypatch)
    save_config(MdteroConfig(
        api_key="mdt_live_config",
        academic=AcademicKeys(semantic_scholar_api_key="s2"),
        zotero=ZoteroConfig(library_id="123", library_type="user", api_key="zotero"),
    ))
    seen_imports: list[str] = []

    def fake_find_spec(name):
        seen_imports.append(name)
        return object() if name in {"curl_cffi.requests", "fastmcp", "pyzotero"} else None

    monkeypatch.setattr(cli.importlib.util, "find_spec", fake_find_spec)

    assert cli.cmd_doctor(type("Args", (), {})()) == 0
    output = capsys.readouterr().out

    assert seen_imports == ["curl_cffi.requests", "fastmcp", "pyzotero"]
    assert "FastMCP" in output
    assert "MCP server available" in output
    assert "pyzotero" in output
    assert "Zotero client available" in output
    assert "Semantic Scholar" in output
    assert "local discovery" in output
    assert "Zotero config" in output
    assert "user:123" in output


def test_doctor_reports_optional_fallbacks_when_integrations_are_missing(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    mock_doctor_remote_auth_ok(monkeypatch)
    save_config(MdteroConfig(api_key="mdt_live_config"))
    monkeypatch.setattr(cli.importlib.util, "find_spec", lambda _name: None)

    assert cli.cmd_doctor(type("Args", (), {})()) == 0
    output = capsys.readouterr().out

    assert "httpx fallback only" in output
    assert "Zotero import/sync unavailable" in output
    assert "server OpenAlex fallback" in output
    assert "run mdtero config zotero" in output


def test_doctor_reports_project_queue_and_rag_readiness(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    mock_doctor_remote_auth_ok(monkeypatch)
    save_config(MdteroConfig(api_key="mdt_live_config"))
    init_project(tmp_path, name="doctor-demo")
    bind_server_project(tmp_path, "42")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))
    add_paper(tmp_path, PaperRecord(input="10.1000/todo", status="pending"))
    monkeypatch.setattr(cli, "_doctor_server_rag_status", lambda cfg, root, *, remote_auth: None)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_doctor(type("Args", (), {})()) == 0
    output = capsys.readouterr().out
    rows = cli._doctor_project_rows(tmp_path)

    assert "Project papers" in output
    assert ("Project papers", "ok", "2 total / 1 pending / 0 running / 1 succeeded / 0 failed") in rows
    assert "Server project" in output
    assert "42" in output
    assert "RAG readiness" in output
    assert ("RAG readiness", "check", "run mdtero project ingest --json, then mdtero rag status --json") in rows


def test_doctor_reports_live_server_rag_readiness(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    mock_doctor_remote_auth_ok(monkeypatch)
    save_config(MdteroConfig(api_key="mdt_live_config"))
    init_project(tmp_path, name="doctor-demo")
    bind_server_project(tmp_path, "42")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    def fake_status(self, project_id):
        assert project_id == "42"
        return {
            "project_id": "42",
            "status": "ready",
            "reason_code": "indexed",
            "selected_provider": "voyage",
            "provider_state": "configured",
            "provider_configured": True,
            "embedding_model": "voyage-test",
            "readiness": {"ready_for_query": True, "next_step": "query", "chunk_count": 8, "embedded_count": 8},
            "agent_summary": {"ready_for_query": True, "selected_provider": "voyage", "provider_state": "configured", "embedding_model": "voyage-test"},
            "next_commands": ["mdtero rag status --json", "mdtero rag query \"<question>\" --build-if-needed --json"],
        }

    monkeypatch.setattr(MdteroClient, "rag_status", fake_status)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_doctor(type("Args", (), {})()) == 0
    output = capsys.readouterr().out
    rows = cli._doctor_project_rows(tmp_path, server_rag_status=cli._doctor_server_rag_status(load_config(), tmp_path, remote_auth={"status": "ok"}))

    assert "RAG readiness" in output
    assert "ready" in output
    assert "voyage-test" in output
    assert ("RAG readiness", "ready", "indexed; query with mdtero rag query \"<question>\" --build-if-needed --json") in rows
    assert ("Server RAG provider", "configured", "voyage / voyage-test") in rows


def test_doctor_reports_unlinked_project_rag_bootstrap_hint(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    mock_doctor_remote_auth_ok(monkeypatch)
    save_config(MdteroConfig(api_key="mdt_live_config"))
    init_project(tmp_path, name="doctor-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))
    monkeypatch.setattr(cli, "_doctor_server_rag_status", lambda cfg, root, *, remote_auth: None)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_doctor(type("Args", (), {})()) == 0
    output = capsys.readouterr().out
    rows = cli._doctor_project_rows(tmp_path)

    assert "Server project" in output
    assert "not linked" in output
    assert "mdtero rag query" in output
    assert ("RAG readiness", "not linked", "run mdtero rag query \"What are the strongest findings?\" --build-if-needed --json") in rows


def test_doctor_json_reports_safe_project_and_rag_summary(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    mock_doctor_remote_auth_ok(monkeypatch)
    secret = "mdt_live_config_secret"
    save_config(MdteroConfig(
        api_key=secret,
        academic=AcademicKeys(
            elsevier_api_key="elsevier-secret",
            wiley_tdm_token="wiley-secret",
            semantic_scholar_api_key="s2-secret",
        ),
        zotero=ZoteroConfig(library_id="123", library_type="user", api_key="zotero-secret"),
    ))
    init_project(tmp_path, name="doctor-demo")
    bind_server_project(tmp_path, "42")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))
    monkeypatch.setattr(cli, "_doctor_server_rag_status", lambda cfg, root, *, remote_auth: None)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_doctor(type("Args", (), {"json": True})()) == 0
    raw = capsys.readouterr().out
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["authenticated"] is True
    assert payload["api_key_source"] == "saved config"
    assert payload["academic"] == {
        "elsevier_api_key": True,
        "wiley_tdm_token": True,
        "semantic_scholar_api_key": True,
        "discover_source": "local_semantic_scholar",
    }
    assert payload["zotero"] == {"configured": True, "library_id": "123", "library_type": "user"}
    assert payload["project"]["server_project_id"] == "42"
    assert payload["project"]["ready_for_ingest_count"] == 1
    assert payload["project"]["rag_status"] == "check"
    assert "mdtero project ingest --json" in payload["next_commands"]
    assert secret not in raw
    assert "elsevier-secret" not in raw
    assert "wiley-secret" not in raw
    assert "s2-secret" not in raw
    assert "zotero-secret" not in raw


def test_doctor_json_detects_invalid_remote_api_key(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    save_config(MdteroConfig(api_key="mdt_live_invalid"))
    monkeypatch.setattr(
        cli,
        "_doctor_remote_auth",
        lambda _cfg: {
            "status": "failed",
            "error_code": "authentication_required",
            "reason_code": "authentication_required",
            "status_code": 401,
            "next_commands": ["mdtero setup --api-key --json", "mdtero doctor --json"],
        },
    )

    assert cli.cmd_doctor(type("Args", (), {"json": True})()) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "invalid_auth"
    assert payload["authenticated"] is False
    assert payload["remote_auth"]["status_code"] == 401
    assert payload["checks"][0] == {"check": "API key", "status": "invalid", "detail": "authentication_required"}
    assert payload["next_commands"] == ["mdtero setup --api-key --json", "mdtero doctor --json"]


def test_doctor_json_reports_missing_auth_and_project_init_next_steps(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_doctor(type("Args", (), {"json": True})()) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "missing_auth"
    assert payload["authenticated"] is False
    assert payload["project"]["initialized"] is False
    assert payload["project"]["path"].endswith(".mdtero/project.json")
    assert payload["next_commands"][0] == "mdtero setup"
    assert "mdtero project init --name <name>" in payload["next_commands"]


def test_client_headers_use_environment_api_key(monkeypatch):
    monkeypatch.setenv("MDTERO_API_KEY", "mdt_live_env")

    headers = MdteroClient(config=MdteroConfig(api_key=None))._headers()

    assert headers["Authorization"] == "ApiKey mdt_live_env"


def test_rag_status_accepts_agent_friendly_flags():
    parser = build_parser()

    doctor_args = parser.parse_args(["doctor", "--json"])
    args = parser.parse_args(["rag", "status", "--project-id", "42", "--json"])

    assert doctor_args.json is True
    assert args.project_id == "42"
    assert args.json is True


def test_rag_build_and_query_accept_agent_friendly_json_flags():
    parser = build_parser()

    build_args = parser.parse_args(["rag", "build", "--project-id", "42", "--json"])
    query_args = parser.parse_args(["rag", "query", "main contribution?", "--project-id", "42", "--json"])

    assert build_args.project_id == "42"
    assert build_args.json is True
    assert query_args.project_id == "42"
    assert query_args.question == "main contribution?"
    assert query_args.json is True


def test_project_management_commands_accept_agent_friendly_json_flags():
    parser = build_parser()

    init_args = parser.parse_args(["project", "init", "--name", "demo", "--json"])
    add_args = parser.parse_args(["project", "add", "10.1000/demo", "--json"])
    link_args = parser.parse_args(["project", "link", "--server-project-id", "42", "--json"])
    remove_args = parser.parse_args(["project", "remove", "10.1000/demo", "--json"])
    list_args = parser.parse_args(["project", "list", "--json"])
    status_args = parser.parse_args(["project", "status", "--json"])
    bib_args = parser.parse_args(["project", "import-bib", "refs.bib", "--json"])

    assert init_args.name == "demo"
    assert init_args.json is True
    assert add_args.input == "10.1000/demo"
    assert add_args.json is True
    assert link_args.server_project_id == "42"
    assert link_args.json is True
    assert remove_args.input == "10.1000/demo"
    assert remove_args.json is True
    assert list_args.json is True
    assert status_args.json is True
    assert bib_args.paths == [Path("refs.bib")]
    assert bib_args.json is True


def test_download_accepts_agent_friendly_json_flag():
    parser = build_parser()

    args = parser.parse_args(["download", "task-1", "paper_md", "--output-dir", "out", "--json"])

    assert args.task_id == "task-1"
    assert args.artifact == "paper_md"
    assert args.output_dir == Path("out")
    assert args.json is True


def test_academic_setup_selection_accepts_numbered_enter_flow():
    assert _parse_academic_selection("") == set()
    assert _parse_academic_selection("1,3") == {"1", "3"}
    assert _parse_academic_selection("2 3") == {"2", "3"}
    assert _parse_academic_selection("all") == {"1", "2", "3"}

    try:
        _parse_academic_selection("4")
    except ValueError as exc:
        assert "Choose 1, 2, 3" in str(exc)
    else:
        raise AssertionError("expected invalid academic option")


def test_config_academic_accepts_headless_key_flags():
    parser = build_parser()

    args = parser.parse_args([
        "config",
        "academic",
        "--elsevier-key",
        "elsevier-1",
        "--wiley-tdm-token",
        "wiley-1",
        "--semantic-scholar-key",
        "s2-1",
        "--json",
    ])

    assert args.elsevier_key == "elsevier-1"
    assert args.wiley_tdm_token == "wiley-1"
    assert args.semantic_scholar_key == "s2-1"
    assert args.json is True


def test_config_academic_headless_json_saves_without_echoing_secrets(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    args = build_parser().parse_args([
        "config",
        "academic",
        "--elsevier-key",
        "elsevier-secret",
        "--wiley-tdm-token",
        "wiley-secret",
        "--semantic-scholar-key",
        "s2-secret",
        "--json",
    ])

    assert cmd_config_academic(args) == 0
    payload = json.loads(capsys.readouterr().out)
    cfg = load_config()

    assert cfg.academic.elsevier_api_key == "elsevier-secret"
    assert cfg.academic.wiley_tdm_token == "wiley-secret"
    assert cfg.academic.semantic_scholar_api_key == "s2-secret"
    assert payload["status"] == "saved"
    assert payload["configured"] == {
        "elsevier_api_key": True,
        "wiley_tdm_token": True,
        "semantic_scholar_api_key": True,
    }
    assert payload["discover_source"] == "local_semantic_scholar"
    assert payload["discover_behavior"] == {
        "semantic_scholar": "local_first",
        "fallback": "server_openalex",
        "action_hint": "Semantic Scholar is configured; discovery tries the local Semantic Scholar API first and falls back to server OpenAlex when needed.",
    }
    assert "mdtero smoke --json" in payload["next_commands"]
    assert "mdtero mcp briefing --json" in payload["next_commands"]
    groups = {group["title"]: group["commands"] for group in payload["next_command_groups"]}
    assert "One-shot launch smoke" in groups
    assert "Browser extension handoff" in groups
    assert "mdtero smoke --json" in groups["One-shot launch smoke"]
    assert "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json" in groups["Browser extension handoff"]
    assert "https://dev.elsevier.com/apikey/manage" in payload["application_links"]["elsevier_api_key"]
    output = json.dumps(payload)
    assert "elsevier-secret" not in output
    assert "wiley-secret" not in output
    assert "s2-secret" not in output


def test_config_academic_json_reports_server_openalex_when_s2_is_absent(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    args = build_parser().parse_args(["config", "academic", "--json"])

    assert cmd_config_academic(args) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "current"
    assert payload["configured"]["semantic_scholar_api_key"] is False
    assert payload["discover_source"] == "server_openalex"
    assert payload["discover_behavior"]["semantic_scholar"] == "not_configured"
    assert payload["discover_behavior"]["fallback"] == "server_openalex"
    assert "server OpenAlex fallback" in payload["discover_behavior"]["action_hint"]


def test_setup_next_steps_cover_project_rag_zotero_and_agent_workflows(capsys):
    from mdtero import cli

    cli._print_next_steps(Console())
    output = capsys.readouterr().out
    compact_output = " ".join(output.split())

    assert "Verify this workstation" in output
    assert "mdtero doctor --json" in output
    assert "mdtero config academic --json" in output
    assert "mdtero agent detect --json" in output
    assert "One-shot launch smoke" in output
    assert "mdtero smoke --json" in output
    assert "mdtero smoke --doi 10.48550/arXiv.1706.03762 --wait --timeout 300 --json" in output
    assert "mdtero mcp briefing --json" in output
    assert "Start a local project" in output
    assert "mdtero project init --name literature-review" in output
    assert "mdtero discover \"graph neural networks\" --limit 5 --interactive" in output
    assert "mdtero discover \"graph neural networks\" --limit 5 --add --select 1,3 --json" in output
    assert "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json" in output
    assert "mdtero parse https://example.org/open-paper --trace --wait --timeout 300 --json" in compact_output
    assert "mdtero parse --file paper.pdf --trace --wait --timeout 600 --json" in output
    assert "mdtero parse --batch ./papers --wait --timeout 300 --json" in output
    assert "Browser extension handoff" in output
    assert "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json" in output
    assert "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json" in compact_output
    assert "mdtero status <task-id> --wait --timeout 300 --json" in output
    assert "Translate completed Markdown" in output
    assert "mdtero translate <parse-task-id> --to zh-CN --wait --timeout 600 --json" in output
    assert "mdtero translate paper.md --to zh-CN --wait --timeout 600 --json" in output
    assert "mdtero download <translation-task-id> translated_md --output-dir ./mdtero-output --json" in compact_output
    assert "mdtero config zotero" in output
    assert "mdtero zotero import --limit 20" in output
    assert "mdtero zotero sync" in output
    assert "mdtero rag status --json" in output
    assert "mdtero rag build --wait --json" in output
    assert "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json" in compact_output
    assert "mdtero rag query \"<question>\" --build-if-needed --json" in compact_output
    assert "mdtero mcp serve" in output
    assert "mdtero agent install --interactive" in output
    assert "mdtero agent install\n" not in output


def test_result_selection_supports_all_and_number_lists():
    assert _parse_result_selection("", max_count=3) == []
    assert _parse_result_selection("all", max_count=2) == [1, 2]
    assert _parse_result_selection("1,3 3", max_count=3) == [1, 3]

    try:
        _parse_result_selection("4", max_count=3)
    except ValueError as exc:
        assert "outside 1..3" in str(exc)
    else:
        raise AssertionError("expected invalid result selection")


def test_discover_results_can_be_added_to_project_queue(monkeypatch, tmp_path: Path):
    init_project(tmp_path, name="discover-demo")
    monkeypatch.chdir(tmp_path)

    summary = _add_discovery_results_to_project(
        {
            "source": "openalex_server",
            "items": [
                {"title": "Paper A", "doi": "10.1000/a", "source": "openalex"},
                {"title": "Paper B", "url": "https://example.test/paper-b", "source": "openalex"},
                {"title": "Paper C"},
            ],
        },
        selection="1,2,3",
    )

    state = load_project(tmp_path)
    assert summary["added_count"] == 2
    assert summary["skipped_count"] == 1
    assert summary["source"] == "openalex_server"
    assert summary["source_mode"] == "openalex_server"
    assert summary["selection"] == [1, 2, 3]
    assert summary["next_commands"] == ["mdtero project parse --wait --timeout 300 --json", "mdtero project refresh --wait --timeout 300 --json", "mdtero project download --output-dir ./mdtero-output --json"]
    assert summary["project"]["pending_count"] == 2
    assert [paper.input for paper in state.papers] == ["10.1000/a", "https://example.test/paper-b"]
    assert state.papers[0].source == "discover:openalex"
    assert state.papers[0].title == "Paper A"


def test_discover_project_add_summary_preserves_semantic_scholar_and_fallback_source(monkeypatch, tmp_path: Path):
    init_project(tmp_path, name="discover-demo")
    monkeypatch.chdir(tmp_path)

    semantic_summary = _add_discovery_results_to_project(
        {"source": "semantic_scholar_local", "items": [{"title": "S2 Paper", "doi": "10.1000/s2", "source": "semantic_scholar"}]},
        selection="all",
    )
    fallback_summary = _add_discovery_results_to_project(
        {
            "source": "openalex_server",
            "discovery_fallback": {"reason_code": "semantic_scholar_rate_limited"},
            "items": [{"title": "OA Paper", "doi": "10.1000/oa", "source": "openalex"}],
        },
        selection="all",
    )

    assert semantic_summary["source_mode"] == "semantic_scholar_local"
    assert semantic_summary["fallback_reason_code"] is None
    assert fallback_summary["source_mode"] == "openalex_server"
    assert fallback_summary["fallback_reason_code"] == "semantic_scholar_rate_limited"


def test_semantic_scholar_discovery_uses_parse_friendly_external_id_urls():
    assert _semantic_scholar_parse_url({"DOI": "10.48550/arXiv.1706.03762", "ArXiv": "1706.03762"}) == "https://doi.org/10.48550/arXiv.1706.03762"
    assert _semantic_scholar_parse_url({"ArXiv": "2312.07559"}) == "https://arxiv.org/abs/2312.07559"
    assert _semantic_scholar_parse_url({"PMCID": "7517829"}) == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7517829/"
    assert _semantic_scholar_parse_url({"PubMed": "123456"}) == "https://pubmed.ncbi.nlm.nih.gov/123456/"


def test_semantic_scholar_discovery_add_prefers_arxiv_over_s2_page(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    init_project(tmp_path, name="s2-discovery")

    result = {
        "source": "semantic_scholar_local",
        "items": [
            {
                "title": "PaperQA",
                "doi": None,
                "url": _semantic_scholar_parse_url({"ArXiv": "2312.07559"}) or "https://www.semanticscholar.org/paper/demo",
                "semantic_scholar_url": "https://www.semanticscholar.org/paper/demo",
                "source": "semantic_scholar_local",
            }
        ],
    }

    summary = _add_discovery_results_to_project(result, selection="1")
    state = load_project(tmp_path)

    assert summary["source_mode"] == "semantic_scholar_local"
    assert summary["added"][0]["input"] == "https://arxiv.org/abs/2312.07559"
    assert state.papers[0].input == "https://arxiv.org/abs/2312.07559"


def test_discover_interactive_adds_prompted_results_to_project(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="discover-demo")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("mdtero.cli.Prompt.ask", lambda *args, **kwargs: "1 2")

    def fake_discover(self, query, *, limit=10):
        assert query == "rag papers"
        assert limit == 3
        return {
            "source": "openalex_server",
            "items": [
                {"title": "Paper A", "doi": "10.1000/a", "source": "openalex"},
                {"title": "Paper B", "url": "https://example.test/paper-b", "source": "openalex"},
                {"title": "Paper C"},
            ],
        }

    monkeypatch.setattr(MdteroClient, "discover", fake_discover)
    args = type("Args", (), {"query": "rag papers", "limit": 3, "add": False, "select": "", "interactive": True, "json": True})()

    assert cli.cmd_discover(args) == 0
    payload = json.loads(capsys.readouterr().out)
    state = load_project(tmp_path)

    assert payload["project_add"]["added_count"] == 2
    assert [paper.input for paper in state.papers] == ["10.1000/a", "https://example.test/paper-b"]


def test_discover_accepts_unquoted_multi_word_query(monkeypatch, capsys):
    from mdtero import cli

    def fake_discover(self, query, *, limit=10):
        assert query == "Thermochemical Energy storage Vermiculite"
        assert limit == 5
        return {"source": "semantic_scholar_local", "items": [{"title": "Vermiculite Paper", "doi": "10.1000/v"}]}

    monkeypatch.setattr(MdteroClient, "discover", fake_discover)
    args = build_parser().parse_args(["discover", "Thermochemical", "Energy", "storage", "Vermiculite", "--limit", "5", "--json"])

    assert cli.cmd_discover(args) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["items"][0]["title"] == "Vermiculite Paper"


def test_discover_interactive_enter_skips_project_add(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="discover-demo")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("mdtero.cli.Prompt.ask", lambda *args, **kwargs: "")
    monkeypatch.setattr(MdteroClient, "discover", lambda self, query, *, limit=10: {"items": [{"title": "Paper A", "doi": "10.1000/a"}]})

    args = type("Args", (), {"query": "rag", "limit": 1, "add": False, "select": "", "interactive": True, "json": True})()

    assert cli.cmd_discover(args) == 0
    payload = json.loads(capsys.readouterr().out)
    state = load_project(tmp_path)

    assert payload["project_add"]["added_count"] == 0
    assert payload["project_add"]["next_commands"] == [
        "mdtero project status --json",
        "mdtero discover \"<topic>\" --limit 5 --interactive",
        "mdtero discover \"<topic>\" --limit 5 --add --select 1,3 --json",
    ]
    assert state.papers == []


def test_discover_non_json_prints_semantic_scholar_fallback_notice(monkeypatch, capsys):
    from mdtero import cli

    def fake_discover(self, query, *, limit=10):
        assert query == "rag papers"
        return {
            "source": "openalex_server",
            "discovery_fallback": {
                "from": "semantic_scholar_local",
                "to": "openalex_server",
                "reason_code": "semantic_scholar_rate_limited",
                "action_hint": "Semantic Scholar rate-limited local discovery. Wait and retry.",
            },
            "items": [{"title": "Fallback Paper", "doi": "10.1000/fallback", "source": "openalex"}],
        }

    monkeypatch.setattr(MdteroClient, "discover", fake_discover)
    args = type("Args", (), {"query": "rag papers", "limit": 3, "add": False, "select": "", "interactive": False, "json": False})()

    assert cli.cmd_discover(args) == 0
    output = capsys.readouterr().out
    assert "Semantic Scholar local discovery failed (semantic_scholar_rate_limited)" in output
    assert "server OpenAlex fallback" in output
    assert "Fallback Paper" in output


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


def test_config_keeps_environment_api_key_as_runtime_override(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MDTERO_API_KEY", "mdt_live_env")

    cfg = load_config()

    assert cfg.api_key is None
    assert cfg.effective_api_key == "mdt_live_env"
    assert cfg.api_key_source == "MDTERO_API_KEY"
    assert cfg.is_authenticated is True


def test_config_reads_headless_academic_keys_from_environment(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MDTERO_ELSEVIER_API_KEY", "elsevier-env")
    monkeypatch.setenv("MDTERO_WILEY_TDM_TOKEN", "wiley-env")
    monkeypatch.setenv("MDTERO_SEMANTIC_SCHOLAR_API_KEY", "s2-env")

    cfg = load_config()

    assert cfg.academic.elsevier_api_key == "elsevier-env"
    assert cfg.academic.wiley_tdm_token == "wiley-env"
    assert cfg.academic.semantic_scholar_api_key == "s2-env"
    assert cfg.has_semantic_scholar_key is True


def test_saved_academic_keys_take_precedence_over_environment(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MDTERO_ELSEVIER_API_KEY", "elsevier-env")
    monkeypatch.setenv("MDTERO_WILEY_TDM_TOKEN", "wiley-env")
    monkeypatch.setenv("MDTERO_SEMANTIC_SCHOLAR_API_KEY", "s2-env")
    path = tmp_path / "config.json"
    save_config(
        MdteroConfig(
            academic=AcademicKeys(
                elsevier_api_key="elsevier-saved",
                wiley_tdm_token="wiley-saved",
                semantic_scholar_api_key="s2-saved",
            )
        ),
        path,
    )

    cfg = load_config(path)

    assert cfg.academic.elsevier_api_key == "elsevier-saved"
    assert cfg.academic.wiley_tdm_token == "wiley-saved"
    assert cfg.academic.semantic_scholar_api_key == "s2-saved"


def test_client_keeps_task_submission_on_v1_when_route_is_not_deployed(monkeypatch):
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
        raise AssertionError(path)

    monkeypatch.setattr(MdteroClient, "_request", fake_request)
    client = MdteroClient()

    route = client.route("10.1000/demo")

    assert route["route_planner_fallback"] is True
    assert route["acquisition_mode"] == "server_parse"
    assert route["server_entrypoint"] == "/api/v1/tasks/parse"
    assert route["upload_entrypoint"] == "/api/v1/tasks/upload"
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        client.parse("10.1000/demo")
    assert exc_info.value.response.status_code == 404
    assert [call[1] for call in calls] == ["/api/v1/route", "/api/v1/tasks/parse"]


def test_client_reports_v1_discovery_failure_without_old_endpoint_fallback(monkeypatch):
    calls = []

    def fake_request(self, method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path == "/api/v1/discovery/search":
            request = httpx.Request(method, "https://api.mdtero.test/api/v1/discovery/search")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("not found", request=request, response=response)
        raise AssertionError(path)

    monkeypatch.setattr(MdteroClient, "_request", fake_request)
    with pytest.raises(DiscoveryError) as exc_info:
        MdteroClient().discover("rag", limit=1)

    assert exc_info.value.payload["error_code"] == "discovery_failed"
    assert exc_info.value.payload["status_code"] == 404
    assert [call[1] for call in calls] == ["/api/v1/discovery/search"]


def test_translate_text_payload_is_compatible_with_v1_schema(monkeypatch):
    captured: dict[str, object] = {}

    def fake_request(self, method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["json"] = kwargs.get("json")
        return {"task_id": "translate-task", "status": "queued"}

    monkeypatch.setattr(MdteroClient, "_request", fake_request)

    result = MdteroClient().translate_text("# Title\n\nHello", filename="paper.md", target_language="zh-CN")

    assert result == {"task_id": "translate-task", "status": "queued"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/tasks/translate"
    assert captured["json"] == {
        "source_markdown_path": "",
        "source_markdown_text": "# Title\n\nHello",
        "source_markdown_filename": "paper.md",
        "target_language": "zh-CN",
        "mode": "full",
    }


def test_translate_server_path_payload_is_compatible_with_v1_schema(monkeypatch):
    captured: dict[str, object] = {}

    def fake_request(self, method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["json"] = kwargs.get("json")
        return {"task_id": "translate-task", "status": "queued"}

    monkeypatch.setattr(MdteroClient, "_request", fake_request)

    result = MdteroClient().translate_server_path("/app/tasks/parse-1/paper.md", target_language="zh-CN")

    assert result == {"task_id": "translate-task", "status": "queued"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/tasks/translate"
    assert captured["json"] == {
        "source_markdown_path": "/app/tasks/parse-1/paper.md",
        "target_language": "zh-CN",
        "mode": "full",
    }


def test_translation_source_path_from_task_prefers_paper_md_artifact_path():
    task = {
        "result": {
            "artifacts": {
                "paper_md": {"path": "/app/tasks/parse-1/paper.md", "filename": "paper.md"},
                "paper_bundle": {"path": "/app/tasks/parse-1/paper.zip"},
            }
        }
    }

    assert translation_source_path_from_task(task) == "/app/tasks/parse-1/paper.md"


def test_translation_source_download_artifact_from_v1_download_artifacts():
    from mdtero.client import translation_source_download_artifact_from_task

    task = {
        "result": {
            "download_artifacts": [
                {"artifact": "paper_bundle", "filename": "paper.zip"},
                {"artifact": "paper_md", "filename": "paper.md", "media_type": "text/markdown"},
            ]
        }
    }

    assert translation_source_download_artifact_from_task(task) == {
        "artifact": "paper_md",
        "filename": "paper.md",
        "media_type": "text/markdown",
    }


def test_translation_source_download_artifact_from_legacy_download_artifacts_dict():
    from mdtero.client import translation_source_download_artifact_from_task

    task = {"result": {"download_artifacts": {"paper_md": {"filename": "legacy.md"}}}}

    assert translation_source_download_artifact_from_task(task) == {
        "artifact": "paper_md",
        "filename": "legacy.md",
    }


def test_translate_task_uses_parse_task_artifact_path(monkeypatch):
    calls = []

    def fake_task(self, task_id):
        calls.append(("task", task_id))
        return {"result": {"artifacts": {"paper_md": {"path": "/app/tasks/parse-1/paper.md"}}}}

    def fake_translate_server_path(self, source_markdown_path, *, target_language="zh-CN"):
        calls.append(("translate", source_markdown_path, target_language))
        return {"task_id": "translate-task", "status": "queued"}

    monkeypatch.setattr(MdteroClient, "task", fake_task)
    monkeypatch.setattr(MdteroClient, "translate_server_path", fake_translate_server_path)

    result = MdteroClient().translate_task("parse-1", target_language="zh-CN")

    assert result == {"task_id": "translate-task", "status": "queued"}
    assert calls == [("task", "parse-1"), ("translate", "/app/tasks/parse-1/paper.md", "zh-CN")]


def test_translate_task_downloads_v1_markdown_artifact_when_server_path_is_absent(monkeypatch):
    calls = []

    class FakeResponse:
        headers = {"content-disposition": 'attachment; filename="vaswani2017attention.md"'}
        text = "# Attention Is All You Need\n\nTransformer text."

        def raise_for_status(self):
            calls.append(("raise_for_status",))

    def fake_task(self, task_id):
        calls.append(("task", task_id))
        return {
            "result": {
                "download_artifacts": [
                    {"artifact": "paper_md", "filename": "vaswani2017attention.md", "media_type": "text/markdown"}
                ]
            }
        }

    def fake_raw_request(self, method, path, **kwargs):
        calls.append(("raw", method, path, kwargs))
        return FakeResponse()

    def fake_translate_text(self, markdown, *, filename="paper.md", target_language="zh-CN"):
        calls.append(("translate_text", markdown, filename, target_language))
        return {"task_id": "translate-task", "status": "queued"}

    monkeypatch.setattr(MdteroClient, "task", fake_task)
    monkeypatch.setattr(MdteroClient, "_raw_request", fake_raw_request)
    monkeypatch.setattr(MdteroClient, "translate_text", fake_translate_text)

    result = MdteroClient().translate_task("parse-1", target_language="zh-CN")

    assert result == {"task_id": "translate-task", "status": "queued"}
    assert calls == [
        ("task", "parse-1"),
        ("raw", "GET", "/api/v1/tasks/parse-1/download/paper_md", {}),
        ("raise_for_status",),
        ("translate_text", "# Attention Is All You Need\n\nTransformer text.", "vaswani2017attention.md", "zh-CN"),
    ]


def test_cmd_translate_accepts_task_id_and_outputs_json(monkeypatch, capsys):
    from mdtero import cli

    def fake_translate_task(self, task_id, *, target_language="zh-CN", artifact="paper_md"):
        assert task_id == "parse-1"
        assert target_language == "zh-CN"
        assert artifact == "paper_md"
        return {"task_id": "translate-task", "status": "queued"}

    monkeypatch.setattr(MdteroClient, "translate_task", fake_translate_task)

    assert cli.cmd_translate(type("Args", (), {"task_or_file": "parse-1", "to": "zh-CN", "json": True})()) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "task_id": "translate-task",
        "status": "queued",
        "task_api": "/api/v1/tasks/{task_id}",
        "download_api": "/api/v1/tasks/{task_id}/download/{artifact}",
        "preferred_artifact": "translated_md",
        "next_commands": [
            "mdtero status translate-task --wait --timeout 300 --json",
            "mdtero download translate-task translated_md --output-dir ./mdtero-output --json",
        ],
    }


def test_cmd_translate_wait_includes_final_task(monkeypatch, capsys):
    from mdtero import cli

    calls = []

    def fake_translate_task(self, task_id, *, target_language="zh-CN", artifact="paper_md"):
        calls.append(("translate", task_id, target_language, artifact))
        return {"task_id": "translate-task", "status": "queued"}

    def fake_wait(self, task_id, *, interval=2.0, timeout=600.0):
        calls.append(("wait", task_id, interval, timeout))
        return {
            "task_id": task_id,
            "status": "succeeded",
            "result": {"artifacts": {"translated_md": {"filename": "paper_CN.md"}}},
        }

    monkeypatch.setattr(MdteroClient, "translate_task", fake_translate_task)
    monkeypatch.setattr(MdteroClient, "wait", fake_wait)

    args = type("Args", (), {"task_or_file": "parse-1", "to": "zh-CN", "wait": True, "timeout": 13, "interval": 4.5, "json": True})()
    assert cli.cmd_translate(args) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["task_id"] == "translate-task"
    assert payload["final_task"]["status"] == "succeeded"
    assert payload["final_task"]["preferred_artifact"] == "translated_md"
    assert payload["final_task"]["next_commands"] == [
        "mdtero download translate-task translated_md --output-dir ./mdtero-output --json"
    ]
    assert calls == [("translate", "parse-1", "zh-CN", "paper_md"), ("wait", "translate-task", 4.5, 13.0)]


def test_cmd_translate_wait_returns_nonzero_for_failed_final_task(monkeypatch, capsys):
    from mdtero import cli

    def fake_translate_task(self, task_id, *, target_language="zh-CN", artifact="paper_md"):
        return {"task_id": "translate-task", "status": "queued"}

    def fake_wait(self, task_id, *, interval=2.0, timeout=600.0):
        return {
            "task_id": task_id,
            "status": "failed",
            "error_code": "translation_provider_chain_failed",
            "result": {
                "reason_code": "translation_provider_chain_failed",
                "action_hint": "All configured server translation providers failed.",
                "translation_attempts": [{"provider": "mimo", "reason_code": "translation_provider_auth_failed"}],
            },
        }

    monkeypatch.setattr(MdteroClient, "translate_task", fake_translate_task)
    monkeypatch.setattr(MdteroClient, "wait", fake_wait)

    args = type("Args", (), {"task_or_file": "parse-1", "to": "zh-CN", "wait": True, "timeout": 13, "interval": 4.5, "json": True})()
    assert cli.cmd_translate(args) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["final_task"]["reason_code"] == "translation_provider_chain_failed"
    assert payload["final_task"]["action_hint"] == "All configured server translation providers failed."
    assert payload["final_task"]["translation_attempts"][0]["reason_code"] == "translation_provider_auth_failed"


def test_cmd_translate_preserves_server_next_commands(monkeypatch, capsys, tmp_path):
    from mdtero import cli

    paper = tmp_path / "paper.md"
    paper.write_text("# Demo\n\nHello", encoding="utf-8")

    def fake_translate_text(self, markdown, *, filename="paper.md", target_language="zh-CN"):
        assert markdown == "# Demo\n\nHello"
        assert filename == "paper.md"
        assert target_language == "zh-CN"
        return {
            "task_id": "translate-task",
            "status": "queued",
            "next_commands": ["mdtero status translate-task --wait --timeout 300 --json"],
        }

    monkeypatch.setattr(MdteroClient, "translate_text", fake_translate_text)

    assert cli.cmd_translate(type("Args", (), {"task_or_file": str(paper), "to": "zh-CN", "json": True})()) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["preferred_artifact"] == "translated_md"
    assert payload["next_commands"] == [
        "mdtero status translate-task --wait --timeout 300 --json",
        "mdtero download translate-task translated_md --output-dir ./mdtero-output --json",
    ]


def test_cmd_translate_reports_missing_task_artifact_without_traceback(monkeypatch, capsys):
    from mdtero import cli

    def fake_translate_task(self, task_id, *, target_language="zh-CN", artifact="paper_md"):
        raise ValueError("translation_source_artifact_missing")

    monkeypatch.setattr(MdteroClient, "translate_task", fake_translate_task)

    assert cli.cmd_translate(type("Args", (), {"task_or_file": "parse-1", "to": "zh-CN", "json": True})()) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["error_code"] == "translation_source_artifact_missing"
    assert payload["task_id"] == "parse-1"
    assert "mdtero status <task-id> --json" in payload["action_hint"]
    assert payload["next_commands"][0] == "mdtero status parse-1 --json"


def test_discover_falls_back_to_server_when_semantic_scholar_is_unreachable(monkeypatch):
    calls = []

    def fake_s2(self, query, *, limit):
        raise httpx.ConnectError("socks tls failed")

    def fake_request(self, method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"items": [{"title": "Server fallback"}]}

    monkeypatch.setattr(MdteroClient, "_semantic_scholar_search", fake_s2)
    monkeypatch.setattr(MdteroClient, "_request", fake_request)

    result = MdteroClient(config=MdteroConfig(api_key="key", academic=AcademicKeys(semantic_scholar_api_key="s2"))).discover("rag", limit=1)

    assert result["source"] == "openalex_server"
    assert result["discovery_diagnostics"] == {
        "semantic_scholar_configured": True,
        "semantic_scholar_attempted": True,
        "server_openalex_attempted": True,
    }
    assert result["local_semantic_scholar_error"] == "ConnectError"
    assert result["local_semantic_scholar_failure"]["reason_code"] == "semantic_scholar_network_error"
    assert result["discovery_fallback"] == {
        "from": "semantic_scholar_local",
        "to": "openalex_server",
        "reason_code": "semantic_scholar_network_error",
        "action_hint": "Local Semantic Scholar discovery failed; using the Mdtero server OpenAlex fallback for this query.",
    }
    assert result["items"][0]["title"] == "Server fallback"
    assert calls[0][1] == "/api/v1/discovery/search"


def test_discover_explains_semantic_scholar_rate_limit_before_openalex_fallback(monkeypatch):
    def fake_s2(self, query, *, limit):
        request = httpx.Request("GET", "https://api.semanticscholar.org/graph/v1/paper/search")
        response = httpx.Response(429, json={"message": "Too many requests"}, request=request)
        raise httpx.HTTPStatusError("rate limited", request=request, response=response)

    monkeypatch.setattr(MdteroClient, "_semantic_scholar_search", fake_s2)
    monkeypatch.setattr(MdteroClient, "_request", lambda self, method, path, **kwargs: {"items": []})

    result = MdteroClient(config=MdteroConfig(api_key="key", academic=AcademicKeys(semantic_scholar_api_key="s2"))).discover("rag", limit=1)

    assert result["source"] == "openalex_server"
    assert result["local_semantic_scholar_failure"]["status_code"] == 429
    assert result["local_semantic_scholar_failure"]["reason_code"] == "semantic_scholar_rate_limited"
    assert "server OpenAlex fallback" in result["discovery_fallback"]["action_hint"]


def test_discover_marks_semantic_scholar_success_diagnostics(monkeypatch):
    def fake_s2(self, query, *, limit):
        return {"source": "semantic_scholar_local", "items": [{"title": "S2 paper"}]}

    monkeypatch.setattr(MdteroClient, "_semantic_scholar_search", fake_s2)

    result = MdteroClient(config=MdteroConfig(api_key="key", academic=AcademicKeys(semantic_scholar_api_key="s2"))).discover("rag", limit=1)

    assert result["source"] == "semantic_scholar_local"
    assert result["discovery_diagnostics"] == {
        "semantic_scholar_configured": True,
        "semantic_scholar_attempted": True,
        "server_openalex_attempted": False,
    }


def test_discover_marks_openalex_when_semantic_scholar_is_not_configured(monkeypatch):
    monkeypatch.setattr(MdteroClient, "_request", lambda self, method, path, **kwargs: {"items": [{"title": "OA paper"}]})

    result = MdteroClient(config=MdteroConfig(api_key="key")).discover("rag", limit=1)

    assert result["source"] == "openalex_server"
    assert result["discovery_diagnostics"] == {
        "semantic_scholar_configured": False,
        "semantic_scholar_attempted": False,
        "server_openalex_attempted": True,
    }


def test_discover_returns_structured_failure_when_all_providers_fail(monkeypatch):
    def fake_s2(self, query, *, limit):
        raise httpx.ConnectError("socks tls failed")

    def fake_request(self, method, path, **kwargs):
        request = httpx.Request(method, "https://api.mdtero.test/api/v1/discovery/search")
        response = httpx.Response(503, json={"error_code": "discovery_provider_disabled"}, request=request)
        raise httpx.HTTPStatusError("disabled", request=request, response=response)

    monkeypatch.setattr(MdteroClient, "_semantic_scholar_search", fake_s2)
    monkeypatch.setattr(MdteroClient, "_request", fake_request)

    try:
        MdteroClient(config=MdteroConfig(api_key="key", academic=AcademicKeys(semantic_scholar_api_key="s2"))).discover("rag", limit=1)
    except Exception as exc:
        payload = exc.payload
    else:
        raise AssertionError("expected discovery failure")

    assert payload["error_code"] == "discovery_provider_disabled"
    assert payload["local_semantic_scholar_error"] == "ConnectError"
    assert payload["local_semantic_scholar_failure"]["reason_code"] == "semantic_scholar_network_error"
    assert payload["status_code"] == 503


def test_discover_auth_failure_returns_login_next_commands(monkeypatch):
    def fake_request(self, method, path, **kwargs):
        request = httpx.Request(method, "https://api.mdtero.test/api/v1/discovery/search")
        response = httpx.Response(401, json={"detail": "missing or invalid credentials"}, request=request)
        raise httpx.HTTPStatusError("unauthorized", request=request, response=response)

    monkeypatch.setattr(MdteroClient, "_request", fake_request)

    try:
        MdteroClient(config=MdteroConfig(api_key=None)).discover("rag", limit=1)
    except Exception as exc:
        payload = exc.payload
    else:
        raise AssertionError("expected discovery failure")

    assert payload["error_code"] == "authentication_required"
    assert payload["reason_code"] == "authentication_required"
    assert payload["status_code"] == 401
    assert "mdtero setup --api-key --json" in payload["action_hint"]
    assert payload["next_commands"] == ["mdtero setup --api-key --json", "mdtero doctor --json", "mdtero discover \"<topic>\" --json"]


def test_acquisition_selects_route_candidate_and_uploads_with_client_metadata(monkeypatch, tmp_path: Path):
    route = {
        "route_kind": "browser_capture_required",
        "acquisition_mode": "native_source_adapter",
        "requires_raw_upload": False,
        "action_sequence": ["fetch_remote_html"],
        "acquisition_candidates": [
            {"connector": "best_oa_location_html", "html_url": "https://example.test/paper"}
        ],
    }
    acquired_path = tmp_path / "paper.html"
    acquired_path.write_text("<html><body><article>Demo</article></body></html>", encoding="utf-8")

    def fake_acquire(route_arg, input_arg, *, timeout, config=None):
        assert route_arg is route
        assert input_arg == "10.1000/demo"
        assert timeout == 45.0
        assert config is not None
        return AcquiredArtifact(
            url="https://example.test/paper",
            path=acquired_path,
            artifact_kind="html",
            source="curl_cffi",
            status_code=200,
            content_type="text/html",
        )

    uploads = []

    def fake_request(self, method, path, **kwargs):
        if path == "/api/v1/route":
            return route
        if path == "/api/v1/tasks/upload":
            uploads.append(kwargs)
            return {"task_id": "task-local", "status": "queued"}
        raise AssertionError(path)

    monkeypatch.setattr("mdtero.client.acquire_from_route", fake_acquire)
    monkeypatch.setattr(MdteroClient, "_request", fake_request)

    route_result, task, acquisition = MdteroClient(timeout=60.0).parse_with_route("10.1000/demo")

    assert route_result is route
    assert task["task_id"] == "task-local"
    assert task["client_acquisition"]["source"] == "curl_cffi"
    assert acquisition["artifact_kind"] == "html"
    assert uploads[0]["data"]["source_url"] == "https://example.test/paper"
    assert uploads[0]["data"]["client_fetch_engine"] == "curl_cffi"
    assert not acquired_path.exists()


def test_acquisition_failure_returns_agent_friendly_error(monkeypatch):
    def fake_acquire(route_arg, input_arg, *, timeout, config=None):
        raise AcquisitionError("client_acquisition_fetch_failed", "Upload the PDF manually.", diagnostics={"attempts": []})

    monkeypatch.setattr("mdtero.client.acquire_from_route", fake_acquire)
    monkeypatch.setattr(MdteroClient, "route", lambda self, input_value: {"requires_raw_upload": True})

    try:
        MdteroClient().parse_with_route("10.1000/demo")
    except AcquisitionError as exc:
        assert exc.reason_code == "client_acquisition_fetch_failed"
        assert "Upload" in exc.action_hint
    else:
        raise AssertionError("expected AcquisitionError")


def test_acquire_from_route_uses_curl_cffi_then_httpx_fallback(monkeypatch):
    calls = []

    def fake_cffi(url, *, artifact_kind, timeout, extra_headers=None):
        calls.append(("curl_cffi", url, artifact_kind, timeout))
        raise AcquisitionError("client_curl_cffi_http_error", "403", diagnostics={"status_code": 403})

    def fake_httpx(url, *, artifact_kind, timeout, extra_headers=None):
        calls.append(("httpx", url, artifact_kind, timeout))
        return AcquiredArtifact(url=url, path=Path("/tmp/demo.html"), artifact_kind=artifact_kind, source="httpx", status_code=200, content_type="text/html")

    monkeypatch.setattr("mdtero.acquisition._fetch_with_curl_cffi", fake_cffi)
    monkeypatch.setattr("mdtero.acquisition._fetch_with_httpx", fake_httpx)

    artifact = acquire_from_route(
        {
            "action_sequence": ["fetch_remote_html"],
            "acquisition_candidates": [{"html_url": "https://example.test/paper"}],
        },
        "10.1000/demo",
        timeout=12,
    )

    assert artifact.source == "httpx"
    assert calls == [
        ("curl_cffi", "https://example.test/paper", "html", 12),
        ("httpx", "https://example.test/paper", "html", 12),
    ]


def test_acquire_from_route_rejects_challenge_pages(monkeypatch):
    def fake_cffi(url, *, artifact_kind, timeout, extra_headers=None):
        raise AcquisitionError(
            "client_acquisition_challenge_page",
            "challenge",
            diagnostics={"url": url, "source": "curl_cffi", "content_type": "text/html"},
        )

    def fake_httpx(url, *, artifact_kind, timeout, extra_headers=None):
        raise AcquisitionError(
            "client_acquisition_challenge_page",
            "challenge",
            diagnostics={"url": url, "source": "httpx", "content_type": "text/html"},
        )

    monkeypatch.setattr("mdtero.acquisition._fetch_with_curl_cffi", fake_cffi)
    monkeypatch.setattr("mdtero.acquisition._fetch_with_httpx", fake_httpx)

    try:
        acquire_from_route(
            {"action_sequence": ["fetch_remote_html"], "acquisition_candidates": [{"html_url": "https://www.mdpi.com/demo"}]},
            "10.3390/demo",
            timeout=12,
        )
    except AcquisitionError as exc:
        assert exc.reason_code == "client_acquisition_fetch_failed"
        assert exc.diagnostics["attempts"][0]["reason_code"] == "client_acquisition_challenge_page"
    else:
        raise AssertionError("expected AcquisitionError")


def test_should_acquire_locally_requires_fetchable_candidate_for_doi_routes():
    assert should_acquire_locally({"action_sequence": ["fetch_remote_html"], "requires_raw_upload": False}, "10.1000/demo") is False
    assert (
        should_acquire_locally(
            {"action_sequence": ["fetch_remote_html"], "acquisition_candidates": [{"html_url": "https://example.test"}]},
            "10.1000/demo",
        )
        is True
    )
    assert should_acquire_locally({"action_sequence": [], "requires_raw_upload": False}, "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC7517829/fullTextXML") is True


def test_elsevier_xml_route_uses_local_acquisition_when_academic_key_is_configured():
    route = {
        "action_sequence": ["fetch_elsevier_xml"],
        "acquisition_candidates": [
            {
                "connector": "elsevier_article_retrieval_api",
                "url": "https://api.elsevier.com/content/article/doi/10.1016/j.energy.2026.140192?httpAccept=text/xml",
            }
        ],
    }
    config = MdteroConfig(academic=AcademicKeys(elsevier_api_key="elsevier-secret"))

    assert should_acquire_locally(route, "10.1016/j.energy.2026.140192") is False
    assert should_acquire_locally(route, "10.1016/j.energy.2026.140192", config=config) is True


def test_elsevier_xml_acquisition_sends_local_api_key(monkeypatch, tmp_path: Path):
    route = {
        "action_sequence": ["fetch_elsevier_xml"],
        "acquisition_candidates": [
            {
                "connector": "elsevier_article_retrieval_api",
                "url": "https://api.elsevier.com/content/article/doi/10.1016/j.energy.2026.140192?httpAccept=text/xml",
            }
        ],
    }
    config = MdteroConfig(academic=AcademicKeys(elsevier_api_key="elsevier-secret"))
    acquired_path = tmp_path / "paper.xml"
    acquired_path.write_text("<article />", encoding="utf-8")
    seen_headers = {}

    def fake_fetch(url, *, artifact_kind, timeout, extra_headers=None):
        seen_headers.update(extra_headers or {})
        return AcquiredArtifact(
            url=url,
            path=acquired_path,
            artifact_kind=artifact_kind,
            source="curl_cffi",
            status_code=200,
            content_type="text/xml",
        )

    monkeypatch.setattr("mdtero.acquisition._fetch_with_curl_cffi", fake_fetch)

    artifact = acquire_from_route(route, "10.1016/j.energy.2026.140192", config=config)

    assert artifact.artifact_kind == "xml"
    assert seen_headers == {"X-ELS-APIKey": "elsevier-secret"}


def test_direct_fulltext_xml_url_uses_local_acquisition_even_when_route_is_server_parse(monkeypatch, tmp_path: Path):
    acquired_path = tmp_path / "paper.xml"
    acquired_path.write_text("<article><front><article-meta /></front></article>", encoding="utf-8")

    def fake_acquire(route_arg, input_arg, *, timeout, config=None):
        assert route_arg["route_kind"] == "server_parse"
        assert input_arg.endswith("/fullTextXML")
        return AcquiredArtifact(
            url=input_arg,
            path=acquired_path,
            artifact_kind="xml",
            source="curl_cffi",
            status_code=200,
            content_type="application/xml",
        )

    uploads = []

    def fake_request(self, method, path, **kwargs):
        if path == "/api/v1/route":
            return {
                "route_kind": "server_parse",
                "acquisition_mode": "server_parse",
                "requires_raw_upload": False,
                "action_hint": "Submit the DOI or URL to /api/v1/tasks/parse.",
            }
        if path == "/api/v1/tasks/upload":
            uploads.append(kwargs)
            return {"task_id": "task-xml", "status": "queued"}
        raise AssertionError(path)

    monkeypatch.setattr("mdtero.client.acquire_from_route", fake_acquire)
    monkeypatch.setattr(MdteroClient, "_request", fake_request)

    input_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC7517829/fullTextXML"
    route_result, task, acquisition = MdteroClient(timeout=60.0).parse_with_route(input_url)

    assert route_result["route_kind"] == "server_parse"
    assert task["task_id"] == "task-xml"
    assert task["client_acquisition"]["artifact_kind"] == "xml"
    assert acquisition["source"] == "curl_cffi"
    assert uploads[0]["data"]["artifact_kind"] == "xml"
    assert uploads[0]["data"]["source_url"] == input_url
    assert not acquired_path.exists()


def test_mdpi_url_candidates_prefer_epub_before_page_fetch(monkeypatch):
    calls = []

    def fake_cffi(url, *, artifact_kind, timeout, extra_headers=None):
        calls.append((url, artifact_kind))
        raise AcquisitionError("client_acquisition_challenge_page", "challenge")

    def fake_httpx(url, *, artifact_kind, timeout, extra_headers=None):
        raise AcquisitionError("client_httpx_http_error", "403")

    monkeypatch.setattr("mdtero.acquisition._fetch_with_curl_cffi", fake_cffi)
    monkeypatch.setattr("mdtero.acquisition._fetch_with_httpx", fake_httpx)

    try:
        acquire_from_route(
            {"action_sequence": ["fetch_remote_html"], "acquisition_candidates": [{"html_url": "https://www.mdpi.com/2071-1050/17/5/2018"}]},
            "10.3390/su17052018",
            timeout=12,
        )
    except AcquisitionError:
        pass
    else:
        raise AssertionError("expected AcquisitionError")

    assert calls[0] == ("https://www.mdpi.com/2071-1050/17/5/2018/epub", "epub")


def test_curl_cffi_tries_browser_profile_cascade(monkeypatch):
    from mdtero import acquisition

    profiles = []

    class FakeResponse:
        status_code = 200
        content = b"<article>ok</article>"
        headers = {"content-type": "text/html"}

    class FakeSession:
        def __init__(self, *, impersonate):
            self.impersonate = impersonate

        def __enter__(self):
            profiles.append(self.impersonate)
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, **kwargs):
            if self.impersonate == "chrome136":
                raise RuntimeError("blocked")
            return FakeResponse()

    class FakeRequests:
        Session = FakeSession

    monkeypatch.setitem(__import__("sys").modules, "curl_cffi", type("FakeCurl", (), {"requests": FakeRequests})())
    monkeypatch.setattr(acquisition.tempfile, "NamedTemporaryFile", lambda **kwargs: open(Path("/tmp/mdtero-test-profile.html"), "wb"))

    artifact = acquisition._fetch_with_curl_cffi("https://example.test/paper", artifact_kind="html", timeout=12)

    assert artifact.source == "curl_cffi:chrome124"
    assert profiles[:2] == ["chrome136", "chrome124"]


def test_curl_cffi_reports_profile_diagnostics_when_challenge_persists(monkeypatch):
    from mdtero import acquisition

    class FakeResponse:
        status_code = 200
        content = b"<html><title>Just a moment...</title></html>"
        headers = {"content-type": "text/html"}

    class FakeSession:
        def __init__(self, *, impersonate):
            self.impersonate = impersonate

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, **kwargs):
            return FakeResponse()

    class FakeRequests:
        Session = FakeSession

    monkeypatch.setitem(__import__("sys").modules, "curl_cffi", type("FakeCurl", (), {"requests": FakeRequests})())

    try:
        acquisition._fetch_with_curl_cffi("https://www.mdpi.com/demo/epub", artifact_kind="epub", timeout=12)
    except AcquisitionError as exc:
        assert exc.reason_code == "client_curl_cffi_request_failed"
        assert exc.diagnostics["profiles"][0] == "chrome136"
        assert exc.diagnostics["attempts"][0]["reason_code"] == "client_acquisition_challenge_page"
    else:
        raise AssertionError("expected AcquisitionError")


def test_project_init_creates_local_project_state(tmp_path: Path):
    target = init_project(tmp_path, name="demo")
    state = load_project(tmp_path)

    assert target.exists()
    assert state.name == "demo"
    assert state.server_project_id is None
    assert state.papers == []


def test_project_state_keeps_optional_server_project_binding(tmp_path: Path):
    init_project(tmp_path, name="demo")
    state = bind_server_project(tmp_path, " 123 ")
    loaded = load_project(tmp_path)

    assert state.server_project_id == "123"
    assert loaded.server_project_id == "123"


def test_project_state_loads_legacy_files_without_server_project_id(tmp_path: Path):
    project_file = init_project(tmp_path, name="legacy")
    project_file.write_text('{"name":"legacy","papers":[]}', encoding="utf-8")

    state = load_project(tmp_path)

    assert state.name == "legacy"
    assert state.server_project_id is None


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


def test_project_management_json_outputs_agent_readable_state(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.chdir(tmp_path)

    assert cli.cmd_project_init(type("Args", (), {"name": "demo", "json": True})()) == 0
    init_payload = json.loads(capsys.readouterr().out)
    assert init_payload["name"] == "demo"
    assert init_payload["paper_count"] == 0
    assert init_payload["project_path"].endswith(".mdtero/project.json")

    assert cli.cmd_project_add(type("Args", (), {"input": "10.1000/demo", "json": True})()) == 0
    add_payload = json.loads(capsys.readouterr().out)
    assert add_payload["status"] == "added"
    assert add_payload["project"]["paper_count"] == 1
    assert add_payload["project"]["papers"][0]["input"] == "10.1000/demo"

    assert cli.cmd_project_link(type("Args", (), {"server_project_id": "42", "json": True})()) == 0
    link_payload = json.loads(capsys.readouterr().out)
    assert link_payload["status"] == "linked"
    assert link_payload["server_project_id"] == "42"

    assert cli.cmd_project_status(type("Args", (), {"json": True})()) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["server_project_id"] == "42"
    assert status_payload["pending_count"] == 1
    assert status_payload["papers"][0]["status"] == "pending"

    assert cli.cmd_project_remove(type("Args", (), {"input": "10.1000/demo", "json": True})()) == 0
    remove_payload = json.loads(capsys.readouterr().out)
    assert remove_payload["status"] == "removed"
    assert remove_payload["project"]["paper_count"] == 0


def test_project_import_bib_json_includes_project_state(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    bib = tmp_path / "refs.bib"
    bib.write_text('@article{a, doi={10.1000/demo}, title={Demo}}', encoding="utf-8")
    init_project(tmp_path, name="demo")
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_project_import_bib(type("Args", (), {"paths": [bib], "json": True})()) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["imported_count"] == 1
    assert payload["skipped_count"] == 0
    assert payload["project"]["paper_count"] == 1
    assert payload["project"]["papers"][0]["input"] == "10.1000/demo"


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


def test_download_json_outputs_path_for_agents(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    downloaded = tmp_path / "donkers_2017_thermochemical_heat_storage_in_salt_hydrates.md"

    def fake_task(self, task_id):
        assert task_id == "task-1"
        return {
            "task_id": "task-1",
            "status": "succeeded",
            "paper_input": "https://doi.org/10.1016/j.apenergy.2017.04.080",
            "result": {
                "metadata": {
                    "title": "Thermochemical heat storage in salt hydrates",
                    "year": 2017,
                    "authors": [{"name": "Donkers"}],
                    "doi": "10.1016/j.apenergy.2017.04.080",
                },
                "parse_outcome": {"outcome_code": "fulltext_accepted"},
            },
        }

    def fake_download(self, task_id, artifact, output_dir, *, filename=None):
        assert task_id == "task-1"
        assert artifact == "paper_md"
        assert output_dir == tmp_path
        assert filename == downloaded.name
        return downloaded

    monkeypatch.setattr(MdteroClient, "task", fake_task)
    monkeypatch.setattr(MdteroClient, "download", fake_download)

    assert cli.cmd_download(type("Args", (), {"task_id": "task-1", "artifact": "paper_md", "output_dir": tmp_path, "json": True})()) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "downloaded"
    assert payload["task_id"] == "task-1"
    assert payload["artifact"] == "paper_md"
    assert payload["path"] == str(downloaded)
    assert payload["quality_label"] == "full_text_good"
    assert payload["task"]["title"] == "Thermochemical heat storage in salt hydrates"
    assert payload["task"]["doi"] == "10.1016/j.apenergy.2017.04.080"


def test_parse_batch_waits_downloads_and_writes_manifest(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    targets = tmp_path / "dois.txt"
    targets.write_text("# comment\n10.1016/S0260-8774(02)00304-7\n", encoding="utf-8")
    output_dir = tmp_path / "out"
    downloaded = output_dir / "bui_2003_water_activity_calcium_chloride_solution.md"

    def fake_parse_with_route(self, value):
        assert value == "10.1016/S0260-8774(02)00304-7"
        return {"route_kind": "server_parse"}, {"task_id": "task-batch", "status": "queued"}, None

    def fake_wait(self, task_id, *, interval=2.0, timeout=600.0):
        assert task_id == "task-batch"
        return {
            "task_id": "task-batch",
            "status": "succeeded",
            "result": {
                "metadata": {
                    "title": "Water activity calcium chloride solution",
                    "year": 2003,
                    "authors": [{"name": "Bui"}],
                    "doi": "10.1016/S0260-8774(02)00304-7",
                },
                "parse_outcome": {"outcome_code": "fulltext_accepted"},
            },
        }

    def fake_download(self, task_id, artifact, out_dir, *, filename=None):
        assert task_id == "task-batch"
        assert artifact == "paper_md"
        assert out_dir == output_dir
        assert filename == downloaded.name
        return downloaded

    monkeypatch.setattr(MdteroClient, "parse_with_route", fake_parse_with_route)
    monkeypatch.setattr(MdteroClient, "wait", fake_wait)
    monkeypatch.setattr(MdteroClient, "download", fake_download)
    monkeypatch.chdir(tmp_path)

    args = build_parser().parse_args(["parse-batch", str(targets), "--wait", "--download", "paper_md", "--output-dir", str(output_dir), "--json"])

    assert cli.cmd_parse_batch(args) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["succeeded_count"] == 1
    assert payload["downloaded_count"] == 1
    assert payload["items"][0]["quality_label"] == "full_text_good"
    assert payload["items"][0]["path"] == str(downloaded)
    manifest = (output_dir / "manifest.csv").read_text(encoding="utf-8")
    assert "task-batch" in manifest
    assert str(downloaded) in manifest
    assert "10.1016/S0260-8774(02)00304-7" in manifest


def test_status_json_includes_download_next_command_for_succeeded_tasks(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="status-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/demo", task_id="task-1", status="queued"))

    def fake_task(self, task_id):
        assert task_id == "task-1"
        return {
            "task_id": "task-1",
            "status": "succeeded",
            "result": {"preferred_artifact": "paper_bundle"},
        }

    monkeypatch.setattr(MdteroClient, "task", fake_task)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_status(type("Args", (), {"task_id": "task-1", "wait": False, "json": True, "trace": False})()) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["preferred_artifact"] == "paper_bundle"
    assert payload["next_commands"] == ["mdtero download task-1 paper_bundle --output-dir ./mdtero-output --json"]
    assert load_project(tmp_path).papers[0].artifact == "paper_bundle"


def test_status_json_preserves_server_recovery_contract(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="status-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/demo", task_id="task-1", status="queued"))

    server_next = [
        "mdtero status task-1 --json",
        "mdtero download task-1 paper_md --output-dir ./mdtero-output --json",
        "mdtero translate task-1 --to zh-CN --wait --timeout 600 --json",
        "mdtero project ingest --json",
        "mdtero rag build --wait --json",
    ]

    def fake_task(self, task_id):
        assert task_id == "task-1"
        return {
            "task_id": "task-1",
            "status": "succeeded",
            "preferred_artifact": "paper_md",
            "next_commands": server_next,
        }

    monkeypatch.setattr(MdteroClient, "task", fake_task)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_status(type("Args", (), {"task_id": "task-1", "wait": False, "json": True, "trace": False})()) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["next_commands"] == server_next
    assert "mdtero download task-1 paper_bundle --output-dir ./mdtero-output --json" not in payload["next_commands"]
    assert load_project(tmp_path).papers[0].artifact == "paper_md"


def test_status_json_promotes_translation_provider_attempts(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="translation-status-demo")
    add_paper(tmp_path, PaperRecord(input="translate-input", task_id="task-translate", status="running"))

    attempts = [
        {
            "provider": "codex",
            "status": "failed",
            "reason_code": "translation_provider_auth_failed",
            "provider_error_code": "auth_error",
            "provider_status_code": 401,
        },
        {
            "provider": "local_legacy",
            "status": "failed",
            "reason_code": "translation_provider_rate_limited",
            "provider_error_code": "rate_limited",
            "provider_status_code": 429,
        },
    ]

    def fake_task(self, task_id):
        assert task_id == "task-translate"
        return {
            "task_id": "task-translate",
            "task_kind": "translate",
            "status": "failed",
            "stage": "failed",
            "error_code": "translation_provider_chain_failed",
            "reason_code": "translation_provider_chain_failed",
            "action_hint": "Refresh provider API keys or quota.",
            "result": {"reason_code": "translation_provider_chain_failed", "translation_attempts": attempts},
        }

    monkeypatch.setattr(MdteroClient, "task", fake_task)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_status(type("Args", (), {"task_id": "task-translate", "wait": False, "json": True, "trace": False})()) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["translation_attempts"] == attempts
    assert payload["next_commands"][0] == "mdtero status task-translate --json"
    paper = load_project(tmp_path).papers[0]
    assert paper.action_hint == "Refresh provider API keys or quota."
    assert paper.translation_attempts == attempts


def test_status_json_promotes_skipped_translation_provider_configuration_attempts(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="translation-not-configured-demo")
    add_paper(tmp_path, PaperRecord(input="translate-input", task_id="task-translate", status="running"))

    attempts = [
        {
            "provider": "mimo",
            "status": "skipped",
            "reason_code": "translation_provider_not_configured",
            "message": "missing MIMO_API_KEY",
        },
        {
            "provider": "codex",
            "status": "skipped",
            "reason_code": "translation_provider_not_configured",
            "message": "missing CODEX_API_KEY or OPENAI_API_KEY",
        },
    ]

    def fake_task(self, task_id):
        assert task_id == "task-translate"
        return {
            "task_id": "task-translate",
            "task_kind": "translate",
            "status": "failed",
            "stage": "failed",
            "error_code": "translation_provider_not_configured",
            "reason_code": "translation_provider_not_configured",
            "action_hint": "No server translation provider is configured.",
            "result": {
                "reason_code": "translation_provider_not_configured",
                "translation_attempts": attempts,
                "provider_plan": attempts,
            },
        }

    monkeypatch.setattr(MdteroClient, "task", fake_task)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_status(type("Args", (), {"task_id": "task-translate", "wait": False, "json": True, "trace": False})()) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["reason_code"] == "translation_provider_not_configured"
    assert payload["translation_attempts"] == attempts
    assert payload["action_hint"] == "No server translation provider is configured."
    paper = load_project(tmp_path).papers[0]
    assert paper.reason_code == "translation_provider_not_configured"
    assert paper.translation_attempts == attempts


def test_project_load_tolerates_legacy_and_future_paper_fields(tmp_path: Path):
    project_dir = tmp_path / ".mdtero"
    project_dir.mkdir()
    (project_dir / "project.json").write_text(
        json.dumps({
            "name": "legacy-demo",
            "papers": [
                {"input": "10.1000/legacy", "status": "pending", "unknown_future_field": "ignored"},
                {"input": "10.1000/attempts", "translation_attempts": None},
            ],
        }),
        encoding="utf-8",
    )

    state = load_project(tmp_path)

    assert state.name == "legacy-demo"
    assert state.papers[0].input == "10.1000/legacy"
    assert state.papers[0].action_hint is None
    assert state.papers[0].translation_attempts == []
    assert state.papers[1].translation_attempts == []


def test_status_text_prints_translation_provider_attempt_table(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="translation-status-text-demo")

    def fake_task(self, task_id):
        return {
            "task_id": task_id,
            "task_kind": "translate",
            "status": "failed",
            "reason_code": "translation_provider_chain_failed",
            "result": {
                "translation_attempts": [
                    {"provider": "codex", "reason_code": "translation_provider_auth_failed", "provider_status_code": 401},
                    {"provider": "local_legacy", "reason_code": "translation_provider_rate_limited", "provider_status_code": 429},
                ]
            },
        }

    monkeypatch.setattr(MdteroClient, "task", fake_task)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_status(type("Args", (), {"task_id": "task-translate", "wait": False, "json": False, "trace": False})()) == 0
    output = capsys.readouterr().out

    assert "codex" in output
    assert "translation_provider_auth_failed" in output
    assert "local_legacy" in output
    assert "translation_provider_rate_limited" in output


def test_status_text_prints_skipped_translation_provider_attempt_messages(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="translation-status-text-demo")

    def fake_task(self, task_id):
        return {
            "task_id": task_id,
            "task_kind": "translate",
            "status": "failed",
            "reason_code": "translation_provider_not_configured",
            "result": {
                "translation_attempts": [
                    {
                        "provider": "mimo",
                        "status": "skipped",
                        "reason_code": "translation_provider_not_configured",
                        "message": "missing MIMO_API_KEY",
                    },
                    {
                        "provider": "codex",
                        "status": "skipped",
                        "reason_code": "translation_provider_not_configured",
                        "message": "missing CODEX_API_KEY or OPENAI_API_KEY",
                    },
                ]
            },
        }

    monkeypatch.setattr(MdteroClient, "task", fake_task)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_status(type("Args", (), {"task_id": "task-translate", "wait": False, "json": False, "trace": False})()) == 0
    output = capsys.readouterr().out

    assert "mimo" in output
    assert "codex" in output
    assert "skipped" in output
    assert "translation_provider_not_configured" in output
    assert "missing MIMO_API_KEY" in output
    assert "missing CODEX_API_KEY or" in output
    assert "OPENAI_API_KEY" in output


def test_status_wait_timeout_returns_structured_payload_without_updating_project(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="status-timeout-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/demo", task_id="task-1", status="queued"))

    def fake_wait(self, task_id, *, interval=2.0, timeout=600.0):
        assert task_id == "task-1"
        assert interval == 0.25
        assert timeout == 1
        raise TimeoutError("slow task")

    monkeypatch.setattr(MdteroClient, "wait", fake_wait)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_status(type("Args", (), {"task_id": "task-1", "wait": True, "json": True, "trace": False, "timeout": 1, "interval": 0.25})()) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "timeout"
    assert payload["reason_code"] == "task_wait_timeout"
    assert payload["wait"] == {"timeout_seconds": 1.0, "interval_seconds": 0.25}
    assert payload["next_commands"] == [
        "mdtero status task-1 --wait --timeout 1 --json",
        "mdtero status task-1 --json",
    ]
    assert load_project(tmp_path).papers[0].status == "queued"


def test_client_wait_returns_terminal_task_seen_on_final_timeout_poll(monkeypatch):
    client = MdteroClient(config=MdteroConfig(api_key="test-key"))
    calls = iter([
        {"task_id": "task-1", "status": "running"},
        {"task_id": "task-1", "status": "failed", "reason_code": "parser_failed"},
    ])

    monkeypatch.setattr(client, "task", lambda task_id: next(calls))
    monkeypatch.setattr("mdtero.client.time.monotonic", lambda: 1000.0)

    task = client.wait("task-1", interval=0.25, timeout=0.25)

    assert task == {"task_id": "task-1", "status": "failed", "reason_code": "parser_failed"}


def test_waited_parse_final_task_is_enriched_without_success_error_noise(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    def fake_parse_with_route(self, value):
        assert value == "10.1000/demo"
        return {"route_kind": "server_parse"}, {"task_id": "task-1", "status": "queued"}, None

    def fake_wait(self, task_id, *, interval=2.0, timeout=600.0):
        assert task_id == "task-1"
        assert interval == 0.5
        assert timeout == 5
        return {
            "task_id": "task-1",
            "status": "succeeded",
            "result": {
                "preferred_artifact": "paper_md",
                "selected_provider": "arxiv",
                "parser_strategy": "html_arxiv",
                "client_acquisition": {"source": "curl_cffi", "artifact_kind": "html"},
                "parse_outcome": {"outcome_code": "fulltext_accepted"},
                "download_artifacts": {"paper_md": {"filename": "paper.md"}},
            },
        }

    monkeypatch.setattr(MdteroClient, "parse_with_route", fake_parse_with_route)
    monkeypatch.setattr(MdteroClient, "wait", fake_wait)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_parse(type("Args", (), {"input": "10.1000/demo", "file": None, "batch": None, "json": True, "wait": True, "trace": False, "timeout": 5, "interval": 0.5})()) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["submission_status"] == "queued"
    assert payload["status"] == "succeeded"
    assert payload["result"]["preferred_artifact"] == "paper_md"
    assert payload["selected_provider"] == "arxiv"
    assert payload["parser_strategy"] == "html_arxiv"
    assert payload["client_acquisition"] == {"source": "curl_cffi", "artifact_kind": "html"}
    assert payload["parse_outcome"] == {"outcome_code": "fulltext_accepted"}
    assert payload["download_artifacts"] == {"paper_md": {"filename": "paper.md"}}
    assert payload["preferred_artifact"] == "paper_md"
    assert payload["next_commands"] == ["mdtero download task-1 paper_md --output-dir ./mdtero-output --json"]
    assert payload["final_task"]["preferred_artifact"] == "paper_md"
    assert payload["final_task"]["next_commands"] == ["mdtero download task-1 paper_md --output-dir ./mdtero-output --json"]
    assert "error" not in payload["final_task"]


def test_cmd_parse_auth_failure_returns_agent_json_without_traceback(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    def fake_request(self, method, path, **kwargs):
        request = httpx.Request(method, f"https://api.mdtero.test{path}")
        response = httpx.Response(401, json={"detail": "missing or invalid credentials"}, request=request)
        raise httpx.HTTPStatusError("unauthorized", request=request, response=response)

    monkeypatch.setattr(MdteroClient, "_request", fake_request)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_parse(type("Args", (), {"input": "10.1000/demo", "file": None, "batch": None, "json": True, "wait": True, "trace": False, "timeout": 5, "interval": 0.5})()) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "failed"
    assert payload["error_code"] == "authentication_required"
    assert payload["reason_code"] == "authentication_required"
    assert payload["status_code"] == 401
    assert payload["next_commands"] == ["mdtero setup --api-key --json", "mdtero doctor --json"]


def test_status_promotes_nested_provider_strategy_and_outcome(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    def fake_task(self, task_id):
        return {
            "task_id": task_id,
            "status": "succeeded",
            "result": {
                "quality": {"provider": "mineru_precision", "parser_strategy": "mineru_precision_markdown"},
                "parse_outcome": {"outcome_code": "fulltext_accepted"},
                "download_artifacts": {"paper_md": {"filename": "paper.md"}},
            },
        }

    monkeypatch.setattr(MdteroClient, "task", fake_task)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_status(type("Args", (), {"task_id": "task-1", "wait": False, "json": True, "trace": False})()) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["selected_provider"] == "mineru_precision"
    assert payload["parser_strategy"] == "mineru_precision_markdown"
    assert payload["parse_outcome"] == {"outcome_code": "fulltext_accepted"}
    assert payload["download_artifacts"] == {"paper_md": {"filename": "paper.md"}}


def test_waited_parse_timeout_promotes_timeout_to_top_level(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    def fake_parse_with_route(self, value):
        assert value == "10.1000/demo"
        return {"route_kind": "server_parse"}, {"task_id": "task-1", "status": "queued"}, None

    def fake_wait(self, task_id, *, interval=2.0, timeout=600.0):
        raise TimeoutError("still queued")

    monkeypatch.setattr(MdteroClient, "parse_with_route", fake_parse_with_route)
    monkeypatch.setattr(MdteroClient, "wait", fake_wait)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_parse(type("Args", (), {"input": "10.1000/demo", "file": None, "batch": None, "json": True, "wait": True, "trace": False, "timeout": 5, "interval": 0.5})()) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["submission_status"] == "queued"
    assert payload["status"] == "timeout"
    assert payload["reason_code"] == "task_wait_timeout"
    assert payload["final_task"]["status"] == "timeout"
    assert payload["next_commands"] == [
        "mdtero status task-1 --wait --timeout 5 --json",
        "mdtero status task-1 --json",
    ]


def test_project_refresh_json_includes_retry_next_command_for_failed_tasks(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="refresh-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/demo", task_id="task-1", status="queued"))

    def fake_task(self, task_id):
        assert task_id == "task-1"
        return {"task_id": "task-1", "status": "failed", "reason_code": "parser_failed"}

    monkeypatch.setattr(MdteroClient, "task", fake_task)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_project_refresh(type("Args", (), {"wait": False, "json": True})()) == 0
    payload = json.loads(capsys.readouterr().out)
    task = payload["items"][0]

    assert task["next_commands"] == ["mdtero status task-1 --json", "mdtero project parse --include-failed --wait --timeout 300 --json"]
    assert load_project(tmp_path).papers[0].reason_code == "parser_failed"


def test_submission_result_maps_provider_artifact_and_reason_to_project_record():
    paper = paper_from_submission(
        "paper.pdf",
        {
            "task_id": "task-file",
            "status": "queued",
            "result": {
                "preferred_artifact": "paper_bundle",
                "selected_provider": "mineru_precision",
                "parser_strategy": "mineru_precision_ast",
                "reason_code": "queued_for_parse",
            },
        },
        source="file:pdf",
    )

    assert paper.input == "paper.pdf"
    assert paper.task_id == "task-file"
    assert paper.source == "file:pdf"
    assert paper.artifact == "paper_bundle"
    assert paper.provider == "mineru_precision"
    assert paper.parser_strategy == "mineru_precision_ast"
    assert paper.reason_code == "queued_for_parse"


def test_parse_batch_records_each_uploaded_file_in_project(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="batch-demo")
    batch = tmp_path / "papers"
    batch.mkdir()
    pdf = batch / "a.pdf"
    epub = batch / "b.epub"
    ignored = batch / "notes.txt"
    pdf.write_bytes(b"%PDF-1.4")
    epub.write_bytes(b"epub")
    ignored.write_text("ignore", encoding="utf-8")

    def fake_upload(self, path, *, source_input=None, source_doi=None):
        return {
            "task_id": f"task-{path.stem}",
            "status": "queued",
            "result": {
                "preferred_artifact": "paper_md",
                "selected_provider": "mineru_precision",
                "parser_strategy": "mineru_precision_ast",
            },
        }

    monkeypatch.setattr(MdteroClient, "upload", fake_upload)
    monkeypatch.chdir(tmp_path)

    assert cli.main(["parse", "--batch", str(batch), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    state = load_project(tmp_path)

    assert [item["task_id"] for item in payload["items"]] == ["task-a", "task-b"]
    assert [paper.input for paper in state.papers] == [str(pdf), str(epub)]
    assert [paper.source for paper in state.papers] == ["file:pdf", "file:epub"]
    assert [paper.provider for paper in state.papers] == ["mineru_precision", "mineru_precision"]
    assert payload["items"][0]["task_api"] == "/api/v1/tasks/{task_id}"
    assert payload["items"][0]["download_api"] == "/api/v1/tasks/{task_id}/download/{artifact}"
    assert payload["items"][0]["preferred_artifact"] == "paper_md"
    assert payload["items"][0]["next_commands"] == [
        "mdtero status task-a --wait --timeout 300 --json",
        "mdtero download task-a paper_md --output-dir ./mdtero-output --json",
    ]


def test_parse_batch_missing_directory_returns_agent_json_without_traceback(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    missing = tmp_path / "missing-papers"
    monkeypatch.chdir(tmp_path)

    assert cli.main(["parse", "--batch", str(missing), "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "failed"
    assert payload["reason_code"] == "batch_path_not_found"
    assert payload["path"] == str(missing)
    assert payload["supported_extensions"] == ["pdf", "epub", "html", "xml"]
    assert payload["next_commands"] == [
        "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
        "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json",
        "mdtero parse --batch <directory> --wait --timeout 300 --json",
    ]


def test_parse_batch_empty_directory_returns_agent_json_without_traceback(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    batch = tmp_path / "papers"
    batch.mkdir()
    (batch / "notes.txt").write_text("not a paper artifact", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert cli.main(["parse", "--batch", str(batch), "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "failed"
    assert payload["reason_code"] == "batch_no_supported_files"
    assert payload["path"] == str(batch)
    assert "PDF, EPUB, XML, or HTML" in payload["action_hint"]


def test_parse_file_missing_or_unsupported_returns_agent_json_without_traceback(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    missing = tmp_path / "missing.pdf"
    monkeypatch.chdir(tmp_path)

    assert cli.main(["parse", "--file", str(missing), "--json"]) == 2
    missing_payload = json.loads(capsys.readouterr().out)
    assert missing_payload["reason_code"] == "file_path_not_found"
    assert missing_payload["path"] == str(missing)

    unsupported = tmp_path / "notes.txt"
    unsupported.write_text("notes", encoding="utf-8")
    assert cli.main(["parse", "--file", str(unsupported), "--json"]) == 2
    unsupported_payload = json.loads(capsys.readouterr().out)
    assert unsupported_payload["reason_code"] == "file_type_not_supported"
    assert unsupported_payload["supported_extensions"] == ["pdf", "epub", "html", "xml"]


def test_parse_missing_input_returns_agent_json_without_traceback(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.chdir(tmp_path)

    assert cli.main(["parse", "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["reason_code"] == "parse_input_missing"
    assert "DOI/URL" in payload["action_hint"]


def test_cmd_parse_enriches_doi_task_submission_for_agents(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="parse-demo")

    def fake_parse_with_route(self, input_value):
        assert input_value == "10.48550/arXiv.1706.03762"
        return (
            {"route_kind": "source_first", "acquisition_mode": "native_source_adapter"},
            {"task_id": "task-parse", "status": "queued", "result": {"preferred_artifact": "paper_bundle"}},
            None,
        )

    monkeypatch.setattr(MdteroClient, "parse_with_route", fake_parse_with_route)
    monkeypatch.chdir(tmp_path)

    assert cli.main(["parse", "10.48550/arXiv.1706.03762", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["task_id"] == "task-parse"
    assert payload["task_api"] == "/api/v1/tasks/{task_id}"
    assert payload["download_api"] == "/api/v1/tasks/{task_id}/download/{artifact}"
    assert payload["preferred_artifact"] == "paper_bundle"
    assert payload["next_commands"] == [
        "mdtero status task-parse --wait --timeout 300 --json",
        "mdtero download task-parse paper_bundle --output-dir ./mdtero-output --json",
    ]


def test_project_parse_enriches_submitted_tasks_for_agents(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="project-demo")
    add_paper(tmp_path, PaperRecord(input="10.48550/arXiv.1706.03762", source="manual"))

    def fake_submit(client, paper):
        assert paper.input == "10.48550/arXiv.1706.03762"
        return {"task_id": "task-project", "status": "queued", "result": {"artifacts": {"paper_md": {"filename": "paper.md"}}}}

    monkeypatch.setattr(cli, "_submit_project_paper", fake_submit)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_project_parse(type("Args", (), {"include_failed": False, "limit": None, "wait": False, "json": True})()) == 0
    payload = json.loads(capsys.readouterr().out)
    task = payload["items"][0]["task"]

    assert task["task_id"] == "task-project"
    assert task["preferred_artifact"] == "paper_md"
    assert task["next_commands"] == [
        "mdtero status task-project --wait --timeout 300 --json",
        "mdtero download task-project paper_md --output-dir ./mdtero-output --json",
    ]


def test_project_parse_wait_timeout_returns_nonzero_without_overwriting_project_status(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="project-timeout-demo")
    add_paper(tmp_path, PaperRecord(input="10.48550/arXiv.1706.03762", source="manual"))

    def fake_submit(client, paper):
        assert paper.input == "10.48550/arXiv.1706.03762"
        return {"task_id": "task-project", "status": "queued", "result": {"artifacts": {"paper_md": {"filename": "paper.md"}}}}

    def fake_wait(self, task_id, *, interval=2.0, timeout=600.0):
        assert task_id == "task-project"
        assert interval == 1
        assert timeout == 3
        raise TimeoutError("still running")

    monkeypatch.setattr(cli, "_submit_project_paper", fake_submit)
    monkeypatch.setattr(MdteroClient, "wait", fake_wait)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_project_parse(type("Args", (), {"include_failed": False, "limit": None, "wait": True, "json": True, "timeout": 3, "interval": 1})()) == 2
    payload = json.loads(capsys.readouterr().out)
    task = payload["items"][0]["task"]

    assert task["status"] == "queued"
    assert task["final_task"]["status"] == "timeout"
    assert task["final_task"]["reason_code"] == "task_wait_timeout"
    state = load_project(tmp_path)
    assert state.papers[0].task_id == "task-project"
    assert state.papers[0].status == "queued"


def test_client_can_create_server_project(monkeypatch):
    calls = []

    def fake_request(self, method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"id": 42, "name": kwargs["json"]["name"]}

    monkeypatch.setattr(MdteroClient, "_request", fake_request)

    result = MdteroClient().create_project("demo", description="local project")

    assert result["id"] == 42
    assert calls == [("POST", "/api/v1/projects", {"json": {"name": "demo", "description": "local project"}})]


def test_project_create_server_reports_backend_gap_without_traceback(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")

    def fake_create(self, name, *, description=None):
        request = httpx.Request("POST", "https://api.mdtero.com/api/v1/projects")
        response = httpx.Response(404, request=request, json={"detail": "Not Found"})
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    monkeypatch.setattr(MdteroClient, "create_project", fake_create)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_project_create_server(type("Args", (), {"name": None, "description": None, "json": True})()) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "failed"
    assert payload["command"] == "project_create_server"
    assert payload["reason_code"] == "server_project_endpoint_missing"
    assert payload["http_status"] == 404
    assert payload["server_project_id"] is None
    assert "backend /api/v1/projects endpoint" in payload["action_hint"]
    assert payload["next_commands"] == [
        "mdtero doctor --json",
        "mdtero project create-server --json",
        "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json",
        "mdtero rag status --json",
        "mdtero rag build --wait --json",
    ]


def test_project_create_server_reports_missing_id_as_agent_json(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")

    def fake_create(self, name, *, description=None):
        return {"name": name}

    monkeypatch.setattr(MdteroClient, "create_project", fake_create)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_project_create_server(type("Args", (), {"name": None, "description": None, "json": True})()) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["reason_code"] == "server_project_id_missing"
    assert payload["server_response"] == {"name": "local-demo"}
    assert "did not include an id" in payload["action_hint"]


def test_client_can_list_server_projects(monkeypatch):
    calls = []

    def fake_request(self, method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"items": [{"id": 42, "name": "demo", "rag_status": {"reason_code": "indexed"}}]}

    monkeypatch.setattr(MdteroClient, "_request", fake_request)

    result = MdteroClient().list_projects()

    assert result["items"][0]["id"] == 42
    assert calls == [("GET", "/api/v1/projects", {})]


def test_setup_headless_api_key_prints_login_step_once(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(cli, "_configure_academic", lambda cfg, console: None)
    monkeypatch.setattr(
        "mdtero.agent.detect_target_status",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("headless setup should not scan agent workspaces")),
    )

    assert cli.cmd_setup(type("Args", (), {"api_key": "mdt_live_demo"})()) == 0
    output = capsys.readouterr().out

    assert output.count("Step 1: saved API-key login for this machine.") == 1
    assert "Step 3: agent skill detection skipped for headless setup." in output


def test_setup_prompts_for_api_key_when_flag_omits_value(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: "mdt_live_prompted")
    monkeypatch.setattr(cli, "_configure_academic", lambda cfg, console: None)
    seen_skip_prompt: list[bool] = []
    monkeypatch.setattr(cli, "_configure_detected_agent_skills", lambda console, *, skip_prompt=False: seen_skip_prompt.append(skip_prompt))
    monkeypatch.setattr(cli, "run_web_login", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("setup --api-key should not run browser OAuth")))

    assert cli.cmd_setup(type("Args", (), {"api_key": API_KEY_PROMPT_SENTINEL})()) == 0
    output = capsys.readouterr().out
    cfg = load_config()

    assert cfg.api_key == "mdt_live_prompted"
    assert seen_skip_prompt == [True]
    assert "Step 1: saved API-key login for this machine." in output


def test_setup_json_headless_api_key_saves_without_echoing_secret(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(
        "mdtero.agent.detect_target_status",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("headless setup --json should not scan agent workspaces")),
    )

    assert cli.cmd_setup(type("Args", (), {"api_key": "mdt_live_json_secret", "json": True})()) == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    cfg = load_config()
    assert_onboarding_payload_commands_parse(payload)

    assert cfg.api_key == "mdt_live_json_secret"
    assert "mdt_live_json_secret" not in output
    assert payload["status"] == "configured"
    assert payload["reason_code"] == "setup_configured"
    assert payload["authenticated"] is True
    assert payload["auth_mode"] == "api_key"
    assert payload["headless"] is True
    assert payload["agents"]["detection_skipped"] is True
    assert payload["agents"]["next_commands"] == ["mdtero agent detect --json", "mdtero agent install --interactive"]
    assert payload["dependencies"]["doctor_command"] == "mdtero doctor --json"
    assert payload["dependencies"]["checks"]["curl_cffi"]["import_name"] == "curl_cffi.requests"
    assert payload["dependencies"]["checks"]["curl_cffi"]["capability"] == "local publisher route acquisition"
    assert payload["dependencies"]["checks"]["fastmcp"]["capability"] == "local MCP server for agents"
    assert payload["dependencies"]["checks"]["pyzotero"]["capability"] == "Zotero import and sync"
    assert payload["dependencies"]["install_command"] == "uv tool install --upgrade mdtero"
    assert payload["dependencies"]["fallback_install_command"] == "uv tool install --upgrade git+https://github.com/JonbinC/doi2md.git"
    assert payload["academic"]["discover_source"] == "server_openalex"
    assert payload["input_routes"]["goal"] == "choose_shortest_markdown_path"
    assert payload["input_routes"]["server_apis"] == {
        "route": "/api/v1/route",
        "parse": "/api/v1/tasks/parse",
        "upload": "/api/v1/tasks/upload",
        "status": "/api/v1/tasks/{task_id}",
        "download": "/api/v1/tasks/{task_id}/download/{artifact}",
        "project_import": "/api/v1/projects/{project_id}/tasks/{task_id}/import",
        "rag_build": "/api/v1/projects/{project_id}/rag/build",
        "rag_query": "/api/v1/projects/{project_id}/rag/query",
    }
    assert [route["id"] for route in payload["input_routes"]["routes"]] == [
        "doi_or_url",
        "file_upload",
        "browser_extension_handoff",
        "rag_mcp_after_parse",
    ]
    route_by_id = {route["id"]: route for route in payload["input_routes"]["routes"]}
    assert route_by_id["doi_or_url"]["primary_command"] == "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json"
    assert route_by_id["file_upload"]["primary_command"] == "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json"
    assert "MinerU-first" in route_by_id["file_upload"]["action_hint"]
    assert "website OAuth" in route_by_id["browser_extension_handoff"]["best_for"]
    assert "publisher challenge" in route_by_id["browser_extension_handoff"]["best_for"]
    assert route_by_id["rag_mcp_after_parse"]["primary_command"] == "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json"
    assert route_by_id["rag_mcp_after_parse"]["next_commands"][:4] == [
        "mdtero project ingest --json",
        "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json",
        "mdtero rag status --json",
        "mdtero rag build --wait --json",
    ]
    assert "mdtero rag query \"<question>\" --build-if-needed --json" in route_by_id["rag_mcp_after_parse"]["next_commands"]
    assert "citations" in route_by_id["rag_mcp_after_parse"]["evidence_fields"]
    assert payload["input_routes"]["separate_smoke_required"] == ["pdf_mineru_urlapi", "epub_upload", "browser_extension_mv3"]
    assert payload["next_commands"][:2] == ["mdtero doctor --json", "mdtero config academic --json"]
    checklist = {item["id"]: item for item in payload["onboarding_checklist"]}
    assert list(checklist) == [
        "auth",
        "local_dependencies",
        "academic_keys",
        "discovery",
        "project",
        "parse",
        "zotero",
        "rag",
        "mcp",
        "agent_skills",
    ]
    assert checklist["auth"]["status"] == "complete"
    assert checklist["auth"]["primary_command"] == "mdtero doctor --json"
    assert checklist["local_dependencies"]["required_modules"] == ["curl_cffi.requests", "fastmcp", "pyzotero"]
    assert checklist["local_dependencies"]["status"] in {"ready", "needs_install"}
    assert checklist["academic_keys"]["status"] == "optional"
    assert "https://dev.elsevier.com/apikey/manage" in checklist["academic_keys"]["links"]["elsevier_api_key"]
    assert checklist["discovery"]["status"] == "server_openalex"
    assert checklist["discovery"]["primary_command"] == "mdtero discover \"<topic>\" --limit 5 --interactive"
    assert "space-bar multi-select" in checklist["discovery"]["action_hint"]
    assert checklist["project"]["primary_command"] == "mdtero project init --name literature-review"
    assert checklist["parse"]["primary_command"] == "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json"
    assert "mdtero parse --file paper.pdf --trace --wait --timeout 600 --json" in checklist["parse"]["secondary_commands"]
    assert checklist["zotero"]["primary_command"] == "mdtero config zotero"
    assert checklist["rag"]["primary_command"] == "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json"
    assert "Voyage runs on the Mdtero backend" in checklist["rag"]["action_hint"]
    assert "manual server project id" in checklist["rag"]["action_hint"]
    assert checklist["agent_skills"]["status"] == "skipped_headless"
    assert checklist["mcp"]["primary_command"] == "mdtero mcp briefing --json"
    assert checklist["agent_skills"]["primary_command"] == "mdtero agent install --interactive"
    assert checklist["rag"]["secondary_commands"] == ["mdtero rag query \"<question>\" --build-if-needed --json", "mdtero rag status --json", "mdtero rag build --wait --json"]
    assert any(group["title"] == "Server RAG and local agents" for group in payload["next_command_groups"])


def test_setup_json_onboarding_uses_local_semantic_scholar_when_configured(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    cfg = load_config()
    cfg.api_key = "mdt_live_saved"
    cfg.academic.semantic_scholar_api_key = "s2-secret"
    save_config(cfg)
    monkeypatch.setattr(
        "mdtero.agent.detect_target_status",
        lambda *args, **kwargs: [],
    )

    assert cli.cmd_setup(type("Args", (), {"api_key": None, "json": True})()) == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    checklist = {item["id"]: item for item in payload["onboarding_checklist"]}
    assert_onboarding_payload_commands_parse(payload)

    assert "s2-secret" not in output
    assert payload["academic"]["discover_source"] == "local_semantic_scholar"
    assert payload["input_routes"]["routes"][0]["id"] == "doi_or_url"
    assert checklist["academic_keys"]["status"] == "enhanced"
    assert checklist["discovery"]["status"] == "local_semantic_scholar"
    assert checklist["agent_skills"]["status"] == "not_detected"


def test_setup_json_missing_auth_is_noninteractive(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(cli.Confirm, "ask", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("setup --json should not prompt")))
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("setup --json should not prompt")))

    assert cli.cmd_setup(type("Args", (), {"api_key": None, "json": True})()) == 1
    payload = json.loads(capsys.readouterr().out)
    assert_onboarding_payload_commands_parse(payload)

    assert payload["status"] == "missing_auth"
    assert payload["reason_code"] == "auth_missing"
    assert payload["authenticated"] is False
    assert payload["next_commands"][0] == "mdtero doctor --json"
    assert "mdtero setup --api-key --json" in payload["action_hint"]


def test_setup_json_environment_api_key_reports_headless_without_saving(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MDTERO_API_KEY", "mdt_live_env_json")
    monkeypatch.setattr(
        "mdtero.agent.detect_target_status",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("environment setup --json should not scan agent workspaces")),
    )

    assert cli.cmd_setup(type("Args", (), {"api_key": None, "json": True})()) == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    cfg = load_config()

    assert cfg.api_key is None
    assert "mdt_live_env_json" not in output
    assert payload["auth_source"] == "MDTERO_API_KEY"
    assert payload["headless"] is True
    assert payload["agents"]["detection_skipped"] is True


def test_setup_rejects_blank_prompted_api_key_without_academic_prompt(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: "   ")
    monkeypatch.setattr(cli, "_configure_academic", lambda cfg, console: (_ for _ in ()).throw(AssertionError("setup should stop before academic config")))
    monkeypatch.setattr(cli, "run_web_login", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("blank setup --api-key should not run browser OAuth")))

    assert cli.cmd_setup(type("Args", (), {"api_key": API_KEY_PROMPT_SENTINEL})()) == 2
    output = capsys.readouterr().out
    cfg = load_config()

    assert "API key cannot be empty" in output
    assert cfg.api_key is None


def test_setup_rejects_blank_api_key_without_academic_prompt(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(cli, "_configure_academic", lambda cfg, console: (_ for _ in ()).throw(AssertionError("setup should stop before academic config")))

    assert cli.cmd_setup(type("Args", (), {"api_key": "   "})()) == 2
    output = capsys.readouterr().out
    cfg = load_config()

    assert "API key cannot be empty" in output
    assert cfg.api_key is None


def test_setup_uses_environment_api_key_without_prompting(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MDTERO_API_KEY", "mdt_live_env")
    monkeypatch.setattr(cli, "_configure_academic", lambda cfg, console: None)
    monkeypatch.setattr(cli.Confirm, "ask", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("setup should not prompt for auth")))
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("setup should not prompt for auth")))
    monkeypatch.setattr(
        "mdtero.agent.detect_target_status",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("environment-key setup should not scan agent workspaces")),
    )

    assert cli.cmd_setup(type("Args", (), {"api_key": None})()) == 0
    output = capsys.readouterr().out
    cfg = load_config()

    assert "Step 1: using existing API-key login from MDTERO_API_KEY." in output
    assert "Step 3: agent skill detection skipped for headless setup." in output
    assert cfg.api_key is None
    assert cfg.effective_api_key == "mdt_live_env"


def test_setup_interactive_prefers_browser_oauth_login(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli
    from mdtero.auth import WebLoginResult

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(cli, "_configure_academic", lambda cfg, console: None)
    seen_skip_prompt: list[bool] = []
    monkeypatch.setattr(cli, "_configure_detected_agent_skills", lambda console, *, skip_prompt=False: seen_skip_prompt.append(skip_prompt))
    monkeypatch.setattr(cli.Confirm, "ask", lambda *args, **kwargs: True)
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("browser setup should not ask for an API key")))

    def fake_run_web_login(site_base_url, *, timeout_seconds, open_browser=None):
        assert site_base_url == "https://mdtero.com"
        assert timeout_seconds == 180.0
        assert open_browser is None
        return WebLoginResult(api_key="mdt_live_web", prefix="mdt_live")

    monkeypatch.setattr(cli, "run_web_login", fake_run_web_login)

    assert cli.cmd_setup(type("Args", (), {"api_key": None})()) == 0
    output = capsys.readouterr().out
    cfg = load_config()

    assert "Opening https://mdtero.com/auth for Mdtero web login" in output
    assert "Saved web login API key" in output
    assert seen_skip_prompt == [False]
    assert cfg.api_key == "mdt_live_web"


def test_setup_interactive_api_key_is_explicit_headless_fallback(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(cli, "_configure_academic", lambda cfg, console: None)
    seen_skip_prompt: list[bool] = []
    monkeypatch.setattr(cli, "_configure_detected_agent_skills", lambda console, *, skip_prompt=False: seen_skip_prompt.append(skip_prompt))
    monkeypatch.setattr(cli.Confirm, "ask", lambda *args, **kwargs: False)
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: "mdt_live_headless")
    monkeypatch.setattr(cli, "run_web_login", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("headless fallback should not run browser login")))

    assert cli.cmd_setup(type("Args", (), {"api_key": None})()) == 0
    output = capsys.readouterr().out
    cfg = load_config()

    assert "Use API-key login for headless servers" in output
    assert "Step 3: agent skill detection skipped for headless setup." not in output
    assert seen_skip_prompt == [True]
    assert cfg.api_key == "mdt_live_headless"


def test_setup_interactive_installs_detected_agent_skills(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    config_dir = tmp_path / "config"
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".hermes").mkdir()
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(cli, "_configure_academic", lambda cfg, console: None)
    monkeypatch.setattr(cli, "run_web_login", lambda *args, **kwargs: WebLoginResult(api_key="mdt_live_web", prefix="mdt_live"))

    confirms = iter([True, True])
    prompts = iter(["1 4"])
    monkeypatch.setattr(cli.Confirm, "ask", lambda *args, **kwargs: next(confirms))
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: next(prompts))

    assert cli.cmd_setup(type("Args", (), {"api_key": None})()) == 0
    output = capsys.readouterr().out

    assert "Step 3: local agent workspaces." in output
    assert "Detected: Codex, Hermes Agent" in output
    assert (home / ".codex" / "skills" / "mdtero" / "SKILL.md").exists()
    assert (home / ".hermes" / "skills" / "mdtero" / "SKILL.md").exists()


def test_setup_interactive_skips_agent_install_when_user_declines(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(cli, "_configure_academic", lambda cfg, console: None)
    monkeypatch.setattr(cli, "run_web_login", lambda *args, **kwargs: WebLoginResult(api_key="mdt_live_web", prefix="mdt_live"))

    confirms = iter([True, False])
    monkeypatch.setattr(cli.Confirm, "ask", lambda *args, **kwargs: next(confirms))
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: "mdt_live_demo")

    assert cli.cmd_setup(type("Args", (), {"api_key": None})()) == 0
    output = capsys.readouterr().out

    assert "Skipped agent skill install." in output
    assert not (home / ".codex" / "skills" / "mdtero" / "SKILL.md").exists()


def test_client_can_import_task_to_server_project(monkeypatch):
    calls = []

    def fake_request(self, method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"document_id": 7, "import_status": "imported"}

    monkeypatch.setattr(MdteroClient, "_request", fake_request)

    result = MdteroClient().import_task_to_project("42", "task-1")

    assert result["document_id"] == 7
    assert calls == [("POST", "/api/v1/projects/42/tasks/task-1/import", {})]


def test_client_can_fetch_server_rag_status(monkeypatch):
    calls = []

    def fake_request(self, method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"project_id": 42, "status": "ready", "reason_code": "indexed"}

    monkeypatch.setattr(MdteroClient, "_request", fake_request)

    result = MdteroClient().rag_status("42")

    assert result["status"] == "ready"
    assert calls == [("GET", "/api/v1/projects/42/rag/status", {})]


def test_project_ingest_imports_succeeded_tasks_into_bound_server_project(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    bind_server_project(tmp_path, "42")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))
    add_paper(tmp_path, PaperRecord(input="10.1000/pending", task_id="task-pending", status="queued"))
    calls = []

    def fake_import(self, project_id, task_id):
        calls.append((project_id, task_id))
        return {"document_id": 7, "import_status": "imported"}

    monkeypatch.setattr(MdteroClient, "import_task_to_project", fake_import)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_project_ingest(type("Args", (), {"project_id": None, "json": True})()) == 0
    payload = json.loads(capsys.readouterr().out)

    assert calls == [("42", "task-done")]
    assert payload["server_project_id"] == "42"
    assert payload["imported_count"] == 1
    assert payload["items"][0]["result"]["document_id"] == 7
    assert payload["failed_count"] == 0


def test_project_ingest_unlinked_project_returns_agent_json_without_traceback(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_project_ingest(type("Args", (), {"project_id": None, "json": True})()) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "not_ready"
    assert payload["command"] == "project_ingest"
    assert payload["reason_code"] == "server_project_not_linked"
    assert payload["local_ready_for_ingest_count"] == 1
    assert payload["server_project_id"] is None
    assert payload["next_commands"] == [
        "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json",
        "mdtero rag status --json",
        "mdtero rag build --wait --json",
        "mdtero rag query \"<question>\" --build-if-needed --json",
    ]


def test_project_ingest_reports_unavailable_server_import_without_traceback(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    bind_server_project(tmp_path, "42")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    def fake_import(self, project_id, task_id):
        request = httpx.Request("POST", f"https://api.mdtero.com/api/v1/projects/{project_id}/tasks/{task_id}/import")
        response = httpx.Response(404, request=request, json={"detail": "Not Found"})
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    monkeypatch.setattr(MdteroClient, "import_task_to_project", fake_import)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_project_ingest(type("Args", (), {"project_id": None, "json": True})()) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["server_project_id"] == "42"
    assert payload["imported_count"] == 0
    assert payload["failed_count"] == 1
    assert payload["failures"][0]["error_code"] == "server_project_import_unavailable"
    assert payload["failures"][0]["http_status"] == 404
    assert "mdtero project ingest" in payload["failures"][0]["action_hint"]
    assert "rag status" in payload["failures"][0]["action_hint"]


def test_mcp_project_status_exposes_agent_rag_workflow(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    bind_server_project(tmp_path, "42")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))
    add_paper(tmp_path, PaperRecord(input="10.1000/todo", status="pending"))

    status = build_project_status(tmp_path)
    commands = build_agent_commands(tmp_path)
    rag = build_rag_context(tmp_path)
    paper = build_paper_context("task-done", tmp_path)

    assert status["status"] == "pending"
    assert status["reason_code"] == "project_has_pending_items"
    assert status["server_project_id"] == "42"
    assert status["ready_for_ingest_count"] == 1
    assert status["pending_count"] == 1
    assert "Submit pending papers" in status["action_hint"]
    assert status["next_commands"] == [
        "mdtero project parse --wait --timeout 300 --json",
        "mdtero project refresh --wait --timeout 300 --json",
        "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json",
    ]
    assert status["next_actions"]["commands"]["mcp_briefing"] == "mdtero mcp briefing --json"
    assert status["project_bridge"]["status"] == "bound"
    assert status["project_bridge"]["server_project"]["id"] == "42"
    assert status["project_bridge"]["local_project_name_is_server_project_id"] is False
    assert status["project_bridge"]["bridge_commands"] == [
        "mdtero doctor --json",
        "mdtero project status --json",
        "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json",
        "mdtero rag status --json",
        "mdtero rag build --wait --json",
        "mdtero rag query \"<question>\" --build-if-needed --json",
        "mdtero mcp briefing --json",
        "mdtero mcp serve",
    ]
    assert commands["commands"]["parse_doi_or_url"] == "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json"
    assert commands["commands"]["parse_file"] == "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json"
    assert commands["commands"]["parse_batch"] == "mdtero parse --batch <directory> --wait --timeout 300 --json"
    assert commands["commands"]["extension_handoff_file"] == "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json"
    assert commands["commands"]["doctor"] == "mdtero doctor --json"
    assert commands["commands"]["discover"] == "mdtero discover \"<topic>\" --interactive"
    assert commands["commands"]["config_academic"] == "mdtero config academic"
    assert commands["commands"]["config_academic_json"] == "mdtero config academic --json"
    assert commands["commands"]["discover_interactive"] == "mdtero discover \"<topic>\" --limit 5 --interactive"
    assert commands["commands"]["discover_add_selected"] == "mdtero discover \"<topic>\" --limit 5 --add --select 1,3 --json"
    assert commands["commands"]["translate"] == "mdtero translate <task-id-or-markdown-file> --to zh-CN --wait --timeout 600 --json"
    assert commands["commands"]["zotero_import"] == "mdtero zotero import --json"
    assert commands["commands"]["agent_install"] == "mdtero agent install --interactive"
    assert commands["commands"]["ingest_for_rag"] == "mdtero project ingest --json"
    assert commands["commands"]["rag_status"] == "mdtero rag status --json"
    assert commands["commands"]["rag_build"] == "mdtero rag build --wait --json"
    assert commands["commands"]["mcp_briefing"] == "mdtero mcp briefing --json"
    assert commands["commands"]["serve_mcp"] == "mdtero mcp serve"
    assert commands["recovery_commands"]["create_server_project"] == "mdtero project create-server --json"
    assert commands["recovery_commands"]["bind_server_project"] == "mdtero project link --server-project-id <id> --json"
    assert commands["workflow"] == [
        "mdtero doctor --json",
        "mdtero project parse --wait --timeout 300 --json",
        "mdtero project refresh --wait --timeout 300 --json",
        "mdtero project ingest --json",
        "mdtero rag status --json",
        "mdtero rag query \"<question>\" --build-if-needed --json",
    ]
    assert rag["ready"] is True
    assert rag["status"] == "ready"
    assert rag["reason_code"] == "ready"
    assert rag["project_bridge"]["status"] == "bound"
    assert rag["project_bridge"]["binding_source"] == "local_project_file"
    assert rag["next_commands"] == [
        "mdtero project ingest --json",
        "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json",
        "mdtero rag status --json",
        "mdtero rag build --wait --json",
        "mdtero rag query \"<question>\" --build-if-needed --json",
        "mdtero mcp briefing --json",
    ]
    assert "linked server project" in rag["action_hint"]
    assert "mdtero project ingest --json" in paper["recommended_commands"]


def test_mcp_rag_context_guides_unlinked_ready_project(tmp_path: Path):
    init_project(tmp_path, name="rag-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    rag = build_rag_context(tmp_path)

    assert rag["status"] == "not_ready"
    assert rag["ready"] is False
    assert rag["reason_code"] == "server_project_not_linked"
    assert rag["server_project_id"] is None
    assert rag["project_bridge"]["status"] == "needs_server_binding"
    assert rag["project_bridge"]["server_project"]["linked"] is False
    assert rag["project_bridge"]["next_commands"][:2] == ["mdtero project status --json", "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json"]
    assert rag["ready_for_ingest_count"] == 1
    assert rag["next_commands"] == [
        "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json",
        "mdtero rag status --json",
        "mdtero rag build --wait --json",
    ]
    assert "create and bind a server project" in rag["action_hint"]


def test_mcp_rag_context_guides_project_without_successful_tasks(tmp_path: Path):
    init_project(tmp_path, name="rag-empty")
    bind_server_project(tmp_path, "42")
    add_paper(tmp_path, PaperRecord(input="10.1000/todo", status="pending"))

    rag = build_rag_context(tmp_path)

    assert rag["status"] == "not_ready"
    assert rag["ready"] is False
    assert rag["reason_code"] == "project_has_pending_items"
    assert rag["ready_for_ingest_count"] == 0
    assert rag["pending_count"] == 1
    assert rag["next_commands"] == [
        "mdtero project parse --wait --timeout 300 --json",
        "mdtero project refresh --wait --timeout 300 --json",
        "mdtero rag query \"<question>\" --build-if-needed --json",
    ]
    assert "Submit pending papers" in rag["action_hint"]


def test_mcp_project_status_guides_uninitialized_agent_workflows(tmp_path: Path):
    status = build_project_status(tmp_path)

    assert status["status"] == "not_initialized"
    assert status["reason_code"] == "project_not_initialized"
    assert status["server_project_id"] is None
    assert status["next_commands"] == [
        "mdtero project init --name <name>",
        "mdtero config academic --json",
        "mdtero discover \"<topic>\" --limit 5 --interactive",
        "mdtero discover \"<topic>\" --limit 5 --add --select 1,3 --json",
        "mdtero project add <doi-or-url> --json",
        "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
    ]
    assert status["next_actions"]["commands"]["project_init_named"] == "mdtero project init --name <name>"
    assert status["project_bridge"]["status"] == "not_initialized"
    assert status["project_bridge"]["next_commands"][:3] == [
        "mdtero doctor --json",
        "mdtero project init --name <name>",
        "mdtero project status --json",
    ]
    assert "project, RAG, or MCP workflows" in status["action_hint"]


def test_mcp_project_bridge_contract_for_agents(tmp_path: Path):
    uninitialized = build_project_bridge(tmp_path)
    assert uninitialized["status"] == "not_initialized"
    assert uninitialized["reason_code"] == "project_not_initialized"
    assert uninitialized["local_project"]["initialized"] is False
    assert uninitialized["server_project"]["linked"] is False
    assert uninitialized["local_project_name_is_server_project_id"] is False

    init_project(tmp_path, name="bridge-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))
    unlinked = build_project_bridge(tmp_path)
    assert unlinked["status"] == "needs_server_binding"
    assert unlinked["reason_code"] == "server_project_not_linked"
    assert unlinked["local_project"]["name"] == "bridge-demo"
    assert unlinked["server_project"]["id"] is None
    assert "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json" in unlinked["next_commands"]
    assert "mdtero rag build --wait --json" not in unlinked["next_commands"][:2]

    bind_server_project(tmp_path, "server-42")
    linked = build_project_bridge(tmp_path)
    assert linked["status"] == "bound"
    assert linked["reason_code"] == "server_project_linked"
    assert linked["server_project"]["id"] == "server-42"
    assert linked["server_project"]["provider"] == "voyage"
    assert linked["binding_source"] == "local_project_file"
    assert linked["bridge_commands"].count("mdtero rag status --json") == 1
    assert linked["bridge_commands"][2] == "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json"
    assert linked["bridge_commands"][-1] == "mdtero mcp serve"


def test_mcp_agent_briefing_summarizes_project_work_for_agents(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MDTERO_API_KEY", "mdt_live_env")
    init_project(tmp_path, name="agent-demo")
    bind_server_project(tmp_path, "42")
    (tmp_path / ".codex").mkdir()
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md", provider="mineru_precision"))
    add_paper(tmp_path, PaperRecord(input="10.1000/todo", status="pending"))
    attempts = [{"provider": "codex", "reason_code": "translation_provider_auth_failed", "provider_status_code": 401}]
    add_paper(
        tmp_path,
        PaperRecord(
            input="10.1000/bad",
            task_id="task-bad",
            status="failed",
            reason_code="translation_provider_chain_failed",
            action_hint="Refresh provider API keys or quota.",
            translation_attempts=attempts,
        ),
    )

    def fake_fetcher(project_id):
        assert project_id == "42"
        return {
            "status": "ready",
            "reason_code": "indexed",
            "selected_provider": "voyage",
            "provider_state": "configured",
            "provider_configured": True,
            "embedding_model": "voyage-test",
            "summary": {"chunk_count": 8, "embedded_count": 8, "pending_embedding_count": 0},
        }

    briefing = build_agent_briefing(tmp_path, rag_status_fetcher=fake_fetcher, agent_root=tmp_path)

    assert briefing["project"]["name"] == "agent-demo"
    assert briefing["account"] == {
        "authenticated": True,
        "api_key_source": "MDTERO_API_KEY",
        "api_base_url": "https://api.mdtero.com",
        "action_hint": "Run `mdtero doctor --json` before cloud parse, translation, discovery fallback, RAG, or MCP.",
        "next_commands": ["mdtero doctor --json"],
    }
    assert briefing["health"] == {
        "pending_count": 1,
        "running_count": 0,
        "succeeded_count": 1,
        "failed_count": 1,
        "ready_for_ingest_count": 1,
        "rag_status": "ready",
        "rag_reason_code": "indexed",
    }
    assert briefing["ready_artifacts"][0]["download_command"] == "mdtero download task-done paper_md --output-dir ./mdtero-output --json"
    assert briefing["blocked_items"][0]["reason_code"] == "translation_provider_chain_failed"
    assert briefing["blocked_items"][0]["action_hint"] == "Refresh provider API keys or quota."
    assert briefing["blocked_items"][0]["translation_attempts"] == attempts
    assert briefing["active_items"][0]["input"] == "10.1000/todo"
    assert briefing["rag"]["agent_summary"]["embedded_count"] == 8
    assert briefing["rag"]["agent_summary"]["selected_provider"] == "voyage"
    assert briefing["rag"]["agent_summary"]["provider_state"] == "configured"
    assert briefing["rag"]["agent_summary"]["provider_configured"] is True
    assert briefing["rag"]["agent_summary"]["embedding_model"] == "voyage-test"
    expected_citation_contract = {
        "answer_kind": "extractive_evidence_pack",
        "evidence_fields": ["answer", "citations", "source_nodes", "matches", "evidence_pack.context_markdown"],
        "required_for_final_answer": ["citations", "source_nodes"],
        "agent_instruction": (
            "Use source_nodes and citations as grounded evidence. Treat answer as an extractive summary, "
            "not a generated final synthesis, unless a downstream LLM rewrites it with citations preserved."
        ),
        "preserve_fields": ["reason_code", "action_hint", "next_commands", "readiness", "agent_summary", "citation_contract"],
    }
    assert briefing["rag"]["citation_contract"] == expected_citation_contract
    assert briefing["rag"]["next_best_action"] == {
        "action": "query",
        "scope": "user_or_agent",
        "reason_code": "indexed",
        "readiness_status": "ready",
        "next_step": "query",
        "primary_command": "mdtero rag query \"<question>\" --build-if-needed --json",
        "action_hint": "RAG is ready; ask a grounded project question and preserve answer, citations, source_nodes, and evidence_pack.",
        "preserve_fields": ["reason_code", "action_hint", "next_commands", "readiness", "agent_summary", "download_artifacts"],
        "citation_contract": expected_citation_contract,
    }
    checklist = {item["id"]: item for item in briefing["onboarding_checklist"]}
    assert list(checklist) == [
        "auth",
        "local_dependencies",
        "academic_keys",
        "discovery",
        "project",
        "parse",
        "zotero",
        "rag",
        "mcp",
        "agent_skills",
    ]
    assert checklist["auth"]["status"] == "complete"
    assert checklist["local_dependencies"]["required_modules"] == ["curl_cffi.requests", "fastmcp", "pyzotero"]
    assert checklist["discovery"]["status"] == "server_openalex"
    assert checklist["rag"]["primary_command"] == "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json"
    assert "mdtero rag query \"<question>\" --build-if-needed --json" in checklist["rag"]["secondary_commands"]
    assert "Mdtero backend" in checklist["rag"]["action_hint"]
    assert "VOYAGE_API_KEY" not in checklist["rag"]["action_hint"]
    assert checklist["agent_skills"]["status"] == "needs_selection"
    assert briefing["project_bridge"]["status"] == "bound"
    assert briefing["project_bridge"]["server_project"]["id"] == "42"
    assert briefing["project_bridge"]["local_project_name_is_server_project_id"] is False
    assert briefing["project_bridge"]["bridge_commands"][-2:] == ["mdtero mcp briefing --json", "mdtero mcp serve"]
    assert briefing["input_routes"]["goal"] == "choose_shortest_markdown_path"
    assert briefing["input_routes"]["server_apis"]["route"] == "/api/v1/route"
    assert briefing["input_routes"]["server_apis"]["project_import"] == "/api/v1/projects/{project_id}/tasks/{task_id}/import"
    input_routes = {route["id"]: route for route in briefing["input_routes"]["routes"]}
    assert list(input_routes) == ["doi_or_url", "file_upload", "browser_extension_handoff", "rag_mcp_after_parse"]
    assert input_routes["doi_or_url"]["primary_command"] == "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json"
    assert input_routes["file_upload"]["primary_command"] == "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json"
    assert "backend MinerU-first" in input_routes["file_upload"]["action_hint"]
    assert "website OAuth" in input_routes["browser_extension_handoff"]["best_for"]
    assert "publisher challenge" in input_routes["browser_extension_handoff"]["best_for"]
    assert input_routes["rag_mcp_after_parse"]["evidence_fields"] == ["answer", "citations", "source_nodes", "evidence_pack.context_markdown", "citation_contract"]
    assert briefing["input_routes"]["separate_smoke_required"] == ["pdf_mineru_urlapi", "epub_upload", "browser_extension_mv3"]
    assert briefing["extension_handoff"] == {
        "purpose": "Use the browser extension for OAuth/session-aware page capture and the CLI/MCP tools for local files, campus-network fetches, status polling, downloads, translation, and RAG.",
        "browser_scope": [
            "website OAuth login and quota display",
            "current tab DOI/page capture",
            "PDF/EPUB upload from the browser",
            "task polling, translation, and artifact download",
        ],
        "cli_scope": [
            "curl_cffi route acquisition for planned HTML/XML/EPUB/PDF sources",
            "local file and batch parsing",
            "project queue/status/download/Zotero/RAG/MCP commands for local agents",
        ],
        "handoff_triggers": [
            "publisher challenge or JavaScript verification page",
            "campus-network or logged-in browser state needs manual confirmation",
            "extension capture cannot access the current tab or direct download URL",
            "server task returns reason_code/action_hint/next_commands for recovery",
        ],
        "commands": [
            "mdtero config academic",
            "mdtero discover \"<topic>\" --limit 5 --interactive",
            "mdtero discover \"<topic>\" --limit 5 --add --select 1,3 --json",
            "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
        "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json",
            "mdtero status <task-id> --wait --timeout 300 --json",
            "mdtero download <task-id> paper_md --output-dir ./mdtero-output --json",
            "mdtero project ingest --json",
            "mdtero project refresh --wait --timeout 300 --json",
            "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json",
            "mdtero rag status --json",
            "mdtero rag build --wait --json",
            "mdtero rag query \"<question>\" --build-if-needed --json",
            "mdtero mcp briefing --json",
            "mdtero mcp serve",
        ],
        "primary_commands": [
            "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
            "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json",
        ],
        "visible_fields": ["task_id", "selected_provider", "parser_strategy", "client_acquisition", "parse_outcome", "reason_code", "action_hint", "preferred_artifact", "download_artifacts", "next_commands"],
        "agent_instruction": "Preserve task_id, selected_provider, parser_strategy, client_acquisition, parse_outcome, reason_code, action_hint, preferred_artifact, download_artifacts, and next_commands when moving between extension, dashboard, CLI, and MCP tools.",
    }
    setup_handoff = briefing["dashboard_setup_handoff_json"]
    assert setup_handoff["source"] == "dashboard_api_key_dialog"
    assert setup_handoff["first_cli_command"] == "mdtero setup --api-key --json"
    assert setup_handoff["api_key"] == {
        "prefix_identifier_field": "api_key.prefix_identifier",
        "full_secret_shown_once": True,
        "full_secret_included": False,
        "copy_secret_action": "Use the dashboard Copy secret button, then paste only into the secure CLI prompt.",
    }
    assert "mdtero setup --api-key --json" in setup_handoff["next_commands"]
    assert "mdtero mcp serve" in setup_handoff["next_commands"]
    assert setup_handoff["mcp"]["first_tool"] == "agent_briefing"
    assert setup_handoff["rag"] == {
        "owner": "backend_voyage",
        "local_voyage_key_required": False,
        "primary_command": "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json",
        "fallback_commands": ["mdtero rag status --json", "mdtero rag build --wait --json", "mdtero rag query \"<question>\" --build-if-needed --json"],
    }
    assert "full API key secret" in setup_handoff["auth_boundary"]["secret_transport"]
    assert "secret value" in setup_handoff["auth_boundary"]["secret_transport"]
    assert "current page session" in setup_handoff["auth_boundary"]["dashboard_secret_retention"]
    assert "explicit clear" in setup_handoff["auth_boundary"]["dashboard_secret_retention"]
    assert "VOYAGE_API_KEY" not in str(setup_handoff)
    assert "mdt_live_env" not in str(setup_handoff)
    assert briefing["dashboard_handoff_json"]["source"] == "dashboard_history_copy"
    assert briefing["dashboard_handoff_json"]["first_mcp_tool"] == "task_status"
    assert briefing["dashboard_handoff_json"]["tool_sequence"] == ["task_status", "download_artifact", "request_translation", "server_rag_status", "rag_query"]
    assert briefing["dashboard_handoff_json"]["expected_fields"] == [
        "task_id",
        "task_kind",
        "status",
        "stage",
        "input_summary",
        "selected_provider",
        "parser_strategy",
        "client_acquisition",
        "parse_outcome",
        "preferred_artifact",
        "download_artifacts",
        "reason_code",
        "action_hint",
        "translation_attempts",
        "next_commands",
        "agent_instruction",
    ]
    assert "signed URLs" in briefing["dashboard_handoff_json"]["redaction_policy"]
    assert [step["step"] for step in briefing["handoff_protocol"]] == [
        "consume_dashboard_setup_handoff_json",
        "inspect_failure",
        "consume_dashboard_handoff_json",
        "retry_source_capture",
        "download_or_translate",
        "build_or_query_rag",
    ]
    assert briefing["handoff_protocol"][0]["use"] == "agent_commands"
    assert briefing["handoff_protocol"][0]["preserve_fields"] == [
        "source",
        "auth_boundary",
        "api_key.full_secret_included",
        "first_cli_command",
        "next_commands",
        "mcp",
        "rag",
        "redaction_policy",
    ]
    assert briefing["handoff_protocol"][1]["preserve_fields"] == [
        "task_id",
        "selected_provider",
        "parser_strategy",
        "client_acquisition",
        "parse_outcome",
        "reason_code",
        "action_hint",
        "preferred_artifact",
        "download_artifacts",
        "translation_attempts",
        "next_commands",
    ]
    assert briefing["handoff_protocol"][2]["step"] == "consume_dashboard_handoff_json"
    assert briefing["handoff_protocol"][2]["use"] == "task_status"
    assert briefing["handoff_protocol"][3]["commands"] == [
        "mdtero config academic",
        "mdtero discover \"<topic>\" --limit 5 --interactive",
        "mdtero discover \"<topic>\" --limit 5 --add --select 1,3 --json",
        "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
            "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json",
        "mdtero status <task-id> --wait --timeout 300 --json",
        "mdtero download <task-id> paper_md --output-dir ./mdtero-output --json",
        "mdtero project ingest --json",
        "mdtero project refresh --wait --timeout 300 --json",
        "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json",
        "mdtero rag status --json",
        "mdtero rag build --wait --json",
        "mdtero rag query \"<question>\" --build-if-needed --json",
        "mdtero mcp briefing --json",
        "mdtero mcp serve",
    ]
    assert briefing["agents"]["detected_count"] == 1
    assert briefing["agents"]["installed_count"] == 0
    assert briefing["agents"]["pending_install_targets"] == ["codex"]
    assert briefing["agents"]["interactive_install_command"] == "mdtero agent install --interactive"
    assert briefing["mcp_server"] == {
        "name": "mdtero",
        "runtime": "FastMCP",
        "transport": "stdio",
        "serve_command": "mdtero mcp serve",
        "briefing_command": "mdtero mcp briefing --json",
        "startup_order": ["mdtero doctor --json", "mdtero mcp briefing --json", "mdtero mcp serve"],
        "primary_tool": "agent_briefing",
        "tools": briefing["mcp_tools"],
        "agent_config_hint": {
            "mcpServers": {
                "mdtero": {
                    "command": "mdtero",
                    "args": ["mcp", "serve"],
                    "cwd": str(tmp_path.resolve()),
                }
            }
        },
        "skill_install_command": "mdtero agent install --interactive",
        "action_hint": "Start this FastMCP stdio server from the local project root after running `mdtero mcp briefing --json`; agents should call `agent_briefing` before other tools.",
    }
    tool_plan = briefing["mcp_tool_plan"]
    assert "input_routes" in tool_plan[0]["success_signal"]
    assert "extension_handoff" in tool_plan[0]["success_signal"]
    assert "dashboard_setup_handoff_json" in tool_plan[0]["success_signal"]
    assert "handoff_protocol" in tool_plan[0]["success_signal"]
    assert [step["tool"] for step in tool_plan][:2] == ["agent_briefing", "project_status"]
    assert any(step["step"] == "submit_pending_parse" and step["tool"] == "submit_parse" for step in tool_plan)
    assert any(step["step"] == "inspect_failed_task" and step["tool"] == "task_status" for step in tool_plan)
    assert any(step["step"] == "download_artifact" and step["tool"] == "download_artifact" for step in tool_plan)
    assert any(step["step"] == "translate_ready_artifact" and step["tool"] == "request_translation" for step in tool_plan)
    assert any(step["step"] == "query_rag" and step["tool"] == "rag_query" for step in tool_plan)
    assert any(step["step"] == "install_agent_skill" and step["tool"] == "agent_commands" for step in tool_plan)
    submit_step = next(step for step in tool_plan if step["step"] == "submit_pending_parse")
    assert submit_step["arguments"] == {"input_value": "10.1000/todo", "wait": True, "timeout": 300, "interval": 2}
    failed_step = next(step for step in tool_plan if step["step"] == "inspect_failed_task")
    assert failed_step["arguments"] == {"task_id": "task-bad", "wait": False}
    query_step = next(step for step in tool_plan if step["step"] == "query_rag")
    assert "evidence_pack.context_markdown" in query_step["purpose"]
    assert "reason_code" in query_step["failure_fields"]
    playbook = briefing["agent_playbook"]
    assert playbook["version"] == "2026-05-agent-playbook-v1"
    assert playbook["mode"] == "mcp_tools_first"
    assert playbook["current_phase"] == "parse_pending"
    assert "dashboard_setup_handoff_json preserves the auth boundary without including the one-time API key secret" in playbook["success_signals"]
    assert playbook["first_action"] == {
        "tool": "submit_parse",
        "command": "mdtero project parse --wait --timeout 300 --json",
        "reason_code": "indexed",
    }
    playbook_steps = {step["step"]: step for step in playbook["ordered_steps"]}
    assert list(playbook_steps)[:3] == ["brief", "inspect_project", "submit_pending_parse"]
    assert playbook_steps["submit_pending_parse"]["tool"] == "submit_parse"
    assert playbook_steps["submit_pending_parse"]["arguments"] == {"input_value": "10.1000/todo", "wait": True, "timeout": 300, "interval": 2}
    assert playbook_steps["inspect_failed_task"]["required"] is False
    assert playbook_steps["query_rag"]["required"] is True
    assert playbook_steps["query_rag"]["command_fallback"] == "mdtero rag query \"<question>\" --build-if-needed --json"
    assert "citation_contract" in playbook["preserve_fields"]
    assert "source_nodes" in playbook["preserve_fields"]
    assert "evidence_pack.context_markdown" in playbook["preserve_fields"]
    assert any("VOYAGE_API_KEY" in condition for condition in playbook["stop_conditions"])
    assert any("citation_contract.required_for_final_answer" in guardrail for guardrail in playbook["guardrails"])
    assert playbook["fallback_commands"] == briefing["recommended_next_commands"]
    assert briefing["recommended_next_commands"] == [
        "mdtero project parse --wait --timeout 300 --json",
        "mdtero project parse --include-failed --wait --timeout 300 --json",
        "mdtero project download --output-dir ./mdtero-output --json",
        "mdtero agent install --interactive",
        "mdtero rag status --json",
        "mdtero rag query \"<question>\" --build-if-needed --json",
        "mdtero mcp briefing --json",
        "mdtero mcp serve",
    ]
    assert "agent_briefing" in briefing["mcp_tools"]
    assert "submit_parse" in briefing["mcp_tools"]
    assert "task_status" in briefing["mcp_tools"]
    assert "download_artifact" in briefing["mcp_tools"]
    assert "request_translation" in briefing["mcp_tools"]
    assert "rag_query" in briefing["mcp_tools"]


def test_mcp_agent_briefing_tool_plan_guides_rag_preparation(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    briefing = build_agent_briefing(tmp_path, rag_status_fetcher=lambda _project_id: {})
    tool_plan = briefing["mcp_tool_plan"]

    assert any(step["step"] == "download_artifact" for step in tool_plan)
    ingest_step = next(step for step in tool_plan if step["step"] == "ingest_project_documents")
    assert ingest_step["tool"] == "project_ingest"
    assert ingest_step["arguments"] == {"project_id": None}
    assert "imported_count" in ingest_step["success_signal"]
    prepare_step = next(step for step in tool_plan if step["step"] == "prepare_rag")
    assert prepare_step["tool"] == "server_rag_status"
    assert "ready_for_query is false" in prepare_step["when"]
    assert "readiness.next_step" in prepare_step["success_signal"]
    assert "next_commands" in prepare_step["failure_fields"]
    assert not any(step["step"] == "query_rag" for step in tool_plan)


def test_mcp_agent_briefing_tool_plan_handles_uninitialized_project(tmp_path: Path):
    briefing = build_agent_briefing(tmp_path, config=MdteroConfig(api_key="key"))
    tool_plan = briefing["mcp_tool_plan"]

    assert [step["step"] for step in tool_plan] == ["brief", "inspect_project", "initialize_project", "add_first_project_item"]
    assert tool_plan[-2]["tool"] == "project_init"
    assert tool_plan[-2]["arguments"] == {"name": "<name>"}
    assert "falling back to shell commands" in tool_plan[-2]["purpose"]
    assert tool_plan[-2]["next_commands"] == [
        "mdtero project init --name <name>",
        "mdtero project add <doi-or-url> --json",
        "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
    ]
    assert tool_plan[-1]["tool"] == "project_add"
    assert tool_plan[-1]["arguments"] == {"input_value": "<doi-or-url-or-file>"}
    assert tool_plan[-1]["next_commands"] == [
        "mdtero project parse --wait --timeout 300 --json",
        "mdtero project refresh --wait --timeout 300 --json",
        "mdtero rag build --wait --json",
    ]


def test_mcp_project_init_and_add_tools_start_project_mode(tmp_path: Path):
    init_payload = initialize_project_for_agent("agent-demo", tmp_path)

    assert init_payload["status"] == "ready"
    assert init_payload["reason_code"] == "project_initialized"
    assert init_payload["project"] == "agent-demo"
    assert init_payload["project_file"].endswith(".mdtero/project.json")
    assert init_payload["project_status"]["status"] == "empty"
    assert "mdtero project status --json" in init_payload["next_commands"]

    add_payload = add_project_item_for_agent("10.48550/arXiv.1706.03762", tmp_path, title="Attention Is All You Need", doi="10.48550/arXiv.1706.03762")
    state = load_project(tmp_path)

    assert add_payload["status"] == "queued"
    assert add_payload["reason_code"] == "project_item_added"
    assert add_payload["paper_count"] == 1
    assert add_payload["project_status"]["pending_count"] == 1
    assert add_payload["next_commands"] == [
        "mdtero project parse --wait --timeout 300 --json",
        "mdtero project refresh --wait --timeout 300 --json",
        "mdtero rag build --wait --json",
        "mdtero mcp briefing --json",
    ]
    assert [(paper.input, paper.title, paper.doi, paper.source, paper.status) for paper in state.papers] == [
        ("10.48550/arXiv.1706.03762", "Attention Is All You Need", "10.48550/arXiv.1706.03762", "mcp", "pending")
    ]


def test_mcp_submit_parse_tool_waits_and_updates_local_project(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    calls = []

    class FakeClient:
        def parse_with_route(self, input_value):
            calls.append(("parse_with_route", input_value))
            return (
                {"route_kind": "source_first"},
                {"task_id": "task-parse", "status": "queued", "result": {"preferred_artifact": "paper_md"}},
                None,
            )

        def wait(self, task_id, *, interval=2.0, timeout=300.0):
            calls.append(("wait", task_id, interval, timeout))
            return {
                "task_id": task_id,
                "status": "succeeded",
                "task_kind": "parse",
                "result": {"artifacts": {"paper_md": {"filename": "paper.md"}}, "preferred_artifact": "paper_md"},
            }

    payload = submit_parse_for_agent("10.48550/arXiv.1706.03762", tmp_path, client=FakeClient(), wait=True, timeout=11, interval=0.5)
    state = load_project(tmp_path)

    assert payload["task_id"] == "task-parse"
    assert payload["status"] == "succeeded"
    assert payload["final_task"]["preferred_artifact"] == "paper_md"
    assert payload["next_commands"] == ["mdtero download task-parse paper_md --output-dir ./mdtero-output --json"]
    assert [(paper.input, paper.task_id, paper.status, paper.artifact) for paper in state.papers] == [
        ("10.48550/arXiv.1706.03762", "task-parse", "succeeded", "paper_md")
    ]
    assert calls == [("parse_with_route", "10.48550/arXiv.1706.03762"), ("wait", "task-parse", 0.5, 11.0)]


def test_mcp_task_status_tool_promotes_reason_and_updates_project(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/demo", task_id="task-failed", status="queued"))

    class FakeClient:
        def task(self, task_id):
            assert task_id == "task-failed"
            return {
                "task_id": task_id,
                "status": "failed",
                "error_code": "parser_failed",
                "result": {"reason_code": "client_acquisition_challenge_page", "action_hint": "Use extension handoff."},
            }

    payload = task_status_for_agent("task-failed", tmp_path, client=FakeClient())
    state = load_project(tmp_path)

    assert payload["reason_code"] == "client_acquisition_challenge_page"
    assert payload["action_hint"] == "Use extension handoff."
    assert payload["next_commands"] == ["mdtero status task-failed --json", "mdtero project parse --include-failed --wait --timeout 300 --json"]
    assert state.papers[0].status == "failed"
    assert state.papers[0].reason_code == "client_acquisition_challenge_page"


def test_mcp_download_artifact_tool_selects_preferred_artifact_and_returns_next_commands(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    downloaded = tmp_path / "mdtero-output" / "paper.zip"
    calls = []

    class FakeClient:
        def task(self, task_id):
            calls.append(("task", task_id))
            return {
                "task_id": task_id,
                "status": "succeeded",
                "result": {
                    "preferred_artifact": "paper_bundle",
                    "download_artifacts": {"paper_bundle": {"filename": "paper.zip"}},
                },
            }

        def download(self, task_id, artifact, output_dir):
            calls.append(("download", task_id, artifact, output_dir))
            output_dir.mkdir(parents=True, exist_ok=True)
            downloaded.write_bytes(b"zip")
            return downloaded

    payload = download_artifact_for_agent("task-done", tmp_path, client=FakeClient())

    assert payload["status"] == "downloaded"
    assert payload["reason_code"] == "artifact_downloaded"
    assert payload["artifact"] == "paper_bundle"
    assert payload["path"] == str(downloaded)
    assert payload["task"]["preferred_artifact"] == "paper_bundle"
    assert payload["next_commands"] == [
        "mdtero status task-done --json",
        "mdtero download <task-id> <artifact> --output-dir ./mdtero-output --json",
        "mdtero project download --output-dir ./mdtero-output --json",
        "mdtero translate <task-id-or-markdown-file> --to zh-CN --wait --timeout 600 --json",
        "mdtero project ingest --json",
        "mdtero rag query \"<question>\" --build-if-needed --json",
        "mdtero mcp briefing --json",
        "mdtero mcp serve",
    ]
    assert calls == [("task", "task-done"), ("download", "task-done", "paper_bundle", tmp_path / "mdtero-output")]


def test_mcp_download_artifact_tool_reports_missing_artifact_without_traceback(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")

    class FakeClient:
        def download(self, task_id, artifact, output_dir):
            raise FileNotFoundError("artifact paper_md is not available; token=secret")

    payload = download_artifact_for_agent("task-done", tmp_path, artifact="paper_md", client=FakeClient())

    assert payload["status"] == "failed"
    assert payload["reason_code"] == "artifact_not_available"
    assert payload["task_id"] == "task-done"
    assert payload["artifact"] == "paper_md"
    assert "secret" not in payload["message"]
    assert payload["next_commands"] == [
        "mdtero status task-done --json",
        "mdtero download task-done <artifact> --output-dir ./mdtero-output --json",
    ]


def test_mcp_request_translation_tool_waits_and_preserves_provider_attempts(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    calls = []

    class FakeClient:
        def translate_task(self, task_id, *, target_language="zh-CN"):
            calls.append(("translate_task", task_id, target_language))
            return {"task_id": "task-translate", "status": "queued"}

        def wait(self, task_id, *, interval=2.0, timeout=600.0):
            calls.append(("wait", task_id, interval, timeout))
            return {
                "task_id": task_id,
                "task_kind": "translate",
                "status": "failed",
                "result": {
                    "reason_code": "translation_provider_chain_failed",
                    "action_hint": "All configured providers failed.",
                    "translation_attempts": [{"provider": "mimo", "reason_code": "translation_provider_auth_failed"}],
                },
            }

    payload = request_translation_for_agent("parse-task", tmp_path, client=FakeClient(), target_language="zh-CN", wait=True, timeout=17, interval=1.5)

    assert payload["task_id"] == "task-translate"
    assert payload["preferred_artifact"] == "translated_md"
    assert payload["final_task"]["reason_code"] == "translation_provider_chain_failed"
    assert payload["final_task"]["translation_attempts"][0]["reason_code"] == "translation_provider_auth_failed"
    assert payload["final_task"]["next_commands"] == [
        "mdtero status task-translate --json",
        "mdtero translate <task-id-or-markdown-file> --to zh-CN --wait --timeout 600 --json",
        "mdtero smoke --skip-translate --json",
    ]
    assert calls == [("translate_task", "parse-task", "zh-CN"), ("wait", "task-translate", 1.5, 17.0)]


def test_mcp_agent_tools_redact_backend_errors(tmp_path: Path):
    class FakeClient:
        def parse_with_route(self, _input_value):
            raise RuntimeError("Bearer mdt_live_secret_token https://mineru.oss-cn-shanghai.aliyuncs.com/a.pdf?Signature=secret")

    payload = submit_parse_for_agent("https://example.test/paper", tmp_path, client=FakeClient())
    text = json.dumps(payload)

    assert payload["reason_code"] == "parse_submission_failed"
    assert "mdt_live_secret_token" not in text
    assert "mineru.oss-cn-shanghai.aliyuncs.com" not in text
    assert "Signature=secret" not in text


def test_mcp_agent_briefing_redacts_signed_urls_and_tokens(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    init_project(tmp_path, name="agent-demo")
    add_paper(
        tmp_path,
        PaperRecord(
            input="10.1000/leak",
            task_id="task-leak",
            status="failed",
            reason_code="uploaded_pdf_v2_parse_failed",
            action_hint="Retry without https://mineru.oss-cn-shanghai.aliyuncs.com/a.pdf?OSSAccessKeyId=AKIA&Signature=secret&x-oss-security-token=token and Bearer mdt_live_secret_token; standalone mdtero_secret_abc.",
            translation_attempts=[{"provider": "codex", "message": "api_key=mdtero_secret_abc token=secret"}],
        ),
    )

    briefing = build_agent_briefing(tmp_path)
    text = json.dumps(briefing)

    assert "mineru.oss-cn-shanghai.aliyuncs.com" not in text
    assert "mdt_live_secret_token" not in text
    assert "mdtero_secret_abc" not in text
    assert "Signature=secret" not in text
    assert "[redacted-url]" in text
    assert "[redacted-key]" in text


def test_mcp_server_rag_status_redacts_backend_signed_urls_and_tokens(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    bind_server_project(tmp_path, "42")

    def fake_fetcher(_project_id):
        return {
            "status": "failed",
            "reason_code": "server_rag_status_failed",
            "action_hint": "Inspect https://mineru.oss-cn-shanghai.aliyuncs.com/status.json?OSSAccessKeyId=AKIA&Signature=secret&x-oss-security-token=token with Bearer mdt_live_secret_token; standalone mdtero_secret_abc.",
            "summary": {
                "chunk_count": 1,
                "embedded_count": 0,
                "pending_embedding_count": 1,
                "last_error": "api_key=mdtero_secret_abc token=secret",
            },
        }

    status = build_server_rag_status(tmp_path, fetcher=fake_fetcher)
    text = json.dumps(status)

    assert status["server_project_id"] == "42"
    assert "mineru.oss-cn-shanghai.aliyuncs.com" not in text
    assert "mdt_live_secret_token" not in text
    assert "mdtero_secret_abc" not in text
    assert "Signature=secret" not in text
    assert "[redacted-url]" in text
    assert "[redacted-key]" in text


def test_mcp_briefing_command_prints_agent_context_without_starting_server(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MDTERO_API_KEY", "mdt_live_env")
    init_project(tmp_path, name="agent-demo")
    bind_server_project(tmp_path, "42")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    def fake_status(self, project_id):
        assert project_id == "42"
        return {
            "status": "ready",
            "reason_code": "indexed",
            "summary": {"chunk_count": 8, "embedded_count": 8, "pending_embedding_count": 0},
        }

    monkeypatch.setattr(MdteroClient, "rag_status", fake_status)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_mcp_briefing(type("Args", (), {"json": True})()) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["project"]["name"] == "agent-demo"
    assert payload["rag"]["status"] == "ready"
    assert payload["rag"]["reason_code"] == "indexed"
    assert "agent_briefing" in payload["mcp_tools"]
    assert "mdtero mcp serve" in payload["recommended_next_commands"]


def test_mcp_rag_query_calls_bound_server_project(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    bind_server_project(tmp_path, "42")

    def fake_query(project_id, question):
        assert project_id == "42"
        assert question == "What is the contribution?"
        return {
            "answer": "A concise project answer.",
            "citations": [{"task_id": "task-1", "doi": "10.1000/rag", "source_url": "https://doi.org/10.1000/rag"}],
            "matches": [{"chunk_id": 9, "doi": "10.1000/rag", "source_url": "https://doi.org/10.1000/rag"}],
        }

    payload = query_server_rag("  What is the contribution?  ", tmp_path, query_fn=fake_query)

    assert payload["status"] == "succeeded"
    assert payload["reason_code"] == "rag_query_succeeded"
    assert payload["project"] == "agent-demo"
    assert payload["server_project_id"] == "42"
    assert payload["question"] == "What is the contribution?"
    assert payload["answer"] == "A concise project answer."
    assert payload["citations"][0]["doi"] == "10.1000/rag"
    assert payload["citations"][0]["source_url"] == "https://doi.org/10.1000/rag"
    assert payload["matches"][0]["doi"] == "10.1000/rag"
    assert payload["next_commands"] == ["mdtero rag status --json", "mdtero rag query \"<question>\" --build-if-needed --json", "mdtero mcp briefing --json", "mdtero mcp serve"]


def test_mcp_rag_query_backfills_agent_evidence_pack_from_matches(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    bind_server_project(tmp_path, "42")

    def fake_query(project_id, question):
        assert project_id == "42"
        assert question == "What does attention replace?"
        return {
            "project_id": 42,
            "selected_provider": "voyage",
            "retrieval_strategy": "voyage_embedding_v1",
            "used_embeddings": True,
            "matches": [
                {
                    "citation_order": 1,
                    "document_id": 7,
                    "document_title": "Attention Is All You Need",
                    "chunk_id": 9,
                    "line_start": 53,
                    "line_end": 58,
                    "snippet": "The Transformer relies entirely on attention and avoids recurrence.",
                    "score": 0.73,
                    "doi": "10.48550/arXiv.1706.03762",
                    "year": 2017,
                    "venue": "arXiv",
                }
            ],
        }

    payload = query_server_rag("What does attention replace?", tmp_path, query_fn=fake_query)

    assert payload["status"] == "succeeded"
    assert payload["reason_code"] == "rag_query_succeeded"
    assert payload["server_project_id"] == "42"
    assert payload["answer"] == "[1] The Transformer relies entirely on attention and avoids recurrence."
    assert payload["answer_kind"] == "extractive_evidence_pack"
    assert payload["citations"][0]["document_title"] == "Attention Is All You Need"
    assert payload["citations"][0]["line_start"] == 53
    assert payload["source_nodes"][0]["node_id"] == "doc-7:chunk-9"
    assert payload["source_nodes"][0]["metadata"]["doi"] == "10.48550/arXiv.1706.03762"
    assert payload["source_nodes"][0]["metadata"]["year"] == 2017
    assert payload["evidence_pack"]["answer_kind"] == "extractive_evidence_pack"
    assert payload["evidence_pack"]["question"] == "What does attention replace?"
    assert "[1] Attention Is All You Need:53-58" in payload["evidence_pack"]["context_markdown"]
    assert "grounded evidence" in payload["evidence_pack"]["agent_instruction"]
    assert payload["citation_contract"]["answer_kind"] == "extractive_evidence_pack"
    assert payload["citation_contract"]["required_for_final_answer"] == ["citations", "source_nodes"]
    assert "evidence_pack.context_markdown" in payload["citation_contract"]["evidence_fields"]
    assert "grounded evidence" in payload["citation_contract"]["agent_instruction"]
    assert payload["next_best_action"]["citation_contract"] == payload["citation_contract"]
    assert payload["readiness"]["ready_for_query"] is True
    assert payload["readiness"]["provider_blocked"] is False
    assert payload["readiness"]["next_step"] == "query"
    assert payload["agent_summary"]["ready_for_query"] is True
    assert payload["agent_summary"]["provider_configured"] is True
    assert payload["agent_summary"]["selected_provider"] == "voyage"
    assert "evidence_pack.context_markdown" in payload["action_hint"]
    assert payload["next_commands"] == ["mdtero rag status --json", "mdtero rag query \"<question>\" --build-if-needed --json", "mdtero mcp briefing --json", "mdtero mcp serve"]


def test_rag_contract_does_not_request_ingest_after_successful_query_without_summary():
    payload = ensure_rag_contract({
        "status": "succeeded",
        "reason_code": "rag_query_succeeded",
        "selected_provider": "voyage",
        "provider_state": "configured",
        "next_commands": ["mdtero rag status --json", "mdtero rag query \"<question>\" --build-if-needed --json", "mdtero mcp briefing --json", "mdtero mcp serve"],
    })

    assert payload["readiness"]["ready_for_query"] is True
    assert payload["readiness"]["needs_ingest"] is False
    assert payload["readiness"]["needs_build"] is False
    assert payload["readiness"]["provider_blocked"] is False
    assert payload["readiness"]["next_step"] == "query"
    assert payload["agent_summary"]["ready_for_query"] is True
    assert payload["agent_summary"]["provider_configured"] is True
    assert payload["agent_summary"]["next_commands"] == [
        "mdtero rag status --json",
        "mdtero rag query \"<question>\" --build-if-needed --json",
        "mdtero mcp briefing --json",
        "mdtero mcp serve",
    ]
    plan_steps = {step["step"]: step for step in payload["agent_tool_plan"]}
    assert "inspect_rag_status" in plan_steps
    assert plan_steps["query_rag"]["tool"] == "rag_query"
    assert plan_steps["handoff_to_local_agent"]["tool"] == "mcp_briefing"
    assert "ingest_project_documents" not in plan_steps
    assert "build_rag_index" not in plan_steps


def test_rag_contract_backfills_dashboard_project_handoff_for_agents():
    payload = ensure_rag_contract({
        "project_id": 42,
        "status": "ready",
        "reason_code": "indexed",
        "selected_provider": "voyage",
        "provider_state": "configured",
        "summary": {"chunk_count": 3, "embedded_count": 3},
    })

    handoff = payload["dashboard_handoff_json"]

    assert handoff["source"] == "dashboard_project_rag_copy"
    assert handoff["first_mcp_tool"] == "server_rag_status"
    assert handoff["tool_sequence"] == ["server_rag_status", "project_ingest", "server_rag_build", "rag_query", "mcp_briefing"]
    assert handoff["validation_step"]["arguments"] == {"project_id": "42"}
    assert "citation_contract" in handoff["expected_fields"]
    assert "evidence_pack.context_markdown" in handoff["expected_fields"]
    assert "provider_configured" in handoff["validation_step"]["failure_fields"]
    assert "provider secrets" in handoff["redaction_policy"]
    assert "VOYAGE_API_KEY" not in handoff["agent_instruction"]
    assert "mdtero mcp serve" in handoff["fallback_commands"]


def test_rag_contract_agent_tool_plan_guides_build_when_index_is_missing():
    payload = ensure_rag_contract({
        "status": "not_ready",
        "reason_code": "rag_index_not_built",
        "selected_provider": "voyage",
        "summary": {"chunk_count": 3, "embedded_count": 0, "pending_embedding_count": 3},
        "next_commands": ["mdtero rag query \"What are the strongest findings?\" --build-if-needed --json", "mdtero rag status --json", "mdtero rag build --wait --json"],
    })

    plan_steps = {step["step"]: step for step in payload["agent_tool_plan"]}

    assert payload["readiness"]["needs_build"] is True
    assert plan_steps["build_rag_index"]["tool"] == "server_rag_build"
    assert plan_steps["build_rag_index"]["arguments"] == {"project_id": "<project-id>", "wait": True, "timeout": 300, "interval": 2}
    assert plan_steps["build_rag_index"]["next_commands"] == ["mdtero rag query \"What are the strongest findings?\" --build-if-needed --json", "mdtero rag status --json", "mdtero rag build --wait --json"]
    assert plan_steps["query_after_build"]["tool"] == "rag_query"
    assert "query_rag" not in plan_steps


def test_rag_contract_agent_tool_plan_treats_voyage_as_backend_status():
    payload = ensure_rag_contract({
        "status": "blocked",
        "reason_code": "voyage_not_configured",
        "selected_provider": "voyage",
        "provider_state": "missing",
        "next_commands": ["mdtero rag status --json"],
    })

    plan_steps = {step["step"]: step for step in payload["agent_tool_plan"]}

    assert payload["readiness"]["provider_blocked"] is True
    assert plan_steps["check_backend_provider"]["tool"] == "server_rag_status"
    assert "users should not provide a local Voyage key" in plan_steps["check_backend_provider"]["purpose"]
    assert "provider_configured" in plan_steps["check_backend_provider"]["failure_fields"]
    assert "readiness" in plan_steps["check_backend_provider"]["failure_fields"]
    assert plan_steps["check_backend_provider"]["next_commands"] == ["mdtero rag status --json"]


def test_mcp_serve_missing_fastmcp_points_to_alpha_reinstall(monkeypatch, tmp_path: Path):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "fastmcp":
            raise ImportError("missing fastmcp")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    try:
        serve_project_context(tmp_path)
    except RuntimeError as exc:
        message = str(exc)
    else:  # pragma: no cover - defensive guard
        raise AssertionError("serve_project_context should fail when FastMCP is unavailable")

    assert "mdtero doctor --json" in message
    assert "uv tool install --force mdtero" in message
    assert "uv tool install --force git+https://github.com/JonbinC/doi2md.git" in message
    assert "npm" not in message.lower()


def test_mcp_rag_query_guides_unlinked_projects(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")

    payload = query_server_rag("What is indexed?", tmp_path)

    assert payload["status"] == "not_ready"
    assert payload["reason_code"] == "server_project_not_linked"
    assert payload["server_project_id"] is None
    assert payload["answer"] is None
    assert payload["next_commands"] == [
        "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json",
        "mdtero rag status --json",
        "mdtero rag build --wait --json",
        "mdtero rag query \"<question>\" --build-if-needed --json",
    ]


def test_mcp_rag_query_requires_non_empty_question(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    bind_server_project(tmp_path, "42")

    payload = query_server_rag("   ", tmp_path, build_if_needed=True)

    assert payload["status"] == "failed"
    assert payload["reason_code"] == "rag_question_required"
    assert payload["project"] == "agent-demo"
    assert payload["server_project_id"] == "42"
    assert payload["answer"] is None
    assert payload["next_commands"] == ["mdtero rag query \"<question>\" --build-if-needed --json"]


def test_mcp_rag_query_build_if_needed_bootstraps_unlinked_project(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))
    calls = []

    class FakeClient:
        def create_project(self, name, *, description=None):
            calls.append(("create", name, description))
            return {"id": 42, "name": name}

        def import_task_to_project(self, project_id, task_id):
            calls.append(("import", project_id, task_id))
            return {"document_id": "doc-1"}

        def rag_build(self, project_id):
            calls.append(("build", project_id))
            return {"status": "ready", "reason_code": "indexed"}

        def rag_query(self, project_id, question):
            calls.append(("query", project_id, question))
            return {"answer": "Bootstrapped answer.", "matches": []}

    payload = query_server_rag("What is indexed?", tmp_path, client=FakeClient(), build_if_needed=True)
    state = load_project(tmp_path)

    assert payload["status"] == "succeeded"
    assert payload["answer"] == "Bootstrapped answer."
    assert payload["server_project_id"] == "42"
    assert payload["bootstrap"]["created_server_project"] is True
    assert payload["bootstrap"]["ingest"]["imported_count"] == 1
    assert payload["bootstrap"]["build"]["reason_code"] == "indexed"
    assert state.server_project_id == "42"
    assert calls == [
        ("create", "agent-demo", "Mdtero local project: agent-demo"),
        ("import", "42", "task-done"),
        ("build", "42"),
        ("query", "42", "What is indexed?"),
    ]


def test_mcp_rag_query_build_if_needed_reuses_matching_server_project(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))
    calls = []

    class FakeClient:
        def list_projects(self):
            calls.append(("list",))
            return {"items": [{"id": 77, "name": "agent-demo", "rag_status": {"reason_code": "indexed"}}]}

        def create_project(self, name, *, description=None):  # pragma: no cover - failure guard
            raise AssertionError("matching server project should be reused")

        def import_task_to_project(self, project_id, task_id):
            calls.append(("import", project_id, task_id))
            return {"document_id": "doc-1"}

        def rag_build(self, project_id):
            calls.append(("build", project_id))
            return {"status": "ready", "reason_code": "indexed"}

        def rag_query(self, project_id, question):
            calls.append(("query", project_id, question))
            return {"answer": "Reused answer.", "matches": []}

    payload = query_server_rag("What is indexed?", tmp_path, client=FakeClient(), build_if_needed=True)
    state = load_project(tmp_path)

    assert payload["status"] == "succeeded"
    assert payload["answer"] == "Reused answer."
    assert payload["server_project_id"] == "77"
    assert payload["bootstrap"]["created_server_project"] is False
    assert payload["bootstrap"]["reused_server_project"] is True
    assert payload["bootstrap"]["bound_local_project"] is True
    assert payload["bootstrap"]["ingest"]["imported_count"] == 1
    assert state.server_project_id == "77"
    assert calls == [
        ("list",),
        ("import", "77", "task-done"),
        ("build", "77"),
        ("query", "77", "What is indexed?"),
    ]


def test_mcp_rag_query_build_if_needed_guides_projects_without_succeeded_tasks(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/todo", status="pending"))

    payload = query_server_rag("What is indexed?", tmp_path, build_if_needed=True)

    assert payload["status"] == "not_ready"
    assert payload["reason_code"] == "no_succeeded_tasks"
    assert payload["answer"] is None
    assert payload["local_ready_for_ingest_count"] == 0
    assert payload["next_commands"] == [
        "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json",
            "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json",
        "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
        "mdtero project refresh --wait --timeout 300 --json",
        "mdtero rag query \"<question>\" --build-if-needed --json",
    ]
    assert "arXiv smoke DOI" in payload["action_hint"]


def test_mcp_rag_query_build_if_needed_guides_bound_projects_without_succeeded_tasks(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    bind_server_project(tmp_path, "42")
    add_paper(tmp_path, PaperRecord(input="10.1000/todo", status="pending"))

    def should_not_query(_project_id, _question):  # pragma: no cover - failure guard
        raise AssertionError("RAG query should not run before a project has succeeded parse tasks")

    payload = query_server_rag("What is indexed?", tmp_path, query_fn=should_not_query, build_if_needed=True)

    assert payload["status"] == "not_ready"
    assert payload["reason_code"] == "no_succeeded_tasks"
    assert payload["server_project_id"] == "42"
    assert payload["answer"] is None
    assert payload["local_ready_for_ingest_count"] == 0
    assert payload["next_commands"] == [
        "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json",
            "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json",
        "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
        "mdtero project refresh --wait --timeout 300 --json",
        "mdtero rag query \"<question>\" --build-if-needed --json",
    ]


def test_mcp_rag_query_returns_reason_codes_on_backend_failures(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    bind_server_project(tmp_path, "42")

    def fake_query(_project_id, _question):
        request = httpx.Request("POST", "https://api.mdtero.com/api/v1/projects/42/rag/query")
        response = httpx.Response(409, request=request, json={"detail": {"reason_code": "rag_index_not_built"}})
        raise httpx.HTTPStatusError("not built", request=request, response=response)

    payload = query_server_rag("Ready?", tmp_path, query_fn=fake_query)

    assert payload["status"] == "failed"
    assert payload["reason_code"] == "rag_index_not_built"
    assert payload["error_type"] == "HTTPStatusError"
    assert payload["next_commands"] == [
        "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json",
        "mdtero rag status --json",
        "mdtero rag build --wait --json",
        "mdtero rag query \"<question>\" --build-if-needed --json",
    ]


def test_mcp_rag_query_preserves_backend_action_hint_and_next_commands(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    bind_server_project(tmp_path, "42")

    def fake_query(_project_id, _question):
        request = httpx.Request("POST", "https://api.mdtero.com/api/v1/projects/42/rag/query")
        response = httpx.Response(
            503,
            request=request,
            json={
                "detail": {
                    "reason_code": "voyage_not_configured",
                    "action_hint": "Configure VOYAGE_API_KEY on the backend before querying.",
                    "next_commands": ["mdtero rag status --json"],
                }
            },
        )
        raise httpx.HTTPStatusError("voyage missing", request=request, response=response)

    payload = query_server_rag("Ready?", tmp_path, query_fn=fake_query)

    assert payload["status"] == "failed"
    assert payload["reason_code"] == "voyage_not_configured"
    assert "Server-side Voyage RAG is not available" in payload["action_hint"]
    assert "backend operations issue" in payload["action_hint"]
    assert "VOYAGE_API_KEY" not in payload["action_hint"]
    assert payload["next_commands"] == ["mdtero rag status --json"]


def test_rag_query_failure_json_redacts_signed_urls_and_tokens(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    bind_server_project(tmp_path, "42")

    def fake_query(self, project_id, question):
        request = httpx.Request("POST", f"https://api.mdtero.com/api/v1/projects/{project_id}/rag/query")
        response = httpx.Response(
            503,
            request=request,
            json={
                "detail": {
                    "error_code": "server_rag_failed",
                    "reason_code": "server_rag_query_failed",
                    "action_hint": "Failed at https://mineru.oss-cn-shanghai.aliyuncs.com/a.pdf?OSSAccessKeyId=AKIA&Signature=secret&x-oss-security-token=token with Bearer mdt_live_secret_token; standalone mdtero_secret_abc.",
                    "next_commands": ["mdtero rag status --json # api_key=mdtero_secret_abc"],
                }
            },
        )
        raise httpx.HTTPStatusError("service unavailable", request=request, response=response)

    monkeypatch.setattr(MdteroClient, "rag_query", fake_query)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_query(type("Args", (), {"project_id": None, "question": "demo", "json": True})()) == 1
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert payload["reason_code"] == "server_rag_query_failed"
    assert "mineru.oss-cn-shanghai.aliyuncs.com" not in output
    assert "mdt_live_secret_token" not in output
    assert "mdtero_secret_abc" not in output
    assert "Signature=secret" not in output
    assert "[redacted-url]" in output
    assert "[redacted-key]" in output


def test_mcp_rag_query_redacts_backend_signed_urls_and_tokens(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    bind_server_project(tmp_path, "42")

    def fake_query(_project_id, _question):
        request = httpx.Request("POST", "https://api.mdtero.com/api/v1/projects/42/rag/query")
        response = httpx.Response(
            503,
            request=request,
            json={
                "detail": {
                    "reason_code": "server_rag_query_failed",
                    "action_hint": "Fetch failed for https://mineru.oss-cn-shanghai.aliyuncs.com/a.pdf?OSSAccessKeyId=AKIA&Signature=secret&x-oss-security-token=token with ApiKey mdt_live_secret_token; standalone mdtero_secret_abc.",
                    "next_commands": ["mdtero rag status --json # token=mdtero_secret_abc"],
                }
            },
        )
        raise httpx.HTTPStatusError("service unavailable", request=request, response=response)

    payload = query_server_rag("Ready?", tmp_path, query_fn=fake_query)
    text = json.dumps(payload)

    assert payload["status"] == "failed"
    assert "mineru.oss-cn-shanghai.aliyuncs.com" not in text
    assert "mdt_live_secret_token" not in text
    assert "mdtero_secret_abc" not in text
    assert "Signature=secret" not in text
    assert "[redacted-url]" in text
    assert "[redacted-key]" in text


def test_mcp_agent_briefing_guides_empty_projects(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv("MDTERO_API_KEY", raising=False)
    init_project(tmp_path, name="empty-demo")

    briefing = build_agent_briefing(tmp_path)

    assert briefing["account"]["authenticated"] is False
    assert briefing["account"]["api_key_source"] == "missing"
    assert briefing["health"]["pending_count"] == 0
    assert briefing["health"]["rag_reason_code"] == "server_project_not_linked"
    assert briefing["recommended_next_commands"][:7] == [
        "mdtero setup --api-key --json",
        "mdtero doctor --json",
        "mdtero config academic --json",
        "mdtero discover \"<topic>\" --limit 5 --interactive",
        "mdtero discover \"<topic>\" --limit 5 --add --select 1,3 --json",
        "mdtero project add <doi-or-url> --json",
        "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
    ]
    assert "mdtero rag build --wait --json" in briefing["recommended_next_commands"]


def test_mcp_agent_briefing_guides_uninitialized_directories(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv("MDTERO_API_KEY", raising=False)

    briefing = build_agent_briefing(tmp_path)

    assert briefing["project"]["initialized"] is False
    assert briefing["project"]["name"] == tmp_path.name
    assert briefing["project"]["paper_count"] == 0
    assert briefing["health"]["rag_reason_code"] == "project_not_initialized"
    assert briefing["rag"]["reason_code"] == "project_not_initialized"
    assert briefing["recommended_next_commands"][:8] == [
        "mdtero setup --api-key --json",
        "mdtero doctor --json",
        "mdtero project init --name <name>",
        "mdtero config academic --json",
        "mdtero discover \"<topic>\" --limit 5 --interactive",
        "mdtero discover \"<topic>\" --limit 5 --add --select 1,3 --json",
        "mdtero project add <doi-or-url> --json",
        "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
    ]


def test_mcp_project_status_guides_uninitialized_directories(tmp_path: Path):
    status = build_project_status(tmp_path)
    commands = build_agent_commands(tmp_path)
    rag = build_rag_context(tmp_path)
    query = query_server_rag("What is indexed?", tmp_path, build_if_needed=True)

    assert status["status"] == "not_initialized"
    assert status["reason_code"] == "project_not_initialized"
    assert status["papers"] == []
    assert status["next_actions"]["commands"]["project_init_named"] == "mdtero project init --name <name>"
    assert commands["workflow"] == [
        "mdtero doctor --json",
        "mdtero config academic --json",
        "mdtero project init --name <name>",
        "mdtero discover \"<topic>\" --limit 5 --interactive",
        "mdtero discover \"<topic>\" --limit 5 --add --select 1,3 --json",
        "mdtero project add <doi-or-url> --json",
        "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
    ]
    assert rag["reason_code"] == "project_not_initialized"
    assert rag["next_commands"][0] == "mdtero project init --name <name>"
    assert query["status"] == "not_ready"
    assert query["reason_code"] == "project_not_initialized"
    assert query["answer"] is None
    assert query["next_commands"][0] == "mdtero project init --name <name>"


def test_mcp_rag_context_prompts_rag_build_when_unlinked(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    rag = build_rag_context(tmp_path)
    commands = build_agent_commands(tmp_path)

    assert rag["ready"] is False
    assert rag["reason_code"] == "server_project_not_linked"
    assert commands["commands"]["rag_build"] == "mdtero rag build --wait --json"
    assert commands["commands"]["bootstrap_rag"] == "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json"
    assert "create_server_project" not in commands["commands"]
    assert commands["recovery_commands"]["create_server_project"] == "mdtero project create-server --json"
    assert commands["workflow"] == [
        "mdtero doctor --json",
        "mdtero project parse --wait --timeout 300 --json",
        "mdtero project refresh --wait --timeout 300 --json",
        "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json",
        "mdtero rag status --json",
        "mdtero rag query \"<question>\" --build-if-needed --json",
    ]


def test_mcp_server_rag_status_reports_unlinked_next_commands(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    status = build_server_rag_status(tmp_path)

    assert status["status"] == "not_ready"
    assert status["reason_code"] == "server_project_not_linked"
    assert status["local_ready_for_ingest_count"] == 1
    assert status["next_commands"][0] == "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json"
    assert "create and bind" in status["action_hint"]
    assert "manual server project id" in status["action_hint"]


def test_mcp_server_rag_status_surfaces_ready_server_state(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    bind_server_project(tmp_path, "42")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    def fake_fetcher(project_id):
        assert project_id == "42"
        return {
            "status": "ready",
            "reason_code": "indexed",
            "selected_provider": "voyage",
            "provider_state": "configured",
            "provider_configured": True,
            "embedding_model": "voyage-test",
            "summary": {"chunk_count": 5, "embedded_count": 5, "pending_embedding_count": 0},
        }

    status = build_server_rag_status(tmp_path, fetcher=fake_fetcher)

    assert status["server_project_id"] == "42"
    assert status["readiness"] == {
        "ready_for_query": True,
        "readiness_status": "ready",
        "can_build": True,
        "needs_ingest": False,
        "needs_build": False,
        "provider_blocked": False,
        "next_step": "query",
        "blocker_reason_code": None,
        "document_count": 0,
        "chunk_count": 5,
        "embedded_count": 5,
        "pending_embedding_count": 0,
        "match_count": 0,
    }
    assert status["agent_summary"] == {
        "status": "ready",
        "reason_code": "indexed",
        "selected_provider": "voyage",
        "provider_state": "configured",
        "provider_configured": True,
        "embedding_model": "voyage-test",
        "ready_for_query": True,
        "readiness_status": "ready",
        "next_step": "query",
        "document_count": 0,
        "embedded_count": 5,
        "chunk_count": 5,
        "pending_embedding_count": 0,
        "match_count": 0,
        "next_commands": ["mdtero rag status --json", "mdtero rag query \"<question>\" --build-if-needed --json", "mdtero mcp briefing --json", "mdtero mcp serve"],
    }
    assert status["next_best_action"] == {
        "action": "query",
        "scope": "user_or_agent",
        "reason_code": "indexed",
        "readiness_status": "ready",
        "next_step": "query",
        "primary_command": "mdtero rag query \"<question>\" --build-if-needed --json",
        "action_hint": "RAG is ready; ask a grounded project question and preserve answer, citations, source_nodes, and evidence_pack.",
        "preserve_fields": ["reason_code", "action_hint", "next_commands", "readiness", "agent_summary", "download_artifacts"],
        "citation_contract": status["citation_contract"],
    }
    assert status["citation_contract"]["required_for_final_answer"] == ["citations", "source_nodes"]
    assert "evidence_pack.context_markdown" in status["citation_contract"]["evidence_fields"]
    assert status["next_commands"] == ["mdtero rag status --json", "mdtero rag query \"<question>\" --build-if-needed --json", "mdtero mcp briefing --json", "mdtero mcp serve"]


def test_mcp_server_rag_status_treats_needs_build_as_needs_build(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    bind_server_project(tmp_path, "42")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    def fake_fetcher(project_id):
        assert project_id == "42"
        return {
            "status": "not_ready",
            "reason_code": "rag_index_not_built",
            "selected_provider": "voyage",
            "provider_state": "configured",
            "provider_configured": True,
            "embedding_model": "voyage-4",
            "summary": {"document_count": 1, "chunk_count": 12, "embedded_count": 0, "pending_embedding_count": 12},
            "action_hint": "Build the server project index before querying.",
        }

    status = build_server_rag_status(tmp_path, fetcher=fake_fetcher)
    briefing = build_agent_briefing(tmp_path, rag_status_fetcher=fake_fetcher, agent_root=tmp_path)

    assert status["readiness"]["readiness_status"] == "needs_build"
    assert status["readiness"]["ready_for_query"] is False
    assert status["readiness"]["needs_build"] is True
    assert status["readiness"]["provider_blocked"] is False
    assert status["readiness"]["next_step"] == "build"
    assert status["agent_summary"]["readiness_status"] == "needs_build"
    assert status["agent_summary"]["next_step"] == "build"
    assert status["next_best_action"]["action"] == "build"
    assert status["next_best_action"]["primary_command"] == "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json"
    assert status["next_commands"][:3] == ["mdtero rag query \"What are the strongest findings?\" --build-if-needed --json", "mdtero rag status --json", "mdtero rag build --wait --json"]
    assert "Build the server project index" in status["action_hint"]
    assert briefing["health"]["rag_reason_code"] == "rag_index_not_built"
    assert briefing["rag"]["agent_summary"]["readiness_status"] == "needs_build"
    assert "mdtero rag build --wait --json" in briefing["recommended_next_commands"]
    assert "server_rag_build" in briefing["mcp_tools"]
    assert "project_ingest" in briefing["mcp_tools"]
    assert briefing["mcp_server"]["tools"] == [
        "agent_briefing",
        "project_init",
        "project_status",
        "project_add",
        "paper_context",
        "submit_parse",
        "task_status",
        "download_artifact",
        "request_translation",
        "rag_context",
        "project_ingest",
        "server_rag_status",
        "server_rag_build",
        "rag_query",
        "agent_commands",
    ]
    prepare_step = next(step for step in briefing["mcp_tool_plan"] if step["step"] == "prepare_rag")
    assert prepare_step["tool"] == "server_rag_build"
    assert prepare_step["arguments"] == {"wait": True, "timeout": 300, "interval": 2}


def test_mcp_server_rag_build_waits_until_ready(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))
    calls = []

    class FakeClient:
        def create_project(self, name, *, description=None):
            calls.append(("create", name, description))
            return {"id": 42, "name": name}

        def import_task_to_project(self, project_id, task_id):
            calls.append(("import", project_id, task_id))
            return {"document_id": "doc-1"}

        def rag_build(self, project_id):
            calls.append(("build", project_id))
            return {"status": "queued", "reason_code": "rag_build_queued"}

        def rag_status(self, project_id):
            calls.append(("status", project_id))
            return {"status": "ready", "reason_code": "indexed", "readiness": {"ready_for_query": True}}

    payload = build_server_rag_for_agent(tmp_path, client=FakeClient(), wait=True, timeout=1, interval=0.01)
    state = load_project(tmp_path)

    assert payload["status"] == "queued"
    assert payload["reason_code"] == "rag_build_queued"
    assert payload["ready_for_query"] is True
    assert payload["server_project_id"] == "42"
    assert payload["bootstrap"]["created_server_project"] is True
    assert payload["bootstrap"]["ingest"]["imported_count"] == 1
    assert payload["status_after_build"]["reason_code"] == "indexed"
    assert state.server_project_id == "42"
    assert calls == [
        ("create", "agent-demo", "Mdtero local project: agent-demo"),
        ("import", "42", "task-done"),
        ("build", "42"),
        ("status", "42"),
    ]


def test_mcp_project_ingest_tool_creates_binds_and_imports(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))
    calls = []

    class FakeClient:
        def list_projects(self):
            calls.append(("list",))
            return {"items": []}

        def create_project(self, name, *, description=None):
            calls.append(("create", name, description))
            return {"id": "server-42", "name": name}

        def import_task_to_project(self, project_id, task_id):
            calls.append(("import", project_id, task_id))
            return {"document_id": "doc-1", "import_status": "imported"}

    payload = ingest_project_for_agent(tmp_path, client=FakeClient())
    state = load_project(tmp_path)

    assert payload["status"] == "succeeded"
    assert payload["reason_code"] == "server_project_imported"
    assert payload["server_project_id"] == "server-42"
    assert payload["project_binding"]["created_server_project"] is True
    assert payload["project_binding"]["bound_local_project"] is True
    assert payload["imported_count"] == 1
    assert payload["failed_count"] == 0
    assert payload["items"] == [{"input": "10.1000/done", "task_id": "task-done", "result": {"document_id": "doc-1", "import_status": "imported"}}]
    assert payload["next_commands"] == [
        "mdtero rag status --json",
        "mdtero rag build --wait --json",
        "mdtero rag query \"<question>\" --build-if-needed --json",
        "mdtero mcp briefing --json",
        "mdtero mcp serve",
    ]
    assert state.server_project_id == "server-42"
    assert calls == [
        ("list",),
        ("create", "agent-demo", "Mdtero local project: agent-demo"),
        ("import", "server-42", "task-done"),
    ]


def test_mcp_project_ingest_tool_does_not_create_server_project_without_succeeded_tasks(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/pending", status="pending"))

    class FakeClient:
        def list_projects(self):  # pragma: no cover - failure guard
            raise AssertionError("empty ingest should not inspect server projects")

        def create_project(self, name, *, description=None):  # pragma: no cover - failure guard
            raise AssertionError("empty ingest should not create a server project")

        def import_task_to_project(self, project_id, task_id):  # pragma: no cover - failure guard
            raise AssertionError("empty ingest should not import tasks")

    payload = ingest_project_for_agent(tmp_path, client=FakeClient())
    state = load_project(tmp_path)

    assert payload["status"] == "not_ready"
    assert payload["reason_code"] == "no_succeeded_tasks"
    assert payload["server_project_id"] is None
    assert payload["imported_count"] == 0
    assert payload["failed_count"] == 0
    assert payload["project_binding"]["created_server_project"] is False
    assert payload["project_binding"]["bound_local_project"] is False
    assert "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json" in payload["next_commands"]
    assert state.server_project_id is None


def test_mcp_project_ingest_tool_reports_import_failures(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    bind_server_project(tmp_path, "server-42")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    class FakeClient:
        def import_task_to_project(self, project_id, task_id):
            raise MdteroApiError({
                "status_code": 404,
                "reason_code": "project_import_missing",
                "action_hint": "signed url token https://mineru.example/path?signature=secret should be redacted",
            })

    payload = ingest_project_for_agent(tmp_path, client=FakeClient())

    assert payload["status"] == "failed"
    assert payload["reason_code"] == "server_project_import_failed"
    assert payload["imported_count"] == 0
    assert payload["failed_count"] == 1
    failure = payload["failures"][0]
    assert failure["error_code"] == "server_project_import_unavailable"
    assert failure["reason_code"] == "project_import_missing"
    assert failure["http_status"] == 404
    assert "POST /api/v1/projects/{id}/tasks/{task_id}/import" in failure["action_hint"]
    assert "secret" not in json.dumps(payload).lower()


def test_mcp_server_rag_build_binds_explicit_project_id_from_tool_plan(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))
    calls = []

    class FakeClient:
        def import_task_to_project(self, project_id, task_id):
            calls.append(("import", project_id, task_id))
            return {"document_id": "doc-1"}

        def rag_build(self, project_id):
            calls.append(("build", project_id))
            return {"status": "queued", "reason_code": "rag_build_queued"}

        def rag_status(self, project_id):
            calls.append(("status", project_id))
            return {"status": "ready", "reason_code": "indexed", "readiness": {"ready_for_query": True}}

    payload = build_server_rag_for_agent(tmp_path, client=FakeClient(), project_id="42", wait=True, timeout=1, interval=0.01)
    state = load_project(tmp_path)

    assert payload["server_project_id"] == "42"
    assert payload["bootstrap"]["created_server_project"] is False
    assert payload["bootstrap"]["bound_local_project"] is True
    assert payload["bootstrap"]["ingest"]["imported_count"] == 1
    assert payload["status_after_build"]["reason_code"] == "indexed"
    assert state.server_project_id == "42"
    assert calls == [
        ("import", "42", "task-done"),
        ("build", "42"),
        ("status", "42"),
    ]


def test_mcp_server_rag_build_rejects_conflicting_explicit_project_id(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    bind_server_project(tmp_path, "local-42")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    class FakeClient:
        def import_task_to_project(self, project_id, task_id):  # pragma: no cover - failure guard
            raise AssertionError("conflicting project id should not import")

        def rag_build(self, project_id):  # pragma: no cover - failure guard
            raise AssertionError("conflicting project id should not build")

    payload = build_server_rag_for_agent(tmp_path, client=FakeClient(), project_id="plan-99", wait=True)
    state = load_project(tmp_path)

    assert payload["status"] == "not_ready"
    assert payload["reason_code"] == "server_project_id_mismatch"
    assert payload["server_project_id"] == "local-42"
    assert payload["requested_server_project_id"] == "plan-99"
    assert "mdtero project link --server-project-id plan-99 --json" in payload["next_commands"]
    assert state.server_project_id == "local-42"


def test_mcp_server_rag_status_treats_voyage_not_configured_as_blocked(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    bind_server_project(tmp_path, "42")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    def fake_fetcher(project_id):
        assert project_id == "42"
        return {
            "status": "failed",
            "reason_code": "voyage_not_configured",
            "selected_provider": "voyage",
            "provider_state": "not_configured",
            "provider_configured": False,
            "action_hint": "Configure VOYAGE_API_KEY on the backend before querying.",
        }

    status = build_server_rag_status(tmp_path, fetcher=fake_fetcher)

    assert status["readiness"]["readiness_status"] == "blocked"
    assert status["readiness"]["provider_blocked"] is True
    assert status["readiness"]["next_step"] == "check_backend_rag_provider"
    assert status["agent_summary"]["readiness_status"] == "blocked"
    assert status["next_best_action"]["action"] == "check_backend_provider"
    assert status["next_best_action"]["scope"] == "backend_operations"
    assert status["next_best_action"]["primary_command"] == "mdtero rag status --json"
    assert "VOYAGE_API_KEY" not in status.get("action_hint", "")


def test_mcp_server_rag_status_handles_server_unavailable(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    bind_server_project(tmp_path, "42")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    def failing_fetcher(_project_id):
        raise TimeoutError("slow")

    status = build_server_rag_status(tmp_path, fetcher=failing_fetcher)

    assert status["status"] == "unavailable"
    assert status["reason_code"] == "server_rag_status_unavailable"
    assert status["error_type"] == "TimeoutError"
    assert status["next_commands"] == ["mdtero project ingest --json", "mdtero rag status --json", "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json", "mdtero rag build --wait --json"]


def test_tui_dashboard_model_guides_login_and_setup(tmp_path: Path):
    init_project(tmp_path, name="tui-demo")

    model = build_dashboard_model(project_root=tmp_path, config=MdteroConfig(api_key=None), agent_root=tmp_path)
    assert_dashboard_model_commands_parse(model)

    assert model["health"]["status"] == "needs_auth"
    assert model["health"]["headline"] == "Needs login"
    assert model["health"]["primary_next_command"] == "mdtero setup"
    assert model["account"]["auth_hint"] == "mdtero setup"
    assert model["account"]["authenticated"] is False
    checklist = {item["id"]: item for item in model["onboarding_checklist"]}
    assert list(checklist) == [
        "auth",
        "local_dependencies",
        "academic_keys",
        "discovery",
        "project",
        "parse",
        "zotero",
        "rag",
        "mcp",
        "agent_skills",
    ]
    assert checklist["auth"] == {
        "id": "auth",
        "title": "Authenticate",
        "status": "needs_action",
        "primary_command": "mdtero setup",
        "action_hint": "Browser OAuth is preferred on workstations; API-key setup is for trusted headless servers and agents.",
    }
    assert checklist["local_dependencies"]["status"] in {"ready", "needs_install"}
    assert checklist["local_dependencies"]["required_modules"] == ["curl_cffi.requests", "fastmcp", "pyzotero"]
    assert checklist["parse"]["primary_command"] == "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json"
    assert checklist["rag"]["primary_command"] == "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json"
    assert "VOYAGE_API_KEY" not in checklist["rag"]["action_hint"]
    assert checklist["mcp"]["primary_command"] == "mdtero mcp briefing --json"
    assert checklist["agent_skills"]["status"] == "not_detected"
    assert model["project"]["name"] == "tui-demo"
    assert model["rag"]["reason_code"] == "no_succeeded_tasks"
    assert model["rag"]["next_commands"][0] == "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json"
    assert model["mcp"]["primary_tool"] == "agent_briefing"
    setup_handoff = model["dashboard_setup_handoff_json"]
    assert model["mcp"]["dashboard_setup_handoff_json"] == setup_handoff
    assert setup_handoff["source"] == "dashboard_api_key_dialog"
    assert setup_handoff["first_cli_command"] == "mdtero setup --api-key --json"
    assert setup_handoff["api_key"]["full_secret_shown_once"] is True
    assert setup_handoff["api_key"]["full_secret_included"] is False
    assert "secure CLI prompt" in setup_handoff["auth_boundary"]["secret_transport"]
    assert "current page session" in setup_handoff["auth_boundary"]["dashboard_secret_retention"]
    assert "explicit clear" in setup_handoff["auth_boundary"]["dashboard_secret_retention"]
    assert setup_handoff["rag"]["owner"] == "backend_voyage"
    assert setup_handoff["rag"]["local_voyage_key_required"] is False
    assert setup_handoff["mcp"]["first_tool"] == "agent_briefing"
    assert "mdtero mcp briefing --json" in setup_handoff["next_commands"]
    assert "mdtero mcp serve" in setup_handoff["next_commands"]
    assert "VOYAGE_API_KEY" not in str(setup_handoff)
    assert model["mcp"]["server"]["transport"] == "stdio"
    assert model["mcp"]["server"]["agent_config_hint"] == {
        "mcpServers": {
            "mdtero": {
                "command": "mdtero",
                "args": ["mcp", "serve"],
                "cwd": str(tmp_path.resolve()),
            }
        }
    }
    assert model["mcp"]["server"]["skill_install_command"] == "mdtero agent install --interactive"
    assert "agent_briefing" in model["mcp"]["tools"]
    assert [step["step"] for step in model["mcp"]["tool_plan"]] == ["brief", "inspect_project", "prepare_rag"]
    assert model["mcp"]["tool_plan"][0]["tool"] == "agent_briefing"
    assert model["mcp"]["tool_plan"][0]["failure_fields"] == ["reason_code", "action_hint", "next_commands"]
    assert model["mcp"]["tool_plan"][-1]["tool"] == "server_rag_status"
    assert "ready_for_query is false" in model["mcp"]["tool_plan"][-1]["when"]
    assert model["mcp"]["agent_playbook"]["current_phase"] == "authenticate"
    assert model["mcp"]["agent_playbook"]["first_action"]["tool"] == "agent_commands"
    assert model["mcp"]["agent_playbook"]["first_action"]["command"] == "mdtero setup --api-key --json"
    assert "citation_contract" in model["mcp"]["agent_playbook"]["preserve_fields"]
    assert "source_nodes" in model["mcp"]["agent_playbook"]["preserve_fields"]
    assert any(step["step"] == "prepare_rag" for step in model["mcp"]["agent_playbook"]["ordered_steps"])
    assert model["mcp"]["task_tools"] == [
        {"tool": "submit_parse", "purpose": "Submit DOI/URL parse and optionally wait for completion"},
        {"tool": "task_status", "purpose": "Poll task status and sync local project state"},
        {"tool": "download_artifact", "purpose": "Download preferred Markdown/ZIP/translation artifact for a task"},
        {"tool": "request_translation", "purpose": "Translate parse task or Markdown with provider-attempt diagnostics"},
        {"tool": "rag_query", "purpose": "Bootstrap/query server-side Voyage RAG with evidence pack"},
    ]
    assert model["extension_handoff"]["commands"][:5] == [
        "mdtero config academic",
        "mdtero discover \"<topic>\" --limit 5 --interactive",
        "mdtero discover \"<topic>\" --limit 5 --add --select 1,3 --json",
        "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
        "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json",
    ]
    assert model["extension_handoff"]["commands"][5:] == [
        "mdtero status <task-id> --wait --timeout 300 --json",
        "mdtero download <task-id> paper_md --output-dir ./mdtero-output --json",
        "mdtero project ingest --json",
        "mdtero project refresh --wait --timeout 300 --json",
        "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json",
        "mdtero rag status --json",
        "mdtero rag build --wait --json",
        "mdtero rag query \"<question>\" --build-if-needed --json",
        "mdtero mcp briefing --json",
        "mdtero mcp serve",
    ]
    assert model["extension_handoff"]["primary_commands"] == [
        "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
        "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json",
    ]
    assert "curl_cffi route acquisition for planned HTML/XML/EPUB/PDF sources" in model["extension_handoff"]["cli_scope"]
    assert "publisher challenge or JavaScript verification page" in model["extension_handoff"]["handoff_triggers"]
    assert model["extension_handoff"]["visible_fields"] == ["task_id", "selected_provider", "parser_strategy", "client_acquisition", "parse_outcome", "reason_code", "action_hint", "preferred_artifact", "download_artifacts", "next_commands"]
    assert model["input_routes"]["goal"] == "choose_shortest_markdown_path"
    assert model["input_routes"]["server_apis"]["upload"] == "/api/v1/tasks/upload"
    assert model["input_routes"]["server_apis"]["rag_query"] == "/api/v1/projects/{project_id}/rag/query"
    input_routes = {route["id"]: route for route in model["input_routes"]["routes"]}
    assert input_routes["doi_or_url"]["primary_command"] == "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json"
    assert input_routes["file_upload"]["primary_command"] == "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json"
    assert "backend MinerU-first" in input_routes["file_upload"]["action_hint"]
    assert input_routes["browser_extension_handoff"]["status"] == "manual_capture"
    assert "website OAuth" in input_routes["browser_extension_handoff"]["best_for"]
    assert input_routes["rag_mcp_after_parse"]["next_commands"][:4] == [
        "mdtero project ingest --json",
        "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json",
        "mdtero rag status --json",
        "mdtero rag build --wait --json",
    ]
    assert input_routes["rag_mcp_after_parse"]["evidence_fields"] == ["answer", "citations", "source_nodes", "evidence_pack.context_markdown", "citation_contract"]
    assert model["input_routes"]["separate_smoke_required"] == ["pdf_mineru_urlapi", "epub_upload", "browser_extension_mv3"]
    assert model["agents"]["detect_command"] == "mdtero agent detect --json"
    assert model["agents"]["install_command"] == "mdtero agent install --interactive"
    assert model["agents"]["fallback_install_command"] == "mdtero agent install --target codex --json"
    assert model["handoff"]["active_items"] == []
    assert model["launch_summary"]["primary_path"] == "authenticate"
    assert model["launch_summary"]["primary_group"] == "Setup"
    assert model["launch_summary"]["primary_next_command"] == "mdtero setup"
    assert model["launch_summary"]["ready_count"] < model["launch_summary"]["total_count"]
    assert any(item["id"] == "auth" and item["ready"] is False for item in model["launch_summary"]["blocked_checks"])
    assert "mdtero setup" in model["launch_summary"]["recommended_flow"]
    assert model["launch_bundle"]["primary_group"] == "Setup"
    assert model["launch_bundle"]["copy_hint"] == "Copy one group into a terminal or agent prompt; commands are ordered and JSON-first where possible."
    launch_groups = {group["label"]: group for group in model["launch_bundle"]["groups"]}
    assert list(launch_groups) == ["Setup", "Parse", "Project", "RAG + MCP", "Extension handoff"]
    assert launch_groups["Setup"]["commands"][:4] == ["mdtero doctor --json", "mdtero setup", "mdtero setup --api-key --json", "mdtero mcp briefing --json"]
    assert "mdtero agent detect --json" in launch_groups["Setup"]["commands"]
    assert "mdtero agent install --interactive" in launch_groups["Setup"]["commands"]
    assert "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json" in launch_groups["Parse"]["commands"]
    assert "mdtero mcp briefing --json" in launch_groups["Extension handoff"]["commands"]
    assert model["next_steps"][:2] == ["mdtero setup", "mdtero doctor --json"]
    assert "mdtero setup --api-key --json" in model["next_steps"]
    assert model["operator_summary"][0] == {"area": "Account", "state": "missing", "detail": "run mdtero setup"}
    assert [item["key"] for item in model["shortcuts"]] == ["r", "d", "p", "g", "m", "q"]
    assert model["command_palette"][0] == {
        "area": "Setup",
        "use": "Authenticate this workstation with browser OAuth",
        "command": "mdtero setup",
        "is_next": True,
    }
    assert any(
        item["area"] == "Setup"
        and item["use"] == "Headless or remote shell fallback"
        and item["command"] == "mdtero setup --api-key --json"
        and item["is_next"]
        for item in model["command_palette"]
    )
    assert any(item["command"] == "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json" for item in model["command_palette"])
    assert any(item["area"] == "MCP" and item["command"] == "submit_parse" for item in model["command_palette"])
    assert any(item["area"] == "MCP" and item["command"] == "task_status" for item in model["command_palette"])
    assert any(item["area"] == "MCP" and item["command"] == "download_artifact" for item in model["command_palette"])
    assert any(item["area"] == "MCP" and item["command"] == "request_translation" for item in model["command_palette"])
    assert any(item["area"] == "Extension" and item["use"] == "Handoff challenged page or saved file to CLI" for item in model["command_palette"])
    assert any(item["area"] == "Extension" and item["use"] == "Upload a browser-saved PDF/EPUB/XML/HTML" for item in model["command_palette"])


def test_tui_dashboard_model_accepts_environment_api_key(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MDTERO_API_KEY", "mdt_live_env")
    init_project(tmp_path, name="tui-env")

    model = build_dashboard_model(project_root=tmp_path, config=MdteroConfig(api_key=None), agent_root=tmp_path)

    assert model["account"]["authenticated"] is True
    assert model["account"]["auth_source"] == "MDTERO_API_KEY"
    assert model["next_steps"][:2] != ["mdtero setup --api-key --json", "mdtero doctor --json"]


def test_tui_dashboard_model_surfaces_rag_ingest_and_integrations(tmp_path: Path):
    init_project(tmp_path, name="tui-demo")
    bind_server_project(tmp_path, "42")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))
    (tmp_path / ".codex").mkdir()
    cfg = MdteroConfig(
        api_key="key",
        academic=AcademicKeys(semantic_scholar_api_key="s2"),
        zotero=ZoteroConfig(library_id="123", library_type="user", api_key="zotero"),
    )

    model = build_dashboard_model(project_root=tmp_path, config=cfg, agent_root=tmp_path, rag_status_fetcher=lambda _project_id: {
        "status": "not_ready",
        "reason_code": "rag_index_not_built",
        "summary": {"chunk_count": 2, "embedded_count": 0},
        "selected_provider": "voyage",
        "provider_state": "configured",
        "provider_configured": True,
        "embedding_model": "voyage-4",
        "action_hint": "Build the server project index before querying.",
        "next_commands": ["mdtero rag build --wait --json", "mdtero rag status --json"],
    })
    assert_dashboard_model_commands_parse(model)
    rendered = render_dashboard_text(model)

    assert model["academic"]["discover_source"] == "local Semantic Scholar"
    assert model["health"]["status"] == "results_ready"
    assert model["health"]["counts"]["ready_artifacts"] == 1
    assert model["health"]["counts"]["pending_agent_installs"] == 1
    assert model["rag"]["ready"] is False
    assert model["rag"]["server_status"] == "not_ready"
    assert model["rag"]["selected_provider"] == "voyage"
    assert model["rag"]["provider_state"] == "configured"
    assert model["rag"]["provider_configured"] is True
    assert model["rag"]["embedding_model"] == "voyage-4"
    assert model["rag"]["action_hint"] == "Build the server project index before querying."
    assert model["rag"]["next_commands"] == ["mdtero rag build --wait --json", "mdtero rag status --json"]
    assert model["rag"]["citation_contract"]["required_for_final_answer"] == ["citations", "source_nodes"]
    assert model["rag"]["citation_rule"] == "Final answers preserve citations, source_nodes"
    assert model["rag"]["server_agent_summary"] == {
        "status": "not_ready",
        "reason_code": "rag_index_not_built",
        "selected_provider": "voyage",
        "provider_state": "configured",
        "provider_configured": True,
        "embedding_model": "voyage-4",
        "embedded_count": 0,
        "chunk_count": 2,
        "pending_embedding_count": 0,
    }
    assert model["next_steps"] == ["mdtero rag query \"What are the strongest findings?\" --build-if-needed --json", "mdtero rag status --json", "mdtero rag build --wait --json"]
    assert model["mcp"]["serve_command"] == "mdtero mcp serve"
    assert model["mcp"]["briefing_command"] == "mdtero mcp briefing --json"
    assert "mdtero rag build --wait --json" in model["mcp"]["recommended_next_commands"]
    plan_steps = {step["step"]: step for step in model["mcp"]["tool_plan"]}
    assert plan_steps["download_artifact"]["tool"] == "download_artifact"
    assert plan_steps["translate_ready_artifact"]["tool"] == "request_translation"
    assert plan_steps["prepare_rag"]["tool"] == "server_rag_build"
    assert plan_steps["prepare_rag"]["arguments"] == {"wait": True, "timeout": 300, "interval": 2}
    assert "readiness" in plan_steps["prepare_rag"]["failure_fields"]
    assert model["mcp"]["agent_playbook"]["current_phase"] == "build_or_query_rag"
    assert model["mcp"]["agent_playbook"]["first_action"]["tool"] == "rag_query"
    assert model["mcp"]["agent_playbook"]["first_action"]["command"] == "mdtero rag query \"<question>\" --build-if-needed --json"
    assert any(step["step"] == "download_artifact" for step in model["mcp"]["agent_playbook"]["ordered_steps"])
    assert any(step["step"] == "prepare_rag" for step in model["mcp"]["agent_playbook"]["ordered_steps"])
    assert "evidence_pack.context_markdown" in model["mcp"]["agent_playbook"]["preserve_fields"]
    palette_commands = [item["command"] for item in model["command_palette"]]
    assert "mdtero project ingest --json" in palette_commands
    assert "mdtero rag query \"<question>\" --build-if-needed --json" in palette_commands
    assert "mdtero mcp briefing --json" in palette_commands
    assert "mdtero mcp serve" in palette_commands
    assert "mdtero zotero sync --json" in palette_commands
    assert "mdtero agent install --interactive" in palette_commands
    assert any(item["command"] == "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json" and item["is_next"] for item in model["command_palette"])
    assert model["handoff"]["ready_artifacts"][0]["download_command"] == "mdtero download task-done paper_md --output-dir ./mdtero-output --json"
    assert model["handoff"]["recommended_next_commands"][0] == "mdtero project download --output-dir ./mdtero-output --json"
    assert model["launch_bundle"]["primary_group"] == "RAG + MCP"
    assert model["launch_summary"]["primary_path"] == "build_rag"
    assert model["launch_summary"]["primary_group"] == "RAG + MCP"
    assert model["launch_summary"]["primary_next_command"] == "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json"
    assert any(item["id"] == "rag" and item["ready"] is False for item in model["launch_summary"]["blocked_checks"])
    assert "mdtero mcp briefing --json" in model["launch_summary"]["recommended_flow"]
    launch_groups = {group["label"]: group for group in model["launch_bundle"]["groups"]}
    assert "mdtero project ingest --json" in launch_groups["RAG + MCP"]["commands"]
    assert "mdtero rag build --wait --json" in launch_groups["RAG + MCP"]["commands"]
    assert "mdtero rag status --json" in launch_groups["RAG + MCP"]["commands"]
    assert "mdtero rag query \"<question>\" --build-if-needed --json" in launch_groups["RAG + MCP"]["commands"]
    assert "mdtero mcp briefing --json" in launch_groups["RAG + MCP"]["commands"]
    assert "mdtero mcp serve" in launch_groups["RAG + MCP"]["commands"]
    assert model["zotero"]["configured"] is True
    assert model["agents"]["labels"] == ["Codex"]
    assert model["agents"]["detected_count"] == 1
    assert model["agents"]["installed_count"] == 0
    assert model["agents"]["pending_install_count"] == 1
    assert model["agents"]["pending_install_labels"] == ["Codex"]
    assert model["agents"]["status"][0]["installed"] is False
    assert model["agents"]["install_command"] == "mdtero agent install --interactive"
    console = Console(record=True, width=140)
    console.print(rendered)
    output = console.export_text()
    assert "Mdtero Control Console" in output
    assert "Launch path" in output
    assert "build_rag" in output
    assert "Dashboard Setup Handoff" in output
    assert "dashboard_api_key_dialog" in output
    assert "full_secret_included=false" in output
    assert "secure CLI prompt" in output
    assert "backend_voyage" in output
    assert "Readiness" in output
    assert "Onboarding Checklist" in output
    assert "Results ready" in output
    assert "Agent Handoff" in output
    assert "Agent skills" in output
    assert "Operator Summary" in output
    assert "Extension to CLI" in output
    assert "client_acquisition" in output
    assert "publisher challenge" in output
    assert "Shortcuts" in output
    assert "Command Palette" in output
    assert "Launch Bundles" in output
    assert "Copy one group into a terminal" in output
    assert "RAG + MCP" in output
    assert "One-command Voyage bootstrap and query" in output
    assert "Explicit recovery build when bootstrap query is not enough" in output
    assert "voyage / configured" in output
    assert "voyage-4" in output
    assert "Build the server project index before" in output
    assert "querying" in output
    assert "Evidence rule" in output
    assert "Final answers preserve citations, source_nodes" in output
    assert "submit_parse" in output
    assert "task_status" in output
    assert "download_artifact" in output
    assert "request_translation" in output
    assert "MCP Tool Plan" in output
    assert "Agent Playbook" in output
    assert "build_or_query_rag" in output
    assert "rag_query" in output
    assert "evidence_pack.context_markdown" in output
    assert "prepare_rag" in output
    assert "server_rag_build" in output
    assert "failure_fields" not in output
    assert "readiness" in output
    assert "r" in output
    assert "refresh" in output
    assert rendered is not None


def test_tui_app_exposes_operator_shortcuts():
    bindings = set(MdteroTui.BINDINGS)

    assert ("r", "refresh_dashboard", "Refresh") in bindings
    assert ("d", "doctor", "Doctor") in bindings
    assert ("p", "parse_pending", "Parse") in bindings
    assert ("g", "rag_status", "RAG") in bindings
    assert ("m", "mcp_briefing", "MCP") in bindings
    assert ("q", "quit", "Quit") in bindings


def test_tui_dashboard_model_reports_installed_agent_skills(tmp_path: Path):
    init_project(tmp_path, name="tui-agent-installed")
    skill_dir = tmp_path / ".codex" / "skills" / "mdtero"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Mdtero", encoding="utf-8")

    model = build_dashboard_model(project_root=tmp_path, config=MdteroConfig(api_key="key"), agent_root=tmp_path)

    assert model["agents"]["detected"] == ["codex"]
    assert model["agents"]["installed_count"] == 1
    assert model["agents"]["pending_install_count"] == 0
    assert model["agents"]["pending_install_labels"] == []
    assert model["agents"]["status"][0]["skill_path"].endswith(".codex/skills/mdtero")


def test_tui_dashboard_model_surfaces_blocked_and_active_handoff_items(tmp_path: Path):
    init_project(tmp_path, name="handoff-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/todo", status="pending"))
    attempts = [{"provider": "codex", "reason_code": "translation_provider_auth_failed", "provider_status_code": 401}]
    add_paper(
        tmp_path,
        PaperRecord(
            input="10.1000/bad",
            task_id="task-bad",
            status="failed",
            reason_code="translation_provider_chain_failed",
            action_hint="Refresh provider API keys or quota.",
            translation_attempts=attempts,
        ),
    )

    model = build_dashboard_model(project_root=tmp_path, config=MdteroConfig(api_key="key"), agent_root=tmp_path)
    rendered = render_dashboard_text(model)

    assert model["health"]["status"] == "needs_attention"
    assert model["health"]["counts"]["blocked_items"] == 1
    assert model["health"]["primary_next_command"] == "mdtero project parse --wait --timeout 300 --json"
    assert model["handoff"]["active_items"][0]["input"] == "10.1000/todo"
    assert model["handoff"]["blocked_items"][0]["reason_code"] == "translation_provider_chain_failed"
    assert model["handoff"]["blocked_items"][0]["action_hint"] == "Refresh provider API keys or quota."
    assert model["handoff"]["blocked_items"][0]["translation_attempts"] == attempts
    assert "mdtero project parse --include-failed --wait --timeout 300 --json" in model["handoff"]["recommended_next_commands"]
    console = Console(record=True, width=140)
    console.print(rendered)
    output = console.export_text()
    assert "Refresh provider API keys or quota" in output
    assert "codex:translation_provider_auth_failed" in output


def test_tui_dashboard_model_surfaces_ready_server_rag_status(tmp_path: Path):
    init_project(tmp_path, name="tui-demo")
    bind_server_project(tmp_path, "42")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    model = build_dashboard_model(
        project_root=tmp_path,
        config=MdteroConfig(api_key="key"),
        agent_root=tmp_path,
        rag_status_fetcher=lambda _project_id: {
            "status": "ready",
            "reason_code": "indexed",
            "summary": {"chunk_count": 3, "embedded_count": 3, "embedding_model": "voyage-test"},
            "selected_provider": "voyage",
            "provider_state": "configured",
            "provider_configured": True,
        },
    )
    assert_dashboard_model_commands_parse(model)
    rendered = render_dashboard_text(model)

    assert model["health"]["status"] == "ready"
    assert model["health"]["headline"] == "Project RAG ready"
    assert model["health"]["primary_next_command"] == "mdtero rag status --json"
    assert model["launch_summary"]["primary_path"] == "query_rag_or_serve_mcp"
    assert model["launch_summary"]["primary_next_command"] == "mdtero rag status --json"
    assert any(item["id"] == "rag" and item["ready"] is True for item in model["launch_summary"]["checks"])
    assert model["rag"]["ready"] is True
    assert model["rag"]["reason_code"] == "indexed"
    assert model["rag"]["server_summary"]["embedded_count"] == 3
    assert model["rag"]["selected_provider"] == "voyage"
    assert model["rag"]["provider_state"] == "configured"
    assert model["rag"]["provider_configured"] is True
    assert model["rag"]["embedding_model"] == "voyage-test"
    assert model["rag"]["citation_contract"]["required_for_final_answer"] == ["citations", "source_nodes"]
    assert model["rag"]["citation_rule"] == "Final answers preserve citations, source_nodes"
    assert model["rag"]["server_agent_summary"]["embedding_model"] == "voyage-test"
    assert model["next_steps"] == ["mdtero rag status --json", "mdtero rag query \"<question>\" --build-if-needed --json", "mdtero mcp briefing --json", "mdtero mcp serve"]
    assert model["mcp"]["briefing_command"] == "mdtero mcp briefing --json"
    assert model["mcp"]["recommended_next_commands"][-1] == "mdtero mcp serve"
    assert rendered is not None


def test_tui_dashboard_model_keeps_local_rag_when_server_status_unavailable(tmp_path: Path):
    init_project(tmp_path, name="tui-demo")
    bind_server_project(tmp_path, "42")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    def failing_fetcher(_project_id):
        raise RuntimeError("offline")

    model = build_dashboard_model(project_root=tmp_path, config=MdteroConfig(api_key="key"), agent_root=tmp_path, rag_status_fetcher=failing_fetcher)

    assert model["rag"]["ready"] is True
    assert model["rag"]["server_status"] == "unavailable"
    assert model["rag"]["server_reason_code"] == "server_rag_status_unavailable"
    assert model["next_steps"] == ["mdtero rag query \"What are the strongest findings?\" --build-if-needed --json", "mdtero rag status --json", "mdtero rag build --wait --json"]


def test_rag_uses_bound_server_project_id_by_default(monkeypatch, tmp_path: Path):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    bind_server_project(tmp_path, "42")

    monkeypatch.chdir(tmp_path)
    assert cli._server_project_id(type("Args", (), {"project_id": None})()) == "42"
    assert cli._server_project_id(type("Args", (), {"project_id": "99"})()) == "99"


def test_rag_project_id_helper_points_unlinked_projects_to_bootstrap_build(monkeypatch, tmp_path: Path):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    monkeypatch.chdir(tmp_path)

    try:
        cli._server_project_id(type("Args", (), {"project_id": None})())
    except SystemExit as exc:
        message = str(exc)
    else:
        raise AssertionError("expected missing binding error")

    assert "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json" in message
    assert "create, bind, import, build, and query" in message


def test_rag_build_guides_empty_projects_before_creating_server_project(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/todo", status="pending"))

    def should_not_create_project(self, name, *, description=None):  # pragma: no cover - failure guard
        raise AssertionError("server project should not be created before a project has succeeded parse tasks")

    monkeypatch.setattr(MdteroClient, "create_project", should_not_create_project)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_build(type("Args", (), {"project_id": None, "json": True})()) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "not_ready"
    assert payload["command"] == "rag_build"
    assert payload["reason_code"] == "no_succeeded_tasks"
    assert payload["server_project_id"] is None
    assert payload["local_ready_for_ingest_count"] == 0
    assert "Parse at least one paper successfully" in payload["action_hint"]
    assert "arXiv smoke DOI" in payload["action_hint"]
    assert payload["next_commands"] == [
        "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json",
        "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json",
        "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
        "mdtero project refresh --wait --timeout 300 --json",
        "mdtero rag query \"<question>\" --build-if-needed --json",
    ]


def test_rag_query_build_if_needed_guides_empty_projects_before_creating_server_project(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/todo", status="pending"))

    def should_not_create_project(self, name, *, description=None):  # pragma: no cover - failure guard
        raise AssertionError("server project should not be created before a project has succeeded parse tasks")

    monkeypatch.setattr(MdteroClient, "create_project", should_not_create_project)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_query(type("Args", (), {"project_id": None, "question": "What is indexed?", "build_if_needed": True, "json": True})()) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "not_ready"
    assert payload["command"] == "rag_query"
    assert payload["reason_code"] == "no_succeeded_tasks"
    assert payload["question"] == "What is indexed?"
    assert payload["answer"] is None
    assert payload["next_commands"][0] == "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json"
    assert payload["next_commands"][1] == "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json"
    assert payload["next_commands"][2] == "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json"


def test_rag_status_prefers_server_status_when_project_is_linked(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    bind_server_project(tmp_path, "42")

    def fake_status(self, project_id):
        assert project_id == "42"
        return {
            "status": "ready",
            "reason_code": "indexed",
            "selected_provider": "voyage",
            "summary": {"chunk_count": 3, "embedded_count": 3, "embedding_model": "voyage-test"},
            "action_hint": "Query this project or serve it over MCP.",
            "next_commands": ["mdtero rag status --json", "mdtero rag query \"<question>\"", "mdtero mcp briefing --json", "mdtero mcp serve"],
        }

    monkeypatch.setattr(MdteroClient, "rag_status", fake_status)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_status(type("Args", (), {"project_id": None, "json": False})()) == 0
    output = capsys.readouterr().out

    assert "server RAG ready (indexed)" in output
    assert "3/3 chunk(s) embedded" in output
    assert "voyage-test" in output
    assert "Hint: Query this project or serve it over MCP." in output
    assert "mdtero rag query \"<question>\"" in output
    assert "mdtero mcp briefing --json" in output
    assert "mdtero mcp serve" in output
    assert "Agent plan" in output
    assert "query_rag -> rag_query" in output
    assert "handoff_to_local_agent -> mcp_briefing" in output


def test_rag_status_prints_server_next_commands_for_partial_index(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    bind_server_project(tmp_path, "42")

    def fake_status(self, project_id):
        assert project_id == "42"
        return {
            "status": "partial",
            "reason_code": "rag_index_partial",
            "selected_provider": "voyage",
            "summary": {"chunk_count": 4, "embedded_count": 2, "pending_embedding_count": 2},
            "action_hint": "Rebuild project RAG so every imported chunk has a Voyage embedding.",
            "next_commands": ["mdtero rag build", "mdtero rag status --json", "mdtero rag query \"<question>\""],
        }

    monkeypatch.setattr(MdteroClient, "rag_status", fake_status)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_status(type("Args", (), {"project_id": None, "json": False})()) == 0
    output = capsys.readouterr().out

    assert "server RAG partial (rag_index_partial)" in output
    assert "2/4 chunk(s)" in output
    assert "embedded" in output
    assert "Hint: Rebuild project RAG" in output
    assert "mdtero rag build" in output
    assert "mdtero rag status --json" in output
    assert "Agent plan" in output
    assert "build_rag_index -> server_rag_build" in output
    assert "query_after_build -> rag_query" in output


def test_rag_status_outputs_server_json_for_agents(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")

    def fake_status(self, project_id):
        assert project_id == "99"
        return {
            "status": "partial",
            "reason_code": "rag_index_partial",
            "selected_provider": "voyage",
            "summary": {"chunk_count": 4, "embedded_count": 2, "pending_embedding_count": 2},
        }

    monkeypatch.setattr(MdteroClient, "rag_status", fake_status)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_status(type("Args", (), {"project_id": "99", "json": True})()) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "partial"
    assert payload["reason_code"] == "rag_index_partial"
    assert payload["server_project_id"] == "99"
    assert payload["summary"]["pending_embedding_count"] == 2
    assert payload["agent_tool_plan"][0]["step"] == "inspect_rag_status"
    assert any(step["step"] == "build_rag_index" and step["tool"] == "server_rag_build" for step in payload["agent_tool_plan"])
    assert any(step["step"] == "query_after_build" and step["tool"] == "rag_query" for step in payload["agent_tool_plan"])


def test_rag_status_unavailable_json_includes_actionable_next_commands(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    bind_server_project(tmp_path, "42")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    def fake_status(self, project_id):
        request = httpx.Request("GET", f"https://api.mdtero.com/api/v1/projects/{project_id}/rag/status")
        response = httpx.Response(404, request=request, json={"detail": "Not Found"})
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    monkeypatch.setattr(MdteroClient, "rag_status", fake_status)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_status(type("Args", (), {"project_id": None, "json": True})()) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == "server_rag_status_unavailable"
    assert payload["http_status"] == 404
    assert payload["local_ready_for_ingest_count"] == 1
    assert "backend /api/v1 project RAG routes" in payload["action_hint"]
    assert payload["next_commands"] == ["mdtero project ingest --json", "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json", "mdtero rag status --json", "mdtero rag build --wait --json"]
    assert payload["agent_tool_plan"][0]["tool"] == "server_rag_status"


def test_rag_build_failure_outputs_agent_json_without_traceback(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    bind_server_project(tmp_path, "42")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    def fake_build(self, project_id):
        assert project_id == "42"
        request = httpx.Request("POST", f"https://api.mdtero.com/api/v1/projects/{project_id}/rag/build")
        response = httpx.Response(
            503,
            request=request,
            json={
                "detail": {
                    "error_code": "server_rag_failed",
                    "reason_code": "voyage_not_configured",
                    "action_hint": "Configure VOYAGE_API_KEY on the server before building or querying RAG.",
                }
            },
        )
        raise httpx.HTTPStatusError("service unavailable", request=request, response=response)

    def fake_import(self, project_id, task_id):
        assert project_id == "42"
        assert task_id == "task-done"
        return {"document_id": "doc-1", "import_status": "imported"}

    monkeypatch.setattr(MdteroClient, "import_task_to_project", fake_import)
    monkeypatch.setattr(MdteroClient, "rag_build", fake_build)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_build(type("Args", (), {"project_id": None, "json": True})()) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "failed"
    assert payload["command"] == "rag_build"
    assert payload["reason_code"] == "voyage_not_configured"
    assert payload["error_code"] == "server_rag_failed"
    assert payload["server_project_id"] == "42"
    assert payload["http_status"] == 503
    assert payload["error_type"] == "HTTPStatusError"
    assert "Server-side Voyage RAG is not available" in payload["action_hint"]
    assert "backend operations issue" in payload["action_hint"]
    assert "VOYAGE_API_KEY" not in payload["action_hint"]
    assert payload["next_commands"] == ["mdtero rag status --json"]


def test_rag_query_not_built_outputs_next_commands(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    bind_server_project(tmp_path, "42")

    def fake_query(self, project_id, question):
        assert project_id == "42"
        assert question == "demo"
        request = httpx.Request("POST", f"https://api.mdtero.com/api/v1/projects/{project_id}/rag/query")
        response = httpx.Response(
            409,
            request=request,
            json={"detail": {"error_code": "server_rag_failed", "reason_code": "rag_index_not_built"}},
        )
        raise httpx.HTTPStatusError("conflict", request=request, response=response)

    monkeypatch.setattr(MdteroClient, "rag_query", fake_query)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_query(type("Args", (), {"project_id": None, "question": "demo", "json": True})()) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "failed"
    assert payload["command"] == "rag_query"
    assert payload["reason_code"] == "rag_index_not_built"
    assert payload["http_status"] == 409
    assert "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json" in payload["action_hint"]
    assert payload["next_commands"] == ["mdtero rag query \"What are the strongest findings?\" --build-if-needed --json", "mdtero rag status --json", "mdtero rag build --wait --json", "mdtero rag query \"<question>\" --build-if-needed --json"]


def test_rag_query_failure_preserves_backend_next_commands(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    bind_server_project(tmp_path, "42")

    def fake_query(self, project_id, question):
        assert project_id == "42"
        assert question == "demo"
        request = httpx.Request("POST", f"https://api.mdtero.com/api/v1/projects/{project_id}/rag/query")
        response = httpx.Response(
            503,
            request=request,
            json={
                "detail": {
                    "error_code": "server_rag_failed",
                    "reason_code": "voyage_not_configured",
                    "action_hint": "Server RAG is not configured in production.",
                    "next_commands": ["mdtero rag status --json"],
                }
            },
        )
        raise httpx.HTTPStatusError("service unavailable", request=request, response=response)

    monkeypatch.setattr(MdteroClient, "rag_query", fake_query)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_query(type("Args", (), {"project_id": None, "question": "demo", "json": True})()) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["reason_code"] == "voyage_not_configured"
    assert "Server-side Voyage RAG is not available" in payload["action_hint"]
    assert "backend operations issue" in payload["action_hint"]
    assert "VOYAGE_API_KEY" not in payload["action_hint"]
    assert payload["next_commands"] == ["mdtero rag status --json"]


def test_rag_query_failure_plain_output_is_actionable(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    bind_server_project(tmp_path, "42")

    def fake_query(self, project_id, question):
        request = httpx.Request("POST", f"https://api.mdtero.com/api/v1/projects/{project_id}/rag/query")
        response = httpx.Response(409, request=request, json={"detail": {"reason_code": "rag_index_not_built"}})
        raise httpx.HTTPStatusError("conflict", request=request, response=response)

    monkeypatch.setattr(MdteroClient, "rag_query", fake_query)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_query(type("Args", (), {"project_id": None, "question": "demo", "json": False})()) == 1
    output = capsys.readouterr().out

    assert "RAG query failed: rag_index_not_built" in output
    assert "Hint:" in output
    assert "Next:" in output
    assert "mdtero rag build" in output


def test_rag_query_success_plain_output_shows_answer_citations_and_next_commands(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    bind_server_project(tmp_path, "42")

    def fake_query(self, project_id, question):
        assert project_id == "42"
        assert question == "What improves corrosion?"
        return {
            "status": "succeeded",
            "reason_code": "rag_query_succeeded",
            "answer": "[1] Coating improves corrosion resistance.",
            "citations": [
                {
                    "citation_order": 1,
                    "document_title": "Corrosion Paper",
                    "document_id": 7,
                    "chunk_id": 9,
                    "line_start": 3,
                    "line_end": 4,
                    "doi": "10.1000/rag",
                    "source_url": "https://doi.org/10.1000/rag",
                }
            ],
            "next_commands": ["mdtero rag status --json", "mdtero mcp briefing --json", "mdtero mcp serve"],
        }

    monkeypatch.setattr(MdteroClient, "rag_query", fake_query)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_query(type("Args", (), {"project_id": None, "question": "What improves corrosion?", "json": False})()) == 0
    output = capsys.readouterr().out

    assert "RAG query: succeeded (rag_query_succeeded)" in output
    assert "Answer" in output
    assert "[1] Coating improves corrosion resistance." in output
    assert "Corrosion Paper:3-4 · 10.1000/rag" in output
    assert "Citation contract" in output
    assert "Final answers must preserve: citations, source_nodes" in output
    assert "Use source_nodes and citations as grounded evidence" in output
    assert "mdtero mcp briefing --json" in output
    assert "mdtero mcp serve" in output
    assert "Agent plan" in output
    assert "query_rag -> rag_query" in output


def test_rag_query_json_backfills_answer_citations_and_next_commands_from_matches(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    bind_server_project(tmp_path, "42")

    def fake_query(self, project_id, question):
        assert project_id == "42"
        assert question == "What is the contribution?"
        return {
            "project_id": 42,
            "question": question,
            "selected_provider": "voyage",
            "retrieval_strategy": "voyage_embedding_v1",
            "used_embeddings": True,
            "reason_code": "ok",
            "matches": [
                {
                    "citation_order": 1,
                    "document_id": 7,
                    "document_title": "Attention Is All You Need",
                    "chunk_id": 9,
                    "line_start": 53,
                    "line_end": 58,
                    "snippet": "The Transformer relies entirely on attention and avoids recurrence.",
                    "score": 0.73,
                }
            ],
        }

    monkeypatch.setattr(MdteroClient, "rag_query", fake_query)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_query(type("Args", (), {"project_id": None, "question": "What is the contribution?", "json": True})()) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "succeeded"
    assert payload["reason_code"] == "ok"
    assert payload["server_project_id"] == "42"
    assert payload["answer"] == "[1] The Transformer relies entirely on attention and avoids recurrence."
    assert payload["answer_kind"] == "extractive_evidence_pack"
    assert payload["citations"][0]["document_title"] == "Attention Is All You Need"
    assert payload["citations"][0]["line_start"] == 53
    assert payload["source_nodes"][0]["node_id"] == "doc-7:chunk-9"
    assert payload["source_nodes"][0]["metadata"]["citation_order"] == 1
    assert payload["source_nodes"][0]["metadata"]["line_end"] == 58
    assert payload["evidence_pack"]["answer_kind"] == "extractive_evidence_pack"
    assert payload["evidence_pack"]["question"] == "What is the contribution?"
    assert "[1] Attention Is All You Need:53-58" in payload["evidence_pack"]["context_markdown"]
    assert "grounded evidence" in payload["evidence_pack"]["agent_instruction"]
    assert payload["citation_contract"]["answer_kind"] == "extractive_evidence_pack"
    assert payload["citation_contract"]["required_for_final_answer"] == ["citations", "source_nodes"]
    assert "evidence_pack.context_markdown" in payload["citation_contract"]["evidence_fields"]
    assert "grounded evidence" in payload["citation_contract"]["agent_instruction"]
    assert payload["next_best_action"]["citation_contract"] == payload["citation_contract"]
    assert payload["readiness"]["ready_for_query"] is True
    assert payload["readiness"]["provider_blocked"] is False
    assert payload["readiness"]["next_step"] == "query"
    assert payload["agent_summary"]["status"] == "succeeded"
    assert payload["agent_summary"]["reason_code"] == "ok"
    assert payload["agent_summary"]["selected_provider"] == "voyage"
    assert payload["agent_summary"]["provider_configured"] is True
    assert payload["agent_summary"]["ready_for_query"] is True
    assert payload["agent_summary"]["next_commands"] == ["mdtero rag status --json", "mdtero rag query \"<question>\" --build-if-needed --json", "mdtero mcp briefing --json", "mdtero mcp serve"]
    assert payload["dashboard_handoff_json"]["first_mcp_tool"] == "server_rag_status"
    assert payload["dashboard_handoff_json"]["validation_step"]["arguments"] == {"project_id": "42"}
    assert "evidence_pack.context_markdown" in payload["dashboard_handoff_json"]["expected_fields"]
    assert any(step["step"] == "query_rag" for step in payload["agent_tool_plan"])
    assert any(step["step"] == "handoff_to_local_agent" for step in payload["agent_tool_plan"])
    assert payload["action_hint"] == "RAG query completed. Review the returned answer, citations, and matches."
    assert payload["next_commands"] == ["mdtero rag status --json", "mdtero rag query \"<question>\" --build-if-needed --json", "mdtero mcp briefing --json", "mdtero mcp serve"]


def test_rag_status_reports_local_precondition_when_project_is_unlinked(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_status(type("Args", (), {"project_id": None, "json": False})()) == 0
    output = capsys.readouterr().out

    assert "1/1 local paper(s)" in output
    assert "mdtero rag build --wait --json" in output
    assert "mdtero rag query \"<question>\" --build-if-needed --json" in output
    assert "Agent plan" in output
    assert "create_or_link_server_project -> project_bridge" in output


def test_rag_status_outputs_unlinked_json_for_agents(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_status(type("Args", (), {"project_id": None, "json": True})()) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "not_ready"
    assert payload["reason_code"] == "server_project_not_linked"
    assert "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json" in payload["action_hint"]
    assert payload["next_commands"] == ["mdtero rag query \"What are the strongest findings?\" --build-if-needed --json", "mdtero rag status --json", "mdtero rag build --wait --json", "mdtero rag query \"<question>\" --build-if-needed --json"]
    assert payload["agent_tool_plan"][0]["step"] == "inspect_rag_status"
    assert any(step["step"] == "create_or_link_server_project" for step in payload["agent_tool_plan"])


def test_rag_build_unlinked_project_auto_creates_ingests_and_builds(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))
    calls = []

    def fake_create(self, name, *, description=None):
        calls.append(("create", name, description))
        return {"id": 42, "name": name}

    def fake_list(self):
        calls.append(("list",))
        return {"items": []}

    def fake_import(self, project_id, task_id):
        calls.append(("import", project_id, task_id))
        return {"document_id": "doc-1", "import_status": "imported"}

    def fake_build(self, project_id):
        calls.append(("build", project_id))
        return {"status": "queued", "reason_code": "rag_build_queued"}

    monkeypatch.setattr(MdteroClient, "list_projects", fake_list)
    monkeypatch.setattr(MdteroClient, "create_project", fake_create)
    monkeypatch.setattr(MdteroClient, "import_task_to_project", fake_import)
    monkeypatch.setattr(MdteroClient, "rag_build", fake_build)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_build(type("Args", (), {"project_id": None, "json": True})()) == 0
    payload = json.loads(capsys.readouterr().out)
    state = load_project(tmp_path)

    assert payload["status"] == "queued"
    assert payload["reason_code"] == "rag_build_queued"
    assert payload["server_project_id"] == "42"
    assert payload["bootstrap"]["created_server_project"] is True
    assert payload["ingest"]["imported_count"] == 1
    assert state.server_project_id == "42"
    assert calls == [
        ("list",),
        ("create", "local-demo", "Mdtero local project: local-demo"),
        ("import", "42", "task-done"),
        ("build", "42"),
    ]


def test_rag_build_wait_polls_until_ready(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))
    calls = []

    def fake_create(self, name, *, description=None):
        calls.append(("create", name, description))
        return {"id": 42, "name": name}

    def fake_import(self, project_id, task_id):
        calls.append(("import", project_id, task_id))
        return {"document_id": "doc-1", "import_status": "imported"}

    def fake_build(self, project_id):
        calls.append(("build", project_id))
        return {"status": "queued", "reason_code": "rag_build_queued"}

    def fake_status(self, project_id):
        calls.append(("status", project_id))
        return {"status": "ready", "reason_code": "indexed", "chunk_count": 6}

    monkeypatch.setattr(MdteroClient, "create_project", fake_create)
    monkeypatch.setattr(MdteroClient, "import_task_to_project", fake_import)
    monkeypatch.setattr(MdteroClient, "rag_build", fake_build)
    monkeypatch.setattr(MdteroClient, "rag_status", fake_status)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_build(type("Args", (), {"project_id": None, "wait": True, "timeout": 1, "interval": 0.01, "json": True})()) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "queued"
    assert payload["reason_code"] == "rag_build_queued"
    assert payload["status_after_build"]["status"] == "ready"
    assert payload["status_after_build"]["reason_code"] == "indexed"
    assert payload["server_project_id"] == "42"
    assert calls == [
        ("create", "local-demo", "Mdtero local project: local-demo"),
        ("import", "42", "task-done"),
        ("build", "42"),
        ("status", "42"),
    ]


def test_rag_build_reuses_matching_server_project_before_creating(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))
    calls = []

    def fake_list(self):
        calls.append(("list",))
        return {"items": [{"id": 77, "name": "local-demo", "rag_status": {"reason_code": "indexed"}}]}

    def fake_create(self, name, *, description=None):
        raise AssertionError("matching server project should be reused")

    def fake_import(self, project_id, task_id):
        calls.append(("import", project_id, task_id))
        return {"document_id": "doc-1", "import_status": "imported"}

    def fake_build(self, project_id):
        calls.append(("build", project_id))
        return {"status": "ready", "reason_code": "indexed"}

    monkeypatch.setattr(MdteroClient, "list_projects", fake_list)
    monkeypatch.setattr(MdteroClient, "create_project", fake_create)
    monkeypatch.setattr(MdteroClient, "import_task_to_project", fake_import)
    monkeypatch.setattr(MdteroClient, "rag_build", fake_build)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_build(type("Args", (), {"project_id": None, "json": True})()) == 0
    payload = json.loads(capsys.readouterr().out)
    state = load_project(tmp_path)

    assert payload["server_project_id"] == "77"
    assert payload["bootstrap"]["created_server_project"] is False
    assert payload["bootstrap"]["reused_server_project"] is True
    assert payload["ingest"]["imported_count"] == 1
    assert state.server_project_id == "77"
    assert calls == [("list",), ("import", "77", "task-done"), ("build", "77")]


def test_rag_build_bootstrap_failure_preserves_backend_next_commands(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    def fake_create(self, name, *, description=None):
        request = httpx.Request("POST", "https://api.mdtero.com/api/v1/projects")
        response = httpx.Response(
            503,
            request=request,
            json={
                "detail": {
                    "error_code": "project_api_unavailable",
                    "reason_code": "project_api_unavailable",
                    "action_hint": "Project API is unavailable; retry after backend deploy.",
                    "next_commands": ["mdtero doctor", "mdtero rag status --json"],
                }
            },
        )
        raise httpx.HTTPStatusError("service unavailable", request=request, response=response)

    monkeypatch.setattr(MdteroClient, "create_project", fake_create)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_build(type("Args", (), {"project_id": None, "json": True})()) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "rag_build"
    assert payload["reason_code"] == "project_api_unavailable"
    assert payload["action_hint"] == "Project API is unavailable; retry after backend deploy."
    assert payload["next_commands"] == ["mdtero doctor", "mdtero rag status --json"]


def test_rag_project_errors_prefer_cli_bootstrap_commands():
    from mdtero import cli

    hint = cli._rag_action_hint("status", "project_not_found")
    commands = cli._rag_failure_next_commands("status", "invalid_project_id")

    assert "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json" in hint
    assert "--build-if-needed" in hint
    assert "mdtero project create-server" not in hint
    assert commands == [
        "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json",
        "mdtero rag status --json",
        "mdtero rag build --wait --json",
        "mdtero rag query \"<question>\" --build-if-needed --json",
    ]


def test_rag_query_unlinked_project_plain_output_is_actionable(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_query(type("Args", (), {"project_id": None, "question": "demo", "json": False})()) == 1
    output = capsys.readouterr().out

    assert "RAG query not ready: server_project_not_linked" in output
    assert "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json" in output
    assert "mdtero project ingest" not in output
    assert "mdtero rag query \"<question>\"" in output


def test_rag_query_build_if_needed_bootstraps_then_queries(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))
    calls = []

    def fake_create(self, name, *, description=None):
        calls.append(("create", name, description))
        return {"id": 42, "name": name}

    def fake_import(self, project_id, task_id):
        calls.append(("import", project_id, task_id))
        return {"document_id": "doc-1", "import_status": "imported"}

    def fake_build(self, project_id):
        calls.append(("build", project_id))
        return {"status": "ready", "reason_code": "indexed"}

    def fake_query(self, project_id, question):
        calls.append(("query", project_id, question))
        return {"status": "succeeded", "reason_code": "ok", "answer": "Ready.", "matches": []}

    monkeypatch.setattr(MdteroClient, "create_project", fake_create)
    monkeypatch.setattr(MdteroClient, "import_task_to_project", fake_import)
    monkeypatch.setattr(MdteroClient, "rag_build", fake_build)
    monkeypatch.setattr(MdteroClient, "rag_query", fake_query)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_query(type("Args", (), {"project_id": None, "question": "What is ready?", "build_if_needed": True, "json": True})()) == 0
    payload = json.loads(capsys.readouterr().out)
    state = load_project(tmp_path)

    assert payload["status"] == "succeeded"
    assert payload["answer"] == "Ready."
    assert payload["server_project_id"] == "42"
    assert payload["bootstrap"]["bootstrap"]["created_server_project"] is True
    assert payload["bootstrap"]["ingest"]["imported_count"] == 1
    assert payload["bootstrap"]["build"]["reason_code"] == "indexed"
    assert state.server_project_id == "42"
    assert calls == [
        ("create", "local-demo", "Mdtero local project: local-demo"),
        ("import", "42", "task-done"),
        ("build", "42"),
        ("query", "42", "What is ready?"),
    ]


def test_rag_query_build_if_needed_returns_bootstrap_context_when_query_not_ready(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    def fake_create(self, name, *, description=None):
        return {"id": 42, "name": name}

    def fake_import(self, project_id, task_id):
        return {"document_id": "doc-1", "import_status": "imported"}

    def fake_build(self, project_id):
        return {"status": "queued", "reason_code": "rag_build_queued"}

    def fake_status(self, project_id):
        return {"status": "waiting", "reason_code": "rag_index_not_built", "next_commands": ["mdtero rag status --json"]}

    def fake_query(self, project_id, question):  # pragma: no cover - should not query until RAG is ready
        raise AssertionError("query should not run before RAG status is ready")

    monkeypatch.setattr(MdteroClient, "create_project", fake_create)
    monkeypatch.setattr(MdteroClient, "import_task_to_project", fake_import)
    monkeypatch.setattr(MdteroClient, "rag_build", fake_build)
    monkeypatch.setattr(MdteroClient, "rag_status", fake_status)
    monkeypatch.setattr(MdteroClient, "rag_query", fake_query)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_query(type("Args", (), {"project_id": None, "question": "What is ready?", "build_if_needed": True, "timeout": 0.01, "interval": 0.01, "json": True})()) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "rag_query"
    assert payload["reason_code"] == "rag_index_not_built"
    assert payload["server_project_id"] == "42"
    assert payload["bootstrap"]["ingest"]["imported_count"] == 1
    assert payload["bootstrap"]["build"]["reason_code"] == "rag_build_queued"
    assert payload["bootstrap"]["status_after_build"]["reason_code"] == "rag_index_not_built"
    assert payload["status_after_build"]["reason_code"] == "rag_index_not_built"
    assert payload["next_commands"] == ["mdtero rag status --json", "mdtero rag query \"What are the strongest findings?\" --build-if-needed --json", "mdtero rag build --wait --json", "mdtero rag query \"<question>\" --build-if-needed --json"]


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
    assert paper.zotero_key == "ABC"


def test_zotero_sync_creates_note_for_succeeded_zotero_papers():
    class FakeZoteroClient:
        def __init__(self):
            self.created = []

        def create_items(self, items):
            self.created.append(items)
            return {"successful": {"0": {"key": "NOTE1"}}}

    papers = [
        PaperRecord(
            input="10.1000/zotero",
            title="A paper",
            task_id="task-1",
            status="succeeded",
            source="zotero",
            artifact="paper_md",
            provider="arxiv",
            parser_strategy="arxiv_native",
            zotero_key="ABC",
        ),
        PaperRecord(input="10.1000/pending", status="pending", source="zotero", zotero_key="DEF"),
        PaperRecord(input="10.1000/manual", status="succeeded", task_id="task-2", source="manual"),
    ]
    client = FakeZoteroClient()

    summary = sync_project_to_zotero(client, papers)

    assert summary["synced_count"] == 1
    assert summary["skipped_count"] == 2
    assert papers[0].zotero_synced_task_id == "task-1"
    assert client.created[0][0]["parentItem"] == "ABC"
    assert "Mdtero parse status" in client.created[0][0]["note"]
    assert {tag["tag"] for tag in client.created[0][0]["tags"]} == {"mdtero", "mdtero:succeeded"}


def test_zotero_sync_note_contains_download_command():
    paper = PaperRecord(input="10.1000/zotero", task_id="task-1", status="succeeded", source="zotero", zotero_key="ABC")

    note = build_sync_note(paper)

    assert note["itemType"] == "note"
    assert note["parentItem"] == "ABC"
    assert "mdtero download" in note["note"]


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


def test_workflow_trace_marks_completed_client_acquisition():
    trace = parse_trace_from_route(
        "10.1000/demo",
        {
            "route_kind": "browser_capture_required",
            "acquisition_mode": "native_source_adapter",
            "requires_raw_upload": False,
            "action_sequence": ["fetch_remote_html"],
        },
        {
            "task_id": "task-local",
            "client_acquisition": {
                "source": "curl_cffi",
                "artifact_kind": "html",
                "url": "https://example.test/paper",
                "status_code": 200,
            },
        },
    ).to_dict()

    assert [step["name"] for step in trace["steps"]] == ["route", "client_acquire_raw", "upload_raw"]
    assert trace["steps"][1]["metadata"]["source"] == "curl_cffi"


def test_python_agent_installer_writes_packaged_skill_without_npm(tmp_path: Path):
    results = install_targets(["codex"], root=tmp_path)
    skill_path = tmp_path / ".codex" / "skills" / "mdtero" / "SKILL.md"

    assert results[0].target == "codex"
    assert results[0].action == "installed"
    assert skill_path.exists()
    skill_text = skill_path.read_text(encoding="utf-8")
    assert "uv tool install mdtero" in skill_text
    assert "uv tool install git+https://github.com/JonbinC/doi2md.git" in skill_text


def test_python_agent_installer_detects_and_uninstalls_targets(tmp_path: Path):
    (tmp_path / ".hermes").mkdir()

    detected = detect_targets(tmp_path)
    results = install_targets(root=tmp_path)
    removed = uninstall_targets(["hermes"], root=tmp_path)

    assert [target.name for target in detected] == ["hermes"]
    assert results[0].target == "hermes"
    assert removed[0].action == "removed"
    assert not (tmp_path / ".hermes" / "skills" / "mdtero").exists()


def test_agent_detect_command_returns_machine_readable_workspace_status(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    (tmp_path / ".codex").mkdir()
    install_targets(["codex"], root=tmp_path)
    (tmp_path / ".hermes").mkdir()

    statuses = detect_target_status(tmp_path)
    codex_status = next(item for item in statuses if item.target == "codex")
    hermes_status = next(item for item in statuses if item.target == "hermes")

    assert codex_status.detected is True
    assert codex_status.installed is True
    assert codex_status.install_command == "mdtero agent install --target codex"
    assert hermes_status.detected is True
    assert hermes_status.installed is False

    assert cli.cmd_agent_detect(type("Args", (), {"root": tmp_path, "json": True})()) == 0
    payload = json.loads(capsys.readouterr().out)
    by_target = {item["target"]: item for item in payload}

    assert by_target["codex"]["detected"] is True
    assert by_target["codex"]["installed"] is True
    assert by_target["hermes"]["detected"] is True
    assert by_target["hermes"]["installed"] is False
    assert by_target["opencode"]["install_command"] == "mdtero agent install --target opencode"
    assert by_target["codex"]["selection_index"] == 1


def test_agent_interactive_selection_defaults_to_detected_pending_targets(tmp_path: Path):
    (tmp_path / ".codex").mkdir()
    install_targets(["codex"], root=tmp_path)
    (tmp_path / ".hermes").mkdir()

    statuses = detect_target_status(tmp_path)

    assert default_interactive_targets(statuses) == ["hermes"]
    assert parse_agent_selection("", statuses) == ["hermes"]
    assert parse_agent_selection("1 4", statuses) == ["codex", "hermes"]
    assert parse_agent_selection("codex,opencode", statuses) == ["codex", "opencode"]
    assert parse_agent_selection("all", statuses) == ["codex", "claude_code", "gemini_cli", "hermes", "opencode"]


def test_agent_install_interactive_uses_prompted_multi_select(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    (tmp_path / ".codex").mkdir()
    (tmp_path / ".hermes").mkdir()
    monkeypatch.setattr("mdtero.cli.Prompt.ask", lambda *args, **kwargs: "1 4")

    args = type("Args", (), {"target": None, "root": tmp_path, "all": False, "dry_run": True, "json": True, "interactive": True})()

    assert cli.cmd_agent_install(args) == 0
    payload = json.loads(capsys.readouterr().out)

    assert [item["target"] for item in payload] == ["codex", "hermes"]
    assert all(item["action"] == "would_install" for item in payload)


def test_public_install_manifest_is_python_runtime_only_and_mirrored_with_site():
    repo_root = Path(__file__).resolve().parents[1]
    manifest = json.loads((repo_root / "install" / "manifest.json").read_text(encoding="utf-8"))
    site_manifest = json.loads((repo_root.parent / "nextmdtero" / "public" / "install" / "manifest.json").read_text(encoding="utf-8"))
    package_version = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]

    assert manifest == site_manifest
    assert manifest["quickInstallCommand"] == "uv tool install mdtero && mdtero setup"
    assert manifest["alphaFallbackInstallCommand"] == "uv tool install git+https://github.com/JonbinC/doi2md.git"
    assert manifest["cli"]["packageName"] == "mdtero"
    assert manifest["cli"]["packageVersion"] == package_version
    assert manifest["releaseTruth"]["current"]["cli"]["version"] == package_version
    assert manifest["cli"]["packageManager"] == "uv"
    assert manifest["cli"]["runtimeInstallCommand"] == "uv tool install mdtero"
    assert manifest["cli"]["runtimeFallbackInstallCommand"] == "uv tool install git+https://github.com/JonbinC/doi2md.git"
    assert manifest["cli"]["skillInstallCommand"] == "mdtero agent install --target <target>"
    assert manifest["cliCommand"] == "mdtero"
    assert "helperCommand" not in manifest
    assert "legacyNpmCompatibility" not in json.dumps(manifest)
    assert "mdtero-install" not in json.dumps(manifest)


def test_public_docs_do_not_advertise_npm_installer_runtime():
    repo_root = Path(__file__).resolve().parents[1]
    docs = [
        repo_root / "README.md",
        repo_root / "install" / "README.md",
        repo_root / "docs" / "public" / "README.md",
    ]
    for path in docs:
        content = path.read_text(encoding="utf-8")
        assert "mdtero-install" not in content
        assert "npx mdtero" not in content
        assert "npm install -g" not in content
        assert "npm is legacy" not in content
        assert "legacy compatibility only" not in content


def test_public_repo_has_no_root_npm_or_per_agent_install_runtime():
    repo_root = Path(__file__).resolve().parents[1]

    assert not (repo_root / "package.json").exists()
    assert not (repo_root / "package-lock.json").exists()
    assert not (repo_root / "npm-shrinkwrap.json").exists()

    retired_install_docs = sorted((repo_root / "skills").glob("*/INSTALL.md"))
    assert retired_install_docs == []

    install_script = (repo_root / "install.sh").read_text(encoding="utf-8")
    assert "uv tool install mdtero" in install_script
    assert "uv tool install git+https://github.com/JonbinC/doi2md.git" in install_script
    assert "mdtero agent install --target" in install_script
    assert "npm" not in install_script.lower()
    assert "npx" not in install_script.lower()


def test_public_script_surface_is_ci_only():
    repo_root = Path(__file__).resolve().parents[1]
    expected = {
        "scripts/ci/extension_dist_smoke.py",
        "scripts/ci/forgejo-remote-doctor.sh",
        "scripts/ci/forgejo_workflow_policy.py",
        "scripts/ci/private_platform_preflight.sh",
        "scripts/ci/release_gate.sh",
        "scripts/ci/secret_guard.py",
    }
    actual = {
        path.relative_to(repo_root).as_posix()
        for path in (repo_root / "scripts").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }

    assert actual == expected

    forbidden_names = {
        "mdtero-install",
        "install-mdtero-agent",
        "native-host",
        "browser-bridge",
        "helper-bundle",
    }
    install_surface = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [repo_root / "install.sh", repo_root / "install" / "README.md", repo_root / "install" / "manifest.json"]
    ).lower()
    for forbidden in forbidden_names:
        assert forbidden not in install_surface


def test_public_github_ci_matches_release_gate_for_extension_quality():
    repo_root = Path(__file__).resolve().parents[1]
    workflow = (repo_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "node-version: 22" in workflow
    assert "npm ci" in workflow
    assert "npm audit --audit-level=moderate" in workflow
    assert "npm test -- --run" in workflow
    assert "npm run build" in workflow
    assert "python3 scripts/ci/extension_dist_smoke.py" in workflow


def test_forgejo_phase_one_workflow_is_manual_lightweight_and_private():
    repo_root = Path(__file__).resolve().parents[1]
    workflow = (repo_root / ".forgejo" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    production_smoke = (repo_root / ".forgejo" / "workflows" / "production-smoke.yml").read_text(encoding="utf-8")
    runbook = (repo_root / "PRIVATE_PLATFORM_PHASE_1.md").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "check_scope:" in workflow
    assert "platform_preflight:" in workflow
    assert 'default: "smoke"' in workflow
    assert "Public smoke gate" in workflow
    assert "Optional private platform preflight" in workflow
    assert "List required secret names" in workflow
    assert "Forgejo secrets used by this workflow: none." in workflow
    assert "scripts/ci/private_platform_preflight.sh" in workflow
    assert "runs-on: linux-small" in workflow
    assert "timeout-minutes: 10" in workflow
    assert "timeout-minutes: 20" in workflow
    assert "test_forgejo_phase_one_workflow_is_manual_lightweight_and_private" in workflow
    assert "if: ${{ inputs.check_scope == 'full' }}" in workflow
    assert "\n  push:" not in workflow
    assert "\n  pull_request:" not in workflow
    assert "INFISICAL_TOKEN=" not in workflow
    assert "PAT=" not in workflow
    assert "PERSONAL_ACCESS_TOKEN" not in workflow

    assert "name: Public Production Smoke" in production_smoke
    assert "workflow_dispatch:" in production_smoke
    assert "auth_smoke:" in production_smoke
    assert "smoke_scope:" in production_smoke
    assert "auth_smoke=skip" in production_smoke
    assert "List required secret names" in production_smoke
    assert "MDTERO_API_KEY: optional; required only when auth_smoke=check." in production_smoke
    assert "Secret values are never printed by this workflow." in production_smoke
    assert "secrets.MDTERO_API_KEY" in production_smoke
    assert "auth_smoke=check requires Forgejo secret MDTERO_API_KEY" in production_smoke
    assert "uv run --project" in production_smoke
    assert "mdtero smoke" in production_smoke
    assert "--skip-translate" in production_smoke
    assert "mktemp -d" in production_smoke
    assert "rm -rf \"$smoke_root\"" in production_smoke
    assert "runs-on: linux-small" in production_smoke
    assert "timeout-minutes: 20" in production_smoke
    assert "\n  push:" not in production_smoke
    assert "\n  pull_request:" not in production_smoke
    assert "INFISICAL_TOKEN=" not in production_smoke
    assert "PAT=" not in production_smoke
    assert "PERSONAL_ACCESS_TOKEN" not in production_smoke

    assert "forgejo`: `http://100.97.234.105:3020/jianbin/doi2md.git`" in runbook
    assert "Do not embed PATs, service tokens, or passwords" in runbook
    assert "platform_preflight=check" in runbook
    assert "Each workflow lists the Forgejo secret names it may use, but must not print secret values." in runbook
    assert "scripts/ci/private_platform_preflight.sh" in runbook
    assert "does not read provider secrets, deploy, publish, or print credentials" in runbook
    assert "Actions API endpoint may return `404 page not found`" in runbook
    assert "Trigger `workflow_dispatch` from Forgejo Web" in runbook
    assert "Manual smoke evidence" in runbook
    assert "Workflow: `Public CLI and Extension CI`" in runbook
    assert "Inputs: `check_scope=smoke`, `platform_preflight=check`" in runbook
    assert "public_private_platform_preflight: status=ok" in runbook
    assert "public_private_platform_preflight: status=ok remote=forgejo extension_tests=ok extension_dist=ok" in runbook
    assert "run the same workflow with `check_scope=full` after the smoke run passes" in runbook
    assert "Workflow: `Public Production Smoke`" in runbook
    assert "auth_smoke=check" in runbook
    assert "Required secret name for authenticated smoke: `MDTERO_API_KEY`" in runbook
    assert "smoke_scope=core" in runbook
    assert "smoke_scope=full" in runbook
    assert "Missing `MDTERO_API_KEY` exits with code `78`" in runbook
    assert "read them from Infisical at runtime through a service token or machine identity" in runbook
    assert "Do not remove GitHub or PyPI/public release paths" in runbook


def test_public_private_platform_preflight_is_non_secret_and_non_deploying():
    repo_root = Path(__file__).resolve().parents[1]
    preflight = (repo_root / "scripts" / "ci" / "private_platform_preflight.sh").read_text(encoding="utf-8")

    assert "MDTERO_FORGEJO_REMOTE:-forgejo" in preflight
    assert "http://100.97.234.105:3020/*" in preflight
    assert "scripts/ci/forgejo-remote-doctor.sh" in preflight
    assert '"$python_bin" scripts/ci/secret_guard.py' in preflight
    assert '"$python_bin" scripts/ci/forgejo_workflow_policy.py' in preflight
    assert "npm --prefix extension test -- --run" in preflight
    assert '"$python_bin" scripts/ci/extension_dist_smoke.py >/dev/null' in preflight
    assert "status=ok" in preflight
    assert "forgejo_policy=ok" in preflight
    assert "INFISICAL_TOKEN" not in preflight
    assert "docker" not in preflight
    assert "uv build" not in preflight
    assert "twine" not in preflight
    assert "set -x" not in preflight


def test_public_forgejo_workflow_policy_enforces_manual_linux_small_secret_listing(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    policy = load_python_script(repo_root / "scripts" / "ci" / "forgejo_workflow_policy.py")

    workflow_dir = tmp_path / ".forgejo" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ok.yml").write_text(
        """
name: OK
on:
  workflow_dispatch:
jobs:
  smoke:
    runs-on: linux-small
    steps:
      - name: List required secret names
        run: |
          echo "Forgejo secrets used by this workflow: none."
""".strip(),
        encoding="utf-8",
    )
    assert policy.check_all(tmp_path) == {}

    (workflow_dir / "bad.yml").write_text(
        """
name: Bad
on:
  push:
  schedule:
    - cron: "0 0 * * *"
jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - run: echo ADMIN_PASSWORD: demo
""".strip(),
        encoding="utf-8",
    )
    failures = policy.check_all(tmp_path)
    assert failures[".forgejo/workflows/bad.yml"] == [
        "missing workflow_dispatch",
        "not workflow_dispatch-only",
        "missing linux-small runner",
        "missing secret-name listing step",
        "missing Forgejo secret-name summary",
        "push-trigger",
        "schedule-trigger",
        "cron-trigger",
        "admin-credential",
    ]


def test_public_generated_dependency_and_package_artifacts_are_not_source():
    repo_root = Path(__file__).resolve().parents[1]

    ignored = (repo_root / ".gitignore").read_text(encoding="utf-8")
    for marker in ["dist/", "extension/node_modules/", "extension/.vite/", "extension/.vitest/"]:
        assert marker in ignored

    tracked = subprocess.run(
        ["git", "ls-files", "dist", "node_modules", "extension/node_modules", "extension/.vite", "extension/.vitest"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert tracked == []

    # The checked-in MV3 bundle is intentionally kept as the browser-extension release artifact.
    assert (repo_root / "extension" / "dist" / "manifest.json").exists()


def test_extension_dist_smoke_script_covers_shipping_mv3_bundle(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    run_smoke = load_python_script(repo_root / "scripts" / "ci" / "extension_dist_smoke.py").run_smoke

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    for relative in [
        "background.js",
        "content.js",
        "popup.html",
        "popup.js",
        "options.html",
        "options.js",
        "styles.css",
        "assets/icon-16.png",
        "assets/icon-32.png",
        "assets/icon-48.png",
        "assets/icon-128.png",
    ]:
        path = dist / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    (dist / "manifest.json").write_text(json.dumps({
        "manifest_version": 3,
        "permissions": ["storage", "downloads", "tabs"],
        "host_permissions": ["https://api.mdtero.com/*"],
        "background": {"service_worker": "background.js"},
        "action": {"default_popup": "popup.html"},
        "options_page": "options.html",
        "content_scripts": [{"matches": ["https://mdtero.com/*"], "js": ["content.js"]}],
    }), encoding="utf-8")
    (dist / "popup.html").write_text("Website OAuth Parse / Upload Translate Download local-file-input copy-cli-handoff mdtero parse", encoding="utf-8")
    (dist / "popup.js").write_text("/api/v1/tasks/translate /api/v1/tasks/upload /download/", encoding="utf-8")
    (dist / "options.html").write_text(
        "Website sign-in Connection guide CLI setup checklist Website OAuth is connected FastMCP stdio mcpServers",
        encoding="utf-8",
    )
    (dist / "options.js").write_text(
        "browser capture, upload, translation, and download settings mdtero setup --json mdtero agent install --interactive mdtero mcp serve",
        encoding="utf-8",
    )

    payload = run_smoke(dist)

    assert payload["status"] == "succeeded"
    assert payload["reason_code"] == "extension_dist_smoke_succeeded"


def test_extension_dist_smoke_rejects_retired_helper_and_native_runtime(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    run_smoke = load_python_script(repo_root / "scripts" / "ci" / "extension_dist_smoke.py").run_smoke

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "manifest.json").write_text(json.dumps({
        "manifest_version": 3,
        "permissions": ["storage", "downloads", "tabs", "nativeMessaging"],
        "background": {"service_worker": "background.js"},
        "action": {"default_popup": "popup.html"},
        "options_page": "options.html",
        "content_scripts": [],
    }), encoding="utf-8")
    (dist / "background.js").write_text("connectNative fetch_helper_source", encoding="utf-8")

    payload = run_smoke(dist)

    assert payload["status"] == "failed"
    reason_codes = {failure["reason_code"] for failure in payload["failures"]}
    assert "extension_native_messaging_present" in reason_codes
    assert "extension_forbidden_marker_present" in reason_codes
    assert "extension_dist_file_missing" in reason_codes


def test_extension_contract_prefers_browser_source_over_retired_helper_action():
    repo_root = Path(__file__).resolve().parents[1]
    shared_contract = (repo_root / "shared" / "src" / "api-contract.ts").read_text(encoding="utf-8")
    ssot_tests = (repo_root / "extension" / "tests" / "ssot-route.test.ts").read_text(encoding="utf-8")
    background_tests = (repo_root / "extension" / "tests" / "background.test.ts").read_text(encoding="utf-8")
    action_executor = (repo_root / "extension" / "src" / "lib" / "action-executor.ts").read_text(encoding="utf-8")

    assert '"fetch_browser_source"' in shared_contract
    assert '"fetch_helper_source"' not in shared_contract
    assert '"fetch_elsevier_xml"' not in shared_contract
    assert '"fetch_wiley_tdm_pdf"' not in shared_contract
    assert '"fetch_springer_pdf"' not in shared_contract
    assert "requiresBrowserCapture?: boolean" in shared_contract
    assert "requiresHelper?: boolean" not in shared_contract
    assert 'action_sequence: ["fetch_browser_source"]' in ssot_tests
    assert 'action_sequence: ["fetch_browser_source"]' in background_tests
    assert 'route_kind: "browser_capture_required"' in ssot_tests
    assert 'route_kind: "browser_capture_required"' in background_tests
    assert "browser_capture_first" not in ssot_tests
    assert "browser_capture_first" not in background_tests
    assert 'fetch_helper_source' not in ssot_tests
    assert "html_helper_first" not in ssot_tests
    assert "requiresHelper" not in ssot_tests
    assert "RETIRED_PUBLISHER_ACTIONS" not in action_executor
    assert "elsevier_article_retrieval_api" not in action_executor
    assert "fetch_elsevier_xml" not in action_executor
    assert "fetch_wiley_tdm_pdf" not in action_executor
    assert "fetch_springer_pdf" not in action_executor


def test_extension_dist_smoke_rejects_retired_publisher_action_names(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    run_smoke = load_python_script(repo_root / "scripts" / "ci" / "extension_dist_smoke.py").run_smoke

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    for relative in [
        "background.js",
        "content.js",
        "popup.html",
        "popup.js",
        "options.html",
        "options.js",
        "styles.css",
        "assets/icon-16.png",
        "assets/icon-32.png",
        "assets/icon-48.png",
        "assets/icon-128.png",
    ]:
        path = dist / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    (dist / "manifest.json").write_text(json.dumps({
        "manifest_version": 3,
        "permissions": ["storage", "downloads", "tabs"],
        "host_permissions": ["https://api.mdtero.com/*"],
        "background": {"service_worker": "background.js"},
        "action": {"default_popup": "popup.html"},
        "options_page": "options.html",
        "content_scripts": [{"matches": ["https://mdtero.com/*"], "js": ["content.js"]}],
    }), encoding="utf-8")
    (dist / "popup.html").write_text("Website OAuth Parse / Upload Translate Download local-file-input copy-cli-handoff mdtero parse", encoding="utf-8")
    (dist / "popup.js").write_text("/api/v1/tasks/translate /api/v1/tasks/upload /download/", encoding="utf-8")
    (dist / "options.html").write_text("Website sign-in Connection guide Website OAuth is connected", encoding="utf-8")
    (dist / "options.js").write_text("browser capture, upload, translation, and download settings fetch_elsevier_xml", encoding="utf-8")

    payload = run_smoke(dist)

    assert payload["status"] == "failed"
    assert any(
        failure.get("marker") == "fetch_elsevier_xml" and failure.get("reason_code") == "extension_forbidden_marker_present"
        for failure in payload["failures"]
    )


def test_public_docs_describe_rag_answer_citation_contract():
    repo_root = Path(__file__).resolve().parents[1]
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [repo_root / "README.md", repo_root / "install" / "README.md", repo_root / "docs" / "public" / "README.md"]
    )

    assert "RAG query" in combined
    assert "answer" in combined
    assert "citations" in combined
    assert "matches" in combined
    assert "source_nodes" in combined
    assert "evidence_pack.context_markdown" in combined
    assert "citation_contract.required_for_final_answer" in combined
    assert "preserve `citations` plus `source_nodes`" in combined
    assert "next_commands" in combined
    assert "primary_failure" in combined
    assert "failed_steps" in combined


def test_public_readme_documents_shared_v1_api_contract():
    repo_root = Path(__file__).resolve().parents[1]
    readme = (repo_root / "README.md").read_text(encoding="utf-8")

    assert "Shared `/api/v1` server contract" in readme
    assert "/api/v1/route" in readme
    assert "/api/v1/tasks/parse" in readme
    assert "/api/v1/tasks/upload" in readme
    assert "/api/v1/tasks/{task_id}" in readme
    assert "/api/v1/tasks/{task_id}/download/{artifact}" in readme
    assert "/api/v1/projects/{project_id}/tasks/{task_id}/import" in readme
    assert "/api/v1/projects/{project_id}/rag/build" in readme
    assert "/api/v1/projects/{project_id}/rag/query" in readme
    assert "The CLI, extension, dashboard, and MCP briefing expose this contract" in readme
    assert "所有输入入口共用同一组 `/api/v1` 服务端契约" in readme
    assert "CLI、扩展、dashboard 和 MCP briefing 都会暴露这组 contract" in readme


def test_public_docs_and_skills_describe_mcp_tool_plan_contract():
    repo_root = Path(__file__).resolve().parents[1]
    combined_docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [repo_root / "README.md", repo_root / "install" / "README.md", repo_root / "docs" / "public" / "README.md"]
    )
    combined_skills = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [repo_root / "skills" / "mdtero" / "SKILL.md", repo_root / "src" / "mdtero" / "skills" / "mdtero" / "SKILL.md"]
    )

    for content in [combined_docs, combined_skills]:
        assert "mcp_tool_plan" in content
        assert "dashboard_handoff_json" in content
        assert "project_init" in content
        assert "project_add" in content
        assert "submit_parse" in content
        assert "task_status" in content
        assert "download_artifact" in content
        assert "request_translation" in content
        assert "server_rag_status" in content
        assert "rag_query" in content
        assert "citation_contract.required_for_final_answer" in content
        assert "failure_fields" in content
        assert "reason_code" in content
        assert "action_hint" in content
        assert "next_commands" in content
    assert "step" in combined_docs
    assert "success_signal" in combined_docs
    assert "本地 agent" in combined_docs
    assert "Use the `mcp_tool_plan` steps" in combined_skills
    assert "copied task handoff JSON" in combined_skills
    assert "client_acquisition" in combined_skills
    assert "parse_outcome" in combined_skills
    assert "readiness" in combined_skills


def test_production_smoke_documents_latest_arxiv_voyage_rag_path():
    repo_root = Path(__file__).resolve().parents[1]
    report = (repo_root / "docs" / "public" / "PRODUCTION_SMOKE_2026-05-24.md").read_text(encoding="utf-8")

    assert "Latest ArXiv + Voyage RAG Re-Smoke" in report
    assert "route_kind=source_first" in report
    assert "provider_id=arxiv" in report
    assert "server project `13`" in report
    assert "embedding_model=voyage-4" in report
    assert "chunk_count=39" in report
    assert "embedded_count=39" in report
    assert "reason_code=rag_query_succeeded" in report
    assert "citation_count=5" in report
    assert "match_count=5" in report
    assert "202 passed" in report
    assert "138 passed" in report
    assert "248 passed" in report
    assert "101 passed" in report
    assert "npm run smoke:routes -- --base-url <production-url> --json" in report
    assert "Production Read-Only Recheck - 2026-05-26 UTC" in report
    assert "backend_production_smoke_succeeded" in report
    assert "deployment_state=current" in report
    assert "returned `401`, which is the expected unauthenticated response" in report
    assert "stale build that returned `404`" in report
    assert "/docs/zh/install.html" in report
    assert "forgejo_policy=ok" in report


def test_release_readiness_matrix_separates_proven_and_post_deploy_smoke():
    repo_root = Path(__file__).resolve().parents[1]
    readiness = (repo_root / "docs" / "public" / "RELEASE_READINESS_2026-05-24.md").read_text(encoding="utf-8")
    proven_section = readiness.split("## Requires Post-Deploy Smoke", 1)[0]
    post_deploy_section = readiness.split("## Requires Post-Deploy Smoke", 1)[1].split("## Not Public Product Scope", 1)[0]
    retired_scope_section = readiness.split("## Not Public Product Scope", 1)[1]

    assert "## Proven Ready" in readiness
    assert "## Requires Post-Deploy Smoke" in readiness
    assert "## Not Public Product Scope" in readiness
    assert "Public Python/uv CLI as the main runtime" in proven_section
    assert "PDF upload through MinerU URL API" in proven_section
    assert "Server-side Voyage RAG" in proven_section
    assert "Browser extension scoped to v1 product" in proven_section
    assert "extension dist smoke passed" in proven_section
    assert "Backend read-only production freshness" in proven_section
    assert "Forgejo manual CI smoke policy" in proven_section
    assert "unauthenticated `/diagnostics/translation/providers` returned the expected 401 instead of stale 404" in proven_section
    assert "workflow_dispatch" in proven_section
    assert "Translation provider health" in post_deploy_section
    assert "Browser extension interactive flow" in post_deploy_section
    assert "/docs/zh/install.html" in post_deploy_section
    assert "The backend diagnostics route is now deployed" in post_deploy_section
    assert "returns 401" in post_deploy_section
    assert "authenticated diagnostics check or successful translation task" in post_deploy_section
    assert "Current production `GET /diagnostics/translation/providers` returns `404`" not in post_deploy_section
    assert "npm run smoke:routes -- --base-url <production-url> --json" in post_deploy_section

    for retired_marker in [
        "npm runtime CLI",
        "Native browser bridge",
        "Public GROBID engine selection",
        "Backend-local copies of the public CLI/TUI/Zotero/RAG/MCP client runtime",
    ]:
        assert retired_marker in retired_scope_section
        assert retired_marker not in proven_section
        assert retired_marker not in post_deploy_section


def test_public_docs_describe_agent_safe_redaction_boundary():
    repo_root = Path(__file__).resolve().parents[1]
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            repo_root / "README.md",
            repo_root / "install" / "README.md",
            repo_root / "docs" / "public" / "README.md",
            repo_root / "skills" / "mdtero" / "SKILL.md",
            repo_root / "src" / "mdtero" / "skills" / "mdtero" / "SKILL.md",
        ]
    )

    assert "agent-facing CLI JSON and MCP payloads sanitize signed MinerU/OSS URLs" in combined
    assert "bearer/API-key headers" in combined
    assert "Mdtero API keys" in combined
    assert "common token query parameters" in combined
    assert "reason_code" in combined
    assert "action_hint" in combined
    assert "next_commands" in combined
    assert "do not ask users to paste long-lived secrets into prompts" in combined
    assert "面向 agent 的 CLI JSON 和 MCP payload" in combined
    assert "signed MinerU/OSS URL" in combined
    assert "常见 token query 参数" in combined


def test_public_docs_and_skill_describe_extension_cli_handoff_contract():
    repo_root = Path(__file__).resolve().parents[1]
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            repo_root / "README.md",
            repo_root / "install" / "README.md",
            repo_root / "docs" / "public" / "README.md",
            repo_root / "skills" / "mdtero" / "SKILL.md",
            repo_root / "src" / "mdtero" / "skills" / "mdtero" / "SKILL.md",
        ]
    )

    assert "Extension-to-CLI handoff" in combined
    assert "扩展到 CLI 的交接" in combined
    assert "publisher challenge" in combined
    assert "campus-network/session-bound access" in combined
    assert "校园网/登录态" in combined
    assert "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json" in combined
    assert "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json" in combined
    assert "mdtero status <task-id> --wait --timeout 300 --json" in combined
    assert "mdtero download <task-id> paper_md --output-dir ./mdtero-output --json" in combined
    assert "mdtero project ingest --json" in combined
    assert "mdtero rag query \"<question>\" --build-if-needed --json" in combined
    assert "mdtero mcp briefing --json" in combined
    assert "client_acquisition" in combined
    assert "raw upload" in combined
    assert "reason_code" in combined
    assert "action_hint" in combined
    assert "download_artifacts" in combined
    assert "next_commands" in combined


def test_public_docs_and_skills_use_agent_safe_discovery_add_json():
    repo_root = Path(__file__).resolve().parents[1]
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            repo_root / "README.md",
            repo_root / "install" / "README.md",
            repo_root / "skills" / "mdtero" / "SKILL.md",
            repo_root / "src" / "mdtero" / "skills" / "mdtero" / "SKILL.md",
        ]
    )

    assert "mdtero discover \"<query>\" --limit 5 --add --select 1,3 --json" in combined
    assert "mdtero discover \"thermochemical energy storage\" --limit 5 --add --select 1,3 --json" in combined
    assert "mdtero discover \"<query>\" --limit 5 --add --select 1,3`" not in combined
    assert "mdtero discover \"thermochemical energy storage\" --limit 5 --add --select 1,3\n" not in combined


def test_packaged_skill_guides_agents_to_structured_rag_evidence():
    repo_root = Path(__file__).resolve().parents[1]
    for path in [repo_root / "skills" / "mdtero" / "SKILL.md", repo_root / "src" / "mdtero" / "skills" / "mdtero" / "SKILL.md"]:
        content = path.read_text(encoding="utf-8")
        assert "evidence_pack.context_markdown" in content
        assert "source_nodes" in content
        assert "extractive summary" in content
        assert "grounded evidence" in content


def test_public_docs_and_skills_prefer_doctor_json_for_agents():
    repo_root = Path(__file__).resolve().parents[1]
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    skill_source = (repo_root / "skills" / "mdtero" / "SKILL.md").read_text(encoding="utf-8")
    packaged_skill = (repo_root / "src" / "mdtero" / "skills" / "mdtero" / "SKILL.md").read_text(encoding="utf-8")

    assert "mdtero doctor --json" in readme
    assert "safe auth/dependency/academic/Zotero/project/RAG summaries" in readme
    for skill in [skill_source, packaged_skill]:
        assert "Run `mdtero doctor --json` before parse" in skill
        assert "safe `next_commands` without echoing secrets" in skill
        assert "authenticated: true" in skill


def test_public_docs_and_skills_prefer_waiting_file_parse_for_agents():
    repo_root = Path(__file__).resolve().parents[1]
    docs = [
        repo_root / "README.md",
        repo_root / "install" / "README.md",
        repo_root / "skills" / "mdtero" / "SKILL.md",
        repo_root / "src" / "mdtero" / "skills" / "mdtero" / "SKILL.md",
    ]

    for path in docs:
        content = path.read_text(encoding="utf-8")
        assert "mdtero parse --file paper.pdf --trace --wait --timeout 600 --json" in content or "mdtero parse --file <paper.pdf|paper.html|paper.xml|paper.epub> --trace --wait --timeout 600 --json" in content or "mdtero parse --file <path> --trace --wait --timeout 600 --json" in content
    for path in [repo_root / "skills" / "mdtero" / "SKILL.md", repo_root / "src" / "mdtero" / "skills" / "mdtero" / "SKILL.md"]:
        content = path.read_text(encoding="utf-8")
        assert "mdtero parse --batch ./papers --wait --timeout 300 --json" in content
        assert "mdtero parse --file <path> --json" not in content
        assert "mdtero parse --file <paper.pdf|paper.html|paper.xml|paper.epub> --json" not in content
        assert "mdtero parse --batch ./papers --json" not in content


def test_public_docs_describe_setup_agent_detection_and_headless_skip():
    repo_root = Path(__file__).resolve().parents[1]
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [repo_root / "README.md", repo_root / "install" / "README.md"]
    )

    assert "`mdtero setup` handles login, optional academic-key configuration, and local agent workspace detection" in combined
    assert "detects local Codex/Claude/Gemini/Hermes/OpenCode workspaces" in combined
    assert "Headless setup with `mdtero setup --api-key --json` or `MDTERO_API_KEY`" in combined
    assert "mdtero setup --api-key --json" in combined
    assert "Do not put the API key value directly in shell history" in combined
    assert "mdtero setup --api-key <key>" not in combined
    assert "skips agent detection" in combined
    assert "mdtero agent install --interactive" in combined


def test_public_docs_keep_account_and_academic_key_boundaries_clear():
    repo_root = Path(__file__).resolve().parents[1]
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    boundary = readme.split("## Product Boundary", 1)[1].split("## Repo Map", 1)[0]

    assert "Mdtero Account is the control plane for Mdtero API keys, quota, billing, history, and install prompts" in boundary
    assert "Academic source keys stay in local `mdtero config academic` configuration" in boundary
    assert "diagnostics" not in boundary.lower()


def test_packaged_skill_template_is_available_to_python_installer():
    from importlib import resources

    skill = resources.files("mdtero.skills.mdtero").joinpath("SKILL.md").read_text(encoding="utf-8")

    assert "mdtero agent install" in skill
    assert "mdtero parse <doi-or-url>" in skill
    assert "mdtero doctor --json" in skill


def test_retired_per_agent_install_docs_are_removed():
    repo_root = Path(__file__).resolve().parents[1]
    retired_docs = [
        repo_root / "skills" / "codex" / "INSTALL.md",
        repo_root / "skills" / "claude_code" / "INSTALL.md",
        repo_root / "skills" / "gemini_cli" / "INSTALL.md",
        repo_root / "skills" / "hermes" / "INSTALL.md",
    ]
    for path in retired_docs:
        assert not path.exists(), str(path)

    skills_readme = (repo_root / "skills" / "README.md").read_text(encoding="utf-8")
    assert "Per-agent `INSTALL.md` copies are retired" in skills_readme
    assert "mdtero agent install --target <target>" in skills_readme


def test_source_and_packaged_agent_skill_templates_stay_in_sync():
    from importlib import resources

    repo_root = Path(__file__).resolve().parents[1]
    source_skill = (repo_root / "skills" / "mdtero" / "SKILL.md").read_text(encoding="utf-8")
    packaged_skill = resources.files("mdtero.skills.mdtero").joinpath("SKILL.md").read_text(encoding="utf-8")

    assert source_skill == packaged_skill
    assert "mdtero rag build --project-id" not in source_skill
    assert "mdtero mcp briefing --json" in source_skill
    assert "one-shot account/project/RAG handoff" in source_skill
    assert "mdtero project ingest" in source_skill
    assert "server_rag_status" in source_skill
    assert "rag_query(question)" in source_skill
    assert "mcp_tool_plan" in source_skill
    assert "submit_parse(input_value" in source_skill
    assert "task_status(task_id" in source_skill
    assert "download_artifact(task_id" in source_skill
    assert "request_translation(task_id_or_markdown_path" in source_skill
    assert "provider-attempt diagnostics" in source_skill
    assert "Prefer MCP tools for multi-step agent work" in source_skill
    assert "JSON responses include `next_commands`" in source_skill
    assert "preferred_artifact" in source_skill
    assert "evidence_pack.context_markdown" in source_skill
    assert "source_nodes" in source_skill
    assert "grounded evidence" in source_skill
