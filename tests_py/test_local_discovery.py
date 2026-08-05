from __future__ import annotations

import json
from typing import Any

import pytest

from mdtero.client import DiscoveryError, MdteroClient
from mdtero.config import AcademicKeys, MdteroConfig, load_config, save_config
from mdtero.discovery_providers import resolve_enrichers, resolve_provider_names
from mdtero.discovery_providers.scihub import download_pdf as scihub_download
from mdtero.local_discovery import LocalDiscoveryError, search_local_discovery


def test_resolve_provider_names_profiles():
    assert resolve_provider_names(None) == ("openalex",)
    assert resolve_provider_names("default") == ("openalex",)
    assert resolve_provider_names("openalex") == ("openalex",)
    free = resolve_provider_names("free_core")
    assert "openalex" in free
    assert "arxiv" in free
    assert "semantic_scholar" not in free  # enrich-only by default
    assert "clinicaltrials" not in free
    assert "scihub" not in resolve_provider_names("all")
    assert resolve_provider_names("arxiv,pubmed") == ("arxiv", "pubmed")
    assert resolve_provider_names(None, entity_type="trial") == ("clinicaltrials",)
    assert resolve_enrichers(None, selected_providers=("openalex",)) == ("semantic_scholar",)
    assert resolve_enrichers("none") == ()
    assert resolve_enrichers(None, entity_type="trial") == ()


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
                    "year": 2024,
                    "citation_count": 2,
                    "citation_count_source": "openalex",
                },
                {
                    "title": "OpenAlex only",
                    "doi": "10.1000/oa",
                    "external_id": "W2",
                    "source": "openalex",
                    "external_source": "openalex",
                    "year": 2023,
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
                    "year": 2024,
                    "citation_count": 5,
                    "citation_count_source": "semantic_scholar",
                },
                {
                    "title": "S2 only",
                    "doi": "10.1000/s2",
                    "external_id": "S2",
                    "source": "semantic_scholar",
                    "external_source": "semantic_scholar",
                    "year": 2022,
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
        enrich="none",
    )

    assert set(calls) == {"openalex", "semantic_scholar"}
    assert result["source"] == "local_multi_source"
    dois = {item["doi"] for item in result["items"]}
    assert dois == {"10.1000/shared", "10.1000/s2", "10.1000/oa"}
    shared = next(item for item in result["items"] if item["doi"] == "10.1000/shared")
    assert set(shared["sources"]) == {"openalex", "semantic_scholar"}
    assert shared["citation_counts"]["openalex"] == 2
    assert shared["citation_counts"]["semantic_scholar"] == 5
    assert result["sources_queried"] == ["openalex", "semantic_scholar"]
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
        search_local_discovery("rag", limit=1, providers=("openalex", "semantic_scholar"), enrich="none")
    assert exc.value.reason_code == "local_discovery_failed"


def test_search_local_discovery_default_enriches_via_s2(monkeypatch):
    def fake_openalex(query, *, limit=10, page=1, **_):
        return {
            "authenticated": False,
            "items": [
                {
                    "title": "Paper",
                    "doi": "10.1000/enrich-me",
                    "external_id": "W9",
                    "source": "openalex",
                    "year": 2024,
                }
            ],
        }

    monkeypatch.setitem(
        __import__("mdtero.discovery_providers", fromlist=["PROVIDER_SEARCHERS"]).PROVIDER_SEARCHERS,
        "openalex",
        fake_openalex,
    )

    def fake_enrich(records, *, api_key=None, api_base_url="", limit=None):
        for row in records:
            row["citation_count"] = 42
            row["citation_count_source"] = "semantic_scholar"
            row["citation_counts"] = {"semantic_scholar": 42}
            row.setdefault("sources", []).append("semantic_scholar")
        return {
            "results": records,
            "errors": [],
            "skipped": [],
            "sources_queried": ["semantic_scholar"],
            "sources_succeeded": ["semantic_scholar"],
        }

    monkeypatch.setattr(
        "mdtero.discovery_providers.semantic_scholar.enrich_records",
        fake_enrich,
    )

    result = search_local_discovery("topic", limit=1, providers=("openalex",))
    assert result["items"][0]["citation_counts"]["semantic_scholar"] == 42
    assert "semantic_scholar" in result["sources_succeeded"]
    assert result["meta"]["enrichment_sources"] == ["semantic_scholar"]


def test_trial_entity_uses_clinicaltrials(monkeypatch):
    def fake_ctg(query, *, limit=10, page=1, **_):
        return {
            "authenticated": False,
            "entity_type": "trial",
            "items": [
                {
                    "title": "Lung cancer immunotherapy trial",
                    "source": "clinicaltrials",
                    "entity_type": "trial",
                    "nct_id": "NCT01234567",
                    "external_id": "NCT01234567",
                    "year": 2021,
                }
            ],
        }

    monkeypatch.setitem(
        __import__("mdtero.discovery_providers", fromlist=["PROVIDER_SEARCHERS"]).PROVIDER_SEARCHERS,
        "clinicaltrials",
        fake_ctg,
    )
    result = search_local_discovery("lung cancer", limit=5, entity_type="trial", enrich="none")
    assert result["entity_type"] == "trial"
    assert result["items"][0]["nct_id"] == "NCT01234567"
    assert result["sources_queried"] == ["clinicaltrials"]


def test_client_discover_defaults_to_auto_local_first(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_local(
        self,
        query,
        *,
        limit,
        page=1,
        providers=None,
        enrich=None,
        entity_type="publication",
        relevance="baseline",
        relax=False,
    ):
        captured["query"] = query
        captured["limit"] = limit
        captured["page"] = page
        captured["providers"] = providers
        captured["enrich"] = enrich
        captured["entity_type"] = entity_type
        captured["relevance"] = relevance
        captured["relax"] = relax
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
    assert captured == {
        "query": "rag",
        "limit": 2,
        "page": 3,
        "providers": None,
        "enrich": None,
        "entity_type": "publication",
        "relevance": "baseline",
        "relax": False,
    }


def test_client_discover_auto_falls_back_to_server_when_local_fails(monkeypatch):
    calls: list[str] = []

    def fake_local(*_args, **_kwargs):
        calls.append("local")
        raise DiscoveryError(
            {
                "error_code": "discovery_failed",
                "reason_code": "openalex_rate_limited",
                "message": "local OpenAlex unavailable",
            }
        )

    def fake_server(self, query, *, limit, page):
        calls.append("server")
        return {
            "items": [{"title": "Server paper"}],
            "meta": {"count": 1, "page": page, "per_page": limit, "has_next": False, "has_previous": False},
        }

    monkeypatch.setattr(MdteroClient, "_local_discovery_search", fake_local)
    monkeypatch.setattr(MdteroClient, "_server_discovery_search", fake_server)

    result = MdteroClient(config=MdteroConfig(api_key="key")).discover("rag", limit=2, page=3)

    assert calls == ["local", "server"]
    assert result["source"] == "openalex_server"
    assert result["discovery_diagnostics"]["mode"] == "auto"
    assert result["discovery_diagnostics"]["local_fallback"]["reason_code"] == "openalex_rate_limited"


def test_client_discover_server_skips_local_campus_proxy_check(monkeypatch):
    def fake_server(self, query, *, limit, page):
        return {
            "items": [{"title": "Server paper"}],
            "meta": {"count": 1, "page": page, "per_page": limit, "has_next": False, "has_previous": False},
        }

    monkeypatch.setattr(MdteroClient, "_server_discovery_search", fake_server)

    result = MdteroClient(
        config=MdteroConfig(api_key="key", require_campus_proxy=True),
    ).discover("rag", source="server")

    assert result["source"] == "openalex_server"
    assert result["discovery_diagnostics"]["mode"] == "server"


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
