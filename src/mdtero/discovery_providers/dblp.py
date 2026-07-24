from __future__ import annotations

from typing import Any

from ..discovery_http import discovery_item, encode_query, http_get_json, normalize_doi

DEFAULT_API_BASE = "https://dblp.org/search/publ/api"


def search(query: str, *, limit: int = 10, page: int = 1, **_: Any) -> dict[str, Any]:
    per_page = max(1, min(int(limit or 10), 100))
    first = (max(1, int(page or 1)) - 1) * per_page
    params = {"q": str(query).strip(), "h": str(per_page), "f": str(first), "format": "json"}
    url = f"{DEFAULT_API_BASE}?{encode_query(params)}"
    payload = http_get_json(url, provider="dblp")
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    hits = result.get("hits") if isinstance(result.get("hits"), dict) else {}
    hit_list = hits.get("hit") if isinstance(hits.get("hit"), list) else []
    items = []
    for hit in hit_list:
        if not isinstance(hit, dict):
            continue
        info = hit.get("info") if isinstance(hit.get("info"), dict) else {}
        item = _normalize(info, hit_id=str(hit.get("@id") or "").strip() or None)
        if item.get("title"):
            items.append(item)
    return {"items": items, "authenticated": False}


def _normalize(info: dict[str, Any], *, hit_id: str | None) -> dict[str, Any]:
    authors_raw = info.get("authors", {}).get("author") if isinstance(info.get("authors"), dict) else []
    if isinstance(authors_raw, dict):
        authors_raw = [authors_raw]
    authors = []
    for author in authors_raw or []:
        if isinstance(author, dict):
            name = str(author.get("text") or author.get("@pid") or "").strip()
        else:
            name = str(author or "").strip()
        if name:
            authors.append(name)
    doi = normalize_doi(info.get("doi"))
    year = info.get("year")
    try:
        year = int(year) if year is not None else None
    except (TypeError, ValueError):
        year = None
    return discovery_item(
        source="dblp",
        external_id=hit_id or str(info.get("key") or "").strip() or None,
        title=str(info.get("title") or "").strip(),
        authors=authors,
        year=year,
        venue=str(info.get("venue") or "").strip() or None,
        doi=doi,
        source_url=str(info.get("url") or (f"https://doi.org/{doi}" if doi else "")).strip() or None,
    )
