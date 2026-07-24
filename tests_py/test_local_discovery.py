from __future__ import annotations

import json
from typing import Any

import pytest

from mdtero.client import DiscoveryError, MdteroClient
from mdtero.config import AcademicKeys, MdteroConfig, load_config, save_config
from mdtero.discovery_providers import resolve_provider_names
from mdtero.discovery_providers.scihub import download_pdf as scihub_download
from mdtero.local_discovery import LocalDiscoveryError, search_local_discovery


def test_resolve_provider_names_profiles():
    assert "openalex" in resolve_provider_names("free_core")
    assert "arxiv" in resolve_provider_names("free_core")
    assert "scihub" not in resolve_provider_names("all")
    assert resolve_provider_names("arxiv,pubmed") == ("arxiv", "pubmed")


def test_search_local_discovery_merges_and_dedupes(monkeypatch):
    calls: list[str] = []

    def fake_openalex(query, *, limit=10, page=1, api_key=None, api_base_url="", **_):
        calls.append("openalex")
        return {
            "authenticated": False,
            "items": [
                {
                    "title": "Shared paper",
                    "doi": "10.1000/shared",
                    "external_id": "W1",
                    "source": "openalex",
                    "external_source": "openalex",
                },
                {
                    "title": "OpenAlex only",
                    "doi": "10.1000/oa",
                    "external_id": "W2",
                    "source": "openalex",
                    "external_source": "openalex",
                },
            ],
        }

    def fake_s2(query, *, limit=10, offset=0, page=1, api_key=None, api_base_url="", **_):
        calls.append("semantic_scholar")
        return {
            "authenticated": False,
            "items": [
                {
                    "title": "Shared paper",
                    "doi": "10.1000/shared",
                    "external_id": "S1",
                    "source": "semantic_scholar",
                    "external_source": "semantic_scholar",
                },
                {
                    "title": "S2 only",
                    "doi": "10.1000/s2",
                    "external_id": "S2",
                    "source": "semantic_scholar",
                    "external_source": "semantic_scholar",
                },
            ],
        }

    monkeypatch.setitem(
        __import__("mdtero.discovery_providers", fromlist=["PROVIDER_SEARCHERS"]).PROVIDER_SEARCHERS,
        "openalex",
        fake_openalex,
    )
    monkeypatch.setitem(
        __import__("mdtero.discovery_providers", fromlist=["PROVIDER_SEARCHERS"]).PROVIDER_SEARCHERS,
        "semantic_scholar",
        fake_s2,
    )

    result = search_local_discovery(
        "graph neural networks",
        limit=3,
        page=1,
        providers=("openalex", "semantic_scholar"),
    )

    assert set(calls) == {"openalex", "semantic_scholar"}
    assert result["source"] == "local_multi_source"
    assert [item["doi"] for item in result["items"]] == ["10.1000/shared", "10.1000/s2", "10.1000/oa"]
    assert result["discovery_diagnostics"]["mode"] == "local"
    assert result["discovery_diagnostics"]["scihub_enabled_for_search"] is False


def test_search_local_discovery_fails_when_all_providers_fail(monkeypatch):
    def boom(*args: Any, **kwargs: Any):
        raise LocalDiscoveryError("rate limited", reason_code="provider_rate_limited")

    monkeypatch.setitem(
        __import__("mdtero.discovery_providers", fromlist=["PROVIDER_SEARCHERS"]).PROVIDER_SEARCHERS,
        "openalex",
        boom,
    )
    monkeypatch.setitem(
        __import__("mdtero.discovery_providers", fromlist=["PROVIDER_SEARCHERS"]).PROVIDER_SEARCHERS,
        "semantic_scholar",
        boom,
    )

    with pytest.raises(LocalDiscoveryError) as exc:
        search_local_discovery("rag", limit=1, providers=("openalex", "semantic_scholar"))
    assert exc.value.reason_code == "local_discovery_failed"


def test_client_discover_defaults_to_local(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_local(self, query, *, limit, page=1, providers=None):
        captured["query"] = query
        captured["limit"] = limit
        captured["page"] = page
        captured["providers"] = providers
        return {
            "source": "local_multi_source",
            "items": [{"title": "Local paper"}],
            "meta": {"count": 1, "page": page, "per_page": limit, "has_next": False, "has_previous": False},
            "discovery_diagnostics": {"mode": "local", "server_openalex_attempted": False},
        }

    def fake_server(self, query, *, limit, page=1):
        raise AssertionError("server discovery should not run by default")

    monkeypatch.setattr(MdteroClient, "_local_discovery_search", fake_local)
    monkeypatch.setattr(MdteroClient, "_server_discovery_search", fake_server)

    result = MdteroClient(config=MdteroConfig(api_key="key")).discover("rag", limit=2, page=3)

    assert result["source"] == "local_multi_source"
    assert captured == {"query": "rag", "limit": 2, "page": 3, "providers": None}


def test_client_discover_source_server_uses_api(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_request(self, method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["params"] = kwargs.get("params")
        return {
            "items": [{"title": "OA paper"}],
            "meta": {"count": 1, "page": 1, "per_page": 1, "has_next": False, "has_previous": False},
        }

    monkeypatch.setattr(MdteroClient, "_request", fake_request)

    result = MdteroClient(config=MdteroConfig(api_key="key")).discover("rag", limit=1, page=2, source="server")

    assert result["source"] == "openalex_server"
    assert captured == {
        "method": "GET",
        "path": "/api/v1/discovery/search",
        "params": {"query": "rag", "limit": 1, "page": 2},
    }
    assert result["discovery_diagnostics"]["server_openalex_attempted"] is True


def test_scihub_disabled_by_default(tmp_path):
    with pytest.raises(LocalDiscoveryError) as exc:
        scihub_download("10.1000/demo", output_dir=tmp_path, enabled=False)
    assert exc.value.reason_code == "scihub_disabled"


def test_academic_keys_roundtrip_openalex_and_s2(monkeypatch, tmp_path):
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    save_config(
        MdteroConfig(
            academic=AcademicKeys(
                openalex_api_key="oa-secret",
                semantic_scholar_api_key="s2-secret",
                unpaywall_email="me@example.com",
                enable_scihub=False,
            )
        )
    )
    loaded = load_config()
    assert loaded.academic.openalex_api_key == "oa-secret"
    assert loaded.academic.semantic_scholar_api_key == "s2-secret"
    assert loaded.academic.unpaywall_email == "me@example.com"
    assert loaded.academic.enable_scihub is False
    save_config(loaded)
    again = json.loads((tmp_path / "config" / "config.json").read_text(encoding="utf-8"))
    assert again["academic"]["openalex_api_key"] == "oa-secret"
    assert again["academic"]["enable_scihub"] is False
