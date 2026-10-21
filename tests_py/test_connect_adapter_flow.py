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
    def __init__(self, pages, routes, final_url=None):
        self.pages = list(pages)  # successive page.content() values
        self.url = ""
        self.final_url = final_url
        self.context = type("C", (), {})()
        self.context.request = FakeRequest(routes)
        self.gotos, self.fronted = [], 0

    def goto(self, url, **kw):
        self.gotos.append(url)
        self.url = self.final_url or url
        return Resp(200)

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
    assert r.status == "pdf" and r.detail.endswith("1.pdf")


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


def test_pdf_challenge_shown_to_user_and_retried(tmp_path):
    state = {"n": 0}

    def pdf_route():
        state["n"] += 1
        return Resp(403, CHALLENGE.encode(), "text/html") if state["n"] == 1 else Resp(200, PDF, "application/pdf")
    page = FakePage(["<html><body>abstract</body></html>"], {"https://www.tandfonline.com/doi/pdf/10.1080/x": pdf_route})
    r = pa.fetch_article(page, "10.1080/x", tmp_path, limiter(tmp_path), translator_runner=no_translator,
                         wait_for_user=lambda p, k: True)
    assert r.status == "pdf" and r.handoffs == 1
    assert "https://www.tandfonline.com/doi/pdf/10.1080/x" in page.gotos


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
