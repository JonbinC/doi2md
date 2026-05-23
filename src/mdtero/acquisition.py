from __future__ import annotations

import mimetypes
import re
import tempfile
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
URL_PATTERN = re.compile(r"^https?://", re.I)
CHALLENGE_MARKERS = (
    "akamai/interstitial",
    "bm-verify=",
    "cf-browser-verification",
    "checking if the site connection is secure",
    "enable javascript and cookies to continue",
    "interstitialchallenge",
    "just a moment",
    "verify you are human",
    "window._cf_chl_opt",
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


def should_acquire_locally(route: dict[str, Any], input_value: str) -> bool:
    if _is_direct_local_artifact_url(input_value):
        return True
    if route.get("legacy_fallback") or route.get("route_planner_fallback"):
        return False
    if route.get("requires_raw_upload"):
        return True
    actions = {str(action) for action in route.get("action_sequence") or []}
    local_actions = {"fetch_remote_html", "fetch_epub_asset", "fetch_structured_xml", "fallback_pdf_parse"}
    if actions.intersection(local_actions) and _candidate_urls(route, input_value):
        return True
    return False


def _is_direct_local_artifact_url(input_value: str) -> bool:
    value = str(input_value or "").strip()
    if not URL_PATTERN.match(value) or DOI_PATTERN.match(value):
        return False
    return bool(_direct_artifact_kind_from_url(value) or _infer_mdpi_epub_url(value))


def acquire_from_route(route: dict[str, Any], input_value: str, *, timeout: float = 45.0) -> AcquiredArtifact:
    candidates = _candidate_urls(route, input_value)
    if not candidates:
        raise AcquisitionError(
            "client_acquisition_no_candidate_url",
            "Route requires local acquisition but did not include a fetchable URL; use the browser extension or upload a local PDF/EPUB/XML/HTML file.",
            diagnostics={"route_kind": route.get("route_kind"), "action_sequence": route.get("action_sequence")},
        )

    errors: list[dict[str, Any]] = []
    for candidate in candidates:
        url = str(candidate.get("url") or "").strip()
        if not url:
            continue
        artifact_kind = _artifact_kind(candidate, route, url)
        try:
            return _fetch_with_curl_cffi(url, artifact_kind=artifact_kind, timeout=timeout)
        except AcquisitionError as exc:
            errors.append({"url": url, "source": "curl_cffi", **exc.to_dict()})
        try:
            return _fetch_with_httpx(url, artifact_kind=artifact_kind, timeout=timeout)
        except AcquisitionError as exc:
            errors.append({"url": url, "source": "httpx", **exc.to_dict()})

    raise AcquisitionError(
        "client_acquisition_fetch_failed",
        "Mdtero could not fetch the routed source locally; retry from a browser session or upload the PDF/EPUB/XML/HTML file directly.",
        diagnostics={"attempts": errors[-6:]},
    )


def curl_cffi_available() -> bool:
    try:
        import curl_cffi.requests  # noqa: F401
    except Exception:
        return False
    return True


def _candidate_urls(route: dict[str, Any], input_value: str) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(url: object, *, kind: str | None = None, connector: str | None = None, prefer_mdpi_epub: bool = True) -> None:
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
        candidates.append(item)

    for candidate in route.get("acquisition_candidates") or []:
        if not isinstance(candidate, dict):
            continue
        connector = str(candidate.get("connector") or "") or None
        add(candidate.get("url"), connector=connector)
        add(candidate.get("html_url"), kind="html", connector=connector)
        add(candidate.get("xml_url") or candidate.get("jats_url") or candidate.get("jatsxml"), kind="xml", connector=connector)
        add(candidate.get("epub_url"), kind="epub", connector=connector)
        add(candidate.get("pdf_url"), kind="pdf", connector=connector)

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
    if "fetch_structured_xml" in actions or "jats" in route_kind or ".xml" in lowered or "fulltextxml" in lowered:
        return "xml"
    return "html"


def _direct_artifact_kind_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(str(url or "").strip())
    lowered_path = parsed.path.lower().rstrip("/")
    lowered_url = urllib.parse.urlunparse(parsed._replace(fragment="")).lower()
    if not lowered_path:
        return ""
    if lowered_path.endswith((".epub", "/epub")) or "/doi/epub/" in lowered_url:
        return "epub"
    if lowered_path.endswith((".pdf", "/pdf")) or "/doi/pdf/" in lowered_url or "/doi/epdf/" in lowered_url:
        return "pdf"
    if lowered_path.endswith((".xml", "/xml", "/fulltextxml")) or "fulltextxml" in lowered_url:
        return "xml"
    if lowered_path.endswith((".html", ".htm", "/html", "/full")) or "/doi/full/" in lowered_url:
        return "html"
    return ""


def _fetch_with_curl_cffi(url: str, *, artifact_kind: str, timeout: float) -> AcquiredArtifact:
    try:
        from curl_cffi import requests as curl_requests
    except Exception as exc:
        raise AcquisitionError(
            "client_curl_cffi_unavailable",
            "curl_cffi is not available in this Python environment; falling back to httpx.",
            diagnostics={"error": exc.__class__.__name__},
        ) from exc
    errors: list[dict[str, Any]] = []
    for profile in CURL_CFFI_IMPERSONATION_PROFILES:
        try:
            with curl_requests.Session(impersonate=profile) as session:
                response = session.get(
                    url,
                    timeout=timeout,
                    allow_redirects=True,
                    headers=_fetch_headers(url=url, artifact_kind=artifact_kind),
                )
                response = _follow_meta_refresh_once(
                    session,
                    response,
                    base_url=url,
                    timeout=timeout,
                    artifact_kind=artifact_kind,
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


def _fetch_with_httpx(url: str, *, artifact_kind: str, timeout: float) -> AcquiredArtifact:
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=_fetch_headers(url=url, artifact_kind=artifact_kind)) as client:
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


def _follow_meta_refresh_once(session: Any, response: Any, *, base_url: str, timeout: float, artifact_kind: str) -> Any:
    content_type = str(response.headers.get("content-type") or "").lower()
    if "html" not in content_type:
        return response
    marker = META_REFRESH_RE.search(bytes(response.content or b"")[:20_000])
    if not marker:
        return response
    target = urllib.parse.urljoin(base_url, marker.group(1).decode("utf-8", errors="ignore").strip("'\""))
    if not target or urllib.parse.urlparse(target).netloc != urllib.parse.urlparse(base_url).netloc:
        return response
    return session.get(
        target,
        timeout=timeout,
        allow_redirects=True,
        headers=_fetch_headers(url=target, artifact_kind=artifact_kind, referer=base_url),
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


def _fetch_headers(*, url: str, artifact_kind: str, referer: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": _accept_header(artifact_kind),
        "Accept-Language": "en-US,en;q=0.9",
        "Upgrade-Insecure-Requests": "1",
    }
    if referer:
        headers["Referer"] = referer
    elif _infer_mdpi_epub_url(url):
        headers["Referer"] = url.rsplit("/", 1)[0] if url.rstrip("/").endswith("/epub") else url
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
