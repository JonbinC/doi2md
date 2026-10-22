"""Connect full-text pipeline with a fake page and a fake parser (synthetic only)."""
import json

from mdtero.connect import fulltext as ft
from mdtero.connect import publisher_adapter as pa

DOI = "10.1007/s99999-026-00001-x"
BODY = "<p>" + "Synthetic sentence about nothing in particular. " * 120 + "</p>"
ARTICLE = (
    '<html><head><title>Synthetic</title></head><body><div class="c-article-body">'
    f'<h2>Intro</h2>{BODY}<h2>Methods</h2>{BODY}'
    f'<a href="/article/{DOI}/tables/1">Table 1</a><a href="/article/{DOI}/tables/2?x=1">Table 2</a>'
    f'<a href="/article/{DOI}/tables/1">dup</a><a href="/article/10.1007/other/tables/9">other</a>'
    "</div></body></html>"
)
OK = {"title": "Synthetic", "cf_iframe": False, "challenge_form": False, "body_chars": 9000}
CF = {"title": "Just a moment...", "cf_iframe": True, "challenge_form": False, "body_chars": 40}


class Page:
    def __init__(self, probes, html=ARTICLE):
        self.probes, self.html, self.url, self.gotos = list(probes), html, "", []

    def goto(self, url, **kw):
        self.gotos.append(url)
        self.url = url

    def wait_for_timeout(self, ms):
        pass

    def bring_to_front(self):
        pass

    def evaluate(self, js, arg=None):
        if js == ft.CHALLENGE_PROBE_JS:
            return self.probes.pop(0) if len(self.probes) > 1 else self.probes[0]
        if "outerHTML" in js:
            return self.html if "/tables/" not in self.url else f"<html><body>table page {self.url}</body></html>"
        return None

    def content(self):
        return self.html


def lim(tmp_path):
    return pa.RateLimiter(tmp_path / "rate.json", min_interval=0, max_interval=0, sleep=lambda s: None)


def fake_parser(calls, signals):
    def parse(payload, **kw):
        calls.append((payload, kw))
        return {"markdown": "# Synthetic\n", "metadata": {"title": "Synthetic"}, "signals": signals}
    return parse


def test_classify_probe_uses_dom_not_substrings():
    assert ft.classify_probe(CF) == "challenge"
    assert ft.classify_probe({**OK, "challenge_form": True}) == "challenge"
    assert ft.classify_probe({"title": "Just a moment...", "body_chars": 50}) == "challenge"
    # article that merely mentions cloudflare/recaptcha in its HTML is not a challenge
    assert ft.classify_probe(OK) is None
    assert ft.classify_probe({"content_type": "application/pdf", "cf_iframe": True}) is None


def test_verdict():
    assert ft.verdict({"body_length": 20000, "section_count": 6}, OK) == "fulltext"
    assert ft.verdict({"body_length": 900, "section_count": 1}, OK) == "paywall"
    assert ft.verdict({"body_length": 20000, "section_count": 6}, CF) == "challenge"


def test_springer_table_urls():
    urls = ft.springer_table_urls(ARTICLE, DOI)
    assert urls == {1: f"https://link.springer.com/article/{DOI}/tables/1",
                    2: f"https://link.springer.com/article/{DOI}/tables/2"}


def test_springer_routed():
    assert pa.route(DOI).key == "springer"
    assert pa.route("10.1186/s1").__class__ is type(None)  # OA stays on backend


def test_fulltext_springer_companions(tmp_path):
    calls, sleeps = [], []
    page = Page([OK])
    res = ft.fetch_fulltext(page, DOI, tmp_path, lim(tmp_path), sleep=sleeps.append,
                            parse=fake_parser(calls, {"body_length": 12000, "section_count": 4,
                                                      "companion_tables_merged": 1, "companion_tables_unmatched": 1}))
    assert res.status == "fulltext"
    assert page.gotos[0] == f"https://link.springer.com/article/{DOI}"
    assert page.gotos[1:] == [f"https://link.springer.com/article/{DOI}/tables/{n}" for n in (1, 2)]
    assert sleeps.count(15.0) == 2  # sequential, spaced
    payload, kw = calls[0]
    assert kw["publisher_hint"] == "springer" and kw["content_type"] == "text/html" and kw["doi"] == DOI
    assert sorted(kw["companion_pages"]) == [f"https://link.springer.com/article/{DOI}/tables/{n}" for n in (1, 2)]
    assert all(isinstance(v, bytes) for v in kw["companion_pages"].values())
    assert (tmp_path / "raw" / f"{res.raw_path.split('/')[-1]}").exists()
    assert (tmp_path / "raw" / "10.1007_s99999-026-00001-x.table2.html").exists()
    assert open(res.markdown_path).read() == "# Synthetic\n"
    saved = json.loads((tmp_path / "10.1007_s99999-026-00001-x.fulltext.json").read_text())
    assert saved["signals"]["companion_tables_unmatched"] == 1  # normal, not an error


def test_fulltext_paywall_reported(tmp_path):
    calls = []
    res = ft.fetch_fulltext(Page([OK], html="<html><body>abstract</body></html>"), "10.1080/0000.1", tmp_path,
                            lim(tmp_path), sleep=lambda s: None,
                            parse=fake_parser(calls, {"body_length": 700, "section_count": 0}))
    assert res.status == "paywall" and res.markdown_path is None and "not bypassed" in res.detail
    assert calls[0][1]["companion_pages"] is None


def test_challenge_handed_to_user_then_cleared(tmp_path):
    notes, calls = [], []
    page = Page([CF, CF, OK])
    res = ft.fetch_fulltext(page, "10.1080/0000.2", tmp_path, lim(tmp_path), sleep=lambda s: None,
                            notify=lambda k, u: notes.append(k),
                            parse=fake_parser(calls, {"body_length": 9000, "section_count": 3}))
    assert notes == ["challenge"] and res.handoffs == 1 and res.status == "fulltext"


def test_challenge_not_cleared_is_reported(tmp_path):
    t = iter(range(0, 10_000, 100))
    res = ft.fetch_fulltext(Page([CF]), "10.1080/0000.3", tmp_path, lim(tmp_path), sleep=lambda s: None,
                            clock=lambda: next(t), handoff_timeout_s=300,
                            parse=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not parse")))
    assert res.status == "challenge" and res.raw_path is None


def test_bridge_fulltext_job(tmp_path):
    import time as _t
    from mdtero.connect.bridge import ConnectBridge

    class C:  # minimal client stub
        pass

    br = ConnectBridge(client=C(), static_dir=tmp_path, fulltext_runner=lambda d: {"doi": d, "status": "paywall"})
    job = br.start_fulltext("https://doi.org/10.1080/0000.4")
    for _ in range(50):
        if br.fulltext_jobs[job["id"]]["state"] != "running":
            break
        _t.sleep(0.01)
    assert br.fulltext_jobs[job["id"]]["result"] == {"doi": "10.1080/0000.4", "status": "paywall"}
    try:
        br.start_fulltext("10.3390/oa")
        raise AssertionError("OA DOI should be rejected")
    except ValueError:
        pass


def test_parser_access_shell_error_is_paywall(tmp_path):
    class ClientParseError(ValueError):
        pass

    def parse(payload, **kw):
        raise ClientParseError("captured HTML is an access shell rather than article body")

    res = ft.fetch_fulltext(Page([OK], html="<html><body>buy</body></html>"), "10.1080/0000.5", tmp_path,
                            lim(tmp_path), sleep=lambda s: None, parse=parse)
    assert res.status == "paywall" and "not bypassed" in res.detail and res.markdown_path is None
