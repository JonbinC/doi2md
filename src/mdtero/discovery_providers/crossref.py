from __future__ import annotations

from typing import Any

from ..discovery_http import discovery_item, encode_query, http_get_json, normalize_doi

DEFAULT_API_BASE = "https://api.crossref.org"


def search(
    query: str,
    *,
    limit: int = 10,
    page: int = 1,
    mailto: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    per_page = max(1, min(int(limit or 10), 100))
    page_number = max(1, int(page or 1))
    offset = (page_number - 1) * per_page
    email = str(mailto or "mdtero@mdtero.com").strip()
    params = {
        "query": str(query).strip(),
        "rows": str(per_page),
        "offset": str(offset),
        "sort": "relevance",
        "order": "desc",
        "mailto": email,
    }
    url = f"{DEFAULT_API_BASE}/works?{encode_query(params)}"
    payload = http_get_json(
        url,
        headers={"Accept": "application/json", "User-Agent": f"mdtero-local-discovery/0.2 (mailto:{email})"},
        provider="crossref",
    )
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    rows = message.get("items") if isinstance(message.get("items"), list) else []
    items = [_normalize(row) for row in rows if isinstance(row, dict)]
    return {"items": [item for item in items if item.get("title")], "authenticated": False}


def _normalize(work: dict[str, Any]) -> dict[str, Any]:
    titles = work.get("title") if isinstance(work.get("title"), list) else []
    title = str(titles[0] if titles else "").strip()
    authors = []
    for author in work.get("author") or []:
        if not isinstance(author, dict):
            continue
        given = str(author.get("given") or "").strip()
        family = str(author.get("family") or "").strip()
        name = " ".join(part for part in (given, family) if part).strip()
        if name:
            authors.append(name)
    year = None
    issued = work.get("issued") if isinstance(work.get("issued"), dict) else {}
    parts = issued.get("date-parts") if isinstance(issued.get("date-parts"), list) else []
    if parts and isinstance(parts[0], list) and parts[0]:
        year = parts[0][0]
    container = work.get("container-title") if isinstance(work.get("container-title"), list) else []
    doi = normalize_doi(work.get("DOI"))
    return discovery_item(
        source="crossref",
        external_id=doi or str(work.get("URL") or "").strip() or None,
        title=title,
        authors=authors,
        year=year,
        venue=str(container[0] if container else "").strip() or None,
        abstract_preview=str(work.get("abstract") or "").strip() or None,
        citation_count=int(work.get("is-referenced-by-count") or 0),
        doi=doi,
        source_url=str(work.get("URL") or (f"https://doi.org/{doi}" if doi else "")).strip() or None,
    )
