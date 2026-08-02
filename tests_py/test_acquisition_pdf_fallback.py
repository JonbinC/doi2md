from __future__ import annotations

from pathlib import Path

from mdtero.acquisition import AcquiredArtifact, AcquisitionError, acquire_from_route


def _artifact(url: str, kind: str = "pdf") -> AcquiredArtifact:
    return AcquiredArtifact(
        url=url,
        path=Path("/tmp/fake.pdf"),
        artifact_kind=kind,
        source="test",
        content_type="application/pdf" if kind == "pdf" else "text/html",
    )


def test_html_only_route_falls_back_to_pdf(monkeypatch):
    calls: list[str] = []

    def fake_curl(url: str, *, artifact_kind: str, timeout: float, extra_headers=None, config=None):
        calls.append(f"curl:{artifact_kind}:{url}")
        if artifact_kind == "html":
            raise AcquisitionError("client_acquisition_http_error", "403", diagnostics={"status_code": 403})
        return _artifact(url, "pdf")

    def fake_httpx(url: str, *, artifact_kind: str, timeout: float, extra_headers=None, config=None):
        calls.append(f"httpx:{artifact_kind}:{url}")
        raise AcquisitionError("client_acquisition_http_error", "403", diagnostics={"status_code": 403})

    monkeypatch.setattr("mdtero.acquisition._fetch_with_curl_cffi", fake_curl)
    monkeypatch.setattr("mdtero.acquisition._fetch_with_httpx", fake_httpx)

    route = {
        "route_kind": "best_oa_location_html",
        "action_sequence": ["fetch_html"],
        "acceptance_rules": {"allowed_artifact_kinds": ["html"]},
        "best_oa_url": "https://iopscience.iop.org/article/10.1088/example",
        "acquisition_candidates": [
            {"url": "https://iopscience.iop.org/article/10.1088/example", "html_url": "https://iopscience.iop.org/article/10.1088/example"},
            {"url": "https://iopscience.iop.org/article/10.1088/example/pdf", "pdf_url": "https://iopscience.iop.org/article/10.1088/example/pdf"},
        ],
    }
    artifact = acquire_from_route(route, "10.1088/example")
    assert artifact.artifact_kind == "pdf"
    assert any(call.startswith("curl:pdf:") for call in calls)
    assert any("html" in call for call in calls)


def test_pdf_candidate_preserves_explicit_kind_for_repository_landing():
    from mdtero.acquisition import _candidate_urls

    route = {
        "acquisition_candidates": [
            {
                "url": "https://research.example.edu/en/publications/example",
                "artifact_kind": "pdf",
            }
        ]
    }

    candidates = _candidate_urls(route, "10.1016/example")

    assert candidates == [
        {
            "url": "https://research.example.edu/en/publications/example",
            "artifact_kind": "pdf",
        }
    ]


def test_extract_pdf_url_from_repository_landing_page():
    from mdtero.acquisition import _extract_pdf_url_from_landing

    assert _extract_pdf_url_from_landing(
        b'<a href="/files/12345/article.pdf">Download PDF</a>',
        base_url="https://research.example.edu/en/publications/example",
    ) == "https://research.example.edu/files/12345/article.pdf"


def test_carsi_cookie_injected_when_enabled(monkeypatch, tmp_path):
    from mdtero.config import AccessOutletConfig, MdteroConfig
    from mdtero import access_outlets

    cookie_file = tmp_path / "carsi_cookies.json"
    monkeypatch.setenv("MDTERO_CARSI_COOKIES_PATH", str(cookie_file))
    access_outlets.save_carsi_cookies(
        [{"name": "session", "value": "abc", "domain": "example.com", "path": "/"}]
    )

    seen_headers: dict[str, str] = {}

    def fake_curl(url: str, *, artifact_kind: str, timeout: float, extra_headers=None, config=None):
        seen_headers.update(extra_headers or {})
        return _artifact(url, "pdf")

    monkeypatch.setattr("mdtero.acquisition._fetch_with_curl_cffi", fake_curl)
    monkeypatch.setattr(
        "mdtero.acquisition._fetch_with_httpx",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not fall through")),
    )

    cfg = MdteroConfig(access=AccessOutletConfig(carsi_enabled=True))
    route = {
        "acceptance_rules": {"allowed_artifact_kinds": ["pdf"]},
        "acquisition_candidates": [{"pdf_url": "https://pubs.example.com/article.pdf"}],
    }
    acquire_from_route(route, "https://pubs.example.com/article.pdf", config=cfg)
    assert seen_headers.get("Cookie") == "session=abc"
