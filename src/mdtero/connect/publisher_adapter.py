"""Publisher fetch adapter for mdtero Connect.

Routes subscription publishers that block server-side HTTP through the
user's own (headed) browser session. Design rules:

* DOI -> URL templates where publishers allow it; otherwise resolve from the
  article landing page (``citation_pdf_url`` / publisher-specific patterns).
* HTML full text preferred over PDF; PDF is the fallback.
* Challenge / login pages are *detected only*: the window is handed to the
  user. Nothing here solves, bypasses or disguises automation.
* Rate limited (min interval + daily cap). Output stays on the local disk.
"""
from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote, urljoin, urlparse

from ..publisher_policy import ieee_arnumber_from_url, ieee_stamp_pdf_url
from ..relay_domains import relay_url_rejection_reason

# Publishers reachable over plain HTTP are served by the backend, never here.
HTTP_DIRECT_PREFIXES = {
    "10.3390": "mdpi", "10.3389": "frontiers", "10.1186": "springer_oa",
    "10.1371": "plos", "10.5194": "copernicus", "10.1088": "iop",
    "10.1017": "cup", "10.1103": "aps",
}


@dataclass(frozen=True)
class Publisher:
    key: str
    name: str
    doi_prefixes: tuple[str, ...]
    hosts: tuple[str, ...]
    landing_template: str
    pdf_templates: tuple[str, ...] = ()
    pdf_hosts: tuple[str, ...] = ()  # optional publisher-owned PDF/CDN hosts
    needs_landing_page: bool = False  # PDF URL needs ids from the article page
    body_selectors: tuple[str, ...] = ()  # (tag.class | tag#id | tag) main body
    notes: str = ""


REGISTRY: dict[str, Publisher] = {p.key: p for p in [
    Publisher("acs", "ACS", ("10.1021",), ("pubs.acs.org",),
              "https://pubs.acs.org/doi/{doi}",
              ("https://pubs.acs.org/doi/pdf/{doi}",),
              body_selectors=("div.article_content-left", "div.NLM_sec_level_1")),
    Publisher("wiley", "Wiley", ("10.1002", "10.1111"), ("onlinelibrary.wiley.com",),
              "https://onlinelibrary.wiley.com/doi/full/{doi}",
              ("https://onlinelibrary.wiley.com/doi/pdfdirect/{doi}",
               "https://onlinelibrary.wiley.com/doi/pdf/{doi}"),
              pdf_hosts=("onlinelibrary.wiley.com", "api.wiley.com"),
              body_selectors=("section.article-section__full", "div.article__body")),
    Publisher("tandf", "Taylor & Francis", ("10.1080",), ("www.tandfonline.com",),
              "https://www.tandfonline.com/doi/full/{doi}",
              ("https://www.tandfonline.com/doi/pdf/{doi}",),
              body_selectors=("div.hlFld-Fulltext",)),
    Publisher("aip", "AIP", ("10.1063",), ("pubs.aip.org",),
              "https://pubs.aip.org/doi/{doi}",
              ("https://pubs.aip.org/doi/pdf/{doi}",),
              pdf_hosts=("pubs.aip.org",),
              body_selectors=("div.article-body", "div#ContentTab"),
              notes="pdf may redirect to /article-pdf/... ; citation_pdf_url preferred"),
    Publisher("ieee", "IEEE", ("10.1109",), ("ieeexplore.ieee.org",),
              "https://doi.org/{doi}",
              pdf_hosts=("ieeexplore.ieee.org", "ieee.org"),
              needs_landing_page=True,
              body_selectors=("div#article", "div.document-text"),
              notes="arnumber taken from the DOI redirect /document/{n}"),
    Publisher("rsc", "RSC", ("10.1039",), ("pubs.rsc.org",),
              "https://doi.org/{doi}",
              ("https://pubs.rsc.org/en/content/articlepdf/{year}/{journal}/{article_id}",),
              needs_landing_page=True,
              body_selectors=("div#wrapper", "article"),
              notes="year/journal/id from /articlelanding/ redirect"),
    Publisher("elsevier", "Elsevier", ("10.1016",), ("www.sciencedirect.com",),
              "https://doi.org/{doi}",
              ("https://www.sciencedirect.com/science/article/pii/{pii}/pdfft?isDTMRedir=true&download=true",),
              pdf_hosts=("www.sciencedirect.com", "api.elsevier.com"),
              needs_landing_page=True,
              body_selectors=("div#body", "div.Body"),
              notes="PII from linkinghub redirect"),
    Publisher("springer", "Springer Nature", ("10.1007",), ("link.springer.com",),
              "https://link.springer.com/article/{doi}",
              ("https://link.springer.com/content/pdf/{doi}.pdf",),
              pdf_hosts=("link.springer.com",),
              body_selectors=("div.c-article-body", "main"),
              notes="tables may live on /article/{doi}/tables/N companion pages"),
    Publisher("oup", "Oxford University Press", ("10.1093",), ("academic.oup.com",),
              "https://doi.org/{doi}", (), needs_landing_page=True,
              body_selectors=("div.article-body", "div.widget-ArticleFulltext"),
              notes="PDF only via citation_pdf_url"),
]}


def normalize_doi(value: str) -> str:
    """Normalise DOI input (URL, ``doi:`` prefix, %-encoding, trailing punctuation)."""
    from urllib.parse import unquote
    v = unquote((value or "").strip())
    v = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", v, flags=re.I).strip()
    v = re.split(r"[?#\s]", v, maxsplit=1)[0]
    v = v.rstrip(".,;)]>\"'")
    return v.lower() if v.lower().startswith("10.") else v


def route(doi: str) -> Optional[Publisher]:
    """Return the Connect publisher, or None if not Connect's job."""
    prefix = normalize_doi(doi).split("/", 1)[0]
    if prefix in HTTP_DIRECT_PREFIXES:
        return None
    for pub in REGISTRY.values():
        if prefix in pub.doi_prefixes:
            return pub
    return None


def landing_url(doi: str) -> str:
    pub = route(doi)
    if pub is None:
        raise ValueError(f"{doi} is not routed through Connect")
    return pub.landing_template.format(doi=quote(normalize_doi(doi), safe="/()-._;:"))


def ids_from_url(url: str) -> dict[str, str]:
    """Extract publisher-internal ids from a resolved landing URL."""
    out: dict[str, str] = {}
    arnumber = ieee_arnumber_from_url(url)
    if arnumber:
        out["arnumber"] = arnumber
    m = re.search(r"/content/article(?:landing|html|pdf)/(\d{4})/([a-z]+)/([a-z0-9]+)", url, re.I)
    if m:
        out.update(year=m.group(1), journal=m.group(2).lower(), article_id=m.group(3).lower())
    m = re.search(r"/pii/(S?[0-9X]{15,17}[0-9X]?)", url, re.I)
    if m:
        out["pii"] = m.group(1).upper()
    return out


def rsc_ids_from_doi(doi: str, html: str = "") -> list[dict[str, str]]:
    """RSC article ids from the DOI suffix (e.g. 10.1039/d5qo01181g).

    RSC moved landing pages to /{journal}/article/{vol}/{issue}/{pages}/{n},
    which no longer contain the year/journal/id needed for /articlepdf/.
    Suffix format: {letter}{year digit}{journal}{5 digits}{check}; the PDF
    path year is the publication year, taken from citation_publication_date /
    citation_date when available, else guessed from the suffix decade.
    """
    m = re.fullmatch(r"10\.1039/(([a-z])(\d)([a-z]{2})\d{5}[a-z])", normalize_doi(doi))
    if not m:
        return []
    article_id, letter, digit, journal = m.group(1), m.group(2), int(m.group(3)), m.group(4)
    years: list[str] = []
    if html:
        meta = parse_meta(html)
        for name in ("citation_publication_date", "citation_date", "citation_online_date"):
            for v in meta.get(name, []):
                y = re.search(r"(19|20)\d{2}", v)
                if y and y.group(0) not in years:
                    years.append(y.group(0))
    # 'b'/'c' -> 2000s/2010s, 'd' -> 2020s (RSC letter roughly tracks decade)
    decade = {"b": 2000, "c": 2010, "d": 2020}.get(letter)
    if decade is not None:
        base = decade + digit
        for y in (base, base + 1):
            if str(y) not in years:
                years.append(str(y))
    return [{"year": y, "journal": journal, "article_id": article_id} for y in years]


def pdf_candidates(doi: str, resolved_url: str = "", html: str = "",
                   translator_pdfs: Optional[list[str]] = None) -> list[str]:
    """Ordered PDF URL candidates: citation_pdf_url, then templates."""
    pub = route(doi)
    if pub is None:
        return []
    cands: list[str] = list(translator_pdfs or [])
    if html:
        meta = parse_meta(html).get("citation_pdf_url")
        if meta:
            cands.append(urljoin(resolved_url or landing_url(doi), meta[0]))
    ids = {"doi": normalize_doi(doi), **ids_from_url(resolved_url)}
    id_sets = [ids]
    if pub.key == "rsc" and "article_id" not in ids:
        id_sets += [{**ids, **extra} for extra in rsc_ids_from_doi(doi, html)]
    if pub.key == "ieee":
        candidate = ieee_stamp_pdf_url(resolved_url)
        if candidate:
            cands.append(candidate)
    else:
        for tpl in pub.pdf_templates:
            for idset in id_sets:
                try:
                    cands.append(tpl.format(**idset))
                except KeyError:
                    continue  # ids not yet known (needs landing page)
    seen: set[str] = set()
    return [c for c in cands if c.startswith("https://") and not (c in seen or seen.add(c))]


_PDF_LINK_PATTERNS = (
    r'<a[^>]+class="[^"]*article-pdfLink[^"]*"[^>]+href="([^"]+)"',
    r'<a[^>]+href="([^"]+)"[^>]+class="[^"]*article-pdfLink',
    r'<i?frame[^>]+src="([^"]+(?:\.pdf|getPDF\.jsp)[^"]*)"',
    r'<meta[^>]+http-equiv="refresh"[^>]+url=([^"\s>]+\.pdf[^"\s>]*)',
    r'<a[^>]+id="pdf-link"[^>]+data-article-url="([^"]+)"',
)


def pdf_links_in_html(html: str, base_url: str) -> list[str]:
    """PDF URLs from an HTML response that should have been a PDF.

    AIP/Silverchair (``/doi/pdf/{doi}`` -> ``/article-pdf/...``), IEEE
    (``stamp.jsp`` frame) and some Atypon sites answer a PDF URL with an HTML
    viewer/interstitial that links to the real file.
    """
    out = [urljoin(base_url, u) for u in parse_meta(html).get("citation_pdf_url", [])]
    for pat in _PDF_LINK_PATTERNS:
        out += [urljoin(base_url, m.replace("&amp;", "&")) for m in re.findall(pat, html, flags=re.I)]
    seen: set[str] = set()
    return [u for u in out if not (u in seen or seen.add(u))]


# --------------------------------------------------------------- HTML parsing
class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, list[str]] = {}

    def handle_starttag(self, tag, attrs):
        if tag != "meta":
            return
        a = dict(attrs)
        name = (a.get("name") or a.get("property") or "").lower()
        if name and a.get("content") is not None:
            self.meta.setdefault(name, []).append(a["content"].strip())


def parse_meta(html: str) -> dict[str, list[str]]:
    p = _MetaParser()
    p.feed(html)
    return p.meta


_VOID = {"br", "img", "hr", "meta", "link", "input", "source", "wbr", "col", "area", "base", "embed", "param", "track"}
_SKIP = {"script", "style", "noscript", "nav", "header", "footer", "button", "form", "svg"}
_BLOCK = {"p": "\n\n", "h1": "\n\n# ", "h2": "\n\n## ", "h3": "\n\n### ", "h4": "\n\n#### ",
          "li": "\n- ", "tr": "\n", "div": "\n", "section": "\n", "figcaption": "\n\n"}


def _match(sel: str, tag: str, attrs: dict) -> bool:
    m = re.fullmatch(r"([a-z0-9]*)(?:([.#])([\w-]+))?", sel)
    if not m:
        return False
    t, kind, val = m.groups()
    if t and t != tag:
        return False
    if kind == ".":
        return val in (attrs.get("class") or "").split()
    if kind == "#":
        return attrs.get("id") == val
    return True


class _BodyExtractor(HTMLParser):
    def __init__(self, selectors: tuple[str, ...]) -> None:
        super().__init__(convert_charrefs=True)
        self.selectors, self.depth, self.skip = selectors, 0, 0
        self.parts: list[str] = []
        self.done = False

    def handle_starttag(self, tag, attrs):
        if self.done or tag in _VOID:
            return
        a = dict(attrs)
        if self.depth == 0:
            if any(_match(s, tag, a) for s in self.selectors):
                self.depth = 1
            return
        self.depth += 1
        if self.skip or tag in _SKIP:
            self.skip += 1
            return
        self.parts.append(_BLOCK.get(tag, ""))

    def handle_endtag(self, tag):
        if self.depth == 0 or tag in _VOID:
            return
        if self.skip:
            self.skip -= 1
        self.depth -= 1
        if self.depth == 0:
            self.done = True

    def handle_data(self, data):
        if self.depth and not self.skip and not self.done:
            self.parts.append(re.sub(r"\s+", " ", data))


MIN_FULLTEXT_CHARS = 1500


def extract_fulltext(doi_or_key: str, html: str) -> Optional[str]:
    """Return Markdown-ish body text, or None if the page lacks full text."""
    pub = REGISTRY.get(doi_or_key) or route(doi_or_key)
    if pub is None:
        return None
    for sel in pub.body_selectors:
        ex = _BodyExtractor((sel,))
        ex.feed(html)
        text = re.sub(r"[ \t]+\n", "\n", "".join(ex.parts))
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if len(text) >= MIN_FULLTEXT_CHARS:
            title = (parse_meta(html).get("citation_title") or [""])[0]
            return (f"# {title}\n\n" if title else "") + text
    return None


# --------------------------------------------------------- challenge detection
CHALLENGE_MARKERS = (
    "cf-challenge", "challenges.cloudflare.com", "cf-turnstile", "just a moment...",
    "checking your browser", "verify you are human", "g-recaptcha", "hcaptcha",
    "px-captcha", "_incapsula_resource", "attention required! | cloudflare",
    "are you a robot", "datadome",
)
LOGIN_MARKERS = (
    "institutional login", "sign in to access", "access through your institution",
    "purchase pdf", "get access", "log in via shibboleth", "openathens", "buy article",
)


def is_pdf_viewer(html: str, url: str = "") -> bool:
    """True when the tab shows Chrome's built-in PDF viewer (i.e. a PDF loaded)."""
    low = (html or "")[:20_000].lower()
    if 'type="application/pdf"' in low and ("<embed" in low or "pdf-viewer" in low):
        return True
    if "the placeholder in the body style is for an optional background-color" in low:
        return True  # Chrome >= ~120 PDF viewer (out-of-process, no <embed> in DOM)
    return "chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai" in low


def page_shows_pdf(page) -> bool:
    """True when the tab's current document is a PDF (built-in viewer)."""
    try:
        if page.evaluate("document.contentType") == "application/pdf":
            return True
    except Exception:  # noqa: BLE001
        pass
    return is_pdf_viewer(safe_content(page, attempts=1), getattr(page, "url", ""))


def detect_block(html: str, status: int = 200, url: str = "") -> Optional[str]:
    """'challenge' | 'login' | None. Detection only; never interacts."""
    if is_pdf_viewer(html, url):
        return None
    low = html.lower()
    if any(m in low for m in CHALLENGE_MARKERS) or ("cloudflare" in low and status in (403, 503)):
        return "challenge"
    if re.search(r"/(login|signin|sso|idp|shibboleth|wayf)\b", url.lower()):
        return "login"
    if any(m in low for m in LOGIN_MARKERS) and "citation_pdf_url" not in low:
        return "login"
    if status in (401, 403):
        return "login"
    return None


def is_pdf(body: bytes) -> bool:
    return body[:5] == b"%PDF-" and len(body) > 10_000


# ---------------------------------------------------------------- rate limit
@dataclass
class RateLimiter:
    state_file: Path
    min_interval: float = 10.0
    max_interval: float = 20.0
    daily_cap: int = 60
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    today: Callable[[], str] = lambda: date.today().isoformat()
    _last: Optional[float] = field(default=None, init=False)

    def _load(self) -> dict:
        try:
            return json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            return {}

    def acquire(self) -> None:
        st = self._load()
        if st.get("day") != self.today():
            st = {"day": self.today(), "count": 0}
        if st["count"] >= self.daily_cap:
            raise RuntimeError("connect_daily_cap_reached")
        if self._last is not None:
            wait = random.uniform(self.min_interval, self.max_interval) - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)
        self._last = self.clock()
        st["count"] += 1
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(st))


# ------------------------------------------------------------ browser driver
@dataclass
class FetchResult:
    doi: str
    publisher: str
    status: str  # html | pdf | challenge | login | not_found | error
    path: Optional[str] = None
    size: int = 0
    detail: str = ""
    metadata: Optional[dict] = None
    tried: list = field(default_factory=list)
    handoffs: int = 0


def bring_to_front(page) -> None:
    try:
        page.bring_to_front()
    except Exception:  # noqa: BLE001
        pass


def wait_for_clearance(page, kind: str, *, timeout_s: float = 300.0, poll_s: float = 2.0,
                       notify: Optional[Callable[[str, str], None]] = None,
                       sleep: Callable[[float], None] = time.sleep,
                       clock: Callable[[], float] = time.monotonic) -> bool:
    """Hand the visible window to the user and poll until the block is gone.

    The user clicks/solves/logs in themselves. We only *read* the page state
    (``page.content()`` / ``page.url``) every ``poll_s`` seconds; nothing is
    clicked, typed, injected or spoofed. Returns True once cleared, False on
    timeout.
    """
    bring_to_front(page)
    if notify:
        notify(kind, page.url)
    deadline = clock() + timeout_s
    while clock() < deadline:
        sleep(poll_s)
        if page_shows_pdf(page):
            return True
        html = safe_content(page, attempts=1)
        if not html:
            continue
        if detect_block(html, 200, page.url) is None:
            # give a just-cleared challenge time to redirect to the article
            try:
                page.wait_for_load_state("domcontentloaded", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            return True
    return False


def safe_content(page, attempts: int = 5) -> str:
    """page.content() that tolerates redirects/JS navigations in progress."""
    for i in range(attempts):
        try:
            return page.content()
        except Exception:  # noqa: BLE001 - "page is navigating"
            try:
                page.wait_for_load_state("domcontentloaded", timeout=10_000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(500 * (i + 1))
    return ""


def _response_status(resp) -> int:
    try:
        return int(resp.status) if resp is not None else 0
    except Exception:  # noqa: BLE001
        return 0


def publisher_pdf_url_rejection_reason(url: str, publisher: Optional[Publisher] = None) -> Optional[str]:
    """Reject unsafe publisher PDF targets before sending browser cookies.

    PDF links can come from publisher HTML or Zotero translator metadata, so
    HTTPS alone is not enough. Reuse Relay's generated research-domain and
    public-IP policy, then apply the stricter HTTPS/default-port rules needed
    for browser-context requests.
    """
    try:
        parsed = urlparse(str(url or "").strip())
        if parsed.scheme.lower() != "https":
            return "publisher_pdf_https_required"
        if not parsed.hostname:
            return "publisher_pdf_host_missing"
        if parsed.username is not None or parsed.password is not None:
            return "publisher_pdf_userinfo_blocked"
        if parsed.port not in (None, 443):
            return "publisher_pdf_port_blocked"
    except ValueError:
        return "publisher_pdf_url_invalid"
    reason = relay_url_rejection_reason(url)
    if publisher is not None:
        host = parsed.hostname.lower().rstrip(".")
        allowed_hosts = publisher.pdf_hosts or publisher.hosts
        publisher_owned = any(host == allowed or host.endswith(f".{allowed}") for allowed in allowed_hosts)
        if not publisher_owned:
            return "publisher_pdf_publisher_host_blocked"
        # A few first-party publishers have not yet entered the generated
        # Relay suffix contract (currently AIP); retain their explicit local
        # publisher host only when Relay's check did not find a private target.
        if reason == "relay_url_domain_not_allowed":
            return None
    if reason:
        return reason
    return None


_PDF_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_PDF_CANDIDATES = 12
MAX_PDF_REDIRECTS = 10


def _response_header(resp, name: str) -> str:
    try:
        headers = resp.headers or {}
        return str(headers.get(name.lower()) or headers.get(name.title()) or "")
    except Exception:  # noqa: BLE001
        return ""


def _request_with_safe_redirects(page, url: str, timeout_ms: int, publisher: Publisher):
    """GET a PDF candidate with every redirect checked before its request."""
    current = url
    for redirect_count in range(MAX_PDF_REDIRECTS + 1):
        reason = publisher_pdf_url_rejection_reason(current, publisher)
        if reason:
            return None, current, reason
        try:
            response = page.context.request.get(current, timeout=timeout_ms, max_redirects=0)
        except Exception as exc:  # noqa: BLE001
            return None, current, f"request_{type(exc).__name__}"
        response_url = str(getattr(response, "url", "") or current)
        response_reason = publisher_pdf_url_rejection_reason(response_url, publisher)
        if response_reason:
            return None, response_url, response_reason
        status = _response_status(response)
        location = _response_header(response, "location")
        if status not in _PDF_REDIRECT_STATUSES or not location:
            return response, response_url, None
        if redirect_count >= MAX_PDF_REDIRECTS:
            return None, current, "publisher_pdf_redirect_limit"
        current = urljoin(response_url, location)
    return None, current, "publisher_pdf_redirect_limit"


class UnsafePublisherRedirect(RuntimeError):
    """Raised when a visible PDF handoff attempts an unapproved navigation."""


_CHALLENGE_ASSET_HOSTS = {
    "challenges.cloudflare.com", "www.google.com", "www.recaptcha.net", "recaptcha.net",
    "hcaptcha.com", "www.hcaptcha.com", "js.hcaptcha.com", "newassets.hcaptcha.com",
}


def _challenge_asset_url_allowed(url: str) -> bool:
    try:
        parsed = urlparse(str(url or "").strip())
        if parsed.scheme.lower() != "https" or parsed.username is not None or parsed.password is not None:
            return False
        if not parsed.hostname or parsed.port not in (None, 443):
            return False
        host = parsed.hostname.lower().rstrip(".")
    except ValueError:
        return False
    if host not in _CHALLENGE_ASSET_HOSTS:
        return False
    # The Relay checker reports private addresses before its general suffix
    # policy. Challenge hosts are intentionally outside the publisher allowlist.
    return relay_url_rejection_reason(url) != "relay_url_private_host_blocked"


def fetch_article(page, doi: str, out_dir: Path, limiter: RateLimiter,
                  wait_for_user: Optional[Callable[[object, str], bool]] = None,
                  goto_timeout_ms: int = 45_000, handoff_timeout_s: float = 300.0,
                  use_translators: bool = True, translator_runner: Optional[Callable] = None,
                  notify: Optional[Callable[[str, str], None]] = None,
                  prefer_html: bool = True, rate_limit: bool = True,
                  preloaded_page: Optional[tuple[str, str] | tuple[str, str, int]] = None) -> FetchResult:
    """Fetch one article in an existing (headed, user-owned) Playwright page.

    Order: landing page -> (challenge/login hand-off) -> HTML body ->
    Zotero translator PDF -> citation_pdf_url -> built URLs.
    ``wait_for_user(page, kind)`` overrides the default hand-off; pass
    ``handoff_timeout_s=0`` to report blocks immediately. ``preloaded_page``
    reuses rendered HTML, final URL and (when available) HTTP status from an
    already opened article tab.
    """
    doi = normalize_doi(doi)
    pub = route(doi)
    if pub is None:
        return FetchResult(doi, "-", "error", detail="not a Connect publisher")
    if rate_limit:
        limiter.acquire()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w.-]+", "_", doi)[:150]
    res = FetchResult(doi, pub.key, "not_found")

    def handoff(kind: str) -> bool:
        if handoff_timeout_s <= 0 and wait_for_user is None:
            return False
        res.handoffs += 1
        if wait_for_user is not None:
            return bool(wait_for_user(page, kind))
        return wait_for_clearance(page, kind, timeout_s=handoff_timeout_s, notify=notify)

    if preloaded_page is not None:
        html, landing = preloaded_page[:2]
        status = int(preloaded_page[2]) if len(preloaded_page) > 2 else 200
        current_page_url = str(getattr(page, "url", "") or "")
        if current_page_url and current_page_url != landing:
            res.status, res.detail = "error", "preloaded_page_url_mismatch"
            return res
    else:
        try:
            resp = page.goto(landing_url(doi), wait_until="domcontentloaded", timeout=goto_timeout_ms)
        except Exception as exc:  # noqa: BLE001
            res.status, res.detail = "error", f"goto: {exc}"[:300]
            return res
        page.wait_for_timeout(3000)
        html, status = safe_content(page), _response_status(resp)
        landing = page.url
    block = detect_block(html, status, landing)
    if block == "login" and status < 400 and extract_fulltext(pub.key, html):
        block = None  # "Get access"/"Sign in" chrome on a page that does show full text
    if block and handoff(block):
        html, status = safe_content(page), 200
        block = detect_block(html, status, page.url)
    if block == "challenge":
        res.status, res.detail = "challenge", f"http {status} {page.url}"
        return res
    if preloaded_page is None:
        landing = page.url or landing

    if use_translators:
        runner = translator_runner
        if runner is None:
            from .zotero.translators import run_translator as runner  # noqa: PLC0415
        tr = runner(page, pub.key) or {}
        items = tr.get("items") or []
        res.metadata = {"translator": tr.get("translator"), "error": tr.get("error"), "item": items[0] if items else None}
    from .zotero.translators import pdf_urls  # noqa: PLC0415
    tr_pdfs = pdf_urls({"items": [res.metadata["item"]]}) if res.metadata and res.metadata.get("item") else []

    if res.metadata:
        (out_dir / f"{stem}.json").write_text(json.dumps(res.metadata, indent=1, ensure_ascii=False), encoding="utf-8")

    text = extract_fulltext(pub.key, html) if prefer_html and not block else None
    if text:
        p = out_dir / f"{stem}.md"
        p.write_text(text, encoding="utf-8")
        res.status, res.path, res.size, res.detail = "html", str(p), len(text.encode()), landing
        return res

    queue = pdf_candidates(doi, landing, html, tr_pdfs)[:MAX_PDF_CANDIDATES]
    seen: set[str] = set()
    followups = 0
    pdf_handoffs = 0

    def save(body: bytes, where: str, how: str) -> FetchResult:
        p = out_dir / f"{stem}.pdf"
        p.write_bytes(body)
        res.status, res.path, res.size, res.detail = "pdf", str(p), len(body), f"{where} [{how}]"
        return res

    while queue:
        cand = queue.pop(0)
        if cand in seen:
            continue
        seen.add(cand)
        res.tried.append(cand)
        r, final, request_error = _request_with_safe_redirects(page, cand, goto_timeout_ms, pub)
        if request_error:
            res.detail = f"{cand}: {request_error}"
            if request_error.startswith("publisher_pdf_") or request_error.startswith("relay_url_"):
                res.status = "error"
            continue
        try:
            body, rstatus, ctype = r.body(), _response_status(r), _response_header(r, "content-type")
        except Exception as exc:  # noqa: BLE001
            res.detail = f"{cand}: response_{type(exc).__name__}"
            continue
        if is_pdf(body):
            return save(body, final, "request")
        snippet = body[:400_000].decode("utf-8", "ignore")
        kind = detect_block(snippet, rstatus, final)
        res.detail = f"{cand}: http {rstatus} {ctype.split(';')[0]}"
        if kind == "challenge":
            # The user clears the challenge in the visible tab. Retry through
            # the cookie-sharing API context afterwards; redirects still pass
            # through the same per-hop policy as the original request.
            if pdf_handoffs >= 1:
                res.status = "challenge"
                res.detail += " (already handed off once for a PDF; not repeating)"
                return res
            pdf_handoffs += 1
            try:
                got = open_pdf_with_handoff(page, final, handoff, goto_timeout_ms, publisher=pub)
            except UnsafePublisherRedirect as exc:
                res.status, res.detail = "error", str(exc)[:300]
                return res
            if got is not None:
                return save(got[0], got[1], got[2])
            res.status = "challenge"
            return res
        if "html" in ctype and followups < 4:
            extra = [u for u in pdf_links_in_html(snippet, final) if u not in seen]
            remaining = MAX_PDF_CANDIDATES - len(seen) - len(queue)
            extra = extra[:max(0, remaining)]
            followups += len(extra) > 0
            queue[:0] = extra
    if block:
        res.status = block
    return res


def open_pdf_with_handoff(page, url: str, handoff: Callable[[str], bool], timeout_ms: int,
                          *, publisher: Optional[Publisher] = None):
    """Navigate the visible tab to a PDF URL, hand a challenge to the user, capture the PDF.

    Capture sources, in order: a PDF response seen on the tab (main-frame
    navigation), a browser download, then a cookie-sharing API retry after
    any user clearance. Returns (bytes, url, how) or None. Hands off at most
    once.
    """
    seen_pdf: list = []
    downloads: list = []
    blocked_navigation: list[str] = []

    def guard_navigation(route):
        request = route.request
        try:
            is_navigation = request.is_navigation_request()
        except Exception:  # noqa: BLE001
            blocked_navigation.append("publisher_pdf_navigation_unverified")
            route.abort()
            return
        if not is_navigation:
            reason = publisher_pdf_url_rejection_reason(request.url, publisher)
            if reason and not _challenge_asset_url_allowed(request.url):
                # Optional analytics/fonts/etc. may be blocked without making
                # an otherwise safe main-frame PDF handoff fail.
                route.abort()
                return
            route.continue_()
            return
        try:
            is_main_frame = request.frame == page.main_frame
        except Exception:  # noqa: BLE001 - fail closed for an uninspectable navigation
            blocked_navigation.append("publisher_pdf_navigation_unverified")
            route.abort()
            return
        if not is_main_frame:
            reason = publisher_pdf_url_rejection_reason(request.url, publisher)
            if reason and not _challenge_asset_url_allowed(request.url):
                route.abort()
                return
            route.continue_()
            return
        reason = publisher_pdf_url_rejection_reason(request.url, publisher)
        if reason:
            blocked_navigation.append(reason)
            route.abort()
            return
        route.continue_()

    def on_response(resp):
        try:
            request = resp.request
            if not request.is_navigation_request() or request.frame != page.main_frame:
                return
            if publisher_pdf_url_rejection_reason(resp.url, publisher):
                return
            if "application/pdf" in (resp.headers.get("content-type") or "").lower():
                seen_pdf.append(resp)
        except Exception:  # noqa: BLE001
            pass

    def captured():
        for resp in reversed(seen_pdf):
            try:
                body = resp.body()
            except Exception:  # noqa: BLE001 - body may be unavailable for viewer loads
                continue
            if is_pdf(body) and not publisher_pdf_url_rejection_reason(resp.url, publisher):
                return body, resp.url, "tab response"
        for dl in reversed(downloads):
            try:
                path = dl.path()
                body = Path(path).read_bytes() if path else b""
            except Exception:  # noqa: BLE001
                continue
            if is_pdf(body) and not publisher_pdf_url_rejection_reason(dl.url, publisher):
                return body, dl.url, "download"
        return None

    def checked_request():
        response, final, reason = _request_with_safe_redirects(page, url, timeout_ms, publisher) if publisher else (None, url, "publisher_pdf_publisher_host_blocked")
        if reason and (reason.startswith("publisher_pdf_") or reason.startswith("relay_url_")):
            raise UnsafePublisherRedirect(f"publisher_pdf_redirect_blocked: {reason}")
        if response is None:
            return None
        try:
            body = response.body()
        except Exception:  # noqa: BLE001
            return None
        return (body, final, "request after browser handoff") if is_pdf(body) else None

    def on_download(dl):
        downloads.append(dl)

    try:
        page.route("**/*", guard_navigation)
    except Exception as exc:  # noqa: BLE001 - fail closed without redirect interception
        raise UnsafePublisherRedirect("publisher_pdf_navigation_guard_unavailable") from exc
    page.on("response", on_response)
    page.on("download", on_download)
    try:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception:  # noqa: BLE001 - PDF navigations may abort as downloads
            pass
        if blocked_navigation:
            raise UnsafePublisherRedirect(f"publisher_pdf_redirect_blocked: {blocked_navigation[0]}")
        page.wait_for_timeout(1500)
        got = captured()
        if got:
            return got
        state = None if page_shows_pdf(page) else detect_block(safe_content(page), 200, page.url)
        if state is not None and not handoff(state):
            return captured()
        # cleared (or never blocked): give the viewer a moment to finish loading
        page.wait_for_timeout(2000)
        return captured() or checked_request()
    finally:
        for ev, fn in (("response", on_response), ("download", on_download)):
            try:
                page.remove_listener(ev, fn)
            except Exception:  # noqa: BLE001
                pass
        try:
            page.unroute("**/*", guard_navigation)
        except Exception:  # noqa: BLE001
            pass
