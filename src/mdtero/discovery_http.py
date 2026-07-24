"""Shared HTTP helpers for local academic discovery providers."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from xml.etree import ElementTree as ET

_USER_AGENT = "mdtero-local-discovery/0.2 (+https://mdtero.com)"


class LocalDiscoveryError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str = "local_discovery_failed", detail: Any = None):
        super().__init__(message)
        self.reason_code = reason_code
        self.detail = detail
_DOI_RE = re.compile(r"^(10\.\d{4,9}/[-._;()/:A-Z0-9]+)$", re.I)
_DOI_URL_RE = re.compile(r"^https?://(?:dx\.)?doi\.org/(10\.\d{4,9}/[-._;()/:A-Z0-9]+)$", re.I)
_DOI_FIND_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)


def user_agent() -> str:
    return _USER_AGENT


def normalize_doi(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = _DOI_URL_RE.match(text) or _DOI_RE.match(text)
    if match:
        return match.group(1).rstrip(".,;)")
    if text.lower().startswith("doi:"):
        candidate = text[4:].strip()
        return candidate.rstrip(".,;)") if _DOI_RE.match(candidate) else None
    found = _DOI_FIND_RE.search(text)
    return found.group(0).rstrip(".,;)") if found else None


def extract_doi(text: Any) -> str | None:
    return normalize_doi(text)


def http_get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    provider: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    data = http_get_bytes(url, headers=headers, provider=provider, timeout=timeout)
    try:
        payload = json.loads(data.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise LocalDiscoveryError(
            f"{provider} returned invalid JSON",
            reason_code="provider_response_invalid",
            detail=str(exc),
        ) from exc
    if not isinstance(payload, dict):
        raise LocalDiscoveryError(
            f"{provider} returned a non-object JSON payload",
            reason_code="provider_response_invalid",
        )
    return payload


def http_get_bytes(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    provider: str,
    timeout: float = 30.0,
) -> bytes:
    merged = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    if headers:
        merged.update(headers)
    request = urllib.request.Request(url, headers=merged, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = _read_error_body(exc)
        reason = "provider_rate_limited" if exc.code == 429 else "provider_http_error"
        if exc.code in {401, 403}:
            reason = "provider_auth_failed"
        raise LocalDiscoveryError(
            f"{provider} request failed with HTTP {exc.code}",
            reason_code=reason,
            detail=detail or str(exc),
        ) from exc
    except urllib.error.URLError as exc:
        raise LocalDiscoveryError(
            f"{provider} request failed: {exc.reason}",
            reason_code="provider_network_error",
            detail=str(exc.reason),
        ) from exc


def http_get_xml(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    provider: str,
    timeout: float = 30.0,
) -> ET.Element:
    data = http_get_bytes(
        url,
        headers={**(headers or {}), "Accept": "application/xml, text/xml, */*"},
        provider=provider,
        timeout=timeout,
    )
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise LocalDiscoveryError(
            f"{provider} returned invalid XML",
            reason_code="provider_response_invalid",
            detail=str(exc),
        ) from exc


def encode_query(params: dict[str, Any]) -> str:
    cleaned = {str(key): str(value) for key, value in params.items() if value is not None}
    return urllib.parse.urlencode(cleaned)


def discovery_item(
    *,
    source: str,
    external_id: str | None,
    title: str,
    authors: list[str] | None = None,
    year: Any = None,
    venue: str | None = None,
    abstract_preview: str | None = None,
    citation_count: int = 0,
    doi: str | None = None,
    source_url: str | None = None,
    open_access_pdf_url: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_doi = normalize_doi(doi)
    authors_list = [str(name).strip() for name in (authors or []) if str(name).strip()]
    landing = str(source_url or "").strip() or None
    pdf = str(open_access_pdf_url or "").strip() or None
    item: dict[str, Any] = {
        "external_source": source,
        "external_id": str(external_id or "").strip() or None,
        "title": str(title or "").strip(),
        "authors": authors_list,
        "year": year,
        "venue": str(venue or "").strip() or None,
        "abstract_preview": str(abstract_preview or "").strip() or None,
        "citation_count": int(citation_count or 0),
        "doi": normalized_doi,
        "source_url": landing,
        "open_access_pdf_url": pdf,
        "parse_input_kind": "doi" if normalized_doi else ("url" if landing or pdf else None),
        "parse_input_value": normalized_doi or landing or pdf,
        "parse_readiness": (
            "ready_via_doi"
            if normalized_doi
            else ("ready_via_url" if landing or pdf else "metadata_only")
        ),
        "source": source,
    }
    if extra:
        item["extra"] = extra
    return item


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read()
    except Exception:
        return str(exc)
    return raw.decode("utf-8", errors="replace").strip()[:500]
