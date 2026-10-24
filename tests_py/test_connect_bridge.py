from __future__ import annotations

import json
import socket
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from mdtero.client import MdteroClient
from mdtero.config import MdteroConfig
from mdtero.connect.bridge import ConnectBridge
from mdtero.connect.library import LibraryClient


APP_DIR = Path(__file__).resolve().parents[1] / "connect" / "app"


@pytest.fixture()
def bridge(tmp_path: Path):
    # Serve the real Connect UI assets.
    assert (APP_DIR / "index.html").is_file()
    config = MdteroConfig(api_key="mdt_live_test_key_not_real")
    client = MdteroClient(config=config)
    client._request = MagicMock()  # type: ignore[method-assign]
    client._raw_request = MagicMock()  # type: ignore[method-assign]
    instance = ConnectBridge(host="127.0.0.1", port=0, client=client, static_dir=APP_DIR)
    instance.start()
    try:
        yield instance
    finally:
        instance.stop()


def _get(bridge: ConnectBridge, path: str, **kwargs):
    return httpx.get(bridge.base_url + path, headers={"Host": f"127.0.0.1:{bridge.bound_port}"}, **kwargs)


def _post(bridge: ConnectBridge, path: str, payload: dict | None, *, csrf: str):
    return httpx.post(
        bridge.base_url + path,
        headers={
            "Host": f"127.0.0.1:{bridge.bound_port}",
            "Origin": f"http://127.0.0.1:{bridge.bound_port}",
            "X-Mdtero-CSRF": csrf,
            "Content-Type": "application/json",
        },
        content=json.dumps(payload) if payload is not None else b"",
    )


def test_session_and_static(bridge: ConnectBridge):
    home = _get(bridge, "/")
    assert home.status_code == 200
    assert "mdtero 客户端".encode() in home.content
    css = (APP_DIR / "style.css").read_text(encoding="utf-8")
    tokens = (APP_DIR / "tokens.css").read_text(encoding="utf-8")
    assert css.startswith('@import url("tokens.css");')
    assert ':root[data-theme="dark"]' in tokens
    assert "prefers-color-scheme: dark" in tokens
    assert "#a3542f" not in css and "#8c4626" not in css
    script = (APP_DIR / "app.js").read_text(encoding="utf-8")
    assert "错误详情" not in script
    assert "复制诊断信息" in script
    bootstrap = Path(__file__).resolve().parents[1] / "connect" / "native" / "bootstrap"
    assert (bootstrap / "style.css").read_text(encoding="utf-8").startswith('@import url("tokens.css");')
    assert (bootstrap / "tokens.css").read_bytes() == (APP_DIR / "tokens.css").read_bytes()
    assert "#925739" not in (bootstrap / "style.css").read_text(encoding="utf-8")
    session = _get(bridge, "/connect/v1/session")
    assert session.status_code == 200
    data = session.json()
    assert data["authenticated"] is True
    assert data["csrf"]
    assert data["agent"]["enabled"] is False
    assert "mdt_live" not in session.text


def test_rejects_bad_host_and_csrf(bridge: ConnectBridge):
    bad_host = httpx.get(
        bridge.base_url + "/connect/v1/session",
        headers={"Host": f"evil.example:{bridge.bound_port}"},
    )
    assert bad_host.status_code == 403
    assert bad_host.json()["reason_code"] == "host_rejected"

    session = _get(bridge, "/connect/v1/session").json()
    missing = httpx.post(
        bridge.base_url + "/connect/v1/library/tags/batch",
        headers={
            "Host": f"127.0.0.1:{bridge.bound_port}",
            "Origin": f"http://127.0.0.1:{bridge.bound_port}",
            "Content-Type": "application/json",
        },
        # CSRF is rejected before the bridge reads a request body. Keep this
        # focused contract check bodyless; the body-bearing rejection and
        # connection-close behavior is covered below.
        content=b"",
    )
    assert missing.status_code == 403
    assert missing.json()["reason_code"] == "csrf_rejected"

    wrong = _post(
        bridge,
        "/connect/v1/library/tags/batch",
        None,
        csrf="nope",
    )
    assert wrong.status_code == 403
    assert wrong.json()["reason_code"] == "csrf_rejected"
    # Ensure valid csrf path reaches the library adapter.
    bridge.client._request.return_value = {"changed_count": 0, "document_ids": [1]}  # type: ignore[attr-defined]
    ok = _post(
        bridge,
        "/connect/v1/library/tags/batch",
        {"document_ids": [1], "add": ["TCES"], "remove": [], "dry_run": True},
        csrf=session["csrf"],
    )
    assert ok.status_code == 200
    bridge.client._request.assert_called()  # type: ignore[attr-defined]
    kwargs = bridge.client._request.call_args  # type: ignore[attr-defined]
    assert kwargs.args[0] == "POST"
    assert kwargs.kwargs["json"]["dry_run"] is True


def test_library_list_and_export(bridge: ConnectBridge):
    bridge.client._request.return_value = {  # type: ignore[attr-defined]
        "items": [
            {
                "id": 11,
                "title": "Attention Is All You Need",
                "authors": ["Vaswani"],
                "year": 2017,
                "venue": "NeurIPS",
                "doi": "10.48550/arXiv.1706.03762",
                "tags": ["transformers"],
                "has_saved_text": True,
            }
        ]
    }
    docs = _get(bridge, "/connect/v1/library/documents").json()
    assert docs["count"] == 1
    assert docs["items"][0]["title"].startswith("Attention")

    session = _get(bridge, "/connect/v1/session").json()
    response = MagicMock()
    response.content = b"@article{mdtero11,}"
    response.headers = {
        "content-type": "application/x-bibtex",
        "content-disposition": 'attachment; filename="mdtero-references.bib"',
        "x-mdtero-export": "bibtex",
    }
    response.raise_for_status = MagicMock()
    bridge.client._raw_request.return_value = response  # type: ignore[attr-defined]
    exported = _post(
        bridge,
        "/connect/v1/library/export",
        {"document_ids": [11], "format": "bibtex"},
        csrf=session["csrf"],
    )
    assert exported.status_code == 200
    assert exported.headers["x-mdtero-export"] == "bibtex"
    assert b"mdtero11" in exported.content


def test_library_client_requires_explicit_dry_run_semantics():
    client = MdteroClient(MdteroConfig(api_key="mdt_live_test"))
    client._request = MagicMock(return_value={"changed_count": 1})  # type: ignore[method-assign]
    LibraryClient(client).update_tags(document_ids=[1], add=["a"], dry_run=True)
    assert client._request.call_args.kwargs["json"]["dry_run"] is True  # type: ignore[attr-defined]
    LibraryClient(client).update_tags(document_ids=[1], add=["a"], dry_run=False)
    assert client._request.call_args.kwargs["json"]["dry_run"] is False  # type: ignore[attr-defined]


def test_ipv6_loopback_bind_and_session():
    # Some CI hosts disable IPv6 entirely; distinguish that from a bridge bug.
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as probe:
            probe.bind(("::1", 0))
    except OSError:
        pytest.skip("IPv6 loopback is unavailable on this host")
    client = MdteroClient(MdteroConfig())
    with ConnectBridge(host="::1", port=0, client=client, static_dir=APP_DIR) as instance:
        assert instance.base_url == f"http://[::1]:{instance.bound_port}"
        response = httpx.get(instance.base_url + "/connect/v1/session", trust_env=False)
        assert response.status_code == 200
        assert response.json()["bridge"]["host"] == "::1"


def test_malformed_origin_gets_a_forbidden_response(bridge: ConnectBridge):
    response = httpx.get(
        bridge.base_url + "/connect/v1/session",
        headers={"Origin": "http://127.0.0.1:bad"},
    )
    assert response.status_code == 403
    assert response.json()["reason_code"] == "origin_rejected"


@pytest.mark.parametrize(
    ("path", "headers", "expected_status", "reason_code"),
    [
        ("/connect/v1/library/tags/batch", {"X-Mdtero-CSRF": ""}, 403, "csrf_rejected"),
        ("/connect/v1/library/tags/batch", {"X-Mdtero-CSRF": "invalid"}, 403, "csrf_rejected"),
        ("/connect/v1/library/tags/batch", {"Origin": "http://evil.example"}, 403, "origin_rejected"),
        ("/connect/v1/library/tags/batch", {"Host": "evil.example"}, 403, "host_rejected"),
        ("/not-an-api", {}, 404, "not_found"),
    ],
)
def test_rejected_post_body_does_not_corrupt_the_next_client_request(
    bridge: ConnectBridge, path: str, headers: dict[str, str], expected_status: int, reason_code: str
):
    session = _get(bridge, "/connect/v1/session").json()
    with httpx.Client(
        base_url=bridge.base_url,
        headers={"Origin": bridge.base_url, "X-Mdtero-CSRF": session["csrf"]},
    ) as client:
        rejected = client.post(path, headers=headers, json={"document_ids": [1], "dry_run": True})
        assert rejected.status_code == expected_status
        assert rejected.json()["reason_code"] == reason_code
        assert rejected.headers["connection"] == "close"
        # The same client's next request must reconnect cleanly, without a 501
        # from parsing the rejected request's JSON as an HTTP method.
        next_request = client.post("/connect/v1/library/tags/batch", json={"document_ids": [1]})
        assert next_request.status_code == 400
        assert next_request.json()["reason_code"] == "dry_run_required"
        assert client.get("/connect/v1/session").status_code == 200
    bridge.client._request.assert_not_called()  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("framing_headers", "expected_status", "reason_code"),
    [
        (["Content-Length: -1"], 400, "invalid_content_length"),
        (["Content-Length: invalid"], 400, "invalid_content_length"),
        (["Content-Length:"], 400, "invalid_content_length"),
        (["Content-Length: 2097153"], 413, "body_too_large"),
        (["Content-Length: " + "9" * 5000], 413, "body_too_large"),
        (["Content-Length: 2", "Content-Length: 2"], 400, "invalid_body_framing"),
        (["Transfer-Encoding: chunked"], 400, "invalid_body_framing"),
    ],
)
def test_rejected_body_framing_closes_without_dispatching_pipelined_bytes(
    bridge: ConnectBridge, framing_headers: list[str], expected_status: int, reason_code: str
):
    session = _get(bridge, "/connect/v1/session").json()
    headers = [
        "POST /connect/v1/library/tags/batch HTTP/1.1",
        f"Host: 127.0.0.1:{bridge.bound_port}",
        f"Origin: {bridge.base_url}",
        f"X-Mdtero-CSRF: {session['csrf']}",
        *framing_headers,
    ]
    # A second request must never be read out of an unconsumed rejected body.
    request = (
        "\r\n".join(headers)
        + "\r\n\r\n{}\r\n"
        + f"GET /connect/v1/session HTTP/1.1\r\nHost: 127.0.0.1:{bridge.bound_port}\r\n\r\n"
    ).encode()
    with socket.create_connection(("127.0.0.1", bridge.bound_port), timeout=2) as connection:
        connection.sendall(request)
        chunks = []
        while chunk := connection.recv(8192):
            chunks.append(chunk)
    response = b"".join(chunks)
    assert response.startswith(f"HTTP/1.1 {expected_status} ".encode())
    assert b"Connection: close\r\n" in response
    assert response.count(b"HTTP/1.1 ") == 1
    assert json.loads(response.split(b"\r\n\r\n", 1)[1])["reason_code"] == reason_code
    bridge.client._request.assert_not_called()  # type: ignore[attr-defined]
