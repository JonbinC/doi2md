from __future__ import annotations

from typing import Any

from ..discovery_http import LocalDiscoveryError, discovery_item, encode_query, extract_doi, http_get_bytes

# BASE often requires institutional IP registration. Return structured skip when empty/forbidden.
DEFAULT_API_BASE = "https://api.base-search.net/cgi-bin/BaseHttpSearchInterface.fcgi"


def search(query: str, *, limit: int = 10, page: int = 1, **_: Any) -> dict[str, Any]:
    per_page = max(1, min(int(limit or 10), 50))
    offset = (max(1, int(page or 1)) - 1) * per_page
    params = {
        "func": "PerformSearch",
        "query": str(query).strip(),
        "format": "json",
        "hits": str(per_page),
        "offset": str(offset),
    }
    url = f"{DEFAULT_API_BASE}?{encode_query(params)}"
    try:
        raw = http_get_bytes(url, headers={"Accept": "application/json"}, provider="base")
    except LocalDiscoveryError as exc:
        raise LocalDiscoveryError(
            "BASE search unavailable (often requires institutional IP registration)",
            reason_code="provider_requires_registration",
            detail=exc.detail or str(exc),
        ) from exc
    text = raw.decode("utf-8", errors="replace").strip()
    if not text or text.startswith("<"):
        raise LocalDiscoveryError(
            "BASE returned no JSON results (institutional registration may be required)",
            reason_code="provider_requires_registration",
            detail=text[:300],
        )
    import json

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LocalDiscoveryError(
            "BASE returned invalid JSON",
            reason_code="provider_response_invalid",
            detail=str(exc),
        ) from exc
    docs = payload.get("response", {}).get("docs") if isinstance(payload.get("response"), dict) else []
    if not isinstance(docs, list):
        docs = []
    items = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        title = str(doc.get("dctitle") or doc.get("title") or "").strip()
        if not title:
            continue
        authors = doc.get("dccreator") if isinstance(doc.get("dccreator"), list) else [doc.get("dccreator")]
        authors = [str(name).strip() for name in authors if name]
        doi = extract_doi(doc.get("dcidentifier") or doc.get("dclink"))
        link = None
        if isinstance(doc.get("dclink"), list) and doc.get("dclink"):
            link = str(doc["dclink"][0])
        elif doc.get("dclink"):
            link = str(doc.get("dclink"))
        items.append(
            discovery_item(
                source="base",
                external_id=str(doc.get("dckey") or "").strip() or doi,
                title=title,
                authors=authors,
                year=_year(doc.get("dcyear")),
                abstract_preview=str(doc.get("dcdescription") or "").strip() or None,
                doi=doi,
                source_url=link,
                open_access_pdf_url=link if link and str(link).lower().endswith(".pdf") else None,
            )
        )
    return {"items": items, "authenticated": False}


def _year(value: Any) -> int | None:
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return None
