"""OA-first download fallback chain (paper-search-mcp compatible, Sci-Hub opt-in)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .discovery_http import LocalDiscoveryError, normalize_doi, user_agent
from .discovery_providers import unpaywall
from .discovery_providers.scihub import download_pdf as scihub_download


def download_with_fallback(
    *,
    pdf_url: str | None = None,
    doi: str | None = None,
    title: str | None = None,
    output_dir: str | Path,
    unpaywall_email: str | None = None,
    enable_scihub: bool = False,
    scihub_base_url: str | None = None,
) -> dict[str, Any]:
    """Try direct PDF URL → Unpaywall OA → optional Sci-Hub.

    Sci-Hub is disabled by default and only runs when ``enable_scihub=True``.
    """
    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    attempts: list[str] = []

    direct = str(pdf_url or "").strip()
    if direct:
        path = _download_url(direct, root, hint="direct")
        if path:
            return {"status": "ok", "path": path, "via": "direct_pdf_url", "attempts": attempts}
        attempts.append("direct_pdf_url: download failed")

    normalized_doi = normalize_doi(doi)
    if normalized_doi and unpaywall_email:
        try:
            oa_url = unpaywall.resolve_best_pdf_url(normalized_doi, email=unpaywall_email)
        except LocalDiscoveryError as exc:
            attempts.append(f"unpaywall: {exc.reason_code}")
            oa_url = None
        if oa_url:
            path = _download_url(oa_url, root, hint=f"unpaywall_{normalized_doi}")
            if path:
                return {"status": "ok", "path": path, "via": "unpaywall", "attempts": attempts}
            attempts.append("unpaywall: resolved URL but download failed")
        else:
            attempts.append("unpaywall: no OA URL")
    elif normalized_doi:
        attempts.append("unpaywall: email not configured")
    else:
        attempts.append("unpaywall: DOI missing")

    if enable_scihub:
        identifier = normalized_doi or str(title or "").strip() or direct
        try:
            path = scihub_download(
                identifier,
                output_dir=root,
                base_url=scihub_base_url,
                enabled=True,
            )
            return {"status": "ok", "path": path, "via": "scihub", "attempts": attempts}
        except LocalDiscoveryError as exc:
            attempts.append(f"scihub: {exc.reason_code}")
    else:
        attempts.append("scihub: disabled (default)")

    return {
        "status": "failed",
        "path": None,
        "via": None,
        "attempts": attempts,
        "reason_code": "oa_download_failed",
        "action_hint": (
            "No lawful OA PDF resolved. Configure Unpaywall email, campus proxy, "
            "publisher keys, or browser extension handoff. Sci-Hub remains opt-in only."
        ),
    }


def _download_url(url: str, root: Path, *, hint: str) -> str | None:
    request = Request(url, headers={"User-Agent": user_agent(), "Accept": "application/pdf,*/*"}, method="GET")
    try:
        with urlopen(request, timeout=45) as response:
            content = response.read()
            content_type = str(response.headers.get("Content-Type") or "").lower()
    except Exception:
        return None
    if not (content.startswith(b"%PDF") or "pdf" in content_type or url.lower().endswith(".pdf")):
        return None
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in hint)[:80] or "paper"
    path = root / f"{safe}.pdf"
    path.write_bytes(content)
    return str(path)
