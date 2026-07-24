from __future__ import annotations

from typing import Any

from ..discovery_http import LocalDiscoveryError, discovery_item, encode_query, extract_doi, http_get_bytes

# ACM DL public HTML search (API key unlocks connector; without key we skip).
SEARCH_URL = "https://dl.acm.org/action/doSearch"


def search(
    query: str,
    *,
    limit: int = 10,
    page: int = 1,
    api_key: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    key = str(api_key or "").strip()
    if not key:
        raise LocalDiscoveryError(
            "ACM Digital Library connector requires an API key to activate",
            reason_code="provider_key_required",
            detail="Set academic.acm_api_key / MDTERO_ACM_API_KEY",
        )
    # Key-gated activation (same policy as paper-search-mcp). Best-effort HTML search when enabled.
    params = {"AllField": str(query).strip(), "pageSize": str(max(1, min(int(limit or 10), 50)))}
    url = f"{SEARCH_URL}?{encode_query(params)}"
    try:
        raw = http_get_bytes(
            url,
            headers={"Accept": "text/html", "Authorization": f"Bearer {key}"},
            provider="acm",
        )
    except LocalDiscoveryError as exc:
        raise LocalDiscoveryError(
            "ACM search failed",
            reason_code=exc.reason_code,
            detail=exc.detail or str(exc),
        ) from exc
    html = raw.decode("utf-8", errors="replace")
    import re

    matches = re.findall(
        r'<a[^>]+href="(/doi/(?:abs|full|pdf)/[^"]+)"[^>]*class="[^"]*issue-item__title[^"]*"[^>]*>(.*?)</a>',
        html,
        flags=re.I | re.S,
    )
    if not matches:
        matches = re.findall(r'href="(/doi/(?:abs|full)/10\.[^"]+)"[^>]*>(.*?)</a>', html, flags=re.I | re.S)
    items = []
    start = (max(1, int(page or 1)) - 1) * max(1, int(limit or 10))
    for href, title_html in matches[start : start + max(1, min(int(limit or 10), 25))]:
        title = re.sub(r"<[^>]+>", "", title_html)
        title = re.sub(r"\s+", " ", title).strip()
        if not title:
            continue
        link = href if href.startswith("http") else f"https://dl.acm.org{href}"
        doi = extract_doi(link)
        items.append(
            discovery_item(
                source="acm",
                external_id=doi,
                title=title,
                doi=doi,
                source_url=link,
            )
        )
    return {"items": items, "authenticated": True}
