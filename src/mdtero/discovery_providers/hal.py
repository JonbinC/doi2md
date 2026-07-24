from __future__ import annotations

from typing import Any

from ..discovery_http import discovery_item, encode_query, http_get_json, normalize_doi

DEFAULT_API_BASE = "https://api.archives-ouvertes.fr/search"


def search(query: str, *, limit: int = 10, page: int = 1, **_: Any) -> dict[str, Any]:
    per_page = max(1, min(int(limit or 10), 100))
    start = (max(1, int(page or 1)) - 1) * per_page
    params = {
        "q": str(query).strip(),
        "wt": "json",
        "rows": str(per_page),
        "start": str(start),
        "fl": "halId_s,title_s,authFullName_s,abstract_s,doiId_s,uri_s,producedDateY_i,files_s,journalTitle_s",
    }
    url = f"{DEFAULT_API_BASE}/?{encode_query(params)}"
    payload = http_get_json(url, provider="hal")
    docs = payload.get("response", {}).get("docs") if isinstance(payload.get("response"), dict) else []
    if not isinstance(docs, list):
        docs = []
    items = [_normalize(doc) for doc in docs if isinstance(doc, dict)]
    return {"items": [item for item in items if item.get("title")], "authenticated": False}


def _first(value: Any) -> str:
    if isinstance(value, list):
        return str(value[0] if value else "").strip()
    return str(value or "").strip()


def _normalize(doc: dict[str, Any]) -> dict[str, Any]:
    title = _first(doc.get("title_s"))
    authors = doc.get("authFullName_s") if isinstance(doc.get("authFullName_s"), list) else []
    authors = [str(name).strip() for name in authors if str(name).strip()]
    doi = normalize_doi(_first(doc.get("doiId_s")))
    files = doc.get("files_s") if isinstance(doc.get("files_s"), list) else []
    pdf = next((str(path).strip() for path in files if str(path).lower().endswith(".pdf")), None)
    return discovery_item(
        source="hal",
        external_id=_first(doc.get("halId_s")) or doi,
        title=title,
        authors=authors,
        year=doc.get("producedDateY_i"),
        venue=_first(doc.get("journalTitle_s")) or None,
        abstract_preview=_first(doc.get("abstract_s")) or None,
        doi=doi,
        source_url=_first(doc.get("uri_s")) or (f"https://doi.org/{doi}" if doi else None),
        open_access_pdf_url=pdf,
    )
