from __future__ import annotations

from typing import Any

from ..discovery_http import discovery_item, encode_query, http_get_json, normalize_doi

DEFAULT_API_BASE = "https://zenodo.org/api"


def search(
    query: str,
    *,
    limit: int = 10,
    page: int = 1,
    access_token: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    per_page = max(1, min(int(limit or 10), 100))
    params = {
        "q": str(query).strip(),
        "size": str(per_page),
        "page": str(max(1, int(page or 1))),
        "type": "publication",
    }
    token = str(access_token or "").strip()
    if token:
        params["access_token"] = token
    url = f"{DEFAULT_API_BASE}/records/?{encode_query(params)}"
    payload = http_get_json(url, provider="zenodo")
    rows = payload.get("hits", {}).get("hits") if isinstance(payload.get("hits"), dict) else []
    if not isinstance(rows, list):
        rows = []
    items = [_normalize(row) for row in rows if isinstance(row, dict)]
    return {"items": [item for item in items if item.get("title")], "authenticated": bool(token)}


def _normalize(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    creators = metadata.get("creators") if isinstance(metadata.get("creators"), list) else []
    authors = [str(c.get("name") or "").strip() for c in creators if isinstance(c, dict) and c.get("name")]
    doi = normalize_doi(metadata.get("doi") or row.get("doi"))
    files = row.get("files") if isinstance(row.get("files"), list) else []
    pdf = None
    for file_row in files:
        if not isinstance(file_row, dict):
            continue
        key = str(file_row.get("key") or "").lower()
        links = file_row.get("links") if isinstance(file_row.get("links"), dict) else {}
        if key.endswith(".pdf") or str(file_row.get("mimetype") or "").endswith("pdf"):
            pdf = str(links.get("download") or links.get("self") or "").strip() or None
            if pdf:
                break
    links = row.get("links") if isinstance(row.get("links"), dict) else {}
    year = None
    pub = str(metadata.get("publication_date") or "")
    if len(pub) >= 4 and pub[:4].isdigit():
        year = int(pub[:4])
    return discovery_item(
        source="zenodo",
        external_id=str(row.get("id") or "").strip() or doi,
        title=str(metadata.get("title") or "").strip(),
        authors=authors,
        year=year,
        abstract_preview=str(metadata.get("description") or "").strip() or None,
        doi=doi,
        source_url=str(links.get("html") or (f"https://doi.org/{doi}" if doi else "")).strip() or None,
        open_access_pdf_url=pdf,
    )
