from __future__ import annotations

from typing import Any

from ..discovery_http import LocalDiscoveryError, discovery_item, encode_query, extract_doi, http_get_json

DEFAULT_API_BASE = "https://citeseerx.ist.psu.edu/api_v2/search"


def search(query: str, *, limit: int = 10, page: int = 1, **_: Any) -> dict[str, Any]:
    per_page = max(1, min(int(limit or 10), 20))
    params = {
        "query": str(query).strip(),
        "start": str((max(1, int(page or 1)) - 1) * per_page),
        "limit": str(per_page),
    }
    url = f"{DEFAULT_API_BASE}?{encode_query(params)}"
    try:
        payload = http_get_json(url, headers={"Accept": "application/json"}, provider="citeseerx")
    except LocalDiscoveryError as exc:
        # Upstream is intermittent; fail soft with structured skip rather than crashing aggregation.
        raise LocalDiscoveryError(
            "CiteSeerX search unavailable",
            reason_code="provider_unavailable",
            detail=exc.detail or str(exc),
        ) from exc
    rows = payload.get("response", {}).get("docs") if isinstance(payload.get("response"), dict) else payload.get("docs")
    if not isinstance(rows, list):
        rows = payload.get("results") if isinstance(payload.get("results"), list) else []
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        authors = row.get("authors") if isinstance(row.get("authors"), list) else []
        authors = [str(name).strip() for name in authors if str(name).strip()]
        doi = extract_doi(row.get("doi") or row.get("url"))
        pdf = str(row.get("url") or row.get("pdf") or "").strip() or None
        items.append(
            discovery_item(
                source="citeseerx",
                external_id=str(row.get("id") or row.get("cluster_id") or "").strip() or None,
                title=title,
                authors=authors,
                year=row.get("year"),
                abstract_preview=str(row.get("abstract") or "").strip() or None,
                citation_count=int(row.get("citation_count") or row.get("ncites") or 0),
                doi=doi,
                source_url=str(row.get("url") or "").strip() or None,
                open_access_pdf_url=pdf if pdf and "pdf" in pdf.lower() else None,
            )
        )
    return {"items": items, "authenticated": False}
