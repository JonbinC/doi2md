from __future__ import annotations

import re
from typing import Any

from ..discovery_http import LocalDiscoveryError, discovery_item, encode_query, extract_doi, http_get_bytes

SEARCH_URL = "https://papers.ssrn.com/sol3/results.cfm"


def search(query: str, *, limit: int = 10, page: int = 1, **_: Any) -> dict[str, Any]:
    params = {"txtKey_Words": str(query).strip()}
    url = f"{SEARCH_URL}?{encode_query(params)}"
    try:
        raw = http_get_bytes(url, headers={"Accept": "text/html"}, provider="ssrn")
    except LocalDiscoveryError as exc:
        raise LocalDiscoveryError(
            "SSRN search blocked or unavailable",
            reason_code=exc.reason_code if exc.reason_code != "provider_http_error" else "provider_bot_detection",
            detail=exc.detail or str(exc),
        ) from exc
    html = raw.decode("utf-8", errors="replace")
    if "captcha" in html.lower() or "cf-challenge" in html.lower():
        raise LocalDiscoveryError(
            "SSRN bot detection / challenge page",
            reason_code="provider_bot_detection",
            detail="Cloudflare or SSRN challenge encountered",
        )
    # Best-effort title/link extraction; public PDF only when exposed.
    pattern = re.compile(
        r'<a[^>]+href="([^"]*abstract_id=\d+[^"]*)"[^>]*>(.*?)</a>',
        re.I | re.S,
    )
    items = []
    start = (max(1, int(page or 1)) - 1) * max(1, int(limit or 10))
    matches = pattern.findall(html)
    for href, title_html in matches[start : start + max(1, min(int(limit or 10), 25))]:
        title = re.sub(r"<[^>]+>", "", title_html)
        title = re.sub(r"\s+", " ", title).strip()
        if not title:
            continue
        link = href if href.startswith("http") else f"https://papers.ssrn.com{href}"
        abs_id_match = re.search(r"abstract_id=(\d+)", link)
        external_id = abs_id_match.group(1) if abs_id_match else None
        items.append(
            discovery_item(
                source="ssrn",
                external_id=external_id,
                title=title,
                doi=extract_doi(title),
                source_url=link,
            )
        )
    return {"items": items, "authenticated": False}
