from __future__ import annotations

import json
import tomllib
import urllib.parse
from pathlib import Path

import httpx
from rich.console import Console

from mdtero.acquisition import AcquiredArtifact, AcquisitionError, acquire_from_route, should_acquire_locally
from mdtero.agent import default_interactive_targets, detect_target_status, detect_targets, install_targets, parse_agent_selection, uninstall_targets
from mdtero.auth import WebLoginResult, build_cli_login_url, run_web_login
from mdtero.cli import build_parser, _add_discovery_results_to_project, cmd_config_academic, _parse_academic_selection, _parse_result_selection
from mdtero.client import MdteroClient, translation_source_path_from_task
from mdtero.config import AcademicKeys, MdteroConfig, ZoteroConfig, load_config, save_config
from mdtero.mcp import build_agent_briefing, build_agent_commands, build_paper_context, build_project_status, build_rag_context, build_server_rag_status, query_server_rag, serve_project_context
from mdtero.core import artifacts_from_task_result, paper_from_task, provider_from_task_result
from mdtero.tui import build_dashboard_model, render_dashboard_text
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
from mdtero.workflow import parse_trace_from_route, status_trace, upload_trace
from mdtero.zotero import build_sync_note, paper_from_zotero_item, sync_project_to_zotero


def mock_doctor_remote_auth_ok(monkeypatch):
    from mdtero import cli

    monkeypatch.setattr(
        cli,
        "_doctor_remote_auth",
        lambda cfg: {"status": "ok", "email": "user@example.com", "wallet_balance_display": "$0.00"}
        if cfg.is_authenticated
        else {
            "status": "missing",
            "action_hint": "Authenticate with `mdtero login --api-key <key>` or run `mdtero setup`.",
            "next_commands": ["mdtero setup", "mdtero login --api-key <key>"],
        },
    )


def test_parser_exposes_next_gen_command_contract():
    parser = build_parser()
    help_text = parser.format_help()
    for command in ["setup", "doctor", "login", "config", "parse", "discover", "project", "parse-bib", "zotero", "translate", "rag", "mcp", "agent", "tui"]:
        assert command in help_text


def test_setup_accepts_headless_api_key_argument():
    parser = build_parser()

    args = parser.parse_args(["setup", "--api-key", "mdt_live_demo"])

    assert args.api_key == "mdt_live_demo"


def test_login_accepts_web_login_flags():
    parser = build_parser()

    args = parser.parse_args(["login", "--no-browser", "--timeout", "12"])

    assert args.no_browser is True
    assert args.timeout == 12


def test_wait_commands_accept_timeout_and_interval_flags():
    parser = build_parser()

    parse_args = parser.parse_args(["parse", "10.1000/demo", "--wait", "--timeout", "5", "--interval", "0.5"])
    status_args = parser.parse_args(["status", "task-1", "--wait", "--timeout", "7", "--interval", "1.5"])
    project_parse_args = parser.parse_args(["project", "parse", "--wait", "--timeout", "9", "--interval", "2.5"])
    project_refresh_args = parser.parse_args(["project", "refresh", "--wait", "--timeout", "11", "--interval", "3.5"])

    assert parse_args.timeout == 5
    assert parse_args.interval == 0.5
    assert status_args.timeout == 7
    assert status_args.interval == 1.5
    assert project_parse_args.timeout == 9
    assert project_parse_args.interval == 2.5
    assert project_refresh_args.timeout == 11
    assert project_refresh_args.interval == 3.5


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
        response = httpx.post(
            query["cli_callback"][0],
            json={"state": query["cli_state"][0], "apiKey": "mdt_live_web", "prefix": "mdt_live"},
            timeout=5,
        )
        assert response.status_code == 200
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

    assert cli.cmd_login(type("Args", (), {"api_key": "", "timeout": 7, "no_browser": False})()) == 0
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

    assert cli.cmd_login(type("Args", (), {"api_key": "", "timeout": 7, "no_browser": True})()) == 0
    output = capsys.readouterr().out

    assert "loopback web-login URL" in output
    assert "mdtero login --api-key <key>" in output
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


def test_doctor_reports_unlinked_project_rag_bootstrap_hint(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    mock_doctor_remote_auth_ok(monkeypatch)
    save_config(MdteroConfig(api_key="mdt_live_config"))
    init_project(tmp_path, name="doctor-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_doctor(type("Args", (), {})()) == 0
    output = capsys.readouterr().out
    rows = cli._doctor_project_rows(tmp_path)

    assert "Server project" in output
    assert "not linked" in output
    assert "run mdtero rag build --json" in output
    assert ("RAG readiness", "not linked", "run mdtero rag build --json to create, bind, ingest, and build") in rows


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
            "next_commands": ["mdtero login --api-key <key>", "mdtero doctor --json"],
        },
    )

    assert cli.cmd_doctor(type("Args", (), {"json": True})()) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "invalid_auth"
    assert payload["authenticated"] is False
    assert payload["remote_auth"]["status_code"] == 401
    assert payload["checks"][0] == {"check": "API key", "status": "invalid", "detail": "authentication_required"}
    assert payload["next_commands"] == ["mdtero login --api-key <key>", "mdtero doctor --json"]


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


def test_setup_next_steps_cover_project_rag_zotero_and_agent_workflows(capsys):
    from mdtero import cli

    cli._print_next_steps(Console())
    output = capsys.readouterr().out
    compact_output = " ".join(output.split())

    assert "Start a local project" in output
    assert "mdtero project init --name literature-review" in output
    assert "mdtero discover \"graph neural networks\" --limit 5 --add --select 1,3" in output
    assert "mdtero parse 10.48550/arXiv.1706.03762 --wait --timeout 300 --json" in output
    assert "mdtero parse https://example.org/open-paper --trace --wait --timeout 300 --json" in compact_output
    assert "mdtero parse --file paper.pdf --wait --timeout 300 --json" in output
    assert "mdtero parse --batch ./papers --wait --timeout 300 --json" in output
    assert "mdtero config zotero" in output
    assert "mdtero zotero import --limit 20" in output
    assert "mdtero zotero sync" in output
    assert "mdtero rag status --json" in output
    assert "mdtero rag build --json" in output
    assert "mdtero rag query \"What are the key claims and methods?\" --build-if-needed --json" in compact_output
    assert "mdtero mcp serve" in output
    assert "mdtero agent install" in output


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
    assert state.papers == []


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


def test_client_falls_back_to_legacy_discovery_when_v1_is_not_deployed(monkeypatch):
    calls = []

    def fake_request(self, method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path == "/api/v1/discovery/search":
            request = httpx.Request(method, "https://api.mdtero.test/api/v1/discovery/search")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("not found", request=request, response=response)
        if path == "/me/discovery/search":
            return {"items": [{"title": "Demo"}]}
        raise AssertionError(path)

    monkeypatch.setattr(MdteroClient, "_request", fake_request)
    result = MdteroClient().discover("rag", limit=1)

    assert result["items"][0]["title"] == "Demo"
    assert result["source"] == "openalex_server"
    assert [call[1] for call in calls] == ["/api/v1/discovery/search", "/me/discovery/search"]


def test_translate_text_payload_is_compatible_with_v1_schema(monkeypatch):
    captured: dict[str, object] = {}

    def fake_request_with_fallback(self, method, primary_path, fallback_path, **kwargs):
        captured["method"] = method
        captured["primary_path"] = primary_path
        captured["fallback_path"] = fallback_path
        captured["json"] = kwargs.get("json")
        return {"task_id": "translate-task", "status": "queued"}

    monkeypatch.setattr(MdteroClient, "_request_with_fallback", fake_request_with_fallback)

    result = MdteroClient().translate_text("# Title\n\nHello", filename="paper.md", target_language="zh-CN")

    assert result == {"task_id": "translate-task", "status": "queued"}
    assert captured["method"] == "POST"
    assert captured["primary_path"] == "/api/v1/tasks/translate"
    assert captured["fallback_path"] == "/tasks/translate"
    assert captured["json"] == {
        "source_markdown_path": "",
        "source_markdown_text": "# Title\n\nHello",
        "source_markdown_filename": "paper.md",
        "target_language": "zh-CN",
        "mode": "full",
    }


def test_translate_server_path_payload_is_compatible_with_v1_schema(monkeypatch):
    captured: dict[str, object] = {}

    def fake_request_with_fallback(self, method, primary_path, fallback_path, **kwargs):
        captured["method"] = method
        captured["primary_path"] = primary_path
        captured["fallback_path"] = fallback_path
        captured["json"] = kwargs.get("json")
        return {"task_id": "translate-task", "status": "queued"}

    monkeypatch.setattr(MdteroClient, "_request_with_fallback", fake_request_with_fallback)

    result = MdteroClient().translate_server_path("/app/tasks/parse-1/paper.md", target_language="zh-CN")

    assert result == {"task_id": "translate-task", "status": "queued"}
    assert captured["method"] == "POST"
    assert captured["primary_path"] == "/api/v1/tasks/translate"
    assert captured["fallback_path"] == "/tasks/translate"
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


def test_discover_returns_structured_failure_when_all_providers_fail(monkeypatch):
    def fake_s2(self, query, *, limit):
        raise httpx.ConnectError("socks tls failed")

    def fake_request(self, method, path, **kwargs):
        request = httpx.Request(method, "https://api.mdtero.test/me/discovery/search")
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
    assert "mdtero login --api-key <key>" in payload["action_hint"]
    assert payload["next_commands"] == ["mdtero login --api-key <key>", "mdtero doctor --json", "mdtero discover \"<topic>\" --json"]


def test_acquisition_selects_route_candidate_and_uploads_with_client_metadata(monkeypatch, tmp_path: Path):
    route = {
        "route_kind": "html_helper_first",
        "acquisition_mode": "native_source_adapter",
        "requires_raw_upload": False,
        "action_sequence": ["fetch_remote_html"],
        "acquisition_candidates": [
            {"connector": "best_oa_location_html", "html_url": "https://example.test/paper"}
        ],
    }
    acquired_path = tmp_path / "paper.html"
    acquired_path.write_text("<html><body><article>Demo</article></body></html>", encoding="utf-8")

    def fake_acquire(route_arg, input_arg, *, timeout):
        assert route_arg is route
        assert input_arg == "10.1000/demo"
        assert timeout == 45.0
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
    def fake_acquire(route_arg, input_arg, *, timeout):
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

    def fake_cffi(url, *, artifact_kind, timeout):
        calls.append(("curl_cffi", url, artifact_kind, timeout))
        raise AcquisitionError("client_curl_cffi_http_error", "403", diagnostics={"status_code": 403})

    def fake_httpx(url, *, artifact_kind, timeout):
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
    def fake_cffi(url, *, artifact_kind, timeout):
        raise AcquisitionError(
            "client_acquisition_challenge_page",
            "challenge",
            diagnostics={"url": url, "source": "curl_cffi", "content_type": "text/html"},
        )

    def fake_httpx(url, *, artifact_kind, timeout):
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


def test_direct_fulltext_xml_url_uses_local_acquisition_even_when_route_is_legacy(monkeypatch, tmp_path: Path):
    acquired_path = tmp_path / "paper.xml"
    acquired_path.write_text("<article><front><article-meta /></front></article>", encoding="utf-8")

    def fake_acquire(route_arg, input_arg, *, timeout):
        assert route_arg["route_kind"] == "legacy_parse"
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
                "route_kind": "legacy_parse",
                "acquisition_mode": "legacy_parse",
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

    assert route_result["route_kind"] == "legacy_parse"
    assert task["task_id"] == "task-xml"
    assert task["client_acquisition"]["artifact_kind"] == "xml"
    assert acquisition["source"] == "curl_cffi"
    assert uploads[0]["data"]["artifact_kind"] == "xml"
    assert uploads[0]["data"]["source_url"] == input_url
    assert not acquired_path.exists()


def test_mdpi_url_candidates_prefer_epub_before_page_fetch(monkeypatch):
    calls = []

    def fake_cffi(url, *, artifact_kind, timeout):
        calls.append((url, artifact_kind))
        raise AcquisitionError("client_acquisition_challenge_page", "challenge")

    def fake_httpx(url, *, artifact_kind, timeout):
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

    downloaded = tmp_path / "paper.md"

    def fake_download(self, task_id, artifact, output_dir):
        assert task_id == "task-1"
        assert artifact == "paper_md"
        assert output_dir == tmp_path
        return downloaded

    monkeypatch.setattr(MdteroClient, "download", fake_download)

    assert cli.cmd_download(type("Args", (), {"task_id": "task-1", "artifact": "paper_md", "output_dir": tmp_path, "json": True})()) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload == {
        "status": "downloaded",
        "task_id": "task-1",
        "artifact": "paper_md",
        "path": str(downloaded),
    }


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
        "mdtero translate task-1 --to zh-CN --json",
        "mdtero project ingest --json",
        "mdtero rag build --json",
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


def test_waited_parse_final_task_is_enriched_without_success_error_noise(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    def fake_parse_with_route(self, value):
        assert value == "10.1000/demo"
        return {"route_kind": "legacy_parse"}, {"task_id": "task-1", "status": "queued"}, None

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
    assert payload["next_commands"] == ["mdtero login --api-key <key>", "mdtero doctor --json"]


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
        return {"route_kind": "legacy_parse"}, {"task_id": "task-1", "status": "queued"}, None

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

    def fake_request_with_fallback(self, method, primary_path, fallback_path, **kwargs):
        calls.append((method, primary_path, fallback_path, kwargs))
        return {"id": 42, "name": kwargs["json"]["name"]}

    monkeypatch.setattr(MdteroClient, "_request_with_fallback", fake_request_with_fallback)

    result = MdteroClient().create_project("demo", description="local project")

    assert result["id"] == 42
    assert calls == [("POST", "/api/v1/projects", "/projects", {"json": {"name": "demo", "description": "local project"}})]


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

    assert cli.cmd_setup(type("Args", (), {"api_key": ""})()) == 0
    output = capsys.readouterr().out
    cfg = load_config()

    assert "Step 1: using existing API-key login from MDTERO_API_KEY." in output
    assert "Step 3: agent skill detection skipped for headless setup." in output
    assert cfg.api_key is None
    assert cfg.effective_api_key == "mdt_live_env"


def test_setup_interactive_installs_detected_agent_skills(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    config_dir = tmp_path / "config"
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".hermes").mkdir()
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(cli, "_configure_academic", lambda cfg, console: None)

    confirms = iter([True, True])
    prompts = iter(["mdt_live_demo", "1 4"])
    monkeypatch.setattr(cli.Confirm, "ask", lambda *args, **kwargs: next(confirms))
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: next(prompts))

    assert cli.cmd_setup(type("Args", (), {"api_key": ""})()) == 0
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

    confirms = iter([True, False])
    monkeypatch.setattr(cli.Confirm, "ask", lambda *args, **kwargs: next(confirms))
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: "mdt_live_demo")

    assert cli.cmd_setup(type("Args", (), {"api_key": ""})()) == 0
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

    assert status["server_project_id"] == "42"
    assert status["ready_for_ingest_count"] == 1
    assert status["pending_count"] == 1
    assert commands["commands"]["parse_doi_or_url"] == "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json"
    assert commands["commands"]["parse_file"] == "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --wait --timeout 300 --json"
    assert commands["commands"]["parse_batch"] == "mdtero parse --batch <directory> --wait --timeout 300 --json"
    assert commands["commands"]["doctor"] == "mdtero doctor --json"
    assert commands["commands"]["discover"] == "mdtero discover \"<topic>\" --interactive"
    assert commands["commands"]["translate"] == "mdtero translate <task-id-or-markdown-file> --to zh-CN --json"
    assert commands["commands"]["zotero_import"] == "mdtero zotero import --json"
    assert commands["commands"]["agent_install"] == "mdtero agent install --interactive"
    assert commands["commands"]["ingest_for_rag"] == "mdtero project ingest --json"
    assert commands["commands"]["rag_status"] == "mdtero rag status --json"
    assert commands["commands"]["rag_build"] == "mdtero rag build --json"
    assert commands["commands"]["mcp_briefing"] == "mdtero mcp briefing --json"
    assert commands["commands"]["serve_mcp"] == "mdtero mcp serve"
    assert commands["recovery_commands"]["create_server_project"] == "mdtero project create-server --json"
    assert commands["workflow"] == [
        "mdtero doctor --json",
        "mdtero project parse --wait --timeout 300 --json",
        "mdtero project refresh --wait --timeout 300 --json",
        "mdtero project ingest --json",
        "mdtero rag status --json",
        "mdtero rag query \"<question>\" --build-if-needed --json",
    ]
    assert rag["ready"] is True
    assert rag["reason_code"] == "ready"
    assert "mdtero project ingest --json" in paper["recommended_commands"]


def test_mcp_agent_briefing_summarizes_project_work_for_agents(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MDTERO_API_KEY", "mdt_live_env")
    init_project(tmp_path, name="agent-demo")
    bind_server_project(tmp_path, "42")
    (tmp_path / ".codex").mkdir()
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md", provider="mineru_precision"))
    add_paper(tmp_path, PaperRecord(input="10.1000/todo", status="pending"))
    add_paper(tmp_path, PaperRecord(input="10.1000/bad", task_id="task-bad", status="failed", reason_code="parser_failed"))

    def fake_fetcher(project_id):
        assert project_id == "42"
        return {
            "status": "ready",
            "reason_code": "indexed",
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
    assert briefing["blocked_items"][0]["reason_code"] == "parser_failed"
    assert briefing["active_items"][0]["input"] == "10.1000/todo"
    assert briefing["rag"]["agent_summary"]["embedded_count"] == 8
    assert briefing["agents"]["detected_count"] == 1
    assert briefing["agents"]["installed_count"] == 0
    assert briefing["agents"]["pending_install_targets"] == ["codex"]
    assert briefing["agents"]["interactive_install_command"] == "mdtero agent install --interactive"
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
    assert "rag_query" in briefing["mcp_tools"]


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
    assert "uv tool install --force git+https://github.com/JonbinC/doi2md.git" in message
    assert "uv tool install --force mdtero" in message
    assert "npm" not in message.lower()


def test_mcp_rag_query_guides_unlinked_projects(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")

    payload = query_server_rag("What is indexed?", tmp_path)

    assert payload["status"] == "not_ready"
    assert payload["reason_code"] == "server_project_not_linked"
    assert payload["server_project_id"] is None
    assert payload["answer"] is None
    assert payload["next_commands"] == ["mdtero rag build --json", "mdtero rag status --json", "mdtero rag query \"<question>\" --build-if-needed --json"]


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


def test_mcp_rag_query_build_if_needed_guides_projects_without_succeeded_tasks(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/todo", status="pending"))

    payload = query_server_rag("What is indexed?", tmp_path, build_if_needed=True)

    assert payload["status"] == "not_ready"
    assert payload["reason_code"] == "no_succeeded_tasks"
    assert payload["answer"] is None
    assert payload["local_ready_for_ingest_count"] == 0
    assert payload["next_commands"] == [
        "mdtero project parse --wait --timeout 300 --json",
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
    assert payload["next_commands"] == ["mdtero rag status --json", "mdtero rag build --json", "mdtero rag query \"<question>\" --build-if-needed --json"]


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
    assert payload["action_hint"] == "Configure VOYAGE_API_KEY on the backend before querying."
    assert payload["next_commands"] == ["mdtero rag status --json"]


def test_mcp_agent_briefing_guides_empty_projects(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv("MDTERO_API_KEY", raising=False)
    init_project(tmp_path, name="empty-demo")

    briefing = build_agent_briefing(tmp_path)

    assert briefing["account"]["authenticated"] is False
    assert briefing["account"]["api_key_source"] == "missing"
    assert briefing["health"]["pending_count"] == 0
    assert briefing["health"]["rag_reason_code"] == "server_project_not_linked"
    assert briefing["recommended_next_commands"][:5] == [
        "mdtero login --api-key <key>",
        "mdtero doctor --json",
        "mdtero discover \"<topic>\" --interactive",
        "mdtero project add <doi-or-url> --json",
        "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
    ]
    assert "mdtero rag build --json" in briefing["recommended_next_commands"]


def test_mcp_rag_context_prompts_rag_build_when_unlinked(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    rag = build_rag_context(tmp_path)
    commands = build_agent_commands(tmp_path)

    assert rag["ready"] is False
    assert rag["reason_code"] == "server_project_not_linked"
    assert commands["commands"]["rag_build"] == "mdtero rag build --json"
    assert commands["commands"]["bootstrap_rag"] == "mdtero rag build --json"
    assert "create_server_project" not in commands["commands"]
    assert commands["recovery_commands"]["create_server_project"] == "mdtero project create-server --json"
    assert commands["workflow"] == [
        "mdtero doctor --json",
        "mdtero project parse --wait --timeout 300 --json",
        "mdtero project refresh --wait --timeout 300 --json",
        "mdtero rag build --json",
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
    assert status["next_commands"][0] == "mdtero rag build --json"
    assert "create and bind" in status["action_hint"]


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
            "summary": {"chunk_count": 5, "embedded_count": 5, "pending_embedding_count": 0},
        }

    status = build_server_rag_status(tmp_path, fetcher=fake_fetcher)

    assert status["server_project_id"] == "42"
    assert status["agent_summary"] == {
        "status": "ready",
        "reason_code": "indexed",
        "embedded_count": 5,
        "chunk_count": 5,
        "pending_embedding_count": 0,
    }
    assert status["next_commands"] == ["mdtero rag status --json", "mdtero rag query \"<question>\" --build-if-needed --json", "mdtero mcp briefing --json", "mdtero mcp serve"]


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
    assert status["next_commands"] == ["mdtero project ingest --json", "mdtero rag status --json", "mdtero rag build --json"]


def test_tui_dashboard_model_guides_login_and_setup(tmp_path: Path):
    init_project(tmp_path, name="tui-demo")

    model = build_dashboard_model(project_root=tmp_path, config=MdteroConfig(api_key=None), agent_root=tmp_path)

    assert model["health"]["status"] == "needs_auth"
    assert model["health"]["headline"] == "Needs login"
    assert model["health"]["primary_next_command"] == "mdtero login --api-key <key>"
    assert model["account"]["authenticated"] is False
    assert model["project"]["name"] == "tui-demo"
    assert model["rag"]["reason_code"] == "server_project_not_linked"
    assert model["mcp"]["primary_tool"] == "agent_briefing"
    assert "agent_briefing" in model["mcp"]["tools"]
    assert model["agents"]["detect_command"] == "mdtero agent detect --json"
    assert model["agents"]["install_command"] == "mdtero agent install --interactive"
    assert model["agents"]["fallback_install_command"] == "mdtero agent install --target codex --json"
    assert model["handoff"]["active_items"] == []
    assert model["next_steps"][:2] == ["mdtero login --api-key <key>", "mdtero doctor --json"]


def test_tui_dashboard_model_accepts_environment_api_key(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MDTERO_API_KEY", "mdt_live_env")
    init_project(tmp_path, name="tui-env")

    model = build_dashboard_model(project_root=tmp_path, config=MdteroConfig(api_key=None), agent_root=tmp_path)

    assert model["account"]["authenticated"] is True
    assert model["account"]["auth_source"] == "MDTERO_API_KEY"
    assert model["next_steps"][:2] != ["mdtero login --api-key <key>", "mdtero doctor --json"]


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
    })
    rendered = render_dashboard_text(model)

    assert model["academic"]["discover_source"] == "local Semantic Scholar"
    assert model["health"]["status"] == "results_ready"
    assert model["health"]["counts"]["ready_artifacts"] == 1
    assert model["health"]["counts"]["pending_agent_installs"] == 1
    assert model["rag"]["ready"] is False
    assert model["rag"]["server_status"] == "not_ready"
    assert model["next_steps"] == ["mdtero rag status --json", "mdtero rag build --json", "mdtero rag query \"<question>\" --build-if-needed --json"]
    assert model["mcp"]["serve_command"] == "mdtero mcp serve"
    assert model["mcp"]["briefing_command"] == "mdtero mcp briefing --json"
    assert "mdtero rag build --json" in model["mcp"]["recommended_next_commands"]
    assert model["handoff"]["ready_artifacts"][0]["download_command"] == "mdtero download task-done paper_md --output-dir ./mdtero-output --json"
    assert model["handoff"]["recommended_next_commands"][0] == "mdtero project download --output-dir ./mdtero-output --json"
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
    assert "Results ready" in output
    assert "Agent Handoff" in output
    assert "Agent skills" in output
    assert rendered is not None


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
    add_paper(tmp_path, PaperRecord(input="10.1000/bad", task_id="task-bad", status="failed", reason_code="parser_failed"))

    model = build_dashboard_model(project_root=tmp_path, config=MdteroConfig(api_key="key"), agent_root=tmp_path)
    rendered = render_dashboard_text(model)

    assert model["health"]["status"] == "needs_attention"
    assert model["health"]["counts"]["blocked_items"] == 1
    assert model["health"]["primary_next_command"] == "mdtero project parse --wait --timeout 300 --json"
    assert model["handoff"]["active_items"][0]["input"] == "10.1000/todo"
    assert model["handoff"]["blocked_items"][0]["reason_code"] == "parser_failed"
    assert "mdtero project parse --include-failed --wait --timeout 300 --json" in model["handoff"]["recommended_next_commands"]
    console = Console(record=True, width=140)
    console.print(rendered)
    assert "parser_failed" in console.export_text()


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
        },
    )
    rendered = render_dashboard_text(model)

    assert model["health"]["status"] == "ready"
    assert model["health"]["headline"] == "Project RAG ready"
    assert model["health"]["primary_next_command"] == "mdtero rag status --json"
    assert model["rag"]["ready"] is True
    assert model["rag"]["reason_code"] == "indexed"
    assert model["rag"]["server_summary"]["embedded_count"] == 3
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
    assert model["next_steps"] == ["mdtero rag build --json", "mdtero rag status --json", "mdtero rag query \"<question>\" --build-if-needed --json"]


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

    assert "mdtero rag build --json" in message
    assert "create, bind, import, and build" in message


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
            "next_commands": ["mdtero rag status --json", "mdtero rag query \"<question>\"", "mdtero mcp serve"],
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
    assert "mdtero mcp serve" in output


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
    assert payload["next_commands"] == ["mdtero project ingest --json", "mdtero rag status --json", "mdtero rag build --json"]


def test_rag_build_failure_outputs_agent_json_without_traceback(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    bind_server_project(tmp_path, "42")

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
    assert "VOYAGE_API_KEY" in payload["action_hint"]
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
    assert "Build this server project RAG index" in payload["action_hint"]
    assert payload["next_commands"] == ["mdtero rag status --json", "mdtero rag build --json", "mdtero rag query \"<question>\" --build-if-needed --json"]


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
    assert payload["action_hint"] == "Server RAG is not configured in production."
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
            "next_commands": ["mdtero rag status --json", "mdtero mcp serve"],
        }

    monkeypatch.setattr(MdteroClient, "rag_query", fake_query)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_query(type("Args", (), {"project_id": None, "question": "What improves corrosion?", "json": False})()) == 0
    output = capsys.readouterr().out

    assert "RAG query: succeeded (rag_query_succeeded)" in output
    assert "Answer" in output
    assert "[1] Coating improves corrosion resistance." in output
    assert "Corrosion Paper:3-4 · 10.1000/rag" in output
    assert "mdtero mcp serve" in output


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
    assert payload["citations"][0]["document_title"] == "Attention Is All You Need"
    assert payload["citations"][0]["line_start"] == 53
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
    assert "mdtero rag build --json" in output
    assert "mdtero rag query \"<question>\" --build-if-needed --json" in output


def test_rag_status_outputs_unlinked_json_for_agents(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_status(type("Args", (), {"project_id": None, "json": True})()) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "not_ready"
    assert payload["reason_code"] == "server_project_not_linked"
    assert "mdtero rag build --json" in payload["action_hint"]
    assert payload["next_commands"] == ["mdtero rag build --json", "mdtero rag status --json", "mdtero rag query \"<question>\" --build-if-needed --json"]


def test_rag_build_unlinked_project_auto_creates_ingests_and_builds(monkeypatch, tmp_path: Path, capsys):
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
        ("create", "local-demo", "Mdtero local project: local-demo"),
        ("import", "42", "task-done"),
        ("build", "42"),
    ]


def test_rag_build_bootstrap_failure_preserves_backend_next_commands(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")

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


def test_rag_query_unlinked_project_plain_output_is_actionable(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_query(type("Args", (), {"project_id": None, "question": "demo", "json": False})()) == 1
    output = capsys.readouterr().out

    assert "RAG query not ready: server_project_not_linked" in output
    assert "mdtero rag build --json" in output
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

    def fake_query(self, project_id, question):
        request = httpx.Request("POST", "https://api.mdtero.com/api/v1/projects/42/rag/query")
        response = httpx.Response(409, request=request, json={"detail": {"reason_code": "rag_index_not_built"}})
        raise httpx.HTTPStatusError("not ready", request=request, response=response)

    monkeypatch.setattr(MdteroClient, "create_project", fake_create)
    monkeypatch.setattr(MdteroClient, "import_task_to_project", fake_import)
    monkeypatch.setattr(MdteroClient, "rag_build", fake_build)
    monkeypatch.setattr(MdteroClient, "rag_query", fake_query)
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_query(type("Args", (), {"project_id": None, "question": "What is ready?", "build_if_needed": True, "json": True})()) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "rag_query"
    assert payload["reason_code"] == "rag_index_not_built"
    assert payload["server_project_id"] == "42"
    assert payload["bootstrap"]["ingest"]["imported_count"] == 1
    assert payload["bootstrap"]["build"]["reason_code"] == "rag_build_queued"
    assert payload["next_commands"] == ["mdtero rag status --json", "mdtero rag build --json", "mdtero rag query \"<question>\" --build-if-needed --json"]


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
            "route_kind": "html_helper_first",
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
    assert "uv tool install git+https://github.com/JonbinC/doi2md.git" in skill_path.read_text(encoding="utf-8")


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
    assert manifest["quickInstallCommand"] == "uv tool install git+https://github.com/JonbinC/doi2md.git && mdtero setup"
    assert manifest["cli"]["packageName"] == "mdtero"
    assert manifest["cli"]["packageVersion"] == package_version
    assert manifest["releaseTruth"]["current"]["cli"]["version"] == package_version
    assert manifest["cli"]["packageManager"] == "uv"
    assert manifest["cli"]["skillInstallCommand"] == "mdtero agent install --target <target>"
    assert "legacyNpmCompatibility" not in json.dumps(manifest)
    assert "mdtero-install" not in json.dumps(manifest)


def test_public_docs_do_not_advertise_npm_installer_runtime():
    repo_root = Path(__file__).resolve().parents[1]
    docs = [
        repo_root / "README.md",
        repo_root / "install" / "README.md",
        repo_root / "docs" / "public" / "README.md",
        repo_root / "helper" / "README.md",
    ]
    for path in docs:
        content = path.read_text(encoding="utf-8")
        assert "mdtero-install" not in content
        assert "npx mdtero" not in content
        assert "npm install -g" not in content


def test_public_docs_describe_rag_answer_citation_contract():
    repo_root = Path(__file__).resolve().parents[1]
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [repo_root / "README.md", repo_root / "install" / "README.md"]
    )

    assert "RAG query" in combined
    assert "answer" in combined
    assert "citations" in combined
    assert "matches" in combined
    assert "next_commands" in combined


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
        assert "mdtero parse --file paper.pdf --wait --timeout 300 --json" in content or "mdtero parse --file <paper.pdf|paper.html|paper.xml|paper.epub> --wait --timeout 300 --json" in content or "mdtero parse --file <path> --wait --timeout 300 --json" in content
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
    assert "Headless setup with `mdtero setup --api-key <key>` or `MDTERO_API_KEY`" in combined
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


def test_legacy_agent_install_docs_use_json_friendly_cli_examples():
    repo_root = Path(__file__).resolve().parents[1]
    docs = [
        repo_root / "skills" / "codex" / "INSTALL.md",
        repo_root / "skills" / "claude_code" / "INSTALL.md",
        repo_root / "skills" / "gemini_cli" / "INSTALL.md",
        repo_root / "skills" / "hermes" / "INSTALL.md",
    ]
    for path in docs:
        content = path.read_text(encoding="utf-8")
        assert "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json" in content
        assert "mdtero status <task-id> --wait --timeout 300 --json" in content
        assert "mdtero parse --file <path> --wait --timeout 300 --json" in content
        assert "mdtero translate <parse-task-id> --to zh-CN --json" in content
        assert "mdtero rag build --json" in content
        assert "mdtero rag status --json" in content
        assert "mdtero rag query \"<question>\" --build-if-needed --json" in content
        assert "mdtero mcp briefing --json" in content
        assert "mdtero mcp serve" in content
        assert "mdtero parse <doi-or-url>\n" not in content
        assert "mdtero parse --file <path> --json" not in content
        assert "mdtero translate <parse-task-id> zh" not in content


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
    assert "JSON responses include `next_commands`" in source_skill
    assert "preferred_artifact" in source_skill
    assert "returned `answer` and `citations`" in source_skill
