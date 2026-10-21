from __future__ import annotations

import pytest

from mdtero.connect.security import (
    ZOTERO_LOCAL_BASE,
    approved_zotero_url,
    assert_loopback_bind,
    csrf_matches,
    host_header_allowed,
    is_loopback_host,
    new_csrf_token,
    origin_allowed,
    reject_user_supplied_zotero_endpoint,
)


def test_csrf_roundtrip():
    token = new_csrf_token()
    assert csrf_matches(token, token)
    assert not csrf_matches(token, token + "x")
    assert not csrf_matches(token, None)


def test_loopback_hosts_and_bind():
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("localhost:8741")
    assert is_loopback_host("[::1]:8741")
    assert not is_loopback_host("example.com")
    assert assert_loopback_bind("127.0.0.1") == "127.0.0.1"
    with pytest.raises(ValueError):
        assert_loopback_bind("0.0.0.0")


def test_origin_and_host_gates():
    assert origin_allowed("http://127.0.0.1:8741", port=8741)
    assert origin_allowed("http://localhost:8741", port=8741)
    assert not origin_allowed("http://127.0.0.1:9999", port=8741)
    assert not origin_allowed("https://127.0.0.1:8741", port=8741)
    assert not origin_allowed("http://evil.example", port=8741)
    assert host_header_allowed("127.0.0.1:8741", port=8741)
    assert host_header_allowed("localhost:8741", port=8741)
    assert not host_header_allowed("evil.example:8741", port=8741)


def test_zotero_endpoint_is_fixed_loopback():
    assert approved_zotero_url("/connector/ping").startswith(ZOTERO_LOCAL_BASE)
    with pytest.raises(ValueError):
        approved_zotero_url("http://evil.example/x")
    with pytest.raises(ValueError):
        approved_zotero_url("/../etc/passwd")
    with pytest.raises(ValueError):
        reject_user_supplied_zotero_endpoint("http://127.0.0.1:9")
    reject_user_supplied_zotero_endpoint(None)
