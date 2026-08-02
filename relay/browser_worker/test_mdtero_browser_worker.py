import base64
import importlib.util
import sys
import types
import unittest
from unittest import mock
from pathlib import Path


def _load_worker_module():
    # Candidate extraction is deliberately dependency-free. Stub Playwright so
    # this focused test also runs in the lightweight relay CI environment.
    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.Error = type("PlaywrightError", (Exception,), {})
    sync_api.TimeoutError = type("PlaywrightTimeoutError", (Exception,), {})
    sync_api.sync_playwright = lambda: None
    playwright = types.ModuleType("playwright")
    playwright.sync_api = sync_api
    sys.modules.setdefault("playwright", playwright)
    sys.modules.setdefault("playwright.sync_api", sync_api)
    path = Path(__file__).with_name("mdtero_browser_worker.py")
    spec = importlib.util.spec_from_file_location("mdtero_browser_worker_test_subject", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ArticlePdfCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worker = _load_worker_module()

    def test_collects_metadata_and_relative_download_link(self):
        candidates = self.worker._article_pdf_candidates(
            """
            <meta name='citation_pdf_url' content='/content/pdf/10.1000%2Fexample.pdf'>
            <link rel='alternate' type='application/pdf' href='https://link.springer.com/download/example.pdf'>
            <a data-download-url='/article/10.1000/example/download'>Download PDF</a>
            """,
            "https://link.springer.com/article/10.1000/example",
        )

        self.assertEqual(
            candidates,
            [
                "https://link.springer.com/content/pdf/10.1000%2Fexample.pdf",
                "https://link.springer.com/download/example.pdf",
                "https://link.springer.com/article/10.1000/example/download",
            ],
        )

    def test_rejects_script_and_data_url_candidates(self):
        candidates = self.worker._article_pdf_candidates(
            """
            <a href='javascript:window.open("paper.pdf")'>PDF</a>
            <a data-pdf-url='data:application/pdf;base64,AAAA'>PDF</a>
            <a href='/article/example.pdf'>PDF</a>
            """,
            "https://pubs.rsc.org/en/content/articlehtml/2026/xx/example",
        )

        self.assertEqual(candidates, ["https://pubs.rsc.org/article/example.pdf"])

    def test_fetch_boundary_stays_publisher_allowlisted(self):
        self.assertTrue(self.worker.allowed_url("https://pubs.acs.org/doi/pdf/10.1021/example"))
        self.assertFalse(self.worker.allowed_url("https://example.invalid/paper.pdf"))

    def test_derives_rsc_native_pdf_from_landing_page(self):
        self.assertEqual(
            self.worker._publisher_pdf_candidates(
                "https://pubs.rsc.org/en/content/articlelanding/2025/ra/d5ra09148a"
            ),
            ["https://pubs.rsc.org/en/content/articlepdf/2025/ra/d5ra09148a"],
        )

    def test_derives_sciencedirect_native_pdf_from_pii_landing_page(self):
        self.assertEqual(
            self.worker._publisher_pdf_candidates(
                "https://www.sciencedirect.com/science/article/pii/S036054422600294X"
            ),
            [
                "https://www.sciencedirect.com/science/article/pii/"
                "S036054422600294X/pdfft?isDTMRedir=true&download=true"
            ],
        )

    def test_classifies_challenge_frame_without_inspecting_its_document(self):
        self.assertEqual(
            self.worker.classify_frame_urls(
                [
                    "https://link.springer.com/article/10.1000/example",
                    "https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/g/turnstile/if/ov2/av0/rcv/0",
                ]
            ),
            "browser_challenge_required",
        )
        self.assertIsNone(
            self.worker.classify_frame_urls(
                ["https://link.springer.com/article/10.1000/example"]
            )
        )

    def test_sanitized_article_html_preserves_static_article_payload(self):
        class Page:
            script = ""

            def evaluate(self, script):
                self.script = script
                return "<!doctype html>\n<html><head><meta name='citation_title' content='Demo'></head><body><article>Text</article></body></html>"

        page = Page()
        html = self.worker.BrowserWorker._sanitized_article_html(page)

        self.assertIn("citation_title", html)
        self.assertIn("<article>", html)
        self.assertIn("script,noscript,style,link,base,iframe", page.script)
        self.assertIn("sensitiveName", page.script)
        self.assertIn("safeMetaNames", page.script)
        self.assertIn("srcset|data-srcset", page.script)

    def test_fetch_accepts_single_fulltext_recipe(self):
        worker = object.__new__(self.worker.BrowserWorker)
        worker._stopping = False
        with mock.patch.object(worker, "_submit", return_value={"status_code": 200}) as submit:
            worker.fetch(
                recipe="article_fulltext",
                url="https://onlinelibrary.wiley.com/doi/full/10.1002/demo",
                timeout_seconds=30,
            )

        self.assertEqual(submit.call_args.args[0], "fetch")
        self.assertEqual(submit.call_args.kwargs["recipe"], "article_fulltext")

    def test_fulltext_html_fallback_rejects_rate_limited_page(self):
        worker = object.__new__(self.worker.BrowserWorker)
        response = types.SimpleNamespace(status=429)

        with self.assertRaisesRegex(self.worker.WorkerFailure, "rate limited") as raised:
            worker._article_html_fallback_artifact(object(), response)

        self.assertEqual(raised.exception.reason_code, "rate_limited")

    def test_fulltext_html_fallback_requires_complete_article(self):
        worker = object.__new__(self.worker.BrowserWorker)
        response = types.SimpleNamespace(status=200)
        with mock.patch.object(worker, "_sanitized_article_html", return_value="<html><body>short</body></html>"):
            with self.assertRaisesRegex(self.worker.WorkerFailure, "complete readable article") as raised:
                worker._article_html_fallback_artifact(object(), response)

        self.assertEqual(raised.exception.reason_code, "browser_article_not_fulltext")

    def test_fulltext_html_fallback_returns_sanitized_complete_article(self):
        worker = object.__new__(self.worker.BrowserWorker)
        response = types.SimpleNamespace(status=200)
        html = "<html><head><meta name='citation_title' content='Demo'></head><body><article>" + ("Full text. " * 500) + "</article></body></html>"
        with mock.patch.object(worker, "_sanitized_article_html", return_value=html):
            artifact = worker._article_html_fallback_artifact(object(), response)

        self.assertEqual(artifact["status_code"], 200)
        self.assertEqual(artifact["headers"]["content-type"], "text/html; charset=utf-8")
        self.assertIn(b"Full text", base64.b64decode(artifact["body_b64"]))

    def test_wait_for_access_retries_destroyed_navigation_context(self):
        class Page:
            def __init__(self, error_type):
                self.error_type = error_type
                self.attempts = 0

            def evaluate(self, _script):
                self.attempts += 1
                if self.attempts == 1:
                    raise self.error_type("navigation")
                return "<html><article><p>Article</p></article></html>"

            @property
            def frames(self):
                return []

        page = Page(self.worker.PlaywrightError)
        worker = object.__new__(self.worker.BrowserWorker)
        with mock.patch.object(self.worker.time, "sleep"):
            worker._wait_for_access(page, self.worker.time.monotonic() + 1)
        self.assertEqual(page.attempts, 2)

    def test_wait_for_access_tolerates_implementation_layer_navigation_error(self):
        class ImplementationNavigationError(Exception):
            pass

        class Page:
            def __init__(self):
                self.attempts = 0

            def evaluate(self, _script):
                self.attempts += 1
                if self.attempts == 1:
                    raise ImplementationNavigationError("Execution context was destroyed during navigation")
                return "<html><article><p>Article</p></article></html>"

            @property
            def frames(self):
                return []

        page = Page()
        worker = object.__new__(self.worker.BrowserWorker)
        with mock.patch.object(self.worker.time, "sleep"):
            worker._wait_for_access(page, self.worker.time.monotonic() + 1)
        self.assertEqual(page.attempts, 2)


if __name__ == "__main__":
    unittest.main()
