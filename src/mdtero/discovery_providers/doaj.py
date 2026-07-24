from __future__ import annotations

from typing import Any

from ..discovery_http import discovery_item, encode_query, http_get_json, normalize_doi

DEFAULT_API_BASE = "https://doaj.org/api"


def search(
    query: str,
    *,
    limit: int = 10,
    page: int = 1,
    api_key: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    per_page = max(1, min(int(limit or 10), 100))
    page_number = max(1, int(page or 1))
    from urllib.parse import quote

    params = {"page": str(page_number), "pageSize": str(per_page)}
    key = str(api_key or "").strip()
    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}" if not key.lower().startswith("bearer ") else key
    # DOAJ path embeds the query string directly.
    url = f"{DEFAULT_API_BASE}/search/articles/{quote(str(query).strip())}?{encode_query(params)}"
    payload = http_get_json(url, headers=headers, provider="doaj")
    rows = payload.get("results") if isinstance(payload.get("results"), list) else []
    items = [_normalize(row) for row in rows if isinstance(row, dict)]
    return {"items": [item for item in items if item.get("title")], "authenticated": bool(key)}


def _normalize(row: dict[str, Any]) -> dict[str, Any]:
    bibjson = row.get("bibjson") if isinstance(row.get("bibjson"), dict) else row
    title = str(bibjson.get("title") or "").strip()
    authors = []
    for author in bibjson.get("author") or []:
        if isinstance(author, dict):
            name = str(author.get("name") or "").strip()
            if name:
                authors.append(name)
    doi = None
    for ident in bibjson.get("identifier") or []:
        if isinstance(ident, dict) and str(ident.get("type") or "").lower() == "doi":
            doi = normalize_doi(ident.get("id"))
            break
    pdf = None
    landing = None
    for link in bibjson.get("link") or []:
        if not isinstance(link, dict):
            continue
        link_type = str(link.get("type") or "").lower()
        url = str(link.get("url") or "").strip()
        if not url:
            continue
        if "pdf" in link_type or url.lower().endswith(".pdf"):
            pdf = pdf or url
        else:
            landing = landing or url
    year = None
    year_text = str(bibjson.get("year") or "").strip()
    if year_text.isdigit():
        year = int(year_text)
    journal = bibjson.get("journal") if isinstance(bibjson.get("journal"), dict) else {}
    return discovery_item(
        source="doaj",
        external_id=str(row.get("id") or "").strip() or doi,
        title=title,
        authors=authors,
        year=year,
        venue=str(journal.get("title") or "").strip() or None,
        abstract_preview=str(bibjson.get("abstract") or "").strip() or None,
        doi=doi,
        source_url=landing or (f"https://doi.org/{doi}" if doi else None),
        open_access_pdf_url=pdf,
    )
