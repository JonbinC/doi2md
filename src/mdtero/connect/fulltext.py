"""Connect full-text pipeline: user's browser -> local article -> local parser.

* The article is opened in the user's own Chrome tab (CDP / Playwright page).
* Challenges are detected from the live DOM (title, Cloudflare iframe,
  challenge forms, short body text) and handed to the user to click. Nothing
  here solves, bypasses or disguises anything.
* Rendered HTML and verified publisher PDFs are stored on the local disk only.
* Conversion is an in-process call to ``mdtero_parser.parse_client_document``;
  no HTTP, and the content is never sent to any server.
* Full text vs paywall is decided from the parser's signals plus the DOM probe
  and reported to the user as-is.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urljoin

from . import publisher_adapter as pa

# ------------------------------------------------------------ DOM challenge probe
# Evaluated inside the page. Reads only; never clicks or types.
CHALLENGE_PROBE_JS = r"""() => {
  const title = (document.title || "").trim();
  const sel = (q) => { try { return !!document.querySelector(q); } catch (e) { return false; } };
  const body = document.body ? (document.body.innerText || "") : "";
  return {
    title: title,
    url: location.href,
    content_type: document.contentType || "",
    cf_iframe: sel('iframe[src*="challenges.cloudflare.com"]'),
    challenge_form: sel('form#challenge-form, #challenge-running, #challenge-stage, .cf-turnstile, #cf-challenge-running, [data-sitekey].g-recaptcha, .h-captcha, #px-captcha'),
    body_chars: body.replace(/\s+/g, " ").trim().length,
  };
}"""

CHALLENGE_TITLES = (
    "just a moment", "attention required", "checking your browser", "verify you are human",
    "are you a robot", "security check", "access denied", "请稍候",
)
SHORT_BODY_CHARS = 400


def probe_page(page) -> dict:
    try:
        out = page.evaluate(CHALLENGE_PROBE_JS)
        return out if isinstance(out, dict) else {}
    except Exception:  # noqa: BLE001 - navigating
        return {}


def classify_probe(probe: dict) -> Optional[str]:
    """'challenge' or None, from a DOM probe dict (no raw-HTML substring matching)."""
    if not probe:
        return None
    if probe.get("content_type") == "application/pdf":
        return None
    title = str(probe.get("title") or "").lower()
    if probe.get("cf_iframe") or probe.get("challenge_form"):
        return "challenge"
    if any(t in title for t in CHALLENGE_TITLES) and int(probe.get("body_chars") or 0) < 2000:
        return "challenge"
    return None


# ------------------------------------------------------------ verdict
MIN_BODY_CHARS = 3000
MIN_SECTIONS = 2


def verdict(signals: dict, probe: Optional[dict] = None) -> str:
    """'fulltext' | 'paywall' | 'challenge' from parser signals + DOM probe."""
    if classify_probe(probe or {}) == "challenge":
        return "challenge"
    body = int(signals.get("body_length") or 0)
    sections = int(signals.get("section_count") or 0)
    if body >= MIN_BODY_CHARS and sections >= MIN_SECTIONS:
        return "fulltext"
    return "paywall"


# ------------------------------------------------------------ Springer tables
def springer_table_urls(html: str, doi: str, base_url: str = "https://link.springer.com/") -> dict[int, str]:
    """{N: absolute URL} for /article/<doi>/tables/N links on a Springer page."""
    d = re.escape(pa.normalize_doi(doi))
    out: dict[int, str] = {}
    for m in re.finditer(r'href="([^"]*/article/(%s)/tables/(\d+))[^"]*"' % d, html, flags=re.I):
        out.setdefault(int(m.group(3)), urljoin(base_url, m.group(1)))
    return dict(sorted(out.items()))


# ------------------------------------------------------------ local parser
class ParserUnavailable(RuntimeError):
    pass


def local_parse(payload: bytes, **kw: Any) -> dict:
    """In-process call to mdtero_parser (``pip install 'mdtero[parse]'``)."""
    try:
        from mdtero_parser import parse_client_document  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - depends on extra
        raise ParserUnavailable("mdtero-parser not installed: pip install 'mdtero[parse]'") from exc
    return parse_client_document(payload, **kw)


# ------------------------------------------------------------ pipeline
@dataclass
class FullTextResult:
    doi: str
    publisher: str
    status: str  # fulltext | paywall | challenge | error
    raw_path: Optional[str] = None
    markdown_path: Optional[str] = None
    url: str = ""
    signals: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    companion_pages: list = field(default_factory=list)
    detail: str = ""
    handoffs: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def _rendered(page) -> str:
    try:
        return page.evaluate("document.documentElement.outerHTML") or pa.safe_content(page)
    except Exception:  # noqa: BLE001
        return pa.safe_content(page)


def _wait_user(page, *, timeout_s: float, poll_s: float, notify, sleep, clock) -> bool:
    """Hand the window to the user; poll the DOM probe until the challenge is gone."""
    pa.bring_to_front(page)
    if notify:
        notify("challenge", getattr(page, "url", ""))
    deadline = clock() + timeout_s
    while clock() < deadline:
        sleep(poll_s)
        if classify_probe(probe_page(page)) is None:
            return True
    return False


def _open(page, url, res, *, timeout_ms, handoff_timeout_s, notify, sleep, clock) -> Optional[dict]:
    """Navigate, wait, hand challenges to the user. Returns final probe or None if still blocked."""
    response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    try:
        status = int(response.status) if response is not None else 0
    except Exception:  # noqa: BLE001
        status = 0
    page.wait_for_timeout(3000)
    probe = probe_page(page)
    if classify_probe(probe) == "challenge":
        if handoff_timeout_s <= 0:
            return None
        res.handoffs += 1
        if not _wait_user(page, timeout_s=handoff_timeout_s, poll_s=2.0, notify=notify, sleep=sleep, clock=clock):
            return None
        page.wait_for_timeout(2000)
        probe = probe_page(page)
        if classify_probe(probe) == "challenge":
            return None
        status = 200  # the person cleared the challenge in the visible browser
    if probe:
        probe["_http_status"] = status
    return probe


def _try_ieee_pdf_fallback(page, doi: str, html: str, http_status: int, out_dir: Path, limiter: pa.RateLimiter,
                           res: FullTextResult, *, parse: Callable[..., dict],
                           goto_timeout_ms: int, handoff_timeout_s: float,
                           notify: Optional[Callable[[str, str], None]]) -> None:
    """Use Connect's visible-browser IEEE PDF route, then parse it locally.

    The caller already acquired the per-article rate-limit slot. The result is
    updated in place; a missing/blocked PDF leaves the HTML/paywall result.
    """
    try:
        fetched = pa.fetch_article(
            page, doi, Path(out_dir), limiter,
            goto_timeout_ms=goto_timeout_ms,
            handoff_timeout_s=handoff_timeout_s,
            use_translators=False,
            notify=notify,
            prefer_html=False,
            rate_limit=False,
            preloaded_page=(html, res.url, http_status),
        )
    except Exception as exc:  # noqa: BLE001 - fallback must not hide the HTML result
        res.detail = (res.detail + f"; IEEE PDF fallback: {type(exc).__name__}: {exc}")[:600]
        return

    res.handoffs += fetched.handoffs
    if fetched.status == "challenge":
        res.status = "challenge"
        res.detail = "IEEE PDF verification was not completed in the visible browser; nothing was bypassed"
        return
    if fetched.status != "pdf" or not fetched.path:
        if fetched.detail:
            res.detail = (res.detail + f"; IEEE PDF fallback: {fetched.status} ({fetched.detail})")[:600]
        return

    pdf_path = Path(fetched.path)
    try:
        pdf_bytes = pdf_path.read_bytes()
    except OSError as exc:
        res.detail = (res.detail + f"; IEEE PDF read: {type(exc).__name__}: {exc}")[:600]
        return
    res.raw_path = str(pdf_path)
    res.url = fetched.detail.rsplit(" [", 1)[0] if " [" in fetched.detail else fetched.detail
    try:
        parsed = parse(pdf_bytes, doi=doi, publisher_hint="ieee", filename=pdf_path.name,
                       content_type="application/pdf")
    except Exception as exc:  # noqa: BLE001 - report local parser failures
        res.status = "error"
        res.detail = f"IEEE PDF local parse: {type(exc).__name__}: {exc}"[:300]
        return

    res.signals = dict(parsed.get("signals") or {})
    res.metadata = dict(parsed.get("metadata") or res.metadata or {})
    res.status = verdict(res.signals)
    if res.status == "fulltext":
        stem = re.sub(r"[^\w.-]+", "_", doi)[:150]
        md = Path(out_dir) / f"{stem}.md"
        md.write_text(parsed.get("markdown") or "", encoding="utf-8")
        res.markdown_path = str(md)
        res.detail = "IEEE publisher PDF fetched in the visible browser and parsed locally"
    else:
        res.detail = "IEEE publisher PDF was fetched locally, but the parser did not confirm full text"


def fetch_fulltext(page, doi: str, out_dir: Path, limiter: pa.RateLimiter, *,
                   parse: Callable[..., dict] = local_parse,
                   companion_interval_s: float = 15.0,
                   goto_timeout_ms: int = 45_000, handoff_timeout_s: float = 300.0,
                   notify: Optional[Callable[[str, str], None]] = None,
                   sleep: Callable[[float], None] = time.sleep,
                   clock: Callable[[], float] = time.monotonic) -> FullTextResult:
    doi = pa.normalize_doi(doi)
    pub = pa.route(doi)
    if pub is None:
        return FullTextResult(doi, "-", "error", detail="not a Connect publisher")
    res = FullTextResult(doi, pub.key, "error")
    limiter.acquire()
    raw_dir = Path(out_dir) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w.-]+", "_", doi)[:150]
    kw = dict(timeout_ms=goto_timeout_ms, handoff_timeout_s=handoff_timeout_s, notify=notify, sleep=sleep, clock=clock)
    try:
        probe = _open(page, pa.landing_url(doi), res, **kw)
    except Exception as exc:  # noqa: BLE001
        res.detail = f"goto: {exc}"[:300]
        return res
    if probe is None:
        res.status, res.detail = "challenge", "verification not completed in the browser window; nothing was bypassed"
        return res
    res.url = str(probe.get("url") or getattr(page, "url", ""))
    html = _rendered(page)
    raw = raw_dir / f"{stem}.html"
    raw.write_text(html, encoding="utf-8")
    res.raw_path = str(raw)

    companions: dict[str, bytes] = {}
    if pub.key == "springer":
        for n, url in springer_table_urls(html, doi, res.url or "https://link.springer.com/").items():
            sleep(companion_interval_s)  # sequential and polite
            try:
                tprobe = _open(page, url, res, **kw)
            except Exception as exc:  # noqa: BLE001
                res.detail += f" table {n}: {type(exc).__name__};"
                continue
            if tprobe is None:
                res.detail += f" table {n}: challenge not cleared;"
                continue
            body = _rendered(page).encode("utf-8")
            (raw_dir / f"{stem}.table{n}.html").write_bytes(body)
            companions[url] = body
            res.companion_pages.append(url)

    parse_error: Optional[BaseException] = None
    try:
        parsed = parse(html.encode("utf-8"), doi=doi, publisher_hint=pub.key, filename=raw.name,
                       content_type="text/html", companion_pages=companions or None)
    except Exception as exc:  # noqa: BLE001 - parser failure is reported, not raised
        parse_error = exc
        res.detail = f"parse: {type(exc).__name__}: {exc}"[:300]
        if is_access_shell_error(exc):
            res.status = "paywall"
            res.detail += "; page has no full text (paywall/abstract only); reported, not bypassed"
    else:
        res.signals = dict(parsed.get("signals") or {})
        res.metadata = dict(parsed.get("metadata") or {})
        res.status = verdict(res.signals, probe)
        if res.status == "fulltext":
            md = Path(out_dir) / f"{stem}.md"
            md.write_text(parsed.get("markdown") or "", encoding="utf-8")
            res.markdown_path = str(md)
        else:
            res.detail = (res.detail + " page has no full text (paywall/abstract only); reported, not bypassed").strip()

    # IEEE OA PDFs can be available even when the landing page exposes only an
    # abstract. Keep that acquisition on the user's visible browser and parse
    # the downloaded bytes in-process, never through the backend worker.
    if pub.key == "ieee" and res.status == "paywall" and (parse_error is None or is_access_shell_error(parse_error)):
        _try_ieee_pdf_fallback(
            page, doi, html, int(probe.get("_http_status") or 200), out_dir, limiter, res, parse=parse,
            goto_timeout_ms=goto_timeout_ms, handoff_timeout_s=handoff_timeout_s, notify=notify,
        )
    _write_result(out_dir, stem, res)
    return res


def is_access_shell_error(exc: BaseException) -> bool:
    """mdtero_parser raises ClientParseError('... access shell ...') for paywall/login pages."""
    return "access shell" in str(exc).lower() or "abstract only" in str(exc).lower()


def _write_result(out_dir, stem: str, res: FullTextResult) -> None:
    (Path(out_dir) / f"{stem}.fulltext.json").write_text(
        json.dumps(res.to_dict(), indent=1, ensure_ascii=False), encoding="utf-8")

