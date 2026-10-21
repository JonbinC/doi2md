from pathlib import Path

import pytest

from mdtero.connect import publisher_adapter as pa

FX = Path(__file__).parent / "fixtures" / "connect"


@pytest.mark.parametrize("doi,key,first", [
    ("10.1021/acsomega.3c00001", "acs", "https://pubs.acs.org/doi/pdf/10.1021/acsomega.3c00001"),
    ("https://doi.org/10.1002/aenm.201703401", "wiley", "https://onlinelibrary.wiley.com/doi/pdfdirect/10.1002/aenm.201703401"),
    ("10.1111/gcb.16000", "wiley", "https://onlinelibrary.wiley.com/doi/pdfdirect/10.1111/gcb.16000"),
    ("doi:10.1080/14686996.2023.2170164", "tandf", "https://www.tandfonline.com/doi/pdf/10.1080/14686996.2023.2170164"),
    ("10.1063/5.0135000", "aip", "https://pubs.aip.org/doi/pdf/10.1063/5.0135000"),
])
def test_template_publishers(doi, key, first):
    assert pa.route(doi).key == key
    assert pa.pdf_candidates(doi)[0] == first


def test_landing_page_publishers():
    assert pa.pdf_candidates("10.1109/TPAMI.2023.3237000") == []
    assert pa.pdf_candidates("10.1109/tpami.2023.3237000", "https://ieeexplore.ieee.org/document/10005208/") == [
        "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=10005208"]
    assert pa.pdf_candidates("10.1039/D3RA00001A", "https://pubs.rsc.org/en/content/articlelanding/2023/RA/D3RA00001A") == [
        "https://pubs.rsc.org/en/content/articlepdf/2023/ra/d3ra00001a"]
    assert pa.pdf_candidates("10.1016/j.rineng.2023.100001", "https://www.sciencedirect.com/science/article/pii/S2590123023000014") == [
        "https://www.sciencedirect.com/science/article/pii/S2590123023000014/pdfft?isDTMRedir=true&download=true"]
    assert pa.pdf_candidates("10.1093/nar/gkac1231") == []


@pytest.mark.parametrize("doi", ["10.3390/ht9030016", "10.3389/fmats.2023.1", "10.1186/s1", "10.1371/journal.pone.1",
                                 "10.5194/acp-1", "10.1088/1748-9326/1", "10.1017/x", "10.1103/PhysRevB.1", "10.9999/x"])
def test_http_direct_not_routed(doi):
    assert pa.route(doi) is None


@pytest.mark.parametrize("key", list(pa.REGISTRY))
def test_meta_and_fulltext_fixture(key):
    html = (FX / f"{key}_oa.html").read_text()
    meta = pa.parse_meta(html)
    assert meta["citation_pdf_url"]
    doi = {"acs": "10.1021/a", "wiley": "10.1002/a", "tandf": "10.1080/a", "aip": "10.1063/a", "ieee": "10.1109/a",
           "rsc": "10.1039/a", "elsevier": "10.1016/a", "oup": "10.1093/a"}[key]
    assert pa.pdf_candidates(doi, pa.landing_url(doi), html)[0].startswith("https://")
    text = pa.extract_fulltext(key, html)
    assert text.startswith(f"# Test {key} article")
    assert "## Introduction" in text and "Figure 1" in text
    assert "var x" not in text and "Menu" not in text and "(c) publisher" not in text
    assert pa.detect_block(html) is None


def test_abstract_only_returns_none():
    assert pa.extract_fulltext("aip", (FX / "abstract_only.html").read_text()) is None


def test_challenge_and_login_detection():
    assert pa.detect_block((FX / "cloudflare_challenge.html").read_text(), 403) == "challenge"
    assert pa.detect_block((FX / "login_wall.html").read_text()) == "login"
    assert pa.detect_block("<html></html>", 200, "https://idp.nottingham.ac.uk/idp/profile/SAML2/login") == "login"
    assert pa.detect_block("<html>cloudflare</html>", 503) == "challenge"


def test_is_pdf():
    assert pa.is_pdf(b"%PDF-1.7" + b"0" * 20000)
    assert not pa.is_pdf(b"<html>")


def test_rate_limiter(tmp_path):
    t = [0.0]
    slept = []
    rl = pa.RateLimiter(tmp_path / "s.json", daily_cap=2, clock=lambda: t[0], sleep=slept.append, today=lambda: "d1")
    rl.acquire(); t[0] = 2.0; rl.acquire()
    assert slept and 8.0 <= slept[0] <= 18.0
    with pytest.raises(RuntimeError):
        rl.acquire()
    rl2 = pa.RateLimiter(tmp_path / "s.json", daily_cap=2, sleep=slept.append, today=lambda: "d2")
    rl2.acquire()


def test_no_bypass_tooling_in_module():
    src = Path(pa.__file__).read_text().lower()
    for bad in ("flaresolverr", "stealth", "automationcontrolled", "navigator.webdriver"):
        assert bad not in src
