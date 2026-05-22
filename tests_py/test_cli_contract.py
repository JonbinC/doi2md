from __future__ import annotations

import json
from pathlib import Path

import httpx

from mdtero.acquisition import AcquiredArtifact, AcquisitionError, acquire_from_route, should_acquire_locally
from mdtero.agent import detect_targets, install_targets, uninstall_targets
from mdtero.cli import build_parser
from mdtero.client import MdteroClient
from mdtero.config import AcademicKeys, MdteroConfig, ZoteroConfig, load_config, save_config
from mdtero.mcp import build_agent_commands, build_paper_context, build_project_status, build_rag_context
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


def test_client_can_create_server_project(monkeypatch):
    calls = []

    def fake_request(self, method, path, **kwargs):
        calls.append((method, path, kwargs.get("json")))
        return {"id": 42, "name": kwargs["json"]["name"]}

    monkeypatch.setattr(MdteroClient, "_request", fake_request)

    result = MdteroClient().create_project("demo", description="local project")

    assert result["id"] == 42
    assert calls == [("POST", "/projects", {"name": "demo", "description": "local project"})]


def test_client_can_import_task_to_server_project(monkeypatch):
    calls = []

    def fake_request(self, method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"document_id": 7, "import_status": "imported"}

    monkeypatch.setattr(MdteroClient, "_request", fake_request)

    result = MdteroClient().import_task_to_project("42", "task-1")

    assert result["document_id"] == 7
    assert calls == [("POST", "/api/v1/projects/42/tasks/task-1/import", {})]


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

    model = build_dashboard_model(project_root=tmp_path, config=cfg, agent_root=tmp_path)
    rendered = render_dashboard_text(model)

    assert model["academic"]["discover_source"] == "local Semantic Scholar"
    assert model["rag"]["ready"] is True
    assert model["next_steps"] == ["mdtero project ingest", "mdtero rag build", "mdtero rag query \"<question>\""]
    assert model["zotero"]["configured"] is True
    assert model["agents"]["labels"] == ["Codex"]
    assert rendered is not None


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
