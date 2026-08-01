import importlib.util
import sys
import types
import unittest
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


if __name__ == "__main__":
    unittest.main()
