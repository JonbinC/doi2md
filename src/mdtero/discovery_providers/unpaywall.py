from __future__ import annotations

from typing import Any

from ..discovery_http import LocalDiscoveryError, discovery_item, encode_query, http_get_json, normalize_doi

DEFAULT_API_BASE = "https://api.unpaywall.org/v2"


def search(
    query: str,
    *,
    limit: int = 10,
    page: int = 1,
    email: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Unpaywall is DOI-centric. Query must be a DOI (or contain one)."""
    mail = str(email or "").strip()
    if not mail:
        raise LocalDiscoveryError(
            "Unpaywall requires an email (config academic --unpaywall-email)",
            reason_code="provider_email_required",
            detail="Set MDTERO_UNPAYWALL_EMAIL or academic.unpaywall_email",
        )
    doi = normalize_doi(query)
    if not doi:
        raise LocalDiscoveryError(
            "Unpaywall search expects a DOI query",
            reason_code="provider_doi_required",
            detail="Pass a DOI such as 10.1038/nature12373",
        )
    item = resolve_doi(doi, email=mail)
    if not item:
        return {"items": [], "authenticated": True}
    return {"items": [item], "authenticated": True}


def resolve_doi(doi: str, *, email: str) -> dict[str, Any] | None:
    normalized = normalize_doi(doi)
    if not normalized:
        return None
    mail = str(email or "").strip()
    if not mail:
        return None
    url = f"{DEFAULT_API_BASE}/{normalized}?{encode_query({'email': mail})}"
    payload = http_get_json(url, provider="unpaywall")
    title = str(payload.get("title") or normalized).strip()
    authors = []
    for author in payload.get("z_authors") or []:
        if not isinstance(author, dict):
            continue
        given = str(author.get("given") or "").strip()
        family = str(author.get("family") or "").strip()
        name = " ".join(part for part in (given, family) if part).strip()
        if name:
            authors.append(name)
    best = payload.get("best_oa_location") if isinstance(payload.get("best_oa_location"), dict) else {}
    pdf = str(best.get("url_for_pdf") or "").strip() or None
    landing = str(best.get("url") or payload.get("doi_url") or "").strip() or None
    year = payload.get("year")
    try:
        year = int(year) if year is not None else None
    except (TypeError, ValueError):
        year = None
    return discovery_item(
        source="unpaywall",
        external_id=normalized,
        title=title,
        authors=authors,
        year=year,
        venue=str((payload.get("journal_name") or "")).strip() or None,
        doi=normalized,
        source_url=landing or f"https://doi.org/{normalized}",
        open_access_pdf_url=pdf,
    )


def resolve_best_pdf_url(doi: str, *, email: str | None) -> str | None:
    mail = str(email or "").strip()
    if not mail:
        return None
    item = resolve_doi(doi, email=mail)
    if not item:
        return None
    return str(item.get("open_access_pdf_url") or "").strip() or None
