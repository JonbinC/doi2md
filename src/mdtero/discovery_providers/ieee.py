from __future__ import annotations

from typing import Any

from ..discovery_http import LocalDiscoveryError, discovery_item, encode_query, http_get_json, normalize_doi

DEFAULT_API_BASE = "https://ieeexploreapi.ieee.org/api/v1/search/articles"


def search(
    query: str,
    *,
    limit: int = 10,
    page: int = 1,
    api_key: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    key = str(api_key or "").strip()
    if not key:
        raise LocalDiscoveryError(
            "IEEE Xplore requires an API key",
            reason_code="provider_key_required",
            detail="Set academic.ieee_api_key / MDTERO_IEEE_API_KEY",
        )
    per_page = max(1, min(int(limit or 10), 100))
    params = {
        "apikey": key,
        "format": "json",
        "max_records": str(per_page),
        "start_record": str((max(1, int(page or 1)) - 1) * per_page + 1),
        "querytext": str(query).strip(),
    }
    url = f"{DEFAULT_API_BASE}?{encode_query(params)}"
    payload = http_get_json(url, provider="ieee")
    rows = payload.get("articles") if isinstance(payload.get("articles"), list) else []
    items = [_normalize(row) for row in rows if isinstance(row, dict)]
    return {"items": [item for item in items if item.get("title")], "authenticated": True}


def _normalize(row: dict[str, Any]) -> dict[str, Any]:
    authors = []
    authors_node = row.get("authors") if isinstance(row.get("authors"), dict) else {}
    for author in authors_node.get("authors") or []:
        if isinstance(author, dict):
            name = str(author.get("full_name") or "").strip()
            if name:
                authors.append(name)
    doi = normalize_doi(row.get("doi"))
    return discovery_item(
        source="ieee",
        external_id=str(row.get("article_number") or "").strip() or doi,
        title=str(row.get("title") or "").strip(),
        authors=authors,
        year=int(row["publication_year"]) if str(row.get("publication_year") or "").isdigit() else None,
        venue=str(row.get("publication_title") or "").strip() or None,
        abstract_preview=str(row.get("abstract") or "").strip() or None,
        doi=doi,
        source_url=str(row.get("html_url") or row.get("abstract_url") or (f"https://doi.org/{doi}" if doi else "")).strip()
        or None,
        open_access_pdf_url=str(row.get("pdf_url") or "").strip() or None,
    )
