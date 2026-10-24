"""Flow tests for fetch_article with a fake Playwright page (no network)."""
from pathlib import Path
from urllib.parse import urlparse

import pytest

from mdtero.connect import publisher_adapter as pa

FX = Path(__file__).parent / "fixtures" / "connect"
PDF = b"%PDF-1.7\n" + b"0" * 20000
CHALLENGE = (FX / "cloudflare_challenge.html").read_text()


class Resp:
    def __init__(self, status=200, body=b"", ctype="text/html", url="", headers=None):
        self.status, self._b, self.headers, self.url = status, body, {"content-type": ctype, **(headers or {})}, url

    def body(self):
        return self._b


class FakeRequest:
    def __init__(self, routes):
        self.routes, self.calls, self.options = routes, [], []

    def get(self, url, **kw):
        self.calls.append(url)
        self.options.append(kw)
        r = self.routes.get(url)
        if callable(r):
            r = r()
        return r or Resp(404, b"not found", url=url)


class FakePage:
    def __init__(self, pages, routes, final_url=None, inpage=None, nav=None, subresources=None):
        self.pages = list(pages)  # successive page.content() values
        self.url = ""
        self.final_url = final_url
        self.inpage = inpage or {}  # url -> bytes returned by in-page fetch (or callable)
        self.nav = nav or {}  # url -> list of (event, obj) emitted on goto
        self.subresources = list(subresources or [])
        self.aborted_subresources = []
        self.listeners = {}
        self.evaluated = []
        self.context = type("C", (), {})()
        self.context.request = FakeRequest(routes)
        self.gotos, self.fronted = [], 0
        self.main_frame, self.route_handlers = object(), []

    def goto(self, url, **kw):
        self.gotos.append(url)
        self.url = self.final_url or url
        for handler in self.route_handlers:
            request = type("Request", (), {
                "url": self.url,
                "frame": self.main_frame,
                "is_navigation_request": lambda _self: True,
            })()
            route = type("Route", (), {
                "request": request,
                "continue_": lambda _self: None,
                "abort": lambda _self: (_ for _ in ()).throw(RuntimeError("navigation aborted")),
            })()
            try:
                handler(route)
            except RuntimeError:
                self.url = ""
                raise
        for target in self.subresources:
            request = type("Request", (), {
                "url": target,
                "frame": object(),
                "is_navigation_request": lambda _self: False,
            })()
            state = {"aborted": False}
            route = type("Route", (), {
                "request": request,
                "continue_": lambda _self: None,
                "abort": lambda _self: state.update(aborted=True),
            })()
            for handler in self.route_handlers:
                handler(route)
            if state["aborted"]:
                self.aborted_subresources.append(target)
        for ev, obj in self.nav.get(url, []):
            for fn in list(self.listeners.get(ev, [])):
                fn(obj)
        return Resp(200)

    def on(self, ev, fn):
        self.listeners.setdefault(ev, []).append(fn)

    def remove_listener(self, ev, fn):
        self.listeners.get(ev, []).remove(fn)

    def route(self, pattern, handler):
        self.route_handlers.append(handler)

    def unroute(self, pattern, handler):
        self.route_handlers.remove(handler)

    def evaluate(self, js, arg=None):
        import base64
        if js == "document.contentType":
            return "application/pdf" if pa.is_pdf_viewer(self.pages[0]) else "text/html"
        self.evaluated.append(arg)
        v = self.inpage.get(arg, b"")
        v = v() if callable(v) else v
        return {"status": 200, "b64": base64.b64encode(v).decode()}

    def wait_for_timeout(self, ms):
        pass

    def wait_for_load_state(self, *a, **k):
        pass

    def bring_to_front(self):
        self.fronted += 1

    def content(self):
        return self.pages.pop(0) if len(self.pages) > 1 else self.pages[0]


@pytest.fixture(autouse=True)
def stub_network_domain_checks(monkeypatch):
    """Keep adapter flow tests offline while retaining production policy tests below."""
    publisher_hosts = {
        host for publisher in pa.REGISTRY.values()
        for host in (*publisher.hosts, *publisher.pdf_hosts)
    }

    def allowed(url):
        host = (urlparse(url).hostname or "").lower()
        return None if host in publisher_hosts else "relay_url_domain_not_allowed"

    monkeypatch.setattr(pa, "relay_url_rejection_reason", allowed)


def limiter(tmp_path):
    return pa.RateLimiter(tmp_path / "rl.json", sleep=lambda s: None)


def no_translator(page, key):
    return {"items": []}


def test_publisher_pdf_url_requires_safe_https_target(monkeypatch):
    monkeypatch.setattr(pa, "relay_url_rejection_reason", lambda _url: None)

    assert pa.publisher_pdf_url_rejection_reason("http://pubs.acs.org/paper.pdf") == "publisher_pdf_https_required"
    assert pa.publisher_pdf_url_rejection_reason("https://user:pass@pubs.acs.org/paper.pdf") == "publisher_pdf_userinfo_blocked"
    assert pa.publisher_pdf_url_rejection_reason("https://pubs.acs.org:444/paper.pdf") == "publisher_pdf_port_blocked"
    assert pa.publisher_pdf_url_rejection_reason("https://pubs.acs.org/paper.pdf") is None

    monkeypatch.setattr(pa, "relay_url_rejection_reason", lambda _url: "relay_url_domain_not_allowed")
    assert pa.publisher_pdf_url_rejection_reason("https://example.com/paper.pdf") == "relay_url_domain_not_allowed"

    monkeypatch.setattr(pa, "relay_url_rejection_reason", lambda _url: None)
    acs = pa.route("10.1021/demo")
    assert pa.publisher_pdf_url_rejection_reason("https://ieeexplore.ieee.org/paper.pdf", acs) == "publisher_pdf_publisher_host_blocked"

    aip = pa.route("10.1063/demo")
    monkeypatch.setattr(pa, "relay_url_rejection_reason", lambda _url: "relay_url_domain_not_allowed")
    assert pa.publisher_pdf_url_rejection_reason("https://pubs.aip.org/doi/pdf/demo", aip) is None
    monkeypatch.setattr(pa, "relay_url_rejection_reason", lambda _url: "relay_url_private_host_blocked")
    assert pa.publisher_pdf_url_rejection_reason("https://pubs.aip.org/doi/pdf/demo", aip) == "relay_url_private_host_blocked"


def test_html_preferred(tmp_path):
    page = FakePage([(FX / "wiley_oa.html").read_text()], {})
    r = pa.fetch_article(page, "10.1002/advs.202300001", tmp_path, limiter(tmp_path), translator_runner=no_translator)
    assert r.status == "html" and Path(r.path).read_text().startswith("# Test wiley")
    assert page.context.request.calls == []


def test_translator_pdf_first_then_meta(tmp_path):
    item = {"title": "T", "attachments": [{"url": "https://pubs.acs.org/doi/pdf/10.1021/x?tr=1", "mimeType": "application/pdf", "title": "Full Text PDF"}]}
    page = FakePage(["<html><head><meta name='citation_pdf_url' content='/meta.pdf'></head><body>abstract</body></html>"],
                    {"https://pubs.acs.org/doi/pdf/10.1021/x?tr=1": Resp(200, PDF, "application/pdf")})
    r = pa.fetch_article(page, "10.1021/X", tmp_path, limiter(tmp_path), translator_runner=lambda p, k: {"items": [item], "translator": "Atypon Journals.js"})
    assert r.status == "pdf" and r.tried[0].endswith("?tr=1")
    assert (tmp_path / "10.1021_x.json").exists()


def test_aip_html_redirect_followed(tmp_path):
    viewer = b'<html><a class="article-pdfLink" href="/aip/adv/article-pdf/13/1/015001/1.pdf">PDF</a></html>'
    routes = {
        "https://pubs.aip.org/doi/pdf/10.1063/5.0275264": Resp(200, viewer, "text/html", "https://pubs.aip.org/aip/adv/article/13/1/015001/x"),
        "https://pubs.aip.org/aip/adv/article-pdf/13/1/015001/1.pdf": Resp(200, PDF, "application/pdf"),
    }
    page = FakePage(["<html><body>abstract only</body></html>"], routes)
    r = pa.fetch_article(page, "10.1063/5.0275264", tmp_path, limiter(tmp_path), translator_runner=no_translator)
    assert r.status == "pdf" and "1.pdf [request]" in r.detail


def test_pdf_redirects_are_checked_before_each_request(tmp_path):
    start = "https://pubs.acs.org/doi/pdf/custom"
    final = "https://pubs.acs.org/doi/pdf/download.pdf"
    evil = "https://example.com/private.pdf"
    routes = {
        start: Resp(302, b"", "text/html", start, {"location": final}),
        final: Resp(200, PDF, "application/pdf", final),
    }
    html = f'<html><meta name="citation_pdf_url" content="{start}"></html>'
    page = FakePage([html], routes)

    result = pa.fetch_article(page, "10.1021/x", tmp_path, limiter(tmp_path),
                              translator_runner=no_translator, prefer_html=False)

    assert result.status == "pdf"
    assert page.context.request.calls == [start, final]
    assert all(options["max_redirects"] == 0 for options in page.context.request.options)
    assert evil not in page.context.request.calls


def test_unapproved_metadata_pdf_url_is_never_requested(tmp_path):
    evil = "https://example.com/private.pdf"
    html = f'<html><meta name="citation_pdf_url" content="{evil}"></html>'
    page = FakePage([html], {})

    result = pa.fetch_article(page, "10.1021/x", tmp_path, limiter(tmp_path),
                              translator_runner=no_translator, prefer_html=False)

    assert result.status == "error"
    assert evil not in page.context.request.calls


def test_total_pdf_candidate_requests_are_capped(tmp_path):
    attachment_urls = [f"https://pubs.acs.org/doi/pdf/attachment-{i}" for i in range(11)]
    item = {"attachments": [
        {"url": url, "mimeType": "application/pdf", "title": "Full Text PDF"}
        for url in attachment_urls
    ]}
    nested = "".join(f'<a href="/doi/pdf/nested-{i}.pdf">PDF</a>' for i in range(10))
    routes = {attachment_urls[0]: Resp(200, nested.encode(), "text/html", attachment_urls[0])}
    page = FakePage(["<html><body>abstract</body></html>"], routes)

    pa.fetch_article(
        page, "10.1021/x", tmp_path, limiter(tmp_path), prefer_html=False,
        translator_runner=lambda _page, _key: {"items": [item]},
    )

    assert len(page.context.request.calls) == pa.MAX_PDF_CANDIDATES


def test_unapproved_http_redirect_is_not_followed(tmp_path):
    start = "https://pubs.acs.org/doi/pdf/custom"
    evil = "https://example.com/private.pdf"
    html = f'<html><meta name="citation_pdf_url" content="{start}"></html>'
    page = FakePage([html], {start: Resp(302, b"", "text/html", start, {"location": evil})})

    result = pa.fetch_article(page, "10.1021/x", tmp_path, limiter(tmp_path),
                              translator_runner=no_translator, prefer_html=False)

    assert result.status == "error"
    assert page.context.request.calls == [start, "https://pubs.acs.org/doi/pdf/10.1021/x"]
    assert all(options["max_redirects"] == 0 for options in page.context.request.options)
    assert evil not in page.gotos


def test_preloaded_page_url_must_match_current_tab(tmp_path):
    page = FakePage(["<html></html>"], {})
    page.url = "https://pubs.acs.org/doi/current"

    result = pa.fetch_article(
        page, "10.1021/x", tmp_path, limiter(tmp_path), use_translators=False,
        prefer_html=False, rate_limit=False,
        preloaded_page=("<html></html>", "https://pubs.acs.org/doi/old", 403),
    )

    assert result.status == "error" and result.detail == "preloaded_page_url_mismatch"
    assert page.context.request.calls == []


def test_pdf_handoff_blocks_new_unsafe_redirect(tmp_path):
    class RedirectPage(FakePage):
        def goto(self, url, **kw):
            self.gotos.append(url)
            self.url = url
            handler = self.route_handlers[0]
            for target, is_navigation, frame in (
                (url, True, self.main_frame),
                ("https://example.com/private.pdf", False, object()),
            ):
                request = type("Request", (), {
                    "url": target,
                    "frame": frame,
                    "is_navigation_request": lambda _self, value=is_navigation: value,
                })()
                state = {"aborted": False}
                route = type("Route", (), {
                    "request": request,
                    "continue_": lambda _self: None,
                    "abort": lambda _self: state.update(aborted=True),
                })()
                handler(route)
                if state["aborted"]:
                    return
            self.url = "https://example.com/private.pdf"

    page = RedirectPage(["<html></html>"], {})

    with pytest.raises(pa.UnsafePublisherRedirect, match="redirect_blocked"):
        pa.open_pdf_with_handoff(page, "https://pubs.acs.org/doi/pdf/custom", lambda _kind: True, 1000)

    assert page.gotos == ["https://pubs.acs.org/doi/pdf/custom"]
    assert page.route_handlers == []


def test_blocked_optional_subresource_does_not_fail_pdf_handoff(tmp_path):
    url = "https://pubs.acs.org/doi/pdf/custom"
    request = type("Request", (), {
        "is_navigation_request": lambda _self: True,
        "frame": None,
    })()
    response = type("PdfResp", (), {
        "request": request,
        "url": url,
        "headers": {"content-type": "application/pdf"},
        "body": lambda _self: PDF,
    })()
    page = FakePage(
        [CHALLENGE, VIEWER],
        {url: Resp(403, CHALLENGE.encode(), url=url)},
        nav={url: [("response", response)]},
        subresources=["https://example.com/analytics.js"],
    )
    response.request.frame = page.main_frame

    result = pa.open_pdf_with_handoff(
        page, url, lambda _kind: True, 1000, publisher=pa.REGISTRY["acs"]
    )

    assert result == (PDF, url, "tab response")
    assert page.aborted_subresources == ["https://example.com/analytics.js"]


def test_rsc_new_url_layout(tmp_path):
    want = "https://pubs.rsc.org/en/content/articlepdf/2026/qo/d5qo01181g"
    html = "<html><head><meta name='citation_publication_date' content='2026/01/05'></head></html>"
    assert pa.pdf_candidates("10.1039/D5QO01181G", "https://pubs.rsc.org/qo/article/13/1/244-250/905604", html)[0] == want
    c = pa.pdf_candidates("10.1039/d5qo01181g", "https://pubs.rsc.org/qo/article/13/1/244-250/905604")
    assert c == ["https://pubs.rsc.org/en/content/articlepdf/2025/qo/d5qo01181g", want]
    assert pa.rsc_ids_from_doi("10.1039/c1ee02148f")[0] == {"year": "2011", "journal": "ee", "article_id": "c1ee02148f"}


def test_challenge_handoff_then_resume(tmp_path):
    article = (FX / "tandf_oa.html").read_text()
    page = FakePage([CHALLENGE, CHALLENGE, CHALLENGE, article], {})
    seen = []
    r = pa.fetch_article(page, "10.1080/x", tmp_path, limiter(tmp_path), translator_runner=no_translator,
                         wait_for_user=lambda p, kind: seen.append(kind) or pa.wait_for_clearance(p, kind, timeout_s=60, sleep=lambda s: None))
    assert seen == ["challenge"] and r.status == "html" and r.handoffs == 1 and page.fronted == 1


def test_challenge_timeout_reports_blocked(tmp_path):
    page = FakePage([CHALLENGE], {})
    t = [0.0]

    def tick(s):
        t[0] += s
    r = pa.fetch_article(page, "10.1080/x", tmp_path, limiter(tmp_path), translator_runner=no_translator,
                         wait_for_user=lambda p, k: pa.wait_for_clearance(p, k, timeout_s=10, sleep=tick, clock=lambda: t[0]))
    assert r.status == "challenge" and t[0] >= 10


VIEWER = '<html><body style="margin:0"><embed name="x" style="position:absolute" src="about:blank" type="application/pdf" internalid="x"></body></html>'
ACS_PDF = "https://pubs.acs.org/joceah/article-pdf/90/37/12984/40754625/jo5c01432.pdf"


def test_pdf_viewer_is_not_a_challenge():
    assert pa.is_pdf_viewer(VIEWER)
    assert pa.detect_block(VIEWER, 200, ACS_PDF) is None
    assert pa.detect_block(VIEWER + "<!-- cloudflare -->", 403, ACS_PDF) is None
    modern = ('<!DOCTYPE html><html style="height:100%;width:100%"><!-- the placeholder in the body style is for an '
              'optional background-color --><head></head><body style="background-color:rgb(40,40,40);"></body></html>')
    assert pa.is_pdf_viewer(modern) and pa.detect_block(modern, 403) is None


class PdfResp:
    def __init__(self, url, body, ctype="application/pdf", frame=None):
        self.url, self._b, self.headers = url, body, {"content-type": ctype}
        self.request = type("Request", (), {
            "frame": frame,
            "is_navigation_request": lambda _self: True,
        })()

    def body(self):
        return self._b


def _acs_page(nav=None, inpage=None, after_clear=VIEWER):
    # landing (abstract only), then PDF URL shows challenge, user clears -> viewer
    page = FakePage(["<html><body>abstract</body></html>", "<html><body>abstract</body></html>", CHALLENGE, CHALLENGE, after_clear],
                    {ACS_PDF: Resp(403, CHALLENGE.encode(), "text/html")}, nav=nav, inpage=inpage)
    return page


def _acs_item():
    return {"items": [{"attachments": [{"url": ACS_PDF, "mimeType": "application/pdf", "title": "Full Text PDF"}]}]}


def _clear(p, kind):
    return pa.wait_for_clearance(p, kind, timeout_s=60, sleep=lambda s: None)


def test_acs_pdf_captured_from_tab_response_after_user_clears(tmp_path):
    page = _acs_page()
    page.nav[ACS_PDF] = [("response", PdfResp(ACS_PDF, PDF, frame=page.main_frame))]
    page.pages = ["<html><body>abstract</body></html>", CHALLENGE, VIEWER]
    calls = []
    r = pa.fetch_article(page, "10.1021/acs.joc.5c01432", tmp_path, limiter(tmp_path),
                         translator_runner=lambda p, k: _acs_item(), wait_for_user=lambda p, k: calls.append(k) or True)
    assert r.status == "pdf" and r.size == len(PDF) and "tab response" in r.detail
    assert Path(r.path).read_bytes()[:5] == b"%PDF-"


def test_pdf_response_from_subframe_is_not_saved(tmp_path):
    page = _acs_page()
    page.nav[ACS_PDF] = [("response", PdfResp(ACS_PDF, PDF, frame=object()))]

    result = pa.fetch_article(
        page, "10.1021/acs.joc.5c01432", tmp_path, limiter(tmp_path),
        translator_runner=lambda p, k: _acs_item(), wait_for_user=lambda _p, _k: True,
    )

    assert result.status == "challenge"
    assert not list(tmp_path.glob("*.pdf"))


def test_acs_pdf_viewer_retries_cookie_context_after_user_clears(tmp_path):
    # The API context first sees a challenge, then succeeds after visible user clearance.
    state = {"cleared": False}

    def pdf_route():
        if state["cleared"]:
            return Resp(200, PDF, "application/pdf", ACS_PDF)
        return Resp(403, CHALLENGE.encode(), "text/html", ACS_PDF)

    def user(p, kind):
        state["cleared"] = True
        p.pages = [VIEWER]
        return pa.wait_for_clearance(p, kind, timeout_s=60, sleep=lambda s: None)
    page = _acs_page()
    page.context.request.routes[ACS_PDF] = pdf_route
    page.pages = ["<html><body>abstract</body></html>", CHALLENGE]
    page.final_url = None
    r = pa.fetch_article(page, "10.1021/acs.joc.5c01432", tmp_path, limiter(tmp_path),
                         translator_runner=lambda p, k: _acs_item(), wait_for_user=user)
    assert r.status == "pdf" and "request after browser handoff" in r.detail and r.handoffs == 1
    assert page.context.request.calls.count(ACS_PDF) == 2


def test_download_event_is_captured(tmp_path):
    f = tmp_path / "dl.pdf"
    f.write_bytes(PDF)
    dl = type("D", (), {"url": ACS_PDF, "path": lambda self: str(f)})()
    page = _acs_page(nav={ACS_PDF: [("download", dl)]})
    r = pa.fetch_article(page, "10.1021/acs.joc.5c01432", tmp_path / "out", limiter(tmp_path),
                         translator_runner=lambda p, k: _acs_item(), wait_for_user=lambda p, k: True)
    assert r.status == "pdf" and "download" in r.detail


def test_pdf_handoff_happens_at_most_once(tmp_path):
    # User never clears; PDF stays challenged. Must not loop.
    calls = []
    page = FakePage(["<html><body>abstract</body></html>", CHALLENGE], {
        ACS_PDF: Resp(403, CHALLENGE.encode(), "text/html"),
        "https://pubs.acs.org/doi/pdf/10.1021/acs.joc.5c01432": Resp(403, CHALLENGE.encode(), "text/html")})
    r = pa.fetch_article(page, "10.1021/acs.joc.5c01432", tmp_path, limiter(tmp_path),
                         translator_runner=lambda p, k: _acs_item(), wait_for_user=lambda p, k: calls.append(k) or True)
    assert r.status == "challenge" and len(calls) <= 2  # landing page (none here) + one PDF hand-off
    assert page.gotos.count(ACS_PDF) == 1


def test_no_handoff_when_disabled(tmp_path):
    page = FakePage([CHALLENGE], {})
    r = pa.fetch_article(page, "10.1021/x", tmp_path, limiter(tmp_path), translator_runner=no_translator, handoff_timeout_s=0)
    assert r.status == "challenge" and r.handoffs == 0 and page.fronted == 0


def test_login_chrome_with_fulltext_is_not_blocked(tmp_path):
    html = (FX / "wiley_oa.html").read_text().replace("<nav>Menu Sign in</nav>", "<nav>Get access</nav>")
    page = FakePage([html], {})
    r = pa.fetch_article(page, "10.1002/x", tmp_path, limiter(tmp_path), translator_runner=no_translator, handoff_timeout_s=0)
    assert r.status == "html"


def test_non_pdf_and_tiny_pdf_rejected(tmp_path):
    routes = {"https://pubs.acs.org/doi/pdf/10.1021/x": Resp(200, b"%PDF-1.4 tiny", "application/pdf")}
    page = FakePage(["<html></html>"], routes)
    r = pa.fetch_article(page, "10.1021/x", tmp_path, limiter(tmp_path), translator_runner=no_translator)
    assert r.status == "not_found" and not list(tmp_path.glob("*.pdf"))


def test_normalize_doi_edge_cases():
    assert pa.normalize_doi("https://doi.org/10.1002%2Fadvs.202300001.") == "10.1002/advs.202300001"
    assert pa.normalize_doi(" doi: 10.1021/ACS.JOC.5C01432?via=x ") == "10.1021/acs.joc.5c01432"
    assert pa.normalize_doi("(10.1063/5.0275264)").endswith("5.0275264")


def test_pdf_links_in_html():
    html = '<iframe src="https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&amp;arnumber=1"></iframe>'
    assert pa.pdf_links_in_html(html, "https://ieeexplore.ieee.org/stamp/stamp.jsp") == [
        "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=1"]
