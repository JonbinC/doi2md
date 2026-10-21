"""Flow tests for fetch_article with a fake Playwright page (no network)."""
from pathlib import Path

from mdtero.connect import publisher_adapter as pa

FX = Path(__file__).parent / "fixtures" / "connect"
PDF = b"%PDF-1.7\n" + b"0" * 20000
CHALLENGE = (FX / "cloudflare_challenge.html").read_text()


class Resp:
    def __init__(self, status=200, body=b"", ctype="text/html", url=""):
        self.status, self._b, self.headers, self.url = status, body, {"content-type": ctype}, url

    def body(self):
        return self._b


class FakeRequest:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, **kw):
        self.calls.append(url)
        r = self.routes.get(url)
        if callable(r):
            r = r()
        return r or Resp(404, b"not found", url=url)


class FakePage:
    def __init__(self, pages, routes, final_url=None, inpage=None, nav=None):
        self.pages = list(pages)  # successive page.content() values
        self.url = ""
        self.final_url = final_url
        self.inpage = inpage or {}  # url -> bytes returned by in-page fetch (or callable)
        self.nav = nav or {}  # url -> list of (event, obj) emitted on goto
        self.listeners = {}
        self.evaluated = []
        self.context = type("C", (), {})()
        self.context.request = FakeRequest(routes)
        self.gotos, self.fronted = [], 0

    def goto(self, url, **kw):
        self.gotos.append(url)
        self.url = self.final_url or url
        for ev, obj in self.nav.get(url, []):
            for fn in list(self.listeners.get(ev, [])):
                fn(obj)
        return Resp(200)

    def on(self, ev, fn):
        self.listeners.setdefault(ev, []).append(fn)

    def remove_listener(self, ev, fn):
        self.listeners.get(ev, []).remove(fn)

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


def limiter(tmp_path):
    return pa.RateLimiter(tmp_path / "rl.json", sleep=lambda s: None)


def no_translator(page, key):
    return {"items": []}


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
    def __init__(self, url, body, ctype="application/pdf"):
        self.url, self._b, self.headers = url, body, {"content-type": ctype}

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
    page = _acs_page(nav={ACS_PDF: [("response", PdfResp(ACS_PDF, PDF))]})
    page.pages = ["<html><body>abstract</body></html>", CHALLENGE, VIEWER]
    calls = []
    r = pa.fetch_article(page, "10.1021/acs.joc.5c01432", tmp_path, limiter(tmp_path),
                         translator_runner=lambda p, k: _acs_item(), wait_for_user=lambda p, k: calls.append(k) or True)
    assert r.status == "pdf" and r.size == len(PDF) and "tab response" in r.detail
    assert Path(r.path).read_bytes()[:5] == b"%PDF-"


def test_acs_pdf_viewer_then_in_page_fetch(tmp_path):
    # The tab's PDF response body is unavailable (viewer load); fetch from inside the page.
    state = {"cleared": False}

    def inpage():
        return PDF if state["cleared"] else CHALLENGE.encode()

    def user(p, kind):
        state["cleared"] = True
        p.pages = [VIEWER]
        return pa.wait_for_clearance(p, kind, timeout_s=60, sleep=lambda s: None)
    page = _acs_page(inpage={ACS_PDF: inpage})
    page.pages = ["<html><body>abstract</body></html>", CHALLENGE]
    page.final_url = None
    r = pa.fetch_article(page, "10.1021/acs.joc.5c01432", tmp_path, limiter(tmp_path),
                         translator_runner=lambda p, k: _acs_item(), wait_for_user=user)
    assert r.status == "pdf" and "in-page fetch" in r.detail and r.handoffs == 1


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


def test_in_page_fetch_skips_cross_origin(tmp_path):
    page = FakePage(["<html></html>"], {}, inpage={"https://other.example/x.pdf": PDF})
    page.url = "https://pubs.acs.org/doi/x"
    assert pa.fetch_in_page(page, "https://other.example/x.pdf") == b""


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
