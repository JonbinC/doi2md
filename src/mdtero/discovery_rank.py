"""Rank and sanitize discovery items before project-add / parse."""

from __future__ import annotations

import re
from typing import Any

from .discovery_http import normalize_doi

_SI_DOI_RE = re.compile(
    r"(?:\.s\d{3,}(?:\.[a-z0-9]+)?$|/suppl(?:ementary)?(?:[./]|$)|[./]si(?:[./]|$)|supporting[-_]?info)",
    re.I,
)
_ARXIV_ID_RE = re.compile(r"^(?:arXiv:)?(\d{4}\.\d{4,5})(?:v\d+)?$", re.I)
_ARXIV_DOI_RE = re.compile(r"^10\.48550/arXiv\.(\d{4}\.\d{4,5})(?:v\d+)?$", re.I)


def is_supplementary_doi(doi: str | None) -> bool:
    text = str(doi or "").strip()
    if not text:
        return False
    return bool(_SI_DOI_RE.search(text))


def sanitize_discovery_item(item: dict[str, Any]) -> dict[str, Any]:
    """Prefer parseable full-text targets over publisher DOI / SI DOI traps."""
    row = dict(item)
    source = str(row.get("source") or row.get("external_source") or "").strip().lower()
    doi = normalize_doi(row.get("doi"))
    external_id = str(row.get("external_id") or "").strip()
    source_url = str(row.get("source_url") or "").strip()
    pdf = str(row.get("open_access_pdf_url") or "").strip() or None

    if is_supplementary_doi(doi):
        row["doi_quality"] = "supplementary"
        row["doi"] = None
        doi = None
        # Fall back to landing/PDF URL for parse.
        if pdf or source_url:
            row["parse_input_kind"] = "url"
            row["parse_input_value"] = pdf or source_url
            row["parse_readiness"] = "ready_via_url"
        else:
            row["parse_input_kind"] = None
            row["parse_input_value"] = None
            row["parse_readiness"] = "metadata_only"

    if source == "arxiv":
        arxiv_id = _arxiv_id_from(external_id) or _arxiv_id_from(source_url) or _arxiv_id_from(doi)
        if arxiv_id:
            abs_url = f"https://arxiv.org/abs/{arxiv_id}"
            pdf_url = pdf or f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            row["external_id"] = arxiv_id
            row["source_url"] = abs_url
            row["open_access_pdf_url"] = pdf_url
            if doi and not str(doi).lower().startswith("10.48550/arxiv."):
                row["publisher_doi"] = doi
            row["doi"] = f"10.48550/arXiv.{arxiv_id}"
            row["parse_input_kind"] = "doi"
            row["parse_input_value"] = row["doi"]
            row["parse_readiness"] = "ready_via_doi"

    if source in {"zenodo", "hal", "core"} and pdf:
        # Prefer direct OA PDF over HTML landing pages that often yield abstract_only.
        row["parse_input_kind"] = "url"
        row["parse_input_value"] = pdf
        row["parse_readiness"] = "ready_via_url"
        row["parse_preference"] = "open_access_pdf"

    return row


def rank_discovery_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            continue
        item = sanitize_discovery_item(raw)
        scored.append((_score(item), index, item))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [item for _, _, item in scored]


def _score(item: dict[str, Any]) -> int:
    score = 0
    readiness = str(item.get("parse_readiness") or "")
    doi = str(item.get("doi") or "")
    source = str(item.get("source") or "").lower()
    sources = item.get("sources") if isinstance(item.get("sources"), list) else []
    source_count = len({str(s).strip().lower() for s in sources if str(s).strip()}) or (1 if source else 0)
    try:
        query_match = float(item.get("query_match_score") or 0)
    except (TypeError, ValueError):
        query_match = 0.0

    if item.get("doi_quality") == "supplementary":
        score -= 250
    if readiness == "ready_via_doi":
        score += 100
    elif readiness == "ready_via_url":
        score += 70
    if item.get("open_access_pdf_url"):
        score += 50
    if item.get("parse_preference") == "open_access_pdf":
        score += 40
    # Multi-source corroboration beats a single weak preprint hit.
    if source_count >= 2:
        score += 25 + min(35, (source_count - 2) * 10)
    # Citation signal (log-ish) so landmark papers outrank random arXiv matches.
    cite = max(int(item.get("citation_count") or 0), 0)
    if cite > 0:
        score += min(55, 8 + int(cite ** 0.5))
    # Query relevance is first-class; low overlap should not win via PDF bonus alone.
    score += int(query_match * 45)
    if query_match < 0.2:
        score -= 35
    # Mild arXiv preference only when the query actually matches.
    if (
        source == "arxiv"
        and str(item.get("parse_input_value") or "").lower().startswith("10.48550/arxiv.")
        and query_match >= 0.25
    ):
        score += 15
    if source in {"biorxiv", "medrxiv"} and doi.startswith("10.1101/") and query_match >= 0.2:
        score += 15
    elif source == "chemrxiv" and doi and query_match >= 0.2:
        score += 15
    if is_supplementary_doi(doi):
        score -= 250
    if item.get("abstract_preview"):
        score += 5
    return score


def _arxiv_id_from(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = _ARXIV_DOI_RE.match(text)
    if match:
        return match.group(1)
    match = _ARXIV_ID_RE.match(text)
    if match:
        return match.group(1)
    url_match = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5})(?:v\d+)?", text, re.I)
    if url_match:
        return url_match.group(1)
    return None
