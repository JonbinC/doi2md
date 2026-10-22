"""Real local listeners must start even when reverse DNS is unavailable."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from pathlib import Path
import socket
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from mdtero.auth import run_web_login
from mdtero.client import MdteroClient
from mdtero.config import MdteroConfig
from mdtero.connect.bridge import ConnectBridge
from mdtero.loopback import LoopbackThreadingHTTPServer


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_real_connect_listener_does_not_resolve_reverse_dns(monkeypatch, host):
    if host == "::1":
        try:
            with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as probe:
                probe.bind((host, 0))
        except OSError:
            pytest.skip("IPv6 loopback is unavailable on this host")
    reverse_dns = MagicMock(side_effect=AssertionError("Local startup must not depend on reverse DNS"))
    monkeypatch.setattr(socket, "getfqdn", reverse_dns)
    client = MdteroClient(MdteroConfig(api_key="synthetic-local-key"))
    static = Path(__file__).resolve().parents[1] / "connect" / "app"
    with ConnectBridge(host=host, port=0, client=client, static_dir=static) as bridge:
        url = bridge.base_url
        assert bridge._httpd.server_name == host
        assert bridge._httpd.server_port == bridge.bound_port
        response = httpx.get(url + "/connect/v1/session", trust_env=False, timeout=2)
        assert response.status_code == 200 and response.json()["csrf"]
        assert httpx.get(url, trust_env=False, timeout=2).status_code == 200
    with pytest.raises(httpx.TransportError):
        httpx.get(url, trust_env=False, timeout=1)
    reverse_dns.assert_not_called()


def test_real_oauth_callback_does_not_resolve_reverse_dns(monkeypatch):
    reverse_dns = MagicMock(side_effect=AssertionError("OAuth startup must not depend on reverse DNS"))
    monkeypatch.setattr(socket, "getfqdn", reverse_dns)
    seen = {}

    def browser(url):
        parameters = parse_qs(urlparse(url).query)
        seen["callback"] = parameters["cli_callback"][0]
        response = httpx.post(seen["callback"], json={"state": parameters["cli_state"][0], "apiKey": "synthetic-oauth-key"},
                              trust_env=False, timeout=2)
        assert response.status_code == 200

    result = run_web_login("https://mdtero.com", open_browser=browser, timeout_seconds=3)
    assert result.api_key == "synthetic-oauth-key"
    with pytest.raises(httpx.TransportError):
        httpx.post(seen["callback"], json={}, trust_env=False, timeout=1)
    reverse_dns.assert_not_called()


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "localhost", "192.0.2.1", "example.test"])
def test_loopback_http_server_rejects_every_nonliteral_bind(monkeypatch, host):
    reverse_dns = MagicMock(side_effect=AssertionError("Rejected binds must not resolve DNS"))
    monkeypatch.setattr(socket, "getfqdn", reverse_dns)
    with pytest.raises(ValueError, match="127.0.0.1 or ::1"):
        LoopbackThreadingHTTPServer((host, 0), BaseHTTPRequestHandler)
    reverse_dns.assert_not_called()
