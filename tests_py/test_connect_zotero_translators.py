"""Zotero translator runtime tests.

Translators (AGPL) are fetched from the pinned zotero/translators commit into
the user cache, not vendored. Browser tests need Playwright + Chromium; both
are skipped when unavailable.
"""
import json
from pathlib import Path

import pytest

from mdtero.connect.zotero import translators as zt

FX = Path(__file__).parent / "fixtures" / "connect"


def _sources_or_skip():
    try:
        for name in {*zt.PUBLISHER_TRANSLATORS.values(), *zt.DEPENDENCIES.values()}:
            zt.load_source(name)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"translator sources unavailable: {exc}")


def test_split_and_program_build():
    _sources_or_skip()
    for key, name in zt.PUBLISHER_TRANSLATORS.items():
        header, code = zt.split_translator(zt.load_source(name))
        assert header["translatorID"] and "BEGIN TEST CASES" not in code
        program, main_id = zt.build_program(name)
        assert main_id == header["translatorID"]
        assert "new Function" not in program.split("const __shim", 1)[1][:200]


def test_targets_cover_publisher_urls():
    _sources_or_skip()
    urls = {
        "acs": "https://pubs.acs.org/doi/10.1021/acs.joc.5c01432",
        "wiley": "https://onlinelibrary.wiley.com/doi/full/10.1002/jnm.70088",
        "tandf": "https://www.tandfonline.com/doi/full/10.1080/00029890.2025.2600905",
        "aip": "https://pubs.aip.org/aip/jcp/article/163/1/014101/3351234",
        "oup": "https://academic.oup.com/treephys/article/doi/10.1093/treephys/tpaf063/8155778",
        "ieee": "https://ieeexplore.ieee.org/document/11455915",
        "rsc": "https://pubs.rsc.org/en/content/articlelanding/2025/qo/d5qo01181g",
        "elsevier": "https://www.sciencedirect.com/science/article/pii/S0263224126016970",
    }
    for key, url in urls.items():
        assert zt.target_matches(zt.PUBLISHER_TRANSLATORS[key], url), key


def test_pdf_urls_filters_supplements():
    r = {"items": [{"attachments": [
        {"url": "https://x/si.pdf", "mimeType": "application/pdf", "title": "Supplementary Information PDF"},
        {"url": "https://x/a.pdf", "mimeType": "application/pdf", "title": "Full Text PDF"},
        {"url": "https://x/snap", "mimeType": "text/html", "title": "Snapshot"}]}]}
    assert zt.pdf_urls(r) == ["https://x/a.pdf"]


@pytest.fixture(scope="module")
def browser():
    _sources_or_skip()
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        p = sync_api.sync_playwright().start()
        b = p.chromium.launch()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"chromium unavailable: {exc}")
    yield b
    b.close()
    p.stop()


def _open(browser, url, html, mocks):
    page = browser.new_page()
    seen = []

    def handler(route):
        req = route.request
        if req.url == url:
            return route.fulfill(body=html, content_type="text/html")
        seen.append((req.method, req.url, req.post_data))
        for prefix, (ctype, body) in mocks.items():
            if req.url.startswith(prefix):
                return route.fulfill(body=body(req) if callable(body) else body, content_type=ctype)
        return route.fulfill(status=404, body="nf")
    page.route("**/*", handler)
    page.goto(url)
    return page, seen


RIS = """TY  - JOUR
TI  - Mocked T&F Article
AU  - Chen, Jianbin
AU  - Doe, Jane
JO  - Science and Technology of Advanced Materials
PY  - 2023
VL  - 24
DO  - 10.1080/14686996.2023.2170164
UR  - https://doi.org/10.1080/14686996.2023.2170164
ER  - 
"""
BIB = "@article{x, title={Mocked T&F Article}, author={Chen, Jianbin and Doe, Jane}, journal={STAM}, year={2023}, doi={10.1080/14686996.2023.2170164}}"


def test_tandf_ris_bibtex_path(browser):
    url = "https://www.tandfonline.com/doi/full/10.1080/14686996.2023.2170164"
    page, seen = _open(browser, url, (FX / "tandf_oa.html").read_text(), {
        "https://www.tandfonline.com/action/downloadCitation": ("text/plain", lambda req: BIB if "format=bibtex" in (req.post_data or "") else RIS)})
    r = zt.run_translator(page, "tandf", timeout_ms=5000)
    page.close()
    assert r["items"], r
    it = r["items"][0]
    assert it["title"] == "Mocked T&F Article" and it["DOI"] == "10.1080/14686996.2023.2170164"
    assert [c["lastName"] for c in it["creators"]] == ["Chen", "Doe"]
    assert any("/doi/pdf/10.1080/14686996.2023.2170164" in u for u in zt.pdf_urls(r))
    assert all(m == "POST" for m, *_ in seen)


def test_ieee_bibtex_rest_path(browser):
    url = "https://ieeexplore.ieee.org/document/10005208"
    bib = "@ARTICLE{10005208, author={Chen, Jianbin}, journal={IEEE Access}, title={Mocked IEEE}, year={2023}, volume={11}, pages={1-10}, doi={10.1109/ACCESS.2023.1}}"
    page, _ = _open(browser, url, (FX / "ieee_oa.html").read_text(), {
        "https://ieeexplore.ieee.org/rest/search/citation/format": ("application/json", json.dumps({"data": bib})),
        "https://ieeexplore.ieee.org/stamp/stamp.jsp": ("text/html", '<iframe src="https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=10005208&ref="></iframe>'),
    })
    r = zt.run_translator(page, "ieee", timeout_ms=5000)
    page.close()
    assert r["items"][0]["title"] == "Mocked IEEE"
    assert zt.pdf_urls(r) == ["https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=10005208&ref="]


@pytest.mark.parametrize("key,url", [
    ("rsc", "https://pubs.rsc.org/en/content/articlelanding/2023/ra/d3ra00001a"),
    ("wiley", "https://onlinelibrary.wiley.com/doi/full/10.1002/advs.202300001"),
])
def test_embedded_metadata_path(browser, key, url):
    page, _ = _open(browser, url, (FX / f"{key}_oa.html").read_text(), {})
    r = zt.run_translator(page, key, timeout_ms=4000)
    page.close()
    assert r["items"] and r["items"][0]["title"] == f"Test {key} article"
    assert zt.pdf_urls(r)


def test_translator_error_never_raises(browser):
    url = "https://ieeexplore.ieee.org/document/1"
    page, _ = _open(browser, url, "<html><body>nothing</body></html>", {})
    r = zt.run_translator(page, "ieee", timeout_ms=1500)
    page.close()
    assert r["items"] == [] and r.get("error")


def test_target_mismatch_skips(browser):
    page, _ = _open(browser, "https://example.org/x", "<html></html>", {})
    r = zt.run_translator(page, "elsevier")
    page.close()
    assert "does not match" in r["error"]


def test_real_browser_pdf_capture_after_handoff(browser, tmp_path):
    """open_pdf_with_handoff in Chromium: challenge first, then the PDF once 'cleared'."""
    from mdtero.connect import publisher_adapter as pa
    pdf = b"%PDF-1.7\n" + b"1" * 30000 + b"\n%%EOF"
    state = {"cleared": False}
    challenge = (FX / "cloudflare_challenge.html").read_text()
    ctx = browser.new_context(accept_downloads=True)
    page = ctx.new_page()

    def handler(route):
        if route.request.url.endswith(".pdf") and state["cleared"]:
            return route.fulfill(body=pdf, content_type="application/pdf")
        return route.fulfill(status=403, body=challenge, content_type="text/html")
    page.route("**/*", handler)
    page.goto("https://pubs.acs.org/doi/10.1021/x")

    def user_clears(kind):
        state["cleared"] = True
        try:
            page.reload()  # headless Chromium turns a PDF navigation into a download
        except Exception:  # noqa: BLE001
            pass
        return True
    url = "https://pubs.acs.org/joceah/article-pdf/90/37/12984/40754625/jo5c01432.pdf"
    got = pa.open_pdf_with_handoff(page, url, user_clears, 10_000)
    ctx.close()
    assert got is not None and got[0] == pdf, got and got[2]
