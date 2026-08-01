#!/usr/bin/env python3
"""Loopback-only authorized browser capture worker for mdtero-relay.

This process deliberately owns a separate browser profile. The user signs into
their institution in that profile; this worker never exports browser cookies,
passwords, local storage, or screenshots. It only returns a validated HTML or
PDF artifact for an allowed publisher URL requested by the local Relay.
"""

from __future__ import annotations

import base64
import hmac
import json
import os
import re
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

HOST = "127.0.0.1"
PORT = int(os.environ.get("MDTERO_BROWSER_WORKER_PORT", "8788"))


def _configured_token() -> str:
    """Use an owner-readable local config so launchd never receives the secret."""
    token = os.environ.get("MDTERO_BROWSER_WORKER_TOKEN", "").strip()
    if token:
        return token
    config_path = Path(
        os.environ.get(
            "MDTERO_BROWSER_WORKER_CONFIG",
            str(Path.home() / ".config" / "mdtero-relay" / "browser-worker.json"),
        )
    ).expanduser()
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(payload.get("token") or "").strip() if isinstance(payload, dict) else ""


TOKEN = _configured_token()
PROFILE_DIR = Path(
    os.environ.get(
        "MDTERO_BROWSER_PROFILE_DIR",
        str(Path.home() / "Library" / "Application Support" / "Mdtero Access"),
    )
).expanduser()
CHROME_EXECUTABLE = os.environ.get(
    "MDTERO_BROWSER_EXECUTABLE",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
).strip()
HEADLESS = os.environ.get("MDTERO_BROWSER_HEADLESS", "false").strip().lower() in {"1", "true", "yes"}
MAX_ARTIFACT_BYTES = 30 * 1024 * 1024

ALLOWED_SUFFIXES = (
    "acm.org", "academic.oup.com", "cambridge.org", "cell.com", "dl.acm.org",
    "elsevier.com", "frontiersin.org", "ieee.org", "ieeexplore.ieee.org",
    "journals.aps.org", "link.springer.com", "mdpi.com", "nature.com",
    "onlinelibrary.wiley.com", "oup.com", "plos.org", "pnas.org", "pubs.acs.org",
    "pubs.rsc.org", "sagepub.com", "science.org", "sciencedirect.com", "springer.com",
    "tandfonline.com", "wiley.com",
)
CHALLENGE_MARKERS = (
    "just a moment", "verify you are human", "checking if the site connection is secure",
    "cf-browser-verification", "challenge-platform", "captcha",
)
LOGIN_MARKERS = (
    "institutional sign in", "login via your institution", "access through your institution",
    "your institution does not have access", "purchase a subscription to gain access",
)


class WorkerFailure(RuntimeError):
    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def allowed_url(value: str) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    return parsed.scheme == "https" and bool(host) and any(host == suffix or host.endswith(f".{suffix}") for suffix in ALLOWED_SUFFIXES)


def text_looks_like_article(html: str) -> bool:
    lowered = html.lower()
    return len(html) > 4_000 and any(marker in lowered for marker in ("citation_title", "<article", "article-body", "article__body", "fulltext"))


def classify_shell(html: str) -> Optional[str]:
    lowered = html.lower()
    if text_looks_like_article(html):
        return None
    if any(marker in lowered for marker in CHALLENGE_MARKERS):
        return "browser_challenge_required"
    if any(marker in lowered for marker in LOGIN_MARKERS):
        return "browser_login_required"
    return None


class BrowserWorker:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def fetch(self, *, recipe: str, url: str, timeout_seconds: int) -> dict[str, Any]:
        if recipe not in {"article_html", "article_pdf"}:
            raise WorkerFailure("browser_recipe_not_allowed", "Unsupported browser capture recipe.")
        if not allowed_url(url):
            raise WorkerFailure("relay_url_domain_not_allowed", "URL is not an approved publisher HTTPS URL.")
        if not self._lock.acquire(blocking=False):
            raise WorkerFailure("browser_relay_busy", "The authorized browser is already acquiring another paper.")
        try:
            return self._fetch_locked(recipe=recipe, url=url, timeout_seconds=max(10, min(timeout_seconds, 120)))
        finally:
            self._lock.release()

    def _fetch_locked(self, *, recipe: str, url: str, timeout_seconds: int) -> dict[str, Any]:
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout_seconds
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(PROFILE_DIR),
                executable_path=CHROME_EXECUTABLE or None,
                headless=HEADLESS,
                locale="en-GB",
                viewport={"width": 1440, "height": 1000},
                # Use ordinary Chrome behavior. Authentication and any publisher
                # challenge remain an explicit action in this user-owned profile.
                args=["--no-first-run", "--disable-popup-blocking"],
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(min(timeout_seconds, 90) * 1000)
                response = page.goto(url, wait_until="domcontentloaded", timeout=min(timeout_seconds, 90) * 1000)
                self._wait_for_access(page, deadline)
                final_url = page.url
                if not allowed_url(final_url):
                    raise WorkerFailure("browser_final_url_not_allowed", "Browser ended outside the approved publisher domains.")
                if recipe == "article_html":
                    body = page.evaluate("document.documentElement.outerHTML").encode("utf-8")
                    return self._artifact(status_code=response.status if response else 200, content_type="text/html; charset=utf-8", body=body)
                return self._pdf_artifact(context, page, final_url)
            except PlaywrightTimeoutError as exc:
                raise WorkerFailure("browser_fetch_timeout", "Authorized browser session timed out.") from exc
            finally:
                context.close()

    def _wait_for_access(self, page, deadline: float) -> None:
        last_shell: Optional[str] = None
        while time.monotonic() < deadline:
            html = page.evaluate("document.documentElement.outerHTML")
            shell = classify_shell(html)
            if shell is None:
                return
            last_shell = shell
            page.wait_for_timeout(1000)
        if last_shell == "browser_login_required":
            raise WorkerFailure(last_shell, "Institution login is required in the Mdtero Access browser profile.")
        raise WorkerFailure(last_shell or "browser_challenge_required", "Publisher challenge was not completed in the authorized browser profile.")

    def _pdf_artifact(self, context, page, article_url: str) -> dict[str, Any]:
        html = page.evaluate("document.documentElement.outerHTML")
        candidates: list[str] = []
        for pattern in (
            r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']citation_pdf_url["\']',
            r'<a[^>]+href=["\']([^"\']*(?:/pdf|\.pdf|stampPDF)[^"\']*)',
        ):
            candidates.extend(re.findall(pattern, html, flags=re.IGNORECASE))
        ieee_arnumber = _ieee_arnumber(article_url)
        if ieee_arnumber:
            candidates.append(
                "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=" + ieee_arnumber + "&ref="
            )
        if "/pdf" in article_url.lower() or article_url.lower().endswith(".pdf"):
            candidates.insert(0, article_url)
        for candidate in candidates:
            candidate = candidate.replace("&amp;", "&").strip()
            if candidate.startswith("/"):
                parsed = urlparse(article_url)
                candidate = f"{parsed.scheme}://{parsed.netloc}{candidate}"
            if not allowed_url(candidate):
                continue
            # Playwright's request context shares this persistent profile's
            # cookies, but avoids Chrome's built-in PDF viewer navigation.
            response = context.request.get(candidate, headers={"Referer": article_url}, timeout=90_000)
            payload = response.body()
            content_type = str(response.headers.get("content-type") or "application/pdf").lower()
            if response.ok and payload.startswith(b"%PDF"):
                return self._artifact(status_code=response.status, content_type=content_type, body=payload)
        raise WorkerFailure("browser_pdf_not_available", "Authorized page did not return a publisher PDF.")

    @staticmethod
    def _artifact(*, status_code: int, content_type: str, body: bytes) -> dict[str, Any]:
        if len(body) > MAX_ARTIFACT_BYTES:
            raise WorkerFailure("browser_artifact_too_large", "Browser artifact exceeds the 30 MiB relay limit.")
        return {
            "status_code": int(status_code),
            "headers": {"content-type": content_type},
            "body_b64": base64.b64encode(body).decode("ascii"),
        }


WORKER = BrowserWorker()


def _ieee_arnumber(url: str) -> str:
    parsed = urlparse(url)
    if not (parsed.hostname or "").lower().endswith("ieeexplore.ieee.org"):
        return ""
    for pattern in (r"/document/(\d+)", r"[?&]arnumber=(\d+)"):
        match = re.search(pattern, url, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


class Handler(BaseHTTPRequestHandler):
    server_version = "MdteroBrowserWorker/0.1"

    def do_GET(self) -> None:
        if self.path != "/health":
            self._write(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        self._write(HTTPStatus.OK, {"status": "ok"})

    def do_POST(self) -> None:
        if self.path != "/v1/fetch":
            self._write(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        if not TOKEN or not hmac.compare_digest(self.headers.get("Authorization", "").removeprefix("Bearer ").strip(), TOKEN):
            self._write(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized", "reason_code": "browser_relay_unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(min(length, 16 * 1024)).decode("utf-8"))
            result = WORKER.fetch(
                recipe=str(payload.get("recipe") or ""),
                url=str(payload.get("url") or ""),
                timeout_seconds=int(payload.get("timeout") or 90),
            )
            self._write(HTTPStatus.OK, result)
        except WorkerFailure as exc:
            self._write(HTTPStatus.BAD_GATEWAY, {"error": str(exc), "reason_code": exc.reason_code})
        except (ValueError, json.JSONDecodeError):
            self._write(HTTPStatus.BAD_REQUEST, {"error": "invalid request", "reason_code": "browser_request_invalid"})
        except Exception:
            self._write(HTTPStatus.BAD_GATEWAY, {"error": "browser worker failed", "reason_code": "browser_relay_failed"})

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _write(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("MDTERO_BROWSER_WORKER_TOKEN must be set")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
