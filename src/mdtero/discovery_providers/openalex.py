from __future__ import annotations

from typing import Any

from ..discovery_http import discovery_item, encode_query, http_get_json, normalize_doi

DEFAULT_API_BASE = "https://api.openalex.org"


def search(
    query: str,
    *,
    limit: int = 10,
    page: int = 1,
    api_key: str | None = None,
    api_base_url: str = DEFAULT_API_BASE,
    **_: Any,
) -> dict[str, Any]:
    params: dict[str, str] = {
        "search": str(query).strip(),
        "per-page": str(max(1, min(int(limit or 10), 25))),
        "page": str(max(1, int(page or 1))),
    }
    key = str(api_key or "").strip()
    if key:
        params["api_key"] = key
    url = f"{api_base_url.rstrip('/')}/works?{encode_query(params)}"
    payload = http_get_json(url, provider="openalex")
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    items = [_normalize(row) for row in results if isinstance(row, dict)]
    return {"items": [item for item in items if item.get("title")], "authenticated": bool(key)}


def _normalize(work: dict[str, Any]) -> dict[str, Any]:
    ids = work.get("ids") if isinstance(work.get("ids"), dict) else {}
    doi = normalize_doi(ids.get("doi") or work.get("doi"))
    primary = work.get("primary_location") if isinstance(work.get("primary_location"), dict) else {}
    best_oa = work.get("best_oa_location") if isinstance(work.get("best_oa_location"), dict) else {}
    open_access = work.get("open_access") if isinstance(work.get("open_access"), dict) else {}
    source_url = (
        str(primary.get("landing_page_url") or "").strip()
        or str(best_oa.get("landing_page_url") or "").strip()
        or None
    )
    authorships = work.get("authorships") if isinstance(work.get("authorships"), list) else []
    authors = []
    for authorship in authorships:
        if not isinstance(authorship, dict):
            continue
        author = authorship.get("author") if isinstance(authorship.get("author"), dict) else {}
        name = str(author.get("display_name") or "").strip()
        if name:
            authors.append(name)
    venue = None
    source = primary.get("source") if isinstance(primary.get("source"), dict) else {}
    if source:
        venue = str(source.get("display_name") or "").strip() or None
    external_id = str(work.get("id") or "").rstrip("/").rsplit("/", 1)[-1] or None
    abstract = _flatten_abstract(work.get("abstract_inverted_index"))
    return discovery_item(
        source="openalex",
        external_id=external_id,
        title=str(work.get("display_name") or "").strip(),
        authors=authors,
        year=work.get("publication_year"),
        venue=venue,
        abstract_preview=abstract,
        citation_count=int(work.get("cited_by_count") or 0),
        doi=doi,
        source_url=source_url,
        open_access_pdf_url=str(open_access.get("oa_url") or "").strip() or None,
    )


def _flatten_abstract(index: Any) -> str | None:
    if not isinstance(index, dict) or not index:
        return None
    positions: list[tuple[int, str]] = []
    for token, offsets in index.items():
        if not isinstance(offsets, list):
            continue
        for offset in offsets:
            if isinstance(offset, int):
                positions.append((offset, str(token)))
    if not positions:
        return None
    positions.sort(key=lambda item: item[0])
    return " ".join(token for _, token in positions)
