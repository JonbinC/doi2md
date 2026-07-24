from __future__ import annotations

from mdtero.access_outlets import (
    access_status,
    cookie_header_for_url,
    import_carsi_cookies_file,
    load_carsi_cookies,
    suggest_carsi_locale,
)
from mdtero.config import AccessOutletConfig, MdteroConfig


def test_cookie_header_domain_match():
    header = cookie_header_for_url(
        "https://www.nature.com/articles/s41586-000",
        [{"name": "sid", "value": "1", "domain": "nature.com"}],
    )
    assert header == "sid=1"
    assert cookie_header_for_url("https://other.org/", [{"name": "sid", "value": "1", "domain": "nature.com"}]) is None


def test_access_status_carsi_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("MDTERO_CARSI_COOKIES_PATH", str(tmp_path / "carsi.json"))
    monkeypatch.delenv("LANG", raising=False)
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    cfg = MdteroConfig(access=AccessOutletConfig(carsi_enabled=False))
    status = access_status(cfg, relay_connected=False)
    carsi = next(row for row in status["outlets"] if row["outlet"] == "carsi")
    assert carsi["enabled"] is False
    assert carsi["ready"] is False


def test_import_cookies_enables_local_store(tmp_path, monkeypatch):
    monkeypatch.setenv("MDTERO_CARSI_COOKIES_PATH", str(tmp_path / "carsi.json"))
    source = tmp_path / "in.json"
    source.write_text('[{"name":"a","value":"b","domain":"wiley.com"}]', encoding="utf-8")
    path = import_carsi_cookies_file(source)
    assert path.exists()
    cookies = load_carsi_cookies()
    assert cookie_header_for_url("https://onlinelibrary.wiley.com/doi/pdf/10.1", cookies) == "a=b"


def test_suggest_carsi_locale_zh(monkeypatch):
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    assert suggest_carsi_locale() is True
