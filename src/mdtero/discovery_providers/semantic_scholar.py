from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from ..discovery_http import LocalDiscoveryError, discovery_item, encode_query, http_get_json, normalize_doi

DEFAULT_API_BASE = "https://api.semanticscholar.org/graph/v1"
_FIELDS = "title,year,authors,venue,externalIds,url,abstract,citationCount,openAccessPdf,paperId"


def search(
    query: str,
    *,
    limit: int = 10,
    page: int = 1,
    offset: int | None = None,
    api_key: str | None = None,
    api_base_url: str = DEFAULT_API_BASE,
    year: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    per_page = max(1, min(int(limit or 10), 100))
    page_number = max(1, int(page or 1))
    start = int(offset) if offset is not None else (page_number - 1) * per_page
    params = {
        "query": str(query).strip(),
        "limit": str(per_page),
        "offset": str(max(0, start)),
        "fields": _FIELDS,
    }
    if year:
        params["year"] = str(year)
    headers = {"Accept": "application/json"}
    key = str(api_key or "").strip()
    if key:
        headers["x-api-key"] = key
    url = f"{api_base_url.rstrip('/')}/paper/search?{encode_query(params)}"
    try:
        payload = http_get_json(url, headers=headers, provider="semantic_scholar")
    except LocalDiscoveryError as exc:
        # paper-search-mcp: rejected key (403) retries without key
        if key and exc.reason_code == "provider_auth_failed":
            headers.pop("x-api-key", None)
            payload = http_get_json(url, headers=headers, provider="semantic_scholar")
            key = ""
        else:
            raise
    rows = payload.get("data") if isinstance(payload.get("data"), list) else []
    items = [_normalize(row) for row in rows if isinstance(row, dict)]
    return {"items": [item for item in items if item.get("title")], "authenticated": bool(key)}


def get_by_id(
    identifier: str,
    *,
    api_key: str | None = None,
    api_base_url: str = DEFAULT_API_BASE,
) -> dict[str, Any]:
    """Resolve one paper by strong id (DOI:/PMID:/ARXIV:/paperId). Used for enrich."""
    lookup = _lookup_identifier(identifier)
    headers = {"Accept": "application/json"}
    key = str(api_key or "").strip()
    if key:
        headers["x-api-key"] = key
    # S2 accepts DOI:/PMID:/ARXIV: prefixes in the path; keep ':' unescaped.
    path_id = quote(lookup, safe=":/")
    url = f"{api_base_url.rstrip('/')}/paper/{path_id}?{encode_query({'fields': _FIELDS})}"
    try:
        payload = http_get_json(url, headers=headers, provider="semantic_scholar")
    except LocalDiscoveryError as exc:
        if key and exc.reason_code == "provider_auth_failed":
            headers.pop("x-api-key", None)
            payload = http_get_json(url, headers=headers, provider="semantic_scholar")
            key = ""
        else:
            raise
    if not isinstance(payload, dict):
        raise LocalDiscoveryError("Malformed Semantic Scholar paper response", reason_code="provider_bad_response")
    item = _normalize(payload)
    item["authenticated"] = bool(key)
    return item


def enrich_records(
    records: list[dict[str, Any]],
    *,
    api_key: str | None = None,
    api_base_url: str = DEFAULT_API_BASE,
    limit: int | None = None,
) -> dict[str, Any]:
    import time

    from ..discovery_merge import merge_discovery_records, strong_identifier

    errors: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    queried = False
    succeeded = False
    # Keep enrich bounded: S2 anonymous quota is tight and 404s are common on weak IDs.
    upper = len(records) if limit is None else min(max(int(limit), 0), len(records))
    upper = min(upper, 3)
    key = str(api_key or "").strip()
    for index, record in enumerate(records[:upper]):
        counts = record.get("citation_counts") if isinstance(record.get("citation_counts"), dict) else {}
        if counts.get("semantic_scholar") is not None or record.get("semantic_scholar_id"):
            skipped.append({"source": "semantic_scholar", "record_index": index, "reason": "already_enriched"})
            continue
        # If another catalog already provided a strong citation signal, skip S2 to save quota.
        other_cite = max(
            (int(v or 0) for k, v in counts.items() if str(k) != "semantic_scholar"),
            default=int(record.get("citation_count") or 0),
        )
        if other_cite >= 50 and record.get("doi"):
            skipped.append(
                {
                    "source": "semantic_scholar",
                    "record_index": index,
                    "reason": "strong_citation_already_present",
                    "citation_count": other_cite,
                }
            )
            continue
        identifier = strong_identifier(record)
        if not identifier:
            skipped.append({"source": "semantic_scholar", "record_index": index, "reason": "missing_strong_identifier"})
            continue
        # Prefer DOI lookups; PMID/ArXiv-only IDs 404 more often on S2.
        if not identifier.upper().startswith("DOI:") and not record.get("doi"):
            skipped.append({"source": "semantic_scholar", "record_index": index, "reason": "prefer_doi_for_enrich"})
            continue
        if record.get("doi"):
            identifier = f"DOI:{record['doi']}"
        queried = True
        try:
            incoming = get_by_id(identifier, api_key=key or None, api_base_url=api_base_url)
        except LocalDiscoveryError as exc:
            errors.append(
                {
                    "source": "semantic_scholar",
                    "record_index": index,
                    "reason_code": exc.reason_code,
                    "error": str(exc),
                    "kind": "rate_limited" if exc.reason_code == "provider_rate_limited" else "source_error",
                }
            )
            if exc.reason_code == "provider_rate_limited":
                skipped.append({"source": "semantic_scholar", "reason": "stopped_after_rate_limit"})
                break
            continue
        succeeded = True
        merge_discovery_records(record, incoming)
        if not key:
            time.sleep(0.35)
    return {
        "results": records,
        "errors": errors,
        "skipped": skipped,
        "sources_queried": ["semantic_scholar"] if queried else [],
        "sources_succeeded": ["semantic_scholar"] if succeeded else [],
    }


def _normalize(paper: dict[str, Any]) -> dict[str, Any]:
    external_ids = paper.get("externalIds") if isinstance(paper.get("externalIds"), dict) else {}
    doi = normalize_doi(external_ids.get("DOI") or external_ids.get("doi"))
    authors_raw = paper.get("authors") if isinstance(paper.get("authors"), list) else []
    authors = [
        str(row.get("name") or "").strip()
        for row in authors_raw
        if isinstance(row, dict) and str(row.get("name") or "").strip()
    ]
    oa = paper.get("openAccessPdf") if isinstance(paper.get("openAccessPdf"), dict) else {}
    paper_id = str(paper.get("paperId") or "").strip() or None
    citation_count = int(paper.get("citationCount") or 0)
    item = discovery_item(
        source="semantic_scholar",
        external_id=paper_id,
        title=str(paper.get("title") or "").strip(),
        authors=authors,
        year=paper.get("year"),
        venue=str(paper.get("venue") or "").strip() or None,
        abstract_preview=str(paper.get("abstract") or "").strip() or None,
        citation_count=citation_count,
        doi=doi,
        source_url=str(paper.get("url") or "").strip() or None,
        open_access_pdf_url=str(oa.get("url") or "").strip() or None,
    )
    item["entity_type"] = "publication"
    item["semantic_scholar_id"] = paper_id
    item["pmid"] = str(external_ids.get("PubMed") or "").strip() or None
    arxiv = str(external_ids.get("ArXiv") or "").strip() or None
    if arxiv:
        item["arxiv_id"] = re.sub(r"v\d+$", "", arxiv)
    item["citation_count_source"] = "semantic_scholar"
    item["citation_counts"] = {"semantic_scholar": citation_count}
    return item


def _lookup_identifier(identifier: str) -> str:
    value = str(identifier or "").strip()
    if not value:
        raise LocalDiscoveryError("Empty Semantic Scholar identifier", reason_code="discovery_query_missing")
    if "semanticscholar.org/paper/" in value.casefold():
        return value.rstrip("/").rsplit("/", 1)[-1]
    upper = value.upper()
    if upper.startswith(("DOI:", "ARXIV:", "PMID:")):
        prefix, raw = value.split(":", 1)
        return f"{prefix.upper()}:{raw.strip()}"
    if value.startswith("10.") and "/" in value:
        return f"DOI:{value}"
    if re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", value):
        return f"ARXIV:{value}"
    if value.isdigit():
        return f"PMID:{value}"
    return value
