"""Browser session for Connect fetches.

Default mode ("cdp"): start (or reuse) the user's ordinary installed Google
Chrome as a plain process with a loopback-only ``--remote-debugging-port``,
then attach with ``chromium.connect_over_cdp``. The browser is exactly what
the user runs every day: no automation flags, no stealth patches, no
fingerprint changes. Challenges are cleared by the person at the window.

Fallback ("playwright", opt-in): Playwright-launched Chromium. Some publishers
keep re-challenging that build, so it is only for tests/CI.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

DEFAULT_PORT = 9222
MODE_ENV = "MDTERO_CONNECT_BROWSER"  # "cdp" (default) | "playwright"


def default_profile_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    if platform.system() == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    return base / "mdtero" / "connect-chrome-profile"


def find_chrome() -> Optional[str]:
    """Locate the user's normal Google Chrome (not Chrome for Testing)."""
    env = os.environ.get("MDTERO_CHROME")
    if env:
        return env
    if platform.system() == "Darwin":
        for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome")):
            if Path(p).exists():
                return p
        return None
    if platform.system() == "Windows":
        for root in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
            if root:
                p = Path(root) / "Google/Chrome/Application/chrome.exe"
                if p.exists():
                    return str(p)
        return None
    for name in ("google-chrome-stable", "google-chrome", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    return None


def chrome_command(executable: str, *, port: int, profile_dir: Path,
                   proxy: Optional[str] = None, start_url: str = "about:blank") -> list[str]:
    """Plain Chrome command line: debugging port + profile (+ optional proxy). Nothing else."""
    cmd = [
        executable,
        f"--user-data-dir={profile_dir}",
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={int(port)}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if proxy:
        cmd.append(f"--proxy-server={proxy}")
    cmd.append(start_url)
    return cmd


def cdp_endpoint(port: int, timeout: float = 1.0) -> Optional[dict]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{int(port)}/json/version", timeout=timeout) as r:  # noqa: S310 - loopback
            return json.loads(r.read().decode())
    except Exception:  # noqa: BLE001
        return None


def is_chrome_for_testing(version_info: Optional[dict]) -> bool:
    ua = json.dumps(version_info or {}).lower()
    return "headless" in ua or "chrome for testing" in ua


def ensure_chrome(*, port: int = DEFAULT_PORT, profile_dir: Optional[Path] = None,
                  proxy: Optional[str] = None, executable: Optional[str] = None,
                  wait_s: float = 20.0, env: Optional[dict] = None) -> dict:
    """Reuse a Chrome already listening on ``port`` or start the user's Chrome."""
    info = cdp_endpoint(port)
    if info:
        return {"reused": True, "version": info}
    exe = executable or find_chrome()
    if not exe:
        raise RuntimeError("Google Chrome not found; install it or set MDTERO_CHROME")
    profile = Path(profile_dir or default_profile_dir())
    profile.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        chrome_command(exe, port=port, profile_dir=profile, proxy=proxy),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        env={**os.environ, **(env or {})},
    )
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        info = cdp_endpoint(port)
        if info:
            return {"reused": False, "version": info}
        time.sleep(0.25)
    raise RuntimeError(f"Chrome did not open a debugging port on 127.0.0.1:{port}")


@dataclass
class ConnectBrowser:
    """Context manager returning (context, page) for fetch_article."""
    mode: str = field(default_factory=lambda: os.environ.get(MODE_ENV, "cdp"))
    port: int = DEFAULT_PORT
    profile_dir: Optional[Path] = None
    proxy: Optional[str] = None
    launch: bool = True  # cdp mode: start Chrome if not running

    def __enter__(self):
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
        self._pw = sync_playwright().start()
        self._owned = None
        if self.mode == "cdp":
            if self.launch:
                ensure_chrome(port=self.port, profile_dir=self.profile_dir, proxy=self.proxy)
            self.browser = self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}", timeout=15_000)
            # The user's real (default) context carries their cookies/logins.
            self.context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
        elif self.mode == "playwright":
            kwargs = {"headless": False}
            if self.proxy:
                kwargs["proxy"] = {"server": self.proxy}
            self.browser = self._pw.chromium.launch(**kwargs)
            self._owned = self.browser
            self.context = self.browser.new_context(accept_downloads=True)
        else:
            raise ValueError(f"unknown browser mode {self.mode!r}")
        self.page = self.context.new_page()
        return self.context, self.page

    def __exit__(self, *exc):
        try:
            self.page.close()  # only our tab; never close the user's Chrome
        except Exception:  # noqa: BLE001
            pass
        if self._owned is not None:
            self._owned.close()
        self._pw.stop()
        return False


def validate_cdp_url(url: str) -> bool:
    """Only loopback CDP endpoints are acceptable."""
    p = urlparse(url)
    return p.scheme in ("http", "ws") and p.hostname in ("127.0.0.1", "localhost", "::1")
