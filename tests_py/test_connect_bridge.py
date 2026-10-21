from __future__ import annotations

import json
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


def _post(bridge: ConnectBridge, path: str, payload: dict, *, csrf: str):
    return httpx.post(
        bridge.base_url + path,
        headers={
            "Host": f"127.0.0.1:{bridge.bound_port}",
            "Origin": f"http://127.0.0.1:{bridge.bound_port}",
            "X-Mdtero-CSRF": csrf,
            "Content-Type": "application/json",
        },
        content=json.dumps(payload),
    )


def test_session_and_static(bridge: ConnectBridge):
    home = _get(bridge, "/")
    assert home.status_code == 200
    assert b"Mdtero Connect" in home.content
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
        content=json.dumps({"document_ids": [1], "add": ["x"], "dry_run": True}),
    )
    assert missing.status_code == 403
    assert missing.json()["reason_code"] == "csrf_rejected"

    wrong = _post(
        bridge,
        "/connect/v1/library/tags/batch",
        {"document_ids": [1], "add": ["x"], "dry_run": True},
        csrf="nope",
    )
    assert wrong.status_code == 403
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
