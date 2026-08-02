from __future__ import annotations

import mimetypes
import os
import re
import tempfile
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .network import local_egress_is_campus_outlet, proxy_settings_from_config


DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
URL_PATTERN = re.compile(r"^https?://", re.I)
CHALLENGE_MARKERS = (
    "akamai/interstitial",
    "bm-verify=",
    "cf-browser-verification",
    "checking if the site connection is secure",
    "google.com/recaptcha/challengepage",
    "enable javascript and cookies to continue",
    "interstitialchallenge",
    "recaptchachallengepageui",
    "recaptcha/challengepage",
    "just a moment",
    "verify you are human",
    "window._cf_chl_opt",
    "making sure you're not a bot",
    "protected by anubis",
    "anubis version",
    "proof-of-work scheme",
    "you must enable javascript to get past this challenge",
)
PUBLISHER_ERROR_SHELL_MARKERS = (
    "ieee xplore - unable to load page",
    "unable to load page",
    "xplorestaging.ieee.org",
)
META_REFRESH_RE = re.compile(
    rb"<meta[^>]+http-equiv=[\"']?refresh[\"']?[^>]+content=[\"'][^\"']*url=([^\"'>\s]+)",
    re.I,
)
CURL_CFFI_IMPERSONATION_PROFILES = (
    "chrome136",
    "chrome124",
    "safari184",
    "chrome",
)


@dataclass
class AcquiredArtifact:
    url: str
    path: Path
    artifact_kind: str
    source: str
    status_code: int | None = None
    content_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "path": str(self.path),
            "artifact_kind": self.artifact_kind,
            "source": self.source,
            "status_code": self.status_code,
            "content_type": self.content_type,
        }


class AcquisitionError(RuntimeError):
    def __init__(self, reason_code: str, action_hint: str, *, diagnostics: dict[str, Any] | None = None) -> None:
        super().__init__(action_hint)
        self.reason_code = reason_code
        self.action_hint = action_hint
        self.diagnostics = diagnostics or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason_code": self.reason_code,
            "action_hint": self.action_hint,
            "diagnostics": self.diagnostics,
        }


def _local_outlet_is_campus(
    config: Any | None,
    *,
    local_outlet_is_campus: bool | None = None,
) -> bool:
    if local_outlet_is_campus is not None:
        return bool(local_outlet_is_campus)
    return local_egress_is_campus_outlet(config=config)


def _should_prefer_cloud_via_relay(
    config: Any | None,
    *,
    relay_connected: bool | None = None,
    local_outlet_is_campus: bool | None = None,
) -> bool:
    if _local_outlet_is_campus(config, local_outlet_is_campus=local_outlet_is_campus):
        return False
    return relay_connected is True


def should_acquire_locally(
    route: dict[str, Any],
    input_value: str,
    *,
    config: Any | None = None,
    relay_connected: bool | None = None,
    local_outlet_is_campus: bool | None = None,
) -> bool:
    if _is_direct_local_artifact_url(input_value):
        return True
    if route.get("legacy_fallback") or route.get("route_planner_fallback"):
        return False
    if route.get("requires_raw_upload"):
        return True
    if _should_prefer_cloud_via_relay(
        config,
        relay_connected=relay_connected,
        local_outlet_is_campus=local_outlet_is_campus,
    ):
        return False
    actions = {str(action) for action in route.get("action_sequence") or []}
    candidate_urls = _candidate_urls(route, input_value)
    # Elsevier XML is a credentialed publisher API route.  Apply the campus
    # outlet policy before the generic can_acquire_locally projection; the
    # latter is intentionally broad and would otherwise make an off-campus
    # CLI fetch without Relay look local merely because a URL is available.
    if "fetch_elsevier_xml" in actions:
        if not _elsevier_api_key(config):
            return False
        if candidate_urls:
            return _should_fetch_elsevier_locally(
                config,
                relay_connected=relay_connected,
                local_outlet_is_campus=local_outlet_is_campus,
            )
        return False
    # A server-side Elsevier key is a valid route even when this client has no
    # local publisher key.  Do not send an unauthenticated local request first;
    # the server can use its configured key and still try public OA fallbacks.
    if bool(route.get("can_acquire_locally")) and candidate_urls:
        return True
    # Compatibility with older servers: new route projections use the boolean
    # above, while historical servers still expose action labels.
    local_actions = {"fetch_remote_html", "fetch_epub_asset", "fetch_structured_xml", "fallback_pdf_parse"}
    if actions.intersection(local_actions) and candidate_urls:
        return True
    return False


def route_needs_browser_fallback(route: dict[str, Any], *, config: Any | None = None) -> bool:
    """Return whether a missing server credential should fall back to a local browser.

    This is deliberately limited to an Elsevier institutional route without a
    public candidate.  An OA/repository candidate remains a normal server
    route, and a locally configured key remains subject to the campus/Relay
    egress policy in :func:`should_acquire_locally`.
    """
    actions = {str(action) for action in route.get("action_sequence") or []}
    if "fetch_elsevier_xml" not in actions or _elsevier_api_key(config):
        return False
    missing = {
        str(name or "").strip().upper()
        for name in route.get("missing_credentials") or []
        if str(name or "").strip()
    }
    if "ELSEVIER_API_KEY" not in missing:
        return False
    candidates = route.get("acquisition_candidates") or []
    if not isinstance(candidates, (list, tuple)):
        candidates = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        access = str(candidate.get("access") or "").strip().lower()
        if access == "open" and not bool(candidate.get("requires_user_rights")) and not bool(candidate.get("requires_api_key")):
            return False
    return True


def _should_fetch_elsevier_locally(
    config: Any | None,
    *,
    relay_connected: bool | None = None,
    local_outlet_is_campus: bool | None = None,
) -> bool:
    if _local_outlet_is_campus(config, local_outlet_is_campus=local_outlet_is_campus):
        return True
    # Off-campus CLI hosts should use cloud parse so the backend can fetch via campus relay.
    if relay_connected is True:
        return False
    if relay_connected is False:
        return False
    return True


def _is_direct_local_artifact_url(input_value: str) -> bool:
    value = str(input_value or "").strip()
    if not URL_PATTERN.match(value) or DOI_PATTERN.match(value):
        return False
    return bool(_direct_artifact_kind_from_url(value) or _infer_mdpi_epub_url(value))


def acquire_from_route(route: dict[str, Any], input_value: str, *, timeout: float = 45.0, config: Any | None = None) -> AcquiredArtifact:
    candidates = _candidate_urls(route, input_value)
    if not candidates:
        raise AcquisitionError(
            "client_acquisition_no_candidate_url",
            "Route requires local acquisition but did not include a fetchable URL; use the browser extension or upload a local PDF/EPUB/XML/HTML file.",
            diagnostics={"route_kind": route.get("route_kind"), "action_sequence": route.get("action_sequence")},
        )

    errors: list[dict[str, Any]] = []
    allowed_kinds = _allowed_artifact_kinds(route)
    artifact = _try_acquire_candidates(
        route,
        candidates,
        allowed_kinds=allowed_kinds,
        timeout=timeout,
        config=config,
        errors=errors,
    )
    if artifact is not None:
        return artifact

    # HTML-first routes (e.g. best_oa_location_html) often skip OA/publisher PDFs.
    # If HTML/XML fails, retry PDF candidates instead of failing closed.
    if "pdf" not in allowed_kinds and _has_pdf_candidate(route, candidates):
        pdf_errors: list[dict[str, Any]] = []
        artifact = _try_acquire_candidates(
            route,
            candidates,
            allowed_kinds={"pdf"},
            timeout=timeout,
            config=config,
            errors=pdf_errors,
            only_kinds={"pdf"},
        )
        if artifact is not None:
            return artifact
        errors.extend(pdf_errors)

    reason_code, action_hint, diagnostics = _summarize_acquisition_failures(errors)
    if any(row.get("reason_code") == "client_acquisition_artifact_kind_not_allowed" for row in errors):
        diagnostics = {
            **(diagnostics if isinstance(diagnostics, dict) else {"errors": diagnostics}),
            "pdf_fallback_attempted": "pdf" not in allowed_kinds,
        }
    raise AcquisitionError(reason_code, action_hint, diagnostics=diagnostics)


def _try_acquire_candidates(
    route: dict[str, Any],
    candidates: list[dict[str, str]],
    *,
    allowed_kinds: set[str],
    timeout: float,
    config: Any | None,
    errors: list[dict[str, Any]],
    only_kinds: set[str] | None = None,
) -> AcquiredArtifact | None:
    for candidate in candidates:
        url = str(candidate.get("url") or "").strip()
        if not url:
            continue
        artifact_kind = _artifact_kind(candidate, route, url)
        if only_kinds and artifact_kind not in only_kinds:
            continue
        if allowed_kinds and artifact_kind not in allowed_kinds:
            errors.append(
                {
                    "url": url,
                    "reason_code": "client_acquisition_artifact_kind_not_allowed",
                    "action_hint": f"Route acceptance rules allow {sorted(allowed_kinds)}, not {artifact_kind}.",
                    "diagnostics": {"artifact_kind": artifact_kind, "allowed_artifact_kinds": sorted(allowed_kinds)},
                }
            )
            continue
        if _candidate_requires_api_key(candidate) and not _candidate_credential_configured(candidate, config=config):
            credential_name = str(candidate.get("credential_name") or "provider API key").strip()
            errors.append(
                {
                    "url": url,
                    "reason_code": "missing_api_key",
                    "action_hint": f"Configure {credential_name} before local acquisition, or let the Mdtero server try its route.",
                    **_candidate_error_context(candidate),
                    "diagnostics": {"credential_name": credential_name},
                }
            )
            continue
        extra_headers = _credential_headers(route, candidate, url, config=config)
        # Repository OA records often expose a landing page but no direct PDF
        # URL. Treat a routed PDF candidate as a landing-page discovery step
        # before recording the publisher response as a terminal failure.
        if artifact_kind == "pdf" and _direct_artifact_kind_from_url(url) != "pdf":
            try:
                artifact = _fetch_pdf_from_landing(
                    url,
                    timeout=timeout,
                    extra_headers=extra_headers,
                    config=config,
                )
                if artifact is not None:
                    return artifact
            except AcquisitionError as exc:
                errors.append({"url": url, "source": "landing_pdf_discovery", **_candidate_error_context(candidate), **exc.to_dict()})
        try:
            return _fetch_with_curl_cffi(url, artifact_kind=artifact_kind, timeout=timeout, extra_headers=extra_headers, config=config)
        except AcquisitionError as exc:
            errors.append({"url": url, "source": "curl_cffi", **_candidate_error_context(candidate), **exc.to_dict()})
        try:
            return _fetch_with_httpx(url, artifact_kind=artifact_kind, timeout=timeout, extra_headers=extra_headers, config=config)
        except AcquisitionError as exc:
            errors.append({"url": url, "source": "httpx", **_candidate_error_context(candidate), **exc.to_dict()})
    return None


def _fetch_pdf_from_landing(
    landing_url: str,
    *,
    timeout: float,
    extra_headers: dict[str, str] | None,
    config: Any | None,
) -> AcquiredArtifact | None:
    try:
        landing_artifact = _fetch_with_curl_cffi(
            landing_url,
            artifact_kind="html",
            timeout=timeout,
            extra_headers=extra_headers,
            config=config,
        )
    except AcquisitionError:
        landing_artifact = _fetch_with_httpx(
            landing_url,
            artifact_kind="html",
            timeout=timeout,
            extra_headers=extra_headers,
            config=config,
        )
    try:
        try:
            html_bytes = landing_artifact.path.read_bytes()
        except OSError:
            return None
    finally:
        landing_artifact.path.unlink(missing_ok=True)
    pdf_url = _extract_pdf_url_from_landing(html_bytes, base_url=landing_url)
    if not pdf_url:
        return None
    try:
        return _fetch_with_curl_cffi(
            pdf_url,
            artifact_kind="pdf",
            timeout=timeout,
            extra_headers=extra_headers,
            config=config,
        )
    except AcquisitionError:
        return _fetch_with_httpx(
            pdf_url,
            artifact_kind="pdf",
            timeout=timeout,
            extra_headers=extra_headers,
            config=config,
        )


def _extract_pdf_url_from_landing(html_bytes: bytes, *, base_url: str) -> str:
    text = html_bytes.decode("utf-8", errors="ignore")
    candidates: list[str] = []
    for match in re.finditer(r"(?:href|data-href|data-url)=[\"']([^\"']+)[\"']", text, flags=re.I):
        candidates.append(match.group(1))
    candidates.extend(re.findall(r"https?://[^\"'<>\\s]+?\.pdf(?:\?[^\"'<>\\s]*)?", text, flags=re.I))
    for raw_url in candidates:
        value = urllib.parse.urljoin(base_url, raw_url.strip())
        if _direct_artifact_kind_from_url(value) == "pdf":
            return value
    return ""


def _has_pdf_candidate(route: dict[str, Any], candidates: list[dict[str, str]]) -> bool:
    for candidate in candidates:
        url = str(candidate.get("url") or "").strip()
        if not url:
            continue
        if _artifact_kind(candidate, route, url) == "pdf":
            return True
    return False


def _allowed_artifact_kinds(route: dict[str, Any]) -> set[str]:
    acceptance_rules = route.get("acceptance_rules") if isinstance(route.get("acceptance_rules"), dict) else {}
    return {
        str(kind or "").strip().lower()
        for kind in (acceptance_rules.get("allowed_artifact_kinds") or [])
        if str(kind or "").strip().lower() in {"html", "xml", "epub", "pdf"}
    }


def _candidate_error_context(candidate: dict[str, str]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    if candidate.get("source"):
        context["candidate_source"] = candidate.get("source")
    if candidate.get("connector"):
        context["candidate_connector"] = candidate.get("connector")
    if candidate.get("requires_browser"):
        context["requires_browser"] = True
    if candidate.get("credential_name"):
        context["credential_name"] = candidate.get("credential_name")
    return context


def _candidate_requires_api_key(candidate: dict[str, str]) -> bool:
    value = candidate.get("requires_api_key")
    return value is True or str(value or "").strip().lower() in {"1", "true", "yes"}


def _candidate_credential_configured(candidate: dict[str, str], *, config: Any | None) -> bool:
    name = str(candidate.get("credential_name") or "").strip().upper()
    if name == "ELSEVIER_API_KEY":
        return bool(_elsevier_api_key(config))
    if name in {"WILEY_TDM_API_KEY", "WILEY_TDM_TOKEN", "TDM_API_TOKEN"}:
        return bool(_wiley_tdm_token(config))
    if name in {"SPRINGER_API_KEY", "SPRINGER_NATURE_API_KEY"}:
        academic = getattr(config, "academic", None)
        return bool(
            str(getattr(academic, "springer_api_key", "") or "").strip()
            or str(getattr(academic, "springer_nature_api_key", "") or "").strip()
            or os.environ.get("SPRINGER_API_KEY", "").strip()
            or os.environ.get("SPRINGER_NATURE_API_KEY", "").strip()
        )
    return True


def curl_cffi_available() -> bool:
    try:
        import curl_cffi.requests  # noqa: F401
    except Exception:
        return False
    return True


def _credential_headers(route: dict[str, Any], candidate: dict[str, str], url: str, *, config: Any | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    host = urllib.parse.urlparse(url).netloc.lower()
    if host == "api.elsevier.com":
        key = _elsevier_api_key(config)
        if key:
            headers["X-ELS-APIKey"] = key
    if host == "api.wiley.com":
        token = _wiley_tdm_token(config)
        if token:
            headers["Wiley-TDM-Client-Token"] = token
    cookie = _access_cookie_header(url, config=config)
    if cookie:
        headers["Cookie"] = cookie
    return headers


def _access_cookie_header(url: str, *, config: Any | None) -> str | None:
    access = getattr(config, "access", None)
    if access is None or not bool(getattr(access, "carsi_enabled", False)):
        return None
    try:
        from .access_outlets import cookie_header_for_url, load_carsi_cookies
    except Exception:
        return None
    return cookie_header_for_url(url, load_carsi_cookies())


def _elsevier_api_key(config: Any | None) -> str:
    academic = getattr(config, "academic", None)
    return str(getattr(academic, "elsevier_api_key", "") or "").strip()


def _wiley_tdm_token(config: Any | None) -> str:
    academic = getattr(config, "academic", None)
    return str(getattr(academic, "wiley_tdm_token", "") or "").strip()


def _candidate_urls(route: dict[str, Any], input_value: str) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(
        url: object,
        *,
        kind: str | None = None,
        connector: str | None = None,
        prefer_mdpi_epub: bool = True,
        source: str | None = None,
        requires_browser: bool = False,
        requires_api_key: bool = False,
        credential_name: str | None = None,
    ) -> None:
        value = str(url or "").strip()
        if not value or not URL_PATTERN.match(value) or value in seen:
            return
        if prefer_mdpi_epub:
            mdpi_epub = _infer_mdpi_epub_url(value)
            if mdpi_epub and mdpi_epub != value:
                add(mdpi_epub, kind="epub", connector="mdpi_epub_asset", prefer_mdpi_epub=False)
        seen.add(value)
        item = {"url": value}
        if kind:
            item["artifact_kind"] = kind
        if connector:
            item["connector"] = connector
        if source:
            item["source"] = source
        if requires_browser:
            item["requires_browser"] = "true"
        if requires_api_key:
            item["requires_api_key"] = "true"
        if credential_name:
            item["credential_name"] = credential_name
        candidates.append(item)

    for candidate in route.get("acquisition_candidates") or []:
        if not isinstance(candidate, dict):
            continue
        connector = str(candidate.get("connector") or "") or None
        candidate_kind = str(candidate.get("artifact_kind") or "").strip().lower() or None
        candidate_requires_api_key = candidate.get("requires_api_key") is True or str(candidate.get("requires_api_key") or "").strip().lower() in {"1", "true", "yes"}
        credential_name = str(candidate.get("credential_name") or "").strip() or None
        add(candidate.get("url"), kind=candidate_kind, connector=connector, requires_api_key=candidate_requires_api_key, credential_name=credential_name)
        html_url = str(candidate.get("html_url") or "").strip()
        add(html_url, kind=None if _direct_artifact_kind_from_url(html_url) else "html", connector=connector, requires_api_key=candidate_requires_api_key, credential_name=credential_name)
        add(candidate.get("xml_url") or candidate.get("jats_url") or candidate.get("jatsxml"), kind="xml", connector=connector, requires_api_key=candidate_requires_api_key, credential_name=credential_name)
        add(candidate.get("epub_url"), kind="epub", connector=connector, requires_api_key=candidate_requires_api_key, credential_name=credential_name)
        add(candidate.get("pdf_url"), kind="pdf", connector=connector, requires_api_key=candidate_requires_api_key, credential_name=credential_name)
        add(candidate.get("tdm_url"), kind="pdf", connector=connector or "wiley_tdm", requires_api_key=candidate_requires_api_key, credential_name=credential_name)

    browser_required: list[dict[str, str]] = []
    for handoff in route.get("client_handoff_candidates") or []:
        if not isinstance(handoff, dict):
            continue
        artifact_kind = str(handoff.get("artifact_kind") or "").strip().lower()
        if artifact_kind not in {"html", "xml", "epub", "pdf"}:
            continue
        capture_mode = str(handoff.get("capture_mode") or "").strip()
        url = handoff.get("source_url") if artifact_kind == "html" or capture_mode == "page_capture" else handoff.get("artifact_url")
        value = str(url or "").strip()
        if not value or not URL_PATTERN.match(value) or value in seen:
            continue
        requires_browser = bool(handoff.get("requires_user_rights")) and not bool(handoff.get("can_try_server_first"))
        item = {
            "url": value,
            "artifact_kind": artifact_kind,
            "connector": str(handoff.get("connector") or "client_handoff"),
            "source": str(handoff.get("source") or handoff.get("reason_code") or "client_handoff_candidate"),
        }
        if requires_browser:
            item["requires_browser"] = "true"
            browser_required.append(item)
        else:
            seen.add(value)
            candidates.append(item)

    for item in browser_required:
        value = item["url"]
        if value in seen:
            continue
        seen.add(value)
        candidates.append(item)

    add(route.get("best_oa_url"))
    if URL_PATTERN.match(str(input_value or "")) and not DOI_PATTERN.match(input_value):
        add(input_value)
    return candidates


def _infer_mdpi_epub_url(url: str) -> str:
    parsed = urllib.parse.urlparse(str(url or "").strip())
    if "mdpi.com" not in parsed.netloc.lower():
        return ""
    path = parsed.path.rstrip("/")
    if not path:
        return ""
    if path.endswith("/epub"):
        return urllib.parse.urlunparse(parsed._replace(query="", fragment=""))
    if path.endswith("/xml") or path.endswith("/pdf") or path.endswith("/html"):
        path = path.rsplit("/", 1)[0]
    # MDPI article paths look like /journal/volume/issue/article. Avoid
    # rewriting site-level pages such as /about or /search.
    if len([part for part in path.split("/") if part]) < 4:
        return ""
    return urllib.parse.urlunparse(parsed._replace(path=f"{path}/epub", query="", fragment=""))


def _artifact_kind(candidate: dict[str, str], route: dict[str, Any], url: str) -> str:
    explicit = str(candidate.get("artifact_kind") or "").strip().lower()
    if explicit in {"html", "xml", "epub", "pdf"}:
        return explicit
    direct_kind = _direct_artifact_kind_from_url(url)
    if direct_kind:
        return direct_kind
    route_kind = str(route.get("route_kind") or "").lower()
    actions = {str(action) for action in route.get("action_sequence") or []}
    lowered = url.lower()
    if "fetch_epub_asset" in actions or ".epub" in lowered or "/epub/" in lowered:
        return "epub"
    if "fallback_pdf_parse" in actions or ".pdf" in lowered or "/pdf" in lowered:
        return "pdf"
    if "fetch_structured_xml" in actions or "fetch_elsevier_xml" in actions or "jats" in route_kind or ".xml" in lowered or "fulltextxml" in lowered:
        return "xml"
    return "html"


def _direct_artifact_kind_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(str(url or "").strip())
    lowered_path = parsed.path.lower().rstrip("/")
    lowered_url = urllib.parse.urlunparse(parsed._replace(fragment="")).lower()
    if not lowered_path:
        return ""
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    http_accept = " ".join(value for value_list in query.values() for value in value_list).lower()
    if "text/xml" in http_accept or "application/xml" in http_accept:
        return "xml"
    if lowered_path.endswith((".epub", "/epub")) or "/doi/epub/" in lowered_url:
        return "epub"
    if (
        lowered_path.endswith((".pdf", "/pdf"))
        or "/doi/pdf/" in lowered_url
        or "/doi/epdf/" in lowered_url
        or "/doi/pdfdirect/" in lowered_url
        or "/stamppdf/" in lowered_url
        or "/stamp/" in lowered_url
    ):
        return "pdf"
    if lowered_path.endswith((".xml", "/xml", "/fulltextxml")) or "fulltextxml" in lowered_url:
        return "xml"
    if lowered_path.endswith((".html", ".htm", "/html", "/full")) or "/doi/full/" in lowered_url:
        return "html"
    return ""


def _fetch_with_curl_cffi(url: str, *, artifact_kind: str, timeout: float, extra_headers: dict[str, str] | None = None, config: Any | None = None) -> AcquiredArtifact:
    try:
        from curl_cffi import requests as curl_requests
    except Exception as exc:
        raise AcquisitionError(
            "client_curl_cffi_unavailable",
            "curl_cffi is not available in this Python environment; falling back to httpx.",
            diagnostics={"error": exc.__class__.__name__},
        ) from exc
    errors: list[dict[str, Any]] = []
    proxy_url = proxy_settings_from_config(config).proxy_url
    for profile in CURL_CFFI_IMPERSONATION_PROFILES:
        try:
            with curl_requests.Session(impersonate=profile) as session:
                request_kwargs: dict[str, Any] = {}
                if proxy_url:
                    request_kwargs["proxies"] = {"http": proxy_url, "https": proxy_url}
                response = session.get(
                    url,
                    timeout=timeout,
                    allow_redirects=True,
                    headers=_fetch_headers(url=url, artifact_kind=artifact_kind, extra_headers=extra_headers),
                    **request_kwargs,
                )
                response = _follow_meta_refresh_once(
                    session,
                    response,
                    base_url=url,
                    timeout=timeout,
                    artifact_kind=artifact_kind,
                    extra_headers=extra_headers,
                    proxy_url=proxy_url,
                )
        except Exception as exc:
            errors.append({"profile": profile, "error": exc.__class__.__name__})
            continue
        try:
            return _artifact_from_response(response, url=url, artifact_kind=artifact_kind, source=f"curl_cffi:{profile}")
        except AcquisitionError as exc:
            errors.append({"profile": profile, **exc.to_dict()})
    raise AcquisitionError(
        "client_curl_cffi_request_failed",
        "curl_cffi failed to fetch a valid routed source with browser impersonation profiles.",
        diagnostics={"profiles": list(CURL_CFFI_IMPERSONATION_PROFILES), "attempts": errors[-8:]},
    )


def _fetch_with_httpx(url: str, *, artifact_kind: str, timeout: float, extra_headers: dict[str, str] | None = None, config: Any | None = None) -> AcquiredArtifact:
    try:
        proxy_settings = proxy_settings_from_config(config)
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=_fetch_headers(url=url, artifact_kind=artifact_kind, extra_headers=extra_headers), **proxy_settings.httpx_kwargs) as client:
            response = client.get(url)
    except Exception as exc:
        raise AcquisitionError(
            "client_httpx_request_failed",
            "httpx failed to fetch the routed source.",
            diagnostics={"error": exc.__class__.__name__},
        ) from exc
    if response.status_code >= 400:
        raise AcquisitionError(
            "client_httpx_http_error",
            f"httpx fetch returned HTTP {response.status_code}.",
            diagnostics={"status_code": response.status_code},
        )
    return _artifact_from_response(response, url=url, artifact_kind=artifact_kind, source="httpx")


def _artifact_from_response(response: Any, *, url: str, artifact_kind: str, source: str) -> AcquiredArtifact:
    if response.status_code >= 400:
        raise AcquisitionError(
            "client_curl_cffi_http_error" if str(source).startswith("curl_cffi") else "client_httpx_http_error",
            f"{source} fetch returned HTTP {response.status_code}.",
            diagnostics={"status_code": response.status_code},
        )
    content = bytes(response.content or b"")
    content_type = str(response.headers.get("content-type") or "")
    _validate_payload(content, url=url, expected_kind=artifact_kind, content_type=content_type, source=source)
    path = _write_payload(content, url=url, artifact_kind=_kind_from_content_type(artifact_kind, content_type), source=source)
    return AcquiredArtifact(url=url, path=path, artifact_kind=_artifact_kind_from_path(path), source=source, status_code=response.status_code, content_type=content_type)


def _follow_meta_refresh_once(session: Any, response: Any, *, base_url: str, timeout: float, artifact_kind: str, extra_headers: dict[str, str] | None = None, proxy_url: str | None = None) -> Any:
    content_type = str(response.headers.get("content-type") or "").lower()
    if "html" not in content_type:
        return response
    marker = META_REFRESH_RE.search(bytes(response.content or b"")[:20_000])
    if not marker:
        return response
    target = urllib.parse.urljoin(base_url, marker.group(1).decode("utf-8", errors="ignore").strip("'\""))
    if not target or urllib.parse.urlparse(target).netloc != urllib.parse.urlparse(base_url).netloc:
        return response
    request_kwargs: dict[str, Any] = {}
    if proxy_url:
        request_kwargs["proxies"] = {"http": proxy_url, "https": proxy_url}
    return session.get(
        target,
        timeout=timeout,
        allow_redirects=True,
        headers=_fetch_headers(url=target, artifact_kind=artifact_kind, referer=base_url, extra_headers=extra_headers),
        **request_kwargs,
    )


def _write_payload(content: bytes, *, url: str, artifact_kind: str, source: str) -> Path:
    if not content:
        raise AcquisitionError(
            "client_acquisition_empty_payload",
            "The routed source returned an empty payload.",
            diagnostics={"url": url, "source": source},
        )
    suffix = _suffix_for_kind(artifact_kind, url)
    handle = tempfile.NamedTemporaryFile(prefix="mdtero-acquired-", suffix=suffix, delete=False)
    try:
        handle.write(content)
        return Path(handle.name)
    finally:
        handle.close()


def _validate_payload(content: bytes, *, url: str, expected_kind: str, content_type: str, source: str) -> None:
    if not content:
        return
    head = content[:120_000]
    text_head = head.decode("utf-8", errors="ignore").lower()
    if any(marker in text_head for marker in CHALLENGE_MARKERS):
        raise AcquisitionError(
            "client_acquisition_challenge_page",
            "The publisher returned an anti-bot or JavaScript challenge page instead of article content; use the browser extension with your logged-in browser session or upload the PDF/EPUB/XML file directly.",
            diagnostics={"url": url, "source": source, "content_type": content_type},
        )
    publisher_error = _publisher_error_shell(text_head, url=url)
    if publisher_error:
        raise AcquisitionError(
            "publisher_blocked_remote_pdf" if expected_kind == "pdf" else "publisher_blocked_remote_content",
            "The publisher returned an HTML error shell instead of article content; open the article in an entitled browser session and use extension capture, upload an authorized file, or import an authorized Zotero attachment.",
            diagnostics={"url": url, "source": source, "content_type": content_type, "publisher_error": publisher_error},
        )
    normalized_type = content_type.lower()
    if expected_kind == "pdf" and not head.startswith(b"%PDF"):
        raise AcquisitionError(
            "client_acquisition_unexpected_content_type",
            "The routed PDF URL did not return a PDF payload; use the browser extension or upload the PDF directly.",
            diagnostics={"url": url, "source": source, "content_type": content_type},
        )
    if expected_kind in {"xml", "epub"} and "html" in normalized_type:
        raise AcquisitionError(
            "client_acquisition_unexpected_content_type",
            f"The routed {expected_kind.upper()} URL returned HTML instead of {expected_kind.upper()} content; use the browser extension or upload the file directly.",
            diagnostics={"url": url, "source": source, "content_type": content_type},
        )


def _publisher_error_shell(text_head: str, *, url: str) -> str:
    normalized_url = str(url or "").lower()
    if "ieee.org" not in normalized_url and "xplorestaging.ieee.org" not in normalized_url:
        return ""
    if any(marker in text_head for marker in PUBLISHER_ERROR_SHELL_MARKERS):
        return "ieee_error_shell"
    return ""


def _summarize_acquisition_failures(errors: list[dict[str, Any]]) -> tuple[str, str, dict[str, Any]]:
    attempts = errors[-20:]
    reason_codes = [str(error.get("reason_code") or "").strip() for error in attempts if str(error.get("reason_code") or "").strip()]
    nested_reason_codes = [
        str(attempt.get("reason_code") or "").strip()
        for error in attempts
        for attempt in ((error.get("diagnostics") or {}).get("attempts") or [])
        if isinstance(attempt, dict) and str(attempt.get("reason_code") or "").strip()
    ]
    all_reason_codes = reason_codes + nested_reason_codes
    diagnostics = {"attempts": attempts}
    if any(bool(error.get("requires_browser")) for error in attempts):
        diagnostics["browser_handoff_candidates"] = [
            {
                "url": error.get("url"),
                "candidate_source": error.get("candidate_source"),
                "candidate_connector": error.get("candidate_connector"),
                "reason_code": error.get("reason_code"),
            }
            for error in attempts
            if error.get("requires_browser")
        ]
    if "publisher_blocked_remote_pdf" in all_reason_codes:
        return (
            "publisher_blocked_remote_pdf",
            "The publisher returned an HTML error shell instead of the routed PDF. Open the article in an entitled browser session and use extension capture, upload an authorized PDF/HTML/XML/EPUB, or import an authorized Zotero attachment.",
            diagnostics,
        )
    if "missing_api_key" in all_reason_codes:
        credential_names = sorted(
            {
                str(error.get("credential_name") or "").strip()
                for error in attempts
                if str(error.get("credential_name") or "").strip()
            }
        )
        credential_text = ", ".join(credential_names) or "the provider API key"
        if "ELSEVIER_API_KEY" in credential_names:
            return (
                "elsevier_api_key_missing",
                "This Elsevier route needs ELSEVIER_API_KEY for the official XML API. "
                "Let the Mdtero server try its configured route, or use the browser extension/upload on your campus computer.",
                diagnostics,
            )
        return (
            "provider_api_key_missing",
            f"This route needs {credential_text}. Configure it locally or let the Mdtero server try the route.",
            diagnostics,
        )
    if any(bool(error.get("requires_browser")) for error in attempts):
        return (
            "client_acquisition_browser_session_required",
            "The route includes a browser-session handoff candidate, but CLI local acquisition did not receive a usable artifact. Use the Mdtero extension from an entitled browser session or upload an authorized PDF/EPUB/XML/HTML file.",
            diagnostics,
        )
    if all_reason_codes and all(code == "client_acquisition_challenge_page" for code in all_reason_codes):
        return (
            "client_acquisition_challenge_page",
            "The publisher returned anti-bot or JavaScript challenge pages for every routed source; use the browser extension with your logged-in browser session or upload an authorized file directly.",
            diagnostics,
        )
    return (
        "client_acquisition_fetch_failed",
        "Mdtero could not fetch the routed source locally; retry from a browser session or upload the PDF/EPUB/XML/HTML file directly.",
        diagnostics,
    )


def _fetch_headers(*, url: str, artifact_kind: str, referer: str | None = None, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "Accept": _accept_header(artifact_kind),
        "Accept-Language": "en-US,en;q=0.9",
        "Upgrade-Insecure-Requests": "1",
    }
    if referer:
        headers["Referer"] = referer
    elif _infer_mdpi_epub_url(url):
        headers["Referer"] = url.rsplit("/", 1)[0] if url.rstrip("/").endswith("/epub") else url
    if extra_headers:
        headers.update({key: value for key, value in extra_headers.items() if value})
    return headers


def _accept_header(artifact_kind: str) -> str:
    if artifact_kind == "pdf":
        return "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8"
    if artifact_kind == "epub":
        return "application/epub+zip,application/octet-stream;q=0.9,text/html;q=0.7,*/*;q=0.6"
    if artifact_kind == "xml":
        return "application/xml,text/xml,application/xhtml+xml;q=0.9,text/html;q=0.7,*/*;q=0.6"
    return "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"


def _kind_from_content_type(default: str, content_type: str) -> str:
    lowered = content_type.lower()
    if "pdf" in lowered:
        return "pdf"
    if "epub" in lowered:
        return "epub"
    if "xml" in lowered:
        return "xml"
    if "html" in lowered:
        return "html"
    return default


def _suffix_for_kind(kind: str, url: str) -> str:
    lowered = kind.lower()
    if lowered == "pdf":
        return ".pdf"
    if lowered == "epub":
        return ".epub"
    if lowered == "xml":
        return ".xml"
    if lowered == "html":
        return ".html"
    guessed = mimetypes.guess_extension(mimetypes.guess_type(url)[0] or "")
    return guessed or ".bin"


def _artifact_kind_from_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".epub":
        return "epub"
    if suffix == ".xml":
        return "xml"
    if suffix in {".html", ".htm"}:
        return "html"
    return "raw"
