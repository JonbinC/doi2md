from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from mdtero.cli import build_parser, cmd_relay_status
from mdtero.relay import execute_relay_fetch, relay_ws_url, run_relay_server
from mdtero.relay_domains import relay_url_allowed, relay_url_rejection_reason


def test_relay_url_allowlist():
    assert relay_url_allowed("https://doi.org/10.1038/nature12373")
    assert relay_url_allowed(
        "https://mdpi-res.com/d_attachment/energies/energies-16-02875/"
        "article_deploy/energies-16-02875.epub"
    )
    assert relay_url_allowed("https://pubs.acs.org/doi/pdf/10.1021/demo")
    assert relay_url_allowed("https://api.wiley.com/onlinelibrary/tdm/v1/articles/10.1002%2Fdemo")
    assert relay_url_rejection_reason("https://example.com/paper.pdf") == "relay_url_domain_not_allowed"


def test_relay_ws_url():
    assert relay_ws_url("https://api.mdtero.com") == "wss://api.mdtero.com/api/v1/relay/ws"
    assert relay_ws_url("http://127.0.0.1:8000") == "ws://127.0.0.1:8000/api/v1/relay/ws"


def test_execute_relay_fetch_blocks_unapproved_domain():
    result = asyncio.run(
        execute_relay_fetch(url="https://example.com/paper.pdf", method="GET", headers={}, timeout=10.0)
    )
    assert result["reason_code"] == "relay_url_domain_not_allowed"


def test_execute_relay_fetch_returns_response_body():
    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/plain"}
        content = b"paper"
        url = "https://doi.org/10.1038/nature12373"

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers):
            assert method == "GET"
            assert url == "https://doi.org/10.1038/nature12373"
            return FakeResponse()

    with patch("mdtero.relay.httpx.AsyncClient", return_value=FakeClient()):
        result = asyncio.run(
            execute_relay_fetch(
                url="https://doi.org/10.1038/nature12373",
                method="GET",
                headers={},
                timeout=10.0,
            )
        )

    assert result["status_code"] == 200
    assert result["body_b64"] == "cGFwZXI="


def test_execute_relay_fetch_blocks_disallowed_redirect_target():
    requested: list[str] = []

    class RedirectResponse:
        status_code = 302
        headers = {"location": "https://example.com/private.pdf"}
        content = b""
        url = "https://doi.org/10.1038/nature12373"

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers):
            requested.append(url)
            return RedirectResponse()

    with patch("mdtero.relay.httpx.AsyncClient", return_value=FakeClient()):
        result = asyncio.run(
            execute_relay_fetch(
                url="https://doi.org/10.1038/nature12373",
                method="GET",
                headers={},
                timeout=10.0,
            )
        )

    assert requested == ["https://doi.org/10.1038/nature12373"]
    assert result["reason_code"] == "relay_url_domain_not_allowed"


def test_run_relay_server_registers_and_handles_fetch():
    cfg = type("Cfg", (), {"effective_api_key": "mdt_test_key", "api_base_url": "https://api.mdtero.com"})()
    events: list[tuple[str, dict]] = []

    class FakeWebSocket:
        def __init__(self):
            self.sent: list[str] = []
            self._queue = [
                json.dumps({"type": "hello", "user_id": 1}),
                json.dumps(
                    {
                        "type": "fetch",
                        "request_id": "req-1",
                        "url": "https://doi.org/10.1038/nature12373",
                        "method": "GET",
                        "headers": {},
                        "timeout": 10,
                    }
                ),
            ]

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def recv(self):
            if not self._queue:
                raise asyncio.CancelledError()
            return self._queue.pop(0)

        async def send(self, payload: str):
            self.sent.append(payload)
            message = json.loads(payload)
            if message.get("type") == "register":
                self._queue.insert(0, json.dumps({"type": "registered", "relay_id": "relay-1"}))

    fake_ws = FakeWebSocket()

    class FakeConnect:
        async def __aenter__(self):
            return fake_ws

        async def __aexit__(self, exc_type, exc, tb):
            return False

    with patch("mdtero.relay.check_campus_outlet", AsyncMock(return_value={"summary": {"asn": "AS786"}, "campus_ok": True})):
        with patch("mdtero.relay.websockets.connect", return_value=FakeConnect()):
            with patch(
                "mdtero.relay._relay_connection_target",
                AsyncMock(
                    return_value=(
                        relay_ws_url(cfg.api_base_url),
                        {"Authorization": "ApiKey mdt_test_key", "X-Client-Channel": "python-relay"},
                    )
                ),
            ):
                with patch(
                    "mdtero.relay.execute_relay_fetch",
                    AsyncMock(return_value={"status_code": 200, "headers": {}, "body_b64": "cGFwZXI="}),
                ):
                    async def _run() -> None:
                        task = asyncio.create_task(
                            run_relay_server(
                                cfg,
                                label="lab-pc",
                                on_status=lambda event, detail: events.append((event, detail)),
                            )
                        )
                        await asyncio.sleep(0.05)
                        task.cancel()
                        with pytest.raises(asyncio.CancelledError):
                            await task

                    asyncio.run(_run())

    assert any(event == "registered" for event, _ in events)
    assert any('"type": "fetch_result"' in payload for payload in fake_ws.sent)


def test_relay_status_command_requires_auth(monkeypatch, capsys):
    monkeypatch.setattr(
        "mdtero.cli.load_config",
        lambda: type("Cfg", (), {"is_authenticated": False, "effective_api_key": None})(),
    )
    parser = build_parser()
    args = parser.parse_args(["relay", "status", "--json"])
    assert cmd_relay_status(args) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason_code"] == "auth_missing"


def test_execute_relay_fetch_drops_elsevier_credentials_on_cross_host_redirect():
    from mdtero.relay import headers_for_url

    sent: list[tuple[str, dict]] = []

    class Redirect:
        status_code = 302
        headers = {"location": "https://www.sciencedirect.com/science/article/pii/X"}
        content = b""
        url = "https://api.elsevier.com/content/article/doi/10.1/x"

    class Final:
        status_code = 200
        headers = {}
        content = b"ok"
        url = "https://www.sciencedirect.com/science/article/pii/X"

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def request(self, method, url, headers):
            sent.append((url, dict(headers)))
            return Redirect() if len(sent) == 1 else Final()

    creds = {"X-ELS-APIKey": "k", "X-ELS-Insttoken": "t", "Accept": "text/xml"}
    with patch("mdtero.relay.httpx.AsyncClient", return_value=FakeClient()):
        result = asyncio.run(
            execute_relay_fetch(
                url="https://api.elsevier.com/content/article/doi/10.1/x",
                method="GET",
                headers=creds,
                timeout=10.0,
            )
        )
    assert result["status_code"] == 200
    assert sent[0][1]["X-ELS-APIKey"] == "k"
    assert "X-ELS-APIKey" not in sent[1][1] and "X-ELS-Insttoken" not in sent[1][1]
    assert sent[1][1]["Accept"] == "text/xml"
    assert "X-ELS-APIKey" not in headers_for_url("http://api.elsevier.com/x", creds)
    assert "x-els-apikey" not in {k.lower() for k in headers_for_url("https://api.elsevier.com.evil.test/", creds)}
    for url in ("https://api.elsevier.com:8443/x", "https://api.elsevier.com:invalid/x", "https://u:p@api.elsevier.com/x"):
        assert headers_for_url(url, creds) == {"Accept": "text/xml"}


def test_relay_check_prints_human_lines(monkeypatch, capsys):
    from mdtero.cli import cmd_relay_check

    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def _request(self, method, path, **kwargs):
            calls.append((method, path, kwargs))
            return {
                "verdict": "not_entitled",
                "effective": False,
                "action_hint": "relay egress IP 1.2.3.4 is not in an institutional range",
                "cli": {"human_lines": ["Relay check: not_entitled", "  hint: relay egress IP 1.2.3.4 ..."]},
            }

    monkeypatch.setattr("mdtero.cli.load_config", lambda: type("Cfg", (), {"is_authenticated": True})())
    monkeypatch.setattr("mdtero.cli.MdteroClient", FakeClient)
    args = build_parser().parse_args(["relay", "check", "--no-confirm-fulltext"])
    assert cmd_relay_check(args) == 1
    out = capsys.readouterr().out
    assert "Relay check: not_entitled" in out and "1.2.3.4" in out
    assert calls == [("POST", "/api/v1/relay/entitlement-check", {"json": {"confirm_fulltext": False}})]


def test_relay_check_json_prints_raw_response(monkeypatch, capsys):
    from mdtero.cli import cmd_relay_check

    response = {"verdict": "full_text_ok", "effective": True, "cli": {"human_lines": ["ok"]}}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def _request(self, method, path, **kwargs):
            return response

    monkeypatch.setattr("mdtero.cli.load_config", lambda: type("Cfg", (), {"is_authenticated": True})())
    monkeypatch.setattr("mdtero.cli.MdteroClient", FakeClient)
    args = build_parser().parse_args(["relay", "check", "--json"])
    assert cmd_relay_check(args) == 0
    assert json.loads(capsys.readouterr().out) == response


def test_relay_status_and_check_multi_outlet_cli(monkeypatch, capsys):
    from mdtero.cli import cmd_relay_check, cmd_relay_status

    requested_paths: list[str] = []
    requested_bodies: list[dict] = []

    status_response = {
        "connected": True,
        "relay_id": "r-mac",
        "label": "mac-campus",
        "active_outlet": "mac-campus",
        "outlets_count": 2,
        "outlets": [
            {"relay_id": "r-pi3", "label": "pi3-campus", "is_active": False},
            {"relay_id": "r-mac", "label": "mac-campus", "is_active": True},
        ],
        "browser": {"enabled": True, "fulltext": False},
    }

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def _request(self, method, path, json=None, **kwargs):
            requested_paths.append(path)
            if json is not None:
                requested_bodies.append(json)
            if "status" in path:
                return status_response
            return {"verdict": "entitled", "effective": True, "cli": {"human_lines": ["ok"]}}

    monkeypatch.setattr("mdtero.cli.load_config", lambda: type("Cfg", (), {"is_authenticated": True})())
    monkeypatch.setattr("mdtero.cli.MdteroClient", FakeClient)

    # Status with --outlet
    parser = build_parser()
    args = parser.parse_args(["relay", "status", "--outlet", "pi3-campus"])
    assert cmd_relay_status(args) == 0
    out = capsys.readouterr().out
    assert "Connected outlets (2):" in out
    assert "pi3-campus" in out
    assert "mac-campus" in out
    assert any("outlet=pi3-campus" in p for p in requested_paths)

    # Check with --outlet
    check_args = parser.parse_args(["relay", "check", "--outlet", "mac-campus", "--json"])
    assert cmd_relay_check(check_args) == 0
    assert requested_bodies[-1].get("outlet") == "mac-campus"
