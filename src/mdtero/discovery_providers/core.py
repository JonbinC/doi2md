from __future__ import annotations

from typing import Any

from ..discovery_http import LocalDiscoveryError, discovery_item, encode_query, http_get_json, normalize_doi

DEFAULT_API_BASE = "https://api.core.ac.uk/v3"


def search(
    query: str,
    *,
    limit: int = 10,
    page: int = 1,
    api_key: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    per_page = max(1, min(int(limit or 10), 100))
    offset = (max(1, int(page or 1)) - 1) * per_page
    params = {"q": str(query).strip(), "limit": str(per_page), "offset": str(offset)}
    headers = {"Accept": "application/json"}
    key = str(api_key or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    url = f"{DEFAULT_API_BASE}/search/works?{encode_query(params)}"
    try:
        payload = http_get_json(url, headers=headers, provider="core")
    except LocalDiscoveryError as exc:
        if key and exc.reason_code == "provider_auth_failed":
            headers.pop("Authorization", None)
            payload = http_get_json(url, headers=headers, provider="core")
            key = ""
        else:
            raise
    rows = payload.get("results") if isinstance(payload.get("results"), list) else []
    items = [_normalize(row) for row in rows if isinstance(row, dict)]
    return {"items": [item for item in items if item.get("title")], "authenticated": bool(key)}


def _normalize(row: dict[str, Any]) -> dict[str, Any]:
    authors = []
    for author in row.get("authors") or []:
        if isinstance(author, dict):
            name = str(author.get("name") or "").strip()
            if name:
                authors.append(name)
        elif str(author).strip():
            authors.append(str(author).strip())
    doi = normalize_doi(row.get("doi"))
    year = row.get("yearPublished") or row.get("year")
    try:
        year = int(year) if year is not None else None
    except (TypeError, ValueError):
        year = None
    download = str(row.get("downloadUrl") or "").strip() or None
    source_urls = row.get("sourceFulltextUrls") if isinstance(row.get("sourceFulltextUrls"), list) else []
    landing = str(source_urls[0]).strip() if source_urls else None
    return discovery_item(
        source="core",
        external_id=str(row.get("id") or "").strip() or doi,
        title=str(row.get("title") or "").strip(),
        authors=authors,
        year=year,
        abstract_preview=str(row.get("abstract") or "").strip() or None,
        citation_count=int(row.get("citationCount") or 0),
        doi=doi,
        source_url=landing or download or (f"https://doi.org/{doi}" if doi else None),
        open_access_pdf_url=download,
    )
