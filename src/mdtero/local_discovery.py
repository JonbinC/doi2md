"""Client-side multi-source academic discovery.

Absorbs paper-search-mcp coverage into Mdtero's existing local discover path.
Keys are optional for most sources. Sci-Hub is download-only and opt-in.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .discovery_http import LocalDiscoveryError, normalize_doi
from .discovery_providers import (
    FREE_CORE_PROVIDERS,
    PROVIDER_SEARCHERS,
    provider_capability_matrix,
    resolve_provider_names,
)
from .discovery_providers import openalex as openalex_provider
from .discovery_providers import semantic_scholar as semantic_provider

DEFAULT_OPENALEX_API_BASE = openalex_provider.DEFAULT_API_BASE
DEFAULT_SEMANTIC_SCHOLAR_API_BASE = semantic_provider.DEFAULT_API_BASE

__all__ = [
    "LocalDiscoveryError",
    "search_local_discovery",
    "search_openalex_local",
    "search_semantic_scholar_local",
    "provider_capability_matrix",
    "FREE_CORE_PROVIDERS",
]


def search_openalex_local(
    query: str,
    *,
    limit: int = 10,
    page: int = 1,
    api_key: str | None = None,
    api_base_url: str = DEFAULT_OPENALEX_API_BASE,
) -> dict[str, Any]:
    return openalex_provider.search(
        query,
        limit=limit,
        page=page,
        api_key=api_key,
        api_base_url=api_base_url,
    )


def search_semantic_scholar_local(
    query: str,
    *,
    limit: int = 10,
    offset: int = 0,
    api_key: str | None = None,
    api_base_url: str = DEFAULT_SEMANTIC_SCHOLAR_API_BASE,
) -> dict[str, Any]:
    return semantic_provider.search(
        query,
        limit=limit,
        offset=offset,
        api_key=api_key,
        api_base_url=api_base_url,
    )


def search_local_discovery(
    query: str,
    *,
    limit: int = 10,
    page: int = 1,
    providers: str | tuple[str, ...] | list[str] | None = None,
    openalex_api_key: str | None = None,
    semantic_scholar_api_key: str | None = None,
    core_api_key: str | None = None,
    doaj_api_key: str | None = None,
    zenodo_access_token: str | None = None,
    ieee_api_key: str | None = None,
    acm_api_key: str | None = None,
    unpaywall_email: str | None = None,
    proxy_url: str | None = None,
    openalex_api_base: str = DEFAULT_OPENALEX_API_BASE,
    semantic_scholar_api_base: str = DEFAULT_SEMANTIC_SCHOLAR_API_BASE,
    max_workers: int = 8,
) -> dict[str, Any]:
    query_text = str(query or "").strip()
    if not query_text:
        raise LocalDiscoveryError("query is required", reason_code="discovery_query_missing")

    page_number = max(1, int(page or 1))
    per_page = max(1, min(int(limit or 10), 25))
    selected = resolve_provider_names(providers)
    credentials = {
        "openalex_api_key": openalex_api_key,
        "semantic_scholar_api_key": semantic_scholar_api_key,
        "core_api_key": core_api_key,
        "doaj_api_key": doaj_api_key,
        "zenodo_access_token": zenodo_access_token,
        "ieee_api_key": ieee_api_key,
        "acm_api_key": acm_api_key,
        "unpaywall_email": unpaywall_email,
        "proxy_url": proxy_url,
        "openalex_api_base": openalex_api_base,
        "semantic_scholar_api_base": semantic_scholar_api_base,
    }

    diagnostics: list[dict[str, Any]] = []
    buckets: list[list[dict[str, Any]]] = []
    bucket_by_provider: dict[str, list[dict[str, Any]]] = {}

    def _run(name: str) -> tuple[str, dict[str, Any] | None, LocalDiscoveryError | None]:
        searcher = PROVIDER_SEARCHERS.get(name)
        if searcher is None:
            return name, None, LocalDiscoveryError("unknown provider", reason_code="unknown_provider")
        try:
            payload = searcher(
                query_text,
                limit=per_page,
                page=page_number,
                **_provider_kwargs(name, credentials),
            )
            return name, payload, None
        except LocalDiscoveryError as exc:
            return name, None, exc
        except Exception as exc:  # pragma: no cover - defensive
            return name, None, LocalDiscoveryError(str(exc), reason_code="provider_unexpected_error", detail=str(exc))

    workers = max(1, min(int(max_workers or 1), len(selected) or 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_run, name) for name in selected]
        for future in as_completed(futures):
            name, payload, error = future.result()
            if error is not None:
                diagnostics.append(
                    {
                        "provider": name,
                        "status": "failed",
                        "reason_code": error.reason_code,
                        "detail": str(error.detail or error),
                    }
                )
                continue
            assert payload is not None
            items = [item for item in payload.get("items") or [] if isinstance(item, dict)]
            for item in items:
                item.setdefault("source", name)
                item.setdefault("external_source", name)
                item.update(_query_match_summary(item, query=query_text))
            bucket_by_provider[name] = items
            diagnostics.append(
                {
                    "provider": name,
                    "status": "succeeded",
                    "item_count": len(items),
                    "authenticated": bool(payload.get("authenticated")),
                }
            )

    # Preserve requested provider order for round-robin fairness.
    for name in selected:
        if name in bucket_by_provider:
            buckets.append(bucket_by_provider[name])

    merged = _merge_discovery_items(buckets, limit=per_page)
    if not merged and not any(row.get("status") == "succeeded" for row in diagnostics):
        raise LocalDiscoveryError(
            "Local discovery providers failed.",
            reason_code="local_discovery_failed",
            detail={"providers": diagnostics},
        )

    used = [row["provider"] for row in diagnostics if row.get("status") == "succeeded"]
    return {
        "provider": "+".join(used) if used else "local",
        "source": "local_multi_source",
        "query": query_text,
        "items": merged,
        "meta": {
            "count": len(merged),
            "page": page_number,
            "per_page": per_page,
            "has_previous": page_number > 1,
            "has_next": len(merged) >= per_page,
            "local": True,
            "sources": list(selected),
            "sources_succeeded": used,
        },
        "discovery_diagnostics": {
            "mode": "local",
            "providers": _ordered_diagnostics(diagnostics, selected),
            "server_openalex_attempted": False,
            "scihub_enabled_for_search": False,
        },
    }


def _provider_kwargs(name: str, credentials: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if name == "openalex":
        kwargs["api_key"] = credentials.get("openalex_api_key")
        kwargs["api_base_url"] = credentials.get("openalex_api_base")
    elif name in {"semantic_scholar", "semantic"}:
        kwargs["api_key"] = credentials.get("semantic_scholar_api_key")
        kwargs["api_base_url"] = credentials.get("semantic_scholar_api_base")
    elif name == "core":
        kwargs["api_key"] = credentials.get("core_api_key")
    elif name == "doaj":
        kwargs["api_key"] = credentials.get("doaj_api_key")
    elif name == "zenodo":
        kwargs["access_token"] = credentials.get("zenodo_access_token")
    elif name == "ieee":
        kwargs["api_key"] = credentials.get("ieee_api_key")
    elif name == "acm":
        kwargs["api_key"] = credentials.get("acm_api_key")
    elif name == "unpaywall":
        kwargs["email"] = credentials.get("unpaywall_email")
    elif name == "google_scholar":
        kwargs["proxy_url"] = credentials.get("proxy_url")
    elif name == "crossref":
        kwargs["mailto"] = credentials.get("unpaywall_email") or "mdtero@mdtero.com"
    return kwargs


def _ordered_diagnostics(diagnostics: list[dict[str, Any]], selected: tuple[str, ...]) -> list[dict[str, Any]]:
    by_name = {str(row.get("provider")): row for row in diagnostics}
    return [by_name[name] for name in selected if name in by_name]


def _query_match_summary(item: dict[str, Any], *, query: str) -> dict[str, Any]:
    import re

    tokens = [
        token
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9+\-]{1,}", str(query or "").lower())
        if token not in {"and", "the", "for", "with", "from", "into", "via", "using", "review"}
    ]
    if not tokens:
        return {}
    haystack = " ".join(
        str(value or "")
        for value in (item.get("title"), item.get("venue"), item.get("abstract_preview"), item.get("doi"))
    ).lower()
    matched = sorted({token for token in tokens if token in haystack})
    score = round(len(matched) / len(set(tokens)), 4) if tokens else 0.0
    return {
        "query_match_score": score,
        "query_matched_terms": matched,
        "query_match_warning": "low_query_term_overlap" if score < 0.25 else None,
    }


def _merge_discovery_items(buckets: list[list[dict[str, Any]]], *, limit: int) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    indexes = [0] * len(buckets)
    while len(merged) < limit:
        progressed = False
        for bucket_index, bucket in enumerate(buckets):
            cursor = indexes[bucket_index]
            while cursor < len(bucket):
                item = bucket[cursor]
                cursor += 1
                indexes[bucket_index] = cursor
                key = _item_key(item)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)
                progressed = True
                break
            if len(merged) >= limit:
                break
        if not progressed:
            break
    return merged


def _item_key(item: dict[str, Any]) -> str:
    doi = normalize_doi(item.get("doi"))
    if doi:
        return f"doi:{doi.lower()}"
    for field in ("external_id", "parse_input_value", "title"):
        value = str(item.get(field) or "").strip().lower()
        if value:
            return f"{field}:{value}"
    return f"row:{id(item)}"
