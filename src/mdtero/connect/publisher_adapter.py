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
              body_selectors=("section.article-section__full", "div.article__body")),
    Publisher("tandf", "Taylor & Francis", ("10.1080",), ("www.tandfonline.com",),
              "https://www.tandfonline.com/doi/full/{doi}",
              ("https://www.tandfonline.com/doi/pdf/{doi}",),
              body_selectors=("div.hlFld-Fulltext",)),
    Publisher("aip", "AIP", ("10.1063",), ("pubs.aip.org",),
              "https://pubs.aip.org/doi/{doi}",
              ("https://pubs.aip.org/doi/pdf/{doi}",),
              body_selectors=("div.article-body", "div#ContentTab"),
              notes="pdf may redirect to /article-pdf/... ; citation_pdf_url preferred"),
    Publisher("ieee", "IEEE", ("10.1109",), ("ieeexplore.ieee.org",),
              "https://doi.org/{doi}",
              ("https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={arnumber}",),
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
              needs_landing_page=True,
              body_selectors=("div#body", "div.Body"),
              notes="PII from linkinghub redirect"),
    Publisher("oup", "Oxford University Press", ("10.1093",), ("academic.oup.com",),
              "https://doi.org/{doi}", (), needs_landing_page=True,
              body_selectors=("div.article-body", "div.widget-ArticleFulltext"),
              notes="PDF only via citation_pdf_url"),
]}


def normalize_doi(value: str) -> str:
    v = value.strip()
    v = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", v, flags=re.I)
    return v.strip().lower() if v.lower().startswith("10.") else v.strip()


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
    m = re.search(r"ieeexplore\.ieee\.org/(?:abstract/)?document/(\d+)", url)
    if m:
        out["arnumber"] = m.group(1)
    m = re.search(r"arnumber=(\d+)", url)
    if m:
        out.setdefault("arnumber", m.group(1))
    m = re.search(r"/content/article(?:landing|html|pdf)/(\d{4})/([a-z]+)/([a-z0-9]+)", url, re.I)
    if m:
        out.update(year=m.group(1), journal=m.group(2).lower(), article_id=m.group(3).lower())
    m = re.search(r"/pii/(S?[0-9X]{15,17}[0-9X]?)", url, re.I)
    if m:
        out["pii"] = m.group(1).upper()
    return out


def pdf_candidates(doi: str, resolved_url: str = "", html: str = "") -> list[str]:
    """Ordered PDF URL candidates: citation_pdf_url, then templates."""
    pub = route(doi)
    if pub is None:
        return []
    cands: list[str] = []
    if html:
        meta = parse_meta(html).get("citation_pdf_url")
        if meta:
            cands.append(urljoin(resolved_url or landing_url(doi), meta[0]))
    ids = {"doi": normalize_doi(doi), **ids_from_url(resolved_url)}
    for tpl in pub.pdf_templates:
        try:
            cands.append(tpl.format(**ids))
        except KeyError:
            continue  # ids not yet known (needs landing page)
    seen: set[str] = set()
    return [c for c in cands if not (c in seen or seen.add(c))]


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


def detect_block(html: str, status: int = 200, url: str = "") -> Optional[str]:
    """'challenge' | 'login' | None. Detection only; never interacts."""
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


def fetch_article(page, doi: str, out_dir: Path, limiter: RateLimiter,
                  wait_for_user: Optional[Callable[[str], bool]] = None,
                  goto_timeout_ms: int = 45_000) -> FetchResult:
    """Fetch one article in an existing (headed, user-owned) Playwright page.

    ``wait_for_user(kind)`` is invoked when a challenge/login is shown; it should
    bring the window to the front and block until the user is done, returning
    True to re-check. With no callback the block is reported as-is.
    """
    pub = route(doi)
    if pub is None:
        return FetchResult(doi, "-", "error", detail="not a Connect publisher")
    limiter.acquire()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w.-]+", "_", normalize_doi(doi))
    resp = page.goto(landing_url(doi), wait_until="domcontentloaded", timeout=goto_timeout_ms)
    page.wait_for_timeout(3000)
    html, status = page.content(), (resp.status if resp else 0)
    block = detect_block(html, status, page.url)
    if block and wait_for_user and wait_for_user(block):
        html, status = page.content(), 200
        block = detect_block(html, status, page.url)
    if block == "challenge":
        return FetchResult(doi, pub.key, "challenge", detail=f"http {status} {page.url}")
    text = extract_fulltext(pub.key, html)
    if text:
        p = out_dir / f"{stem}.md"
        p.write_text(text, encoding="utf-8")
        return FetchResult(doi, pub.key, "html", str(p), len(text.encode()), page.url)
    for cand in pdf_candidates(doi, page.url, html):
        try:
            r = page.context.request.get(cand, timeout=goto_timeout_ms)
            body = r.body()
        except Exception as exc:  # noqa: BLE001
            last = f"{cand}: {exc}"
            continue
        if is_pdf(body):
            p = out_dir / f"{stem}.pdf"
            p.write_bytes(body)
            return FetchResult(doi, pub.key, "pdf", str(p), len(body), cand)
        last = f"{cand}: http {r.status} {r.headers.get('content-type','')}"
        if detect_block(body[:200_000].decode("utf-8", "ignore"), r.status) == "challenge":
            return FetchResult(doi, pub.key, "challenge", detail=last)
    return FetchResult(doi, pub.key, block or "not_found", detail=locals().get("last", f"http {status}"))
