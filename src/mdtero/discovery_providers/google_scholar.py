from __future__ import annotations

import re
from typing import Any
from urllib.request import ProxyHandler, build_opener

from ..discovery_http import LocalDiscoveryError, discovery_item, encode_query, extract_doi, user_agent

SEARCH_URL = "https://scholar.google.com/scholar"


def search(
    query: str,
    *,
    limit: int = 10,
    page: int = 1,
    proxy_url: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    per_page = max(1, min(int(limit or 10), 20))
    start = (max(1, int(page or 1)) - 1) * 10
    params = {"q": str(query).strip(), "start": str(start), "hl": "en"}
    url = f"{SEARCH_URL}?{encode_query(params)}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html",
    }
    proxy = str(proxy_url or "").strip()
    try:
        html = _fetch(url, headers=headers, proxy_url=proxy)
    except LocalDiscoveryError:
        raise
    except Exception as exc:
        raise LocalDiscoveryError(
            "Google Scholar request failed",
            reason_code="provider_network_error",
            detail=str(exc),
        ) from exc
    if "captcha" in html.lower() or "unusual traffic" in html.lower():
        raise LocalDiscoveryError(
            "Google Scholar bot detection; configure campus/proxy",
            reason_code="provider_bot_detection",
            detail="Set proxy_url / MDTERO_PROXY_URL or use campus outlet",
        )
    items = _parse(html)[:per_page]
    return {"items": items, "authenticated": False, "proxied": bool(proxy)}


def _fetch(url: str, *, headers: dict[str, str], proxy_url: str) -> str:
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, headers=headers, method="GET")
    opener = build_opener(ProxyHandler({"http": proxy_url, "https": proxy_url})) if proxy_url else build_opener()
    try:
        with opener.open(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        reason = "provider_rate_limited" if exc.code == 429 else "provider_http_error"
        if exc.code in {401, 403}:
            reason = "provider_bot_detection"
        raise LocalDiscoveryError(
            f"google_scholar request failed with HTTP {exc.code}",
            reason_code=reason,
            detail=str(exc),
        ) from exc
    except urllib.error.URLError as exc:
        raise LocalDiscoveryError(
            f"google_scholar request failed: {exc.reason}",
            reason_code="provider_network_error",
            detail=str(exc.reason),
        ) from exc


def _parse(html: str) -> list[dict[str, Any]]:
    blocks = re.split(r'<div class="gs_r[^"]*"', html)[1:]
    items: list[dict[str, Any]] = []
    for block in blocks:
        title_match = re.search(r'<h3[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.I | re.S)
        if not title_match:
            continue
        href = title_match.group(1)
        title = re.sub(r"<[^>]+>", "", title_match.group(2))
        title = re.sub(r"\s+", " ", title).strip()
        if not title:
            continue
        pdf_match = re.search(r'<div class="gs_or_ggsm"[^>]*>\s*<a[^>]+href="([^"]+)"', block, re.I)
        snippet_match = re.search(r'<div class="gs_rs">(.*?)</div>', block, re.I | re.S)
        snippet = re.sub(r"<[^>]+>", "", snippet_match.group(1)) if snippet_match else ""
        items.append(
            discovery_item(
                source="google_scholar",
                external_id=None,
                title=title,
                abstract_preview=re.sub(r"\s+", " ", snippet).strip() or None,
                doi=extract_doi(href) or extract_doi(snippet),
                source_url=href,
                open_access_pdf_url=pdf_match.group(1) if pdf_match else None,
            )
        )
    return items
