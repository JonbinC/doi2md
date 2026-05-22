from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import httpx
from rich.console import Console

from mdtero.acquisition import AcquiredArtifact, AcquisitionError, acquire_from_route, should_acquire_locally
from mdtero.agent import detect_target_status, detect_targets, install_targets, uninstall_targets
from mdtero.auth import WebLoginResult, build_cli_login_url, run_web_login
from mdtero.cli import build_parser, _add_discovery_results_to_project, _parse_academic_selection, _parse_result_selection
from mdtero.client import MdteroClient
from mdtero.config import AcademicKeys, MdteroConfig, ZoteroConfig, load_config, save_config
from mdtero.mcp import build_agent_commands, build_paper_context, build_project_status, build_rag_context, build_server_rag_status
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


def test_rag_status_accepts_agent_friendly_flags():
    parser = build_parser()

    args = parser.parse_args(["rag", "status", "--project-id", "42", "--json"])

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


def test_setup_next_steps_cover_project_rag_zotero_and_agent_workflows(capsys):
    from mdtero import cli

    cli._print_next_steps(Console())
    output = capsys.readouterr().out

    assert "Start a local project" in output
    assert "mdtero project init --name literature-review" in output
    assert "mdtero discover \"graph neural networks\" --limit 5 --add --select 1,3" in output
    assert "mdtero parse 10.48550/arXiv.1706.03762 --wait" in output
    assert "mdtero parse --file paper.pdf --wait" in output
    assert "mdtero parse --batch ./papers --wait" in output
    assert "mdtero config zotero" in output
    assert "mdtero zotero import --limit 20" in output
    assert "mdtero zotero sync" in output
    assert "mdtero project create-server" in output
    assert "mdtero project ingest" in output
    assert "mdtero rag status --json" in output
    assert "mdtero rag build" in output
    assert "mdtero mcp serve" in output
    assert "mdtero agent install" in output


def test_result_selection_supports_all_and_number_lists():
    assert _parse_result_selection("", max_count=3) == [1, 2, 3]
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
    assert [paper.input for paper in state.papers] == ["10.1000/a", "https://example.test/paper-b"]
    assert state.papers[0].source == "discover:openalex"
    assert state.papers[0].title == "Paper A"


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
    assert result["items"][0]["title"] == "Server fallback"
    assert calls[0][1] == "/api/v1/discovery/search"


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
    assert payload["status_code"] == 503


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

    assert cli.cmd_setup(type("Args", (), {"api_key": "mdt_live_demo"})()) == 0
    output = capsys.readouterr().out

    assert output.count("Step 1: saved API-key login for this machine.") == 1


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
    assert commands["commands"]["ingest_for_rag"] == "mdtero project ingest"
    assert commands["commands"]["rag_status"] == "mdtero rag status --json"
    assert commands["commands"]["rag_build"] == "mdtero rag build"
    assert rag["ready"] is True
    assert rag["reason_code"] == "ready"
    assert "mdtero project ingest" in paper["recommended_commands"]


def test_mcp_rag_context_prompts_server_project_creation_when_unlinked(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    rag = build_rag_context(tmp_path)
    commands = build_agent_commands(tmp_path)

    assert rag["ready"] is False
    assert rag["reason_code"] == "server_project_not_linked"
    assert commands["commands"]["create_server_project"] == "mdtero project create-server"


def test_mcp_server_rag_status_reports_unlinked_next_commands(tmp_path: Path):
    init_project(tmp_path, name="agent-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))

    status = build_server_rag_status(tmp_path)

    assert status["status"] == "not_ready"
    assert status["reason_code"] == "server_project_not_linked"
    assert status["local_ready_for_ingest_count"] == 1
    assert status["next_commands"][0] == "mdtero project create-server"


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
    assert status["next_commands"] == ["mdtero rag status --json", "mdtero rag query \"<question>\"", "mdtero mcp serve"]


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
    assert status["next_commands"] == ["mdtero project ingest", "mdtero rag status --json", "mdtero rag build"]


def test_tui_dashboard_model_guides_login_and_setup(tmp_path: Path):
    init_project(tmp_path, name="tui-demo")

    model = build_dashboard_model(project_root=tmp_path, config=MdteroConfig(api_key=None), agent_root=tmp_path)

    assert model["account"]["authenticated"] is False
    assert model["project"]["name"] == "tui-demo"
    assert model["rag"]["reason_code"] == "server_project_not_linked"
    assert model["next_steps"][:2] == ["mdtero login --api-key <key>", "mdtero doctor"]


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
    assert model["rag"]["ready"] is False
    assert model["rag"]["server_status"] == "not_ready"
    assert model["next_steps"] == ["mdtero rag status --json", "mdtero rag build", "mdtero rag query \"<question>\""]
    assert model["zotero"]["configured"] is True
    assert model["agents"]["labels"] == ["Codex"]
    assert rendered is not None


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

    assert model["rag"]["ready"] is True
    assert model["rag"]["reason_code"] == "indexed"
    assert model["rag"]["server_summary"]["embedded_count"] == 3
    assert model["next_steps"] == ["mdtero rag status --json", "mdtero rag query \"<question>\"", "mdtero mcp serve"]
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
    assert model["next_steps"] == ["mdtero project ingest", "mdtero rag status --json", "mdtero rag build"]


def test_rag_uses_bound_server_project_id_by_default(monkeypatch, tmp_path: Path):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    bind_server_project(tmp_path, "42")

    monkeypatch.chdir(tmp_path)
    assert cli._server_project_id(type("Args", (), {"project_id": None})()) == "42"
    assert cli._server_project_id(type("Args", (), {"project_id": "99"})()) == "99"


def test_rag_requires_project_binding_when_project_id_is_omitted(monkeypatch, tmp_path: Path):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    monkeypatch.chdir(tmp_path)

    try:
        cli._server_project_id(type("Args", (), {"project_id": None})())
    except SystemExit as exc:
        message = str(exc)
    else:
        raise AssertionError("expected missing binding error")

    assert "mdtero project create-server" in message


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
    assert payload["next_commands"] == ["mdtero project ingest", "mdtero rag status --json", "mdtero rag build"]


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
    assert payload["next_commands"] == ["mdtero rag status --json", "mdtero rag build", "mdtero rag query \"<question>\""]


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


def test_rag_status_reports_local_precondition_when_project_is_unlinked(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_status(type("Args", (), {"project_id": None, "json": False})()) == 0
    output = capsys.readouterr().out

    assert "1/1 local paper(s)" in output
    assert "mdtero project create-server" in output


def test_rag_status_outputs_unlinked_json_for_agents(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_status(type("Args", (), {"project_id": None, "json": True})()) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "not_ready"
    assert payload["reason_code"] == "server_project_not_linked"
    assert "project create-server" in payload["action_hint"]


def test_rag_build_unlinked_project_returns_agent_json(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    add_paper(tmp_path, PaperRecord(input="10.1000/done", task_id="task-done", status="succeeded", artifact="paper_md"))
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_build(type("Args", (), {"project_id": None, "json": True})()) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "not_ready"
    assert payload["command"] == "rag_build"
    assert payload["reason_code"] == "server_project_not_linked"
    assert payload["error_code"] == "rag_precondition_failed"
    assert payload["local_ready_for_ingest_count"] == 1
    assert payload["next_commands"] == [
        "mdtero project create-server",
        "mdtero project ingest",
        "mdtero rag status --json",
        "mdtero rag build",
    ]


def test_rag_query_unlinked_project_plain_output_is_actionable(monkeypatch, tmp_path: Path, capsys):
    from mdtero import cli

    init_project(tmp_path, name="local-demo")
    monkeypatch.chdir(tmp_path)

    assert cli.cmd_rag_query(type("Args", (), {"project_id": None, "question": "demo", "json": False})()) == 1
    output = capsys.readouterr().out

    assert "RAG query not ready: server_project_not_linked" in output
    assert "mdtero project create-server" in output
    assert "mdtero project ingest" in output
    assert "mdtero rag query \"<question>\"" in output


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


def test_public_install_manifest_is_python_runtime_only_and_mirrored_with_site():
    repo_root = Path(__file__).resolve().parents[1]
    manifest = json.loads((repo_root / "install" / "manifest.json").read_text(encoding="utf-8"))
    site_manifest = json.loads((repo_root.parent / "nextmdtero" / "public" / "install" / "manifest.json").read_text(encoding="utf-8"))

    assert manifest == site_manifest
    assert manifest["quickInstallCommand"] == "uv tool install git+https://github.com/JonbinC/doi2md.git && mdtero setup"
    assert manifest["cli"]["packageName"] == "mdtero"
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


def test_packaged_skill_template_is_available_to_python_installer():
    from importlib import resources

    skill = resources.files("mdtero.skills.mdtero").joinpath("SKILL.md").read_text(encoding="utf-8")

    assert "mdtero agent install" in skill
    assert "mdtero parse <doi-or-url>" in skill


def test_source_and_packaged_agent_skill_templates_stay_in_sync():
    from importlib import resources

    repo_root = Path(__file__).resolve().parents[1]
    source_skill = (repo_root / "skills" / "mdtero" / "SKILL.md").read_text(encoding="utf-8")
    packaged_skill = resources.files("mdtero.skills.mdtero").joinpath("SKILL.md").read_text(encoding="utf-8")

    assert source_skill == packaged_skill
    assert "mdtero rag build --project-id" not in source_skill
    assert "mdtero project ingest" in source_skill
    assert "server_rag_status" in source_skill
