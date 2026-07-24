"""Optional Sci-Hub download helper.

Disabled by default. Never used by discover search aggregation.
Enable explicitly via academic.enable_scihub / --enable-scihub.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from ..discovery_http import LocalDiscoveryError, user_agent

DEFAULT_BASE_URL = "https://sci-hub.se"


def download_pdf(
    identifier: str,
    *,
    output_dir: str | Path,
    base_url: str | None = None,
    enabled: bool = False,
) -> str:
    if not enabled:
        raise LocalDiscoveryError(
            "Sci-Hub is disabled by default",
            reason_code="scihub_disabled",
            detail="Pass enable_scihub=True / configure academic.enable_scihub to opt in",
        )
    text = str(identifier or "").strip()
    if not text:
        raise LocalDiscoveryError("Sci-Hub identifier required", reason_code="scihub_identifier_missing")
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    mirror = str(base_url or DEFAULT_BASE_URL).rstrip("/")
    pdf_url = _resolve_pdf_url(text, mirror=mirror)
    if not pdf_url:
        raise LocalDiscoveryError(
            "Sci-Hub could not resolve a PDF URL",
            reason_code="scihub_not_found",
            detail=text,
        )
    request = Request(
        pdf_url,
        headers={
            "User-Agent": user_agent(),
            "Accept": "application/pdf,*/*",
        },
        method="GET",
    )
    with urlopen(request, timeout=45) as response:
        content = response.read()
        content_type = str(response.headers.get("Content-Type") or "").lower()
    if not (content.startswith(b"%PDF") or "pdf" in content_type):
        raise LocalDiscoveryError(
            "Sci-Hub response was not a PDF",
            reason_code="scihub_not_pdf",
            detail=content_type,
        )
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", text)[:80] or "paper"
    path = root / f"scihub_{safe}_{digest}.pdf"
    path.write_bytes(content)
    return str(path)


def _resolve_pdf_url(identifier: str, *, mirror: str) -> str | None:
    if identifier.lower().endswith(".pdf") and identifier.startswith("http"):
        return identifier
    page_url = f"{mirror}/{identifier}"
    request = Request(page_url, headers={"User-Agent": user_agent(), "Accept": "text/html"}, method="GET")
    try:
        with urlopen(request, timeout=30) as response:
            html = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise LocalDiscoveryError(
            f"Sci-Hub page fetch failed: {exc}",
            reason_code="scihub_network_error",
            detail=str(exc),
        ) from exc
    if "article not found" in html.lower():
        return None
    embed = re.search(r'<embed[^>]+src=["\']([^"\']+)["\']', html, re.I)
    iframe = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.I)
    candidate = (embed.group(1) if embed else None) or (iframe.group(1) if iframe else None)
    if not candidate:
        pdf_link = re.search(r'location\.href\s*=\s*[\'"]([^\'"]+\.pdf[^\'"]*)[\'"]', html, re.I)
        candidate = pdf_link.group(1) if pdf_link else None
    if not candidate:
        return None
    if candidate.startswith("//"):
        return "https:" + candidate
    if candidate.startswith("/"):
        return mirror + candidate
    return candidate


def capability() -> dict[str, Any]:
    return {
        "provider": "scihub",
        "search": False,
        "download": True,
        "default_enabled": False,
        "notes": "Optional download fallback only; user must opt in",
    }
