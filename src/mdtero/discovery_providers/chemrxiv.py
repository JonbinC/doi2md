from __future__ import annotations

from typing import Any

from ..discovery_http import discovery_item, encode_query, http_get_json, normalize_doi

# ChemRxiv Open Engage public search endpoint used by paper-search-mcp / Mdtero router.
DEFAULT_API_BASE = "https://chemrxiv.org/engage/chemrxiv/public-api/desktop/v1"


def search(query: str, *, limit: int = 10, page: int = 1, **_: Any) -> dict[str, Any]:
    per_page = max(1, min(int(limit or 10), 50))
    params = {
        "term": str(query).strip(),
        "skip": str((max(1, int(page or 1)) - 1) * per_page),
        "limit": str(per_page),
    }
    url = f"{DEFAULT_API_BASE}/items?{encode_query(params)}"
    try:
        payload = http_get_json(url, provider="chemrxiv")
    except Exception:
        # Fallback: Crossref filtered to ChemRxiv prefix when Open Engage is unavailable.
        from . import crossref

        result = crossref.search(f"{query} chemrxiv", limit=per_page, page=page)
        items = []
        for item in result.get("items") or []:
            if not isinstance(item, dict):
                continue
            cloned = dict(item)
            cloned["source"] = "chemrxiv"
            cloned["external_source"] = "chemrxiv"
            items.append(cloned)
        return {"items": items, "authenticated": False, "fallback": "crossref"}
    rows = payload.get("itemHits") or payload.get("items") or payload.get("results") or []
    if not isinstance(rows, list):
        rows = []
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        record = row.get("item") if isinstance(row.get("item"), dict) else row
        item = _normalize(record)
        if item.get("title"):
            items.append(item)
    return {"items": items, "authenticated": False}


def _normalize(record: dict[str, Any]) -> dict[str, Any]:
    doi = normalize_doi(record.get("doi"))
    authors = []
    for author in record.get("authors") or []:
        if isinstance(author, dict):
            name = " ".join(
                part
                for part in (
                    str(author.get("firstName") or "").strip(),
                    str(author.get("lastName") or "").strip(),
                )
                if part
            ).strip() or str(author.get("name") or "").strip()
            if name:
                authors.append(name)
    asset = record.get("asset") if isinstance(record.get("asset"), dict) else {}
    pdf = str(asset.get("original") or record.get("pdfUrl") or "").strip() or None
    year = None
    published = str(record.get("publishedDate") or record.get("postedDate") or "")
    if len(published) >= 4 and published[:4].isdigit():
        year = int(published[:4])
    external_id = str(record.get("id") or "").strip() or doi
    return discovery_item(
        source="chemrxiv",
        external_id=external_id,
        title=str(record.get("title") or "").strip(),
        authors=authors,
        year=year,
        venue="ChemRxiv",
        abstract_preview=str(record.get("abstract") or "").strip() or None,
        doi=doi,
        source_url=(
            str(record.get("url") or "").strip()
            or (f"https://chemrxiv.org/engage/chemrxiv/article-details/{external_id}" if external_id else None)
            or (f"https://doi.org/{doi}" if doi else None)
        ),
        open_access_pdf_url=pdf,
    )
