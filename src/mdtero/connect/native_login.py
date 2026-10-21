"""Desktop login using the existing CLI callback/state and account contracts."""

from __future__ import annotations

import os
import subprocess
import sys
import threading

from mdtero.auth import WebLoginCancelled, run_web_login
from mdtero.client import MdteroClient
from mdtero.config import load_config, save_config


class NativeLoginError(ValueError):
    def __init__(self, reason_code: str, hint: str) -> None:
        super().__init__(hint)
        self.reason_code = reason_code
        self.hint = hint


def _open_browser(url: str) -> None:
    # Use the OS's browser handler. A BROWSER override must not execute an
    # arbitrary PATH command or print the callback/state into the stdio protocol.
    try:
        if sys.platform == "win32":
            os.startfile(url)  # type: ignore[attr-defined]
            return
        executable = "/usr/bin/open" if sys.platform == "darwin" else "/usr/bin/xdg-open"
        env = {key: value for key, value in os.environ.items() if key != "BROWSER"}
        env["PATH"] = os.defpath
        subprocess.Popen([executable, url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, env=env, start_new_session=True)
    except OSError:
        raise NativeLoginError("native_login_browser_unavailable", "Connect could not open your system browser. Check the default browser and try login again.") from None


def login_account(stopped: threading.Event, *, timeout_seconds: float = 180.0) -> None:
    """Verify before saving, just like CLI login; return no credential data."""
    cfg = load_config()
    try:
        result = run_web_login(cfg.site_base_url, timeout_seconds=timeout_seconds,
                               open_browser=_open_browser, cancel_event=stopped)
    except WebLoginCancelled:
        raise NativeLoginError("native_login_cancelled", "Account login was cancelled.") from None
    except TimeoutError:
        raise NativeLoginError("native_login_timeout", "Account login timed out. Choose Login again to restart the browser flow.") from None
    except NativeLoginError:
        raise
    except Exception:
        raise NativeLoginError("native_login_failed", "Account login could not complete. Choose Login again and retry the browser flow.") from None
    if stopped.is_set():
        raise NativeLoginError("native_login_cancelled", "Account login was cancelled.")
    cfg.api_key = result.api_key
    try:
        # Reuse the same authenticated endpoint used by CLI login. Keep this
        # request bounded and never expose upstream error bodies or account data.
        MdteroClient(config=cfg, timeout=3.0).usage()
        if stopped.is_set():
            raise NativeLoginError("native_login_cancelled", "Account login was cancelled.")
        save_config(cfg)
    except NativeLoginError:
        raise
    except Exception:
        raise NativeLoginError("native_login_verification_failed", "The account key could not be verified and saved. Check connectivity and try Login again.") from None
    finally:
        cfg.api_key = None
        result.api_key = ""
