"""Client-side multi-source academic discovery.

Absorbs paper-search-mcp coverage plus nature-academic-search merge/enrich patterns.
Keys are optional for most sources. Sci-Hub is download-only and opt-in.
Semantic Scholar defaults to strong-ID enrich (not free_core fan-out).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .discovery_http import LocalDiscoveryError
from .discovery_merge import deduplicate_discovery_records, prepare_discovery_record
from .discovery_providers import (
    FREE_CORE_PROVIDERS,
    PROVIDER_SEARCHERS,
    provider_capability_matrix,
    resolve_enrichers,
    resolve_provider_names,
)
from .discovery_providers import openalex as openalex_provider
from .discovery_providers import semantic_scholar as semantic_provider
from .discovery_rank import rank_discovery_items, sanitize_discovery_item

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
    enrich: str | tuple[str, ...] | list[str] | None = None,
    entity_type: str = "publication",
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
    max_workers: int = 5,
) -> dict[str, Any]:
    query_text = str(query or "").strip()
    if not query_text:
        raise LocalDiscoveryError("query is required", reason_code="discovery_query_missing")

    entity = str(entity_type or "publication").strip().lower()
    if entity not in {"publication", "trial"}:
        raise LocalDiscoveryError(
            f"Unsupported entity_type: {entity_type}",
            reason_code="invalid_discovery_entity_type",
        )

    page_number = max(1, int(page or 1))
    per_page = max(1, min(int(limit or 10), 25))
    selected = resolve_provider_names(providers, entity_type=entity)
    enrichers = resolve_enrichers(enrich, entity_type=entity, selected_providers=selected)
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
    errors: list[dict[str, Any]] = []
    bucket_by_provider: dict[str, list[dict[str, Any]]] = {}
    sources_queried = list(selected)
    sources_succeeded: list[str] = []
    sources_skipped: list[dict[str, Any]] = []

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
                errors.append(
                    {
                        "source": name,
                        "error": str(error),
                        "reason_code": error.reason_code,
                        "kind": "rate_limited" if error.reason_code == "provider_rate_limited" else "source_error",
                    }
                )
                continue
            assert payload is not None
            items = [item for item in payload.get("items") or [] if isinstance(item, dict)]
            prepared_items: list[dict[str, Any]] = []
            for item in items:
                item.setdefault("source", name)
                item.setdefault("external_source", name)
                item.setdefault("entity_type", entity)
                item.update(_query_match_summary(item, query=query_text))
                prepared_items.append(prepare_discovery_record(item))
            bucket_by_provider[name] = prepared_items
            sources_succeeded.append(name)
            diagnostics.append(
                {
                    "provider": name,
                    "status": "succeeded",
                    "item_count": len(prepared_items),
                    "authenticated": bool(payload.get("authenticated")),
                }
            )

    raw_records: list[dict[str, Any]] = []
    for name in selected:
        raw_records.extend(bucket_by_provider.get(name) or [])

    merged = deduplicate_discovery_records(raw_records)
    ranked = rank_discovery_items([sanitize_discovery_item(item) for item in merged])
    # Re-prepare after sanitize so identifier fields stay consistent.
    ranked = [prepare_discovery_record(item) for item in ranked]
    page_items = ranked[:per_page]

    enrichment_meta: dict[str, Any] = {
        "enrichment_sources": list(enrichers),
        "enrichment_sources_queried": [],
        "enrichment_sources_succeeded": [],
    }
    if enrichers and page_items:
        for enricher in enrichers:
            if enricher != "semantic_scholar":
                sources_skipped.append({"source": enricher, "reason": "unsupported_enricher"})
                continue
            result = semantic_provider.enrich_records(
                page_items,
                api_key=semantic_scholar_api_key,
                api_base_url=semantic_scholar_api_base,
                limit=per_page,
            )
            page_items = [prepare_discovery_record(item) for item in result["results"]]
            enrichment_meta["enrichment_sources_queried"] = list(result.get("sources_queried") or [])
            enrichment_meta["enrichment_sources_succeeded"] = list(result.get("sources_succeeded") or [])
            sources_queried = list(dict.fromkeys([*sources_queried, *enrichment_meta["enrichment_sources_queried"]]))
            sources_succeeded = list(
                dict.fromkeys([*sources_succeeded, *enrichment_meta["enrichment_sources_succeeded"]])
            )
            sources_skipped.extend(result.get("skipped") or [])
            errors.extend(result.get("errors") or [])

    if not page_items and not sources_succeeded:
        raise LocalDiscoveryError(
            "Local discovery providers failed.",
            reason_code="local_discovery_failed",
            detail={"providers": diagnostics, "errors": errors},
        )

    key_hints = _rate_limit_key_hints(errors, credentials=credentials)
    return {
        "provider": "+".join(sources_succeeded) if sources_succeeded else "local",
        "source": "local_multi_source",
        "query": query_text,
        "entity_type": entity,
        "items": page_items,
        "raw_result_count": len(raw_records),
        "result_count": len(page_items),
        "sources_queried": sources_queried,
        "sources_succeeded": sources_succeeded,
        "sources_skipped": sources_skipped or None,
        "errors": errors or None,
        "meta": {
            "count": len(page_items),
            "page": page_number,
            "per_page": per_page,
            "has_previous": page_number > 1,
            "has_next": len(ranked) > per_page,
            "local": True,
            "entity_type": entity,
            "sources": list(selected),
            "sources_queried": sources_queried,
            "sources_succeeded": sources_succeeded,
            "sources_skipped": sources_skipped,
            "enrichment_sources": list(enrichers),
            **enrichment_meta,
        },
        "discovery_diagnostics": {
            "mode": "local",
            "entity_type": entity,
            "providers": _ordered_diagnostics(diagnostics, selected),
            "sources_queried": sources_queried,
            "sources_succeeded": sources_succeeded,
            "sources_skipped": sources_skipped,
            "errors": errors or None,
            "key_hints": key_hints or None,
            "server_openalex_attempted": False,
            "scihub_enabled_for_search": False,
            "semantic_scholar_default_role": "enrich",
            **enrichment_meta,
        },
    }


def _rate_limit_key_hints(errors: list[dict[str, Any]], *, credentials: dict[str, Any]) -> list[dict[str, str]]:
    hints: list[dict[str, str]] = []
    rate_limited = {
        str(row.get("source") or "")
        for row in errors
        if row.get("kind") == "rate_limited" or row.get("reason_code") == "provider_rate_limited"
    }
    if "openalex" in rate_limited and not str(credentials.get("openalex_api_key") or "").strip():
        hints.append(
            {
                "provider": "openalex",
                "action_hint": (
                    "OpenAlex rate-limited without a key. Discover still returned other sources. "
                    "Free key: https://openalex.org/settings/api then "
                    "`mdtero config academic --openalex-key <key> --json`."
                ),
            }
        )
    if "semantic_scholar" in rate_limited and not str(credentials.get("semantic_scholar_api_key") or "").strip():
        hints.append(
            {
                "provider": "semantic_scholar",
                "action_hint": (
                    "Semantic Scholar rate-limited without a key. "
                    "Add one with `mdtero config academic --semantic-scholar-key <key> --json`, or use `--enrich none`."
                ),
            }
        )
    return hints


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
        for value in (item.get("title"), item.get("venue"), item.get("abstract_preview"), item.get("doi"), item.get("nct_id"))
    ).lower()
    matched = sorted({token for token in tokens if token in haystack})
    score = round(len(matched) / len(set(tokens)), 4) if tokens else 0.0
    return {
        "query_match_score": score,
        "query_matched_terms": matched,
        "query_match_warning": "low_query_term_overlap" if score < 0.25 else None,
    }
