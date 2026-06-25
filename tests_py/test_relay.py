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
