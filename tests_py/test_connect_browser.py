from pathlib import Path

import pytest

from mdtero.connect import browser as cb


def test_chrome_command_is_plain():
    cmd = cb.chrome_command("/usr/bin/google-chrome", port=9222, profile_dir=Path("/p"), proxy="http://127.0.0.1:1")
    assert cmd[0] == "/usr/bin/google-chrome"
    assert "--remote-debugging-port=9222" in cmd and "--remote-debugging-address=127.0.0.1" in cmd
    assert "--user-data-dir=/p" in cmd and "--proxy-server=http://127.0.0.1:1" in cmd
    joined = " ".join(cmd).lower()
    for bad in ("automationcontrolled", "enable-automation", "headless", "user-agent", "disable-blink-features",
                "stealth", "flaresolverr"):
        assert bad not in joined


def test_no_proxy_flag_by_default():
    assert not any(a.startswith("--proxy-server") for a in cb.chrome_command("c", port=1, profile_dir=Path("/p")))


def test_default_mode_is_cdp(monkeypatch):
    monkeypatch.delenv(cb.MODE_ENV, raising=False)
    assert cb.ConnectBrowser().mode == "cdp"
    monkeypatch.setenv(cb.MODE_ENV, "playwright")
    assert cb.ConnectBrowser().mode == "playwright"


def test_find_chrome_env_override(monkeypatch):
    monkeypatch.setenv("MDTERO_CHROME", "/opt/chrome")
    assert cb.find_chrome() == "/opt/chrome"


def test_ensure_chrome_reuses_running(monkeypatch):
    monkeypatch.setattr(cb, "cdp_endpoint", lambda port, timeout=1.0: {"Browser": "Chrome/155"})
    monkeypatch.setattr(cb.subprocess, "Popen", lambda *a, **k: pytest.fail("must not launch"))
    assert cb.ensure_chrome(port=9222)["reused"] is True


def test_ensure_chrome_launches_then_waits(monkeypatch, tmp_path):
    calls, state = [], {"up": False}
    monkeypatch.setattr(cb, "cdp_endpoint", lambda port, timeout=1.0: {"Browser": "Chrome/155"} if state["up"] else None)

    def popen(cmd, **kw):
        calls.append(cmd)
        state["up"] = True
    monkeypatch.setattr(cb.subprocess, "Popen", popen)
    r = cb.ensure_chrome(port=9333, profile_dir=tmp_path / "prof", executable="/x/chrome", proxy=None)
    assert r["reused"] is False and calls[0][0] == "/x/chrome" and (tmp_path / "prof").is_dir()
    assert "shell" not in calls[0]


def test_ensure_chrome_missing(monkeypatch):
    monkeypatch.setattr(cb, "cdp_endpoint", lambda port, timeout=1.0: None)
    monkeypatch.setattr(cb, "find_chrome", lambda: None)
    with pytest.raises(RuntimeError, match="Chrome not found"):
        cb.ensure_chrome(port=9444)


def test_cdp_url_must_be_loopback():
    assert cb.validate_cdp_url("http://127.0.0.1:9222")
    assert not cb.validate_cdp_url("http://192.168.1.5:9222")


def test_chrome_for_testing_detection():
    assert cb.is_chrome_for_testing({"User-Agent": "HeadlessChrome/156"})
    assert not cb.is_chrome_for_testing({"Browser": "Chrome/155.0.8059.84"})


def test_module_has_no_stealth():
    src = Path(cb.__file__).read_text().lower()
    for bad in ("navigator.webdriver", "automationcontrolled", "add_init_script", "flaresolverr"):
        assert bad not in src
