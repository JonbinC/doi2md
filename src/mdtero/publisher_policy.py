"""Shared, side-effect-free publisher URL policy used by Connect and Relay.

This module is intentionally small so Relay's isolated browser sidecar can
bundle the same implementation without installing the full Python client.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

IEEE_HOST = "ieeexplore.ieee.org"


def ieee_arnumber_from_url(url: str) -> str:
    """Return an IEEE document number only from a canonical Xplore URL."""
    parsed = urlparse(str(url or "").strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme.lower() != "https" or host != IEEE_HOST:
        return ""
    match = re.search(r"/(?:abstract/)?document/(\d+)(?:/|$)", parsed.path, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    values = parse_qs(parsed.query).get("arnumber") or []
    return values[0] if values and re.fullmatch(r"\d+", values[0]) else ""


def ieee_stamp_pdf_url(article_url: str) -> str:
    """Build IEEE's first-party stampPDF route from an authorized article URL."""
    arnumber = ieee_arnumber_from_url(article_url)
    if not arnumber:
        return ""
    return f"https://{IEEE_HOST}/stampPDF/getPDF.jsp?tp=&arnumber={arnumber}"
