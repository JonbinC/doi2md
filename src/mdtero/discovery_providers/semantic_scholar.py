from __future__ import annotations

from typing import Any

from ..discovery_http import LocalDiscoveryError, discovery_item, encode_query, http_get_json, normalize_doi

DEFAULT_API_BASE = "https://api.semanticscholar.org/graph/v1"


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
        "fields": "title,year,authors,venue,externalIds,url,abstract,citationCount,openAccessPdf",
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
    return discovery_item(
        source="semantic_scholar",
        external_id=str(paper.get("paperId") or "").strip() or None,
        title=str(paper.get("title") or "").strip(),
        authors=authors,
        year=paper.get("year"),
        venue=str(paper.get("venue") or "").strip() or None,
        abstract_preview=str(paper.get("abstract") or "").strip() or None,
        citation_count=int(paper.get("citationCount") or 0),
        doi=doi,
        source_url=str(paper.get("url") or "").strip() or None,
        open_access_pdf_url=str(oa.get("url") or "").strip() or None,
    )
