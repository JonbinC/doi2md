from __future__ import annotations

from typing import Any

from ..discovery_http import discovery_item, encode_query, http_get_json, normalize_doi

DEFAULT_API_BASE = "https://api.openaire.eu/search/publications"


def search(query: str, *, limit: int = 10, page: int = 1, **_: Any) -> dict[str, Any]:
    per_page = max(1, min(int(limit or 10), 50))
    page_number = max(1, int(page or 1))
    params = {
        "keywords": str(query).strip(),
        "size": str(per_page),
        "page": str(page_number),
        "format": "json",
    }
    url = f"{DEFAULT_API_BASE}?{encode_query(params)}"
    payload = http_get_json(url, headers={"Accept": "application/json"}, provider="openaire")
    response = payload.get("response") if isinstance(payload.get("response"), dict) else payload
    results = response.get("results") if isinstance(response.get("results"), dict) else {}
    result = results.get("result") if isinstance(results.get("result"), list) else []
    if isinstance(results.get("result"), dict):
        result = [results.get("result")]
    items = []
    for row in result:
        if not isinstance(row, dict):
            continue
        item = _normalize(row)
        if item.get("title"):
            items.append(item)
        if len(items) >= per_page:
            break
    return {"items": items, "authenticated": False}


def _normalize(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else row
    oaf = metadata.get("oaf:entity") if isinstance(metadata.get("oaf:entity"), dict) else metadata
    result = oaf.get("oaf:result") if isinstance(oaf.get("oaf:result"), dict) else oaf
    title = _text(result.get("title"))
    doi = None
    pids = result.get("pid")
    if isinstance(pids, list):
        for pid in pids:
            if isinstance(pid, dict) and str(pid.get("@classid") or "").lower() == "doi":
                doi = normalize_doi(pid.get("$") or pid.get("#text"))
                break
    elif isinstance(pids, dict) and str(pids.get("@classid") or "").lower() == "doi":
        doi = normalize_doi(pids.get("$") or pids.get("#text"))
    authors = []
    creator = result.get("creator")
    if isinstance(creator, list):
        authors = [_text(item) for item in creator if _text(item)]
    elif creator:
        text = _text(creator)
        if text:
            authors = [text]
    year = _text(result.get("dateofacceptance") or result.get("date"))
    year_value = int(year[:4]) if year[:4].isdigit() else None
    return discovery_item(
        source="openaire",
        external_id=doi or _text(result.get("objidentifier")) or None,
        title=title,
        authors=authors,
        year=year_value,
        abstract_preview=_text(result.get("description")) or None,
        doi=doi,
        source_url=f"https://doi.org/{doi}" if doi else None,
    )


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("$") or value.get("#text") or value.get("content") or "").strip()
    if isinstance(value, list):
        for item in value:
            text = _text(item)
            if text:
                return text
        return ""
    return str(value or "").strip()
