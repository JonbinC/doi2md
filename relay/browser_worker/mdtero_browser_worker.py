#!/usr/bin/env python3
"""Loopback-only authorized browser capture worker for mdtero-relay.

This process deliberately owns a separate browser profile. The user signs into
their institution in that profile; this worker never exports browser cookies,
passwords, local storage, or screenshots. It only returns a validated HTML or
PDF artifact for an allowed publisher URL requested by the local Relay.
"""

from __future__ import annotations

import base64
import atexit
import hmac
import json
import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from html import unescape
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote, urljoin, urlparse

from playwright.sync_api import Error as PlaywrightError
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


def _configured_cdp_url() -> str:
    """Return only a loopback CDP endpoint from local worker configuration."""
    raw = os.environ.get("MDTERO_BROWSER_CDP_URL", "").strip()
    if not raw:
        config_path = Path(
            os.environ.get(
                "MDTERO_BROWSER_WORKER_CONFIG",
                str(Path.home() / ".config" / "mdtero-relay" / "browser-worker.json"),
            )
        ).expanduser()
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            raw = str(payload.get("cdp_url") or "").strip() if isinstance(payload, dict) else ""
        except (OSError, json.JSONDecodeError):
            raw = ""
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
        logging.warning("Ignoring non-loopback MDTERO_BROWSER_CDP_URL")
        return ""
    return raw.rstrip("/")


TOKEN = _configured_token()
CDP_URL = _configured_cdp_url()


def _default_profile_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Mdtero Access"
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "Mdtero Access"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "mdtero-relay" / "browser-profile"


PROFILE_DIR = Path(os.environ.get("MDTERO_BROWSER_PROFILE_DIR", str(_default_profile_dir()))).expanduser()


def _default_browser_executable() -> str:
    """Find a locally installed browser without assuming the host OS.

    An empty result is intentional: Playwright then uses its managed browser
    when the operator has installed it with ``playwright install chromium``.
    """
    if sys.platform == "darwin":
        mac_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if Path(mac_path).exists():
            return mac_path
    candidates = (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "chrome",
        "msedge",
    )
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return ""


CHROME_EXECUTABLE = os.environ.get("MDTERO_BROWSER_EXECUTABLE", "").strip() or _default_browser_executable()
_headless_override = os.environ.get("MDTERO_BROWSER_HEADLESS")
if _headless_override is None:
    # A server usually has no display; a desktop Linux session should remain
    # visible so the owner can complete an institution login or challenge.
    _has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    HEADLESS = sys.platform == "linux" and not _has_display
else:
    HEADLESS = _headless_override.strip().lower() in {"1", "true", "yes"}
MAX_ARTIFACT_BYTES = 30 * 1024 * 1024

ALLOWED_SUFFIXES = (
    "aacrjournals.org", "acm.org", "academic.oup.com", "ahajournals.org", "aiaa.org",
    "annualreviews.org", "arvojournals.org", "ashpublications.org", "asm.org", "asme.org",
    "aspetjournals.org", "atsjournals.org", "cambridge.org", "cancerbiomed.org", "cell.com",
    "degruyter.com", "degruyterbrill.com", "diabetesjournals.org", "dl.acm.org", "elsevier.com",
    "emerald.com", "frontiersin.org", "ieee.org", "ieeexplore.ieee.org", "ingentaconnect.com",
    "jci.org", "journals.aps.org", "journals.uchicago.edu", "jstage.jst.go.jp", "jstor.org",
    "karger.com", "liebertpub.com", "link.springer.com", "lww.com", "mdpi.com", "mdpi-res.com", "nature.com",
    "nejm.org", "onlinelibrary.wiley.com", "optica.org", "oup.com", "plos.org", "pnas.org",
    "pubs.acs.org", "pubs.rsc.org", "rupress.org", "sagepub.com", "science.org", "sciencedirect.com",
    "sciendo.com", "siam.org", "spandidos-publications.com", "springer.com", "tandfonline.com",
    "thieme-connect.com", "wiley.com", "worldscientific.com",
)
CHALLENGE_MARKERS = (
    "just a moment", "verify you are human", "checking if the site connection is secure",
    "cf-browser-verification", "challenge-platform", "captcha",
)
CHALLENGE_FRAME_MARKERS = (
    "challenges.cloudflare.com", "challenge-platform", "turnstile", "captcha",
    "recaptcha.net", "google.com/recaptcha",
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


def classify_frame_urls(urls: list[str]) -> Optional[str]:
    """Classify a visible challenge frame without reading its contents.

    Publisher challenges commonly isolate their UI in a cross-origin frame.
    The Relay only uses its URL as a page-state signal so it can foreground the
    tab for the account holder; it never queries a frame's DOM, clicks a
    control, or reads a challenge token.
    """
    for value in urls:
        lowered = str(value or "").lower()
        if any(marker in lowered for marker in CHALLENGE_FRAME_MARKERS):
            return "browser_challenge_required"
    return None


class BrowserWorker:
    def __init__(self) -> None:
        self._requests: queue.Queue[tuple[str, dict[str, Any], threading.Event, dict[str, Any]]] = queue.Queue()
        self._busy = threading.Lock()
        self._stopping = False
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._cdp_attached = False
        self._thread = threading.Thread(target=self._serve_requests, name="mdtero-authorized-browser", daemon=True)
        self._thread.start()

    def close(self) -> None:
        """Stop the executor after the active browser request finishes."""
        if self._stopping:
            return
        self._stopping = True
        completed = threading.Event()
        result: dict[str, Any] = {}
        self._requests.put(("close", {}, completed, result))
        completed.wait(timeout=5)

    def _close_session(self) -> None:
        if self._context is not None:
            if not self._cdp_attached:
                try:
                    self._context.close()
                except Exception:
                    pass
            self._context = None
            self._page = None
        # A CDP connection is intentionally detached by stopping Playwright;
        # it must never close the visible user-controlled Chrome process.
        self._browser = None
        self._cdp_attached = False
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    @property
    def session_active(self) -> bool:
        return self._context is not None

    def prepare(self, *, url: str, timeout_seconds: int) -> dict[str, Any]:
        """Open an approved publisher page for the user to authorize locally."""
        if not allowed_url(url):
            raise WorkerFailure("relay_url_domain_not_allowed", "URL is not an approved publisher HTTPS URL.")
        return self._submit("prepare", url=url, timeout_seconds=max(10, min(timeout_seconds, 120)))

    def fetch(self, *, recipe: str, url: str, timeout_seconds: int) -> dict[str, Any]:
        if recipe not in {"article_html", "article_pdf", "article_fulltext"}:
            raise WorkerFailure("browser_recipe_not_allowed", "Unsupported browser capture recipe.")
        if not allowed_url(url):
            raise WorkerFailure("relay_url_domain_not_allowed", "URL is not an approved publisher HTTPS URL.")
        return self._submit(
            "fetch",
            recipe=recipe,
            url=url,
            timeout_seconds=max(10, min(timeout_seconds, 120)),
        )

    def _submit(self, action: str, **payload: Any) -> dict[str, Any]:
        if self._stopping:
            raise WorkerFailure("browser_relay_stopping", "The authorized browser worker is stopping.")
        if not self._busy.acquire(blocking=False):
            raise WorkerFailure("browser_relay_busy", "The authorized browser is already acquiring another paper.")
        completed = threading.Event()
        result: dict[str, Any] = {}
        self._requests.put((action, payload, completed, result))
        if not completed.wait(timeout=float(payload["timeout_seconds"]) + 10):
            # The executor owns the lock while this timed-out request unwinds.
            # It releases it only after browser work has actually stopped.
            raise WorkerFailure("browser_fetch_timeout", "Authorized browser session timed out.")
        error = result.get("error")
        if isinstance(error, Exception):
            raise error
        value = result.get("value")
        if not isinstance(value, dict):
            raise WorkerFailure("browser_relay_failed", "Authorized browser worker returned no result.")
        return value

    def _serve_requests(self) -> None:
        """Keep every Playwright object on one thread, across requests."""
        while True:
            action, payload, completed, result = self._requests.get()
            try:
                if action == "close":
                    self._close_session()
                    result["value"] = {"status": "closed"}
                    return
                if action == "prepare":
                    result["value"] = self._prepare_locked(**payload)
                elif action == "fetch":
                    result["value"] = self._fetch_locked(**payload)
                else:
                    result["error"] = WorkerFailure("browser_request_invalid", "Unsupported browser operation.")
            except Exception as exc:
                result["error"] = exc
            finally:
                completed.set()
                if action != "close" and self._busy.locked():
                    self._busy.release()

    def _prepare_locked(self, *, url: str, timeout_seconds: int) -> dict[str, Any]:
        page = self._page_for_session()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
        except PlaywrightTimeoutError:
            # The visible page remains useful for an institution login or
            # publisher challenge that the user completes themselves.
            pass
        self._bring_page_to_front(page)
        return {"status": "ready", "url": page.url}

    def _fetch_locked(self, *, recipe: str, url: str, timeout_seconds: int) -> dict[str, Any]:
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout_seconds
        context = self._context_for_session()
        page = self._page_for_session()
        try:
            page.set_default_timeout(min(timeout_seconds, 90) * 1000)
            response = page.goto(url, wait_until="domcontentloaded", timeout=min(timeout_seconds, 90) * 1000)
            self._wait_for_access(page, deadline)
            final_url = page.url
            if not allowed_url(final_url):
                raise WorkerFailure("browser_final_url_not_allowed", "Browser ended outside the approved publisher domains.")
            if recipe == "article_html":
                body = self._sanitized_article_html(page).encode("utf-8")
                return self._artifact(status_code=response.status if response else 200, content_type="text/html; charset=utf-8", body=body)
            if recipe == "article_fulltext":
                try:
                    return self._pdf_artifact(context, page, final_url)
                except WorkerFailure as exc:
                    if exc.reason_code != "browser_pdf_not_available":
                        raise
                    # Keep PDF preference and HTML fallback in one bounded,
                    # user-visible browser operation. This prevents an
                    # intermittent relay reconnect from losing a readable
                    # article between two otherwise independent recipes.
                    return self._article_html_fallback_artifact(page, response)
            return self._pdf_artifact(context, page, final_url)
        except PlaywrightTimeoutError as exc:
            raise WorkerFailure("browser_fetch_timeout", "Authorized browser session timed out.") from exc

    def _context_for_session(self):
        if self._context is not None:
            return self._context
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        if CDP_URL:
            return self._attach_user_controlled_chrome()
        try:
            self._context = self._playwright.chromium.launch_persistent_context(
                str(PROFILE_DIR),
                executable_path=CHROME_EXECUTABLE or None,
                headless=HEADLESS,
                locale="en-GB",
                viewport={"width": 1440, "height": 1000},
                # Use ordinary Chrome behavior. Authentication and any publisher
                # challenge remain an explicit action in this user-owned profile.
                args=["--no-first-run", "--disable-popup-blocking"],
            )
        except PlaywrightError as exc:
            message = str(exc)
            try:
                self._playwright.stop()
            finally:
                self._playwright = None
            if "ProcessSingleton" in message or "profile directory" in message:
                raise WorkerFailure(
                    "browser_profile_in_use",
                    "Close the existing Mdtero Access Chrome window, then retry so the authorized worker can own that profile.",
                ) from exc
            raise
        return self._context

    def _attach_user_controlled_chrome(self):
        """Attach to the dedicated visible Chrome without launching it as automation.

        The CDP port is loopback-only and belongs to the Mdtero Access profile.
        We do not read, export, import, or inject browser session state; the
        user completes any login or challenge in that same visible browser.
        """
        assert self._playwright is not None
        attach_error: Exception | None = None
        for attempt in range(6):
            try:
                self._browser = self._playwright.chromium.connect_over_cdp(CDP_URL, timeout=10_000)
                contexts = self._browser.contexts
                if not contexts:
                    raise WorkerFailure("browser_cdp_unavailable", "Mdtero Access Chrome has no available browser context.")
                self._context = contexts[0]
                self._cdp_attached = True
                return self._context
            except (PlaywrightError, WorkerFailure) as exc:
                attach_error = exc
                if attempt == 0:
                    self._launch_user_controlled_chrome()
                time.sleep(2)
        try:
            self._playwright.stop()
        finally:
            self._playwright = None
            self._browser = None
        raise WorkerFailure(
            "browser_cdp_unavailable",
            "Could not connect to the local Mdtero Access Chrome browser. Close only that profile and retry.",
        ) from attach_error

    @staticmethod
    def _launch_user_controlled_chrome() -> None:
        if not CHROME_EXECUTABLE:
            raise WorkerFailure("browser_cdp_unavailable", "No Chrome executable is configured for the local CDP browser.")
        parsed = urlparse(CDP_URL)
        port = parsed.port or 9223
        try:
            subprocess.Popen(
                [
                    CHROME_EXECUTABLE,
                    f"--user-data-dir={PROFILE_DIR}",
                    "--remote-debugging-address=127.0.0.1",
                    f"--remote-debugging-port={port}",
                    "--no-first-run",
                    "--disable-popup-blocking",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise WorkerFailure("browser_cdp_unavailable", "Could not start the local Mdtero Access Chrome browser.") from exc

    def _page_for_session(self):
        context = self._context_for_session()
        if self._page is None or self._page.is_closed():
            self._page = context.pages[0] if context.pages else context.new_page()
        return self._page

    def _wait_for_access(self, page, deadline: float) -> None:
        last_shell: Optional[str] = None
        attention_requested = False
        while time.monotonic() < deadline:
            try:
                # A few publisher pages make one or more client-side redirects
                # immediately after DOMContentLoaded.  Re-read after that
                # navigation instead of turning a normal browser transition
                # into an opaque relay failure.  This does not inspect or act
                # on challenge controls.
                html = page.evaluate("document.documentElement.outerHTML")
                frame_urls = [frame.url for frame in page.frames]
            except PlaywrightError:
                # During a publisher redirect the previous execution context
                # can disappear between evaluate() and Playwright's own wait.
                # Sleep locally, then retry against the current page context.
                # This is not a challenge interaction.
                time.sleep(0.25)
                continue
            except Exception as exc:
                # Some Playwright releases surface this navigation race as an
                # implementation-layer Error rather than sync_api.Error. Do
                # not turn a normal redirect into an acquisition failure.
                if "execution context was destroyed" in str(exc).lower():
                    time.sleep(0.25)
                    continue
                raise
            shell = classify_shell(html) or classify_frame_urls(
                frame_urls
            )
            if shell is None:
                return
            last_shell = shell
            if not attention_requested:
                # The user, not automation, completes a publisher challenge or
                # institution login. Bringing the dedicated profile forward
                # makes that explicit without inspecting challenge controls or
                # session material.
                self._bring_page_to_front(page)
                attention_requested = True
            page.wait_for_timeout(1000)
        if last_shell == "browser_login_required":
            raise WorkerFailure(last_shell, "Institution login is required in the Mdtero Access browser profile.")
        raise WorkerFailure(last_shell or "browser_challenge_required", "Publisher challenge was not completed in the authorized browser profile.")

    @staticmethod
    def _bring_page_to_front(page) -> None:
        """Request attention for the user-owned tab; failure is non-fatal."""
        try:
            page.bring_to_front()
        except PlaywrightError:
            pass

    @staticmethod
    def _sanitized_article_html(page) -> str:
        """Return static article HTML without executable or session material."""
        result = page.evaluate(
            """() => {
                const root = document.documentElement.cloneNode(true);
                root.querySelectorAll('script,noscript,style,link,base,iframe,frame,object,embed,form,button,input,textarea,select,option').forEach((node) => node.remove());
                const safeMetaNames = new Set(['citation_title', 'citation_doi', 'citation_author', 'citation_journal_title', 'citation_publication_date', 'dc.title', 'dc.identifier', 'prism.doi']);
                root.querySelectorAll('meta').forEach((node) => {
                    const name = (node.getAttribute('name') || node.getAttribute('property') || '').toLowerCase();
                    if (!safeMetaNames.has(name)) node.remove();
                });
                const sensitiveName = /(?:token|auth|cookie|session|nonce|csrf|xsrf)/i;
                const urlName = /^(?:src|href|xlink:href|poster|action|data-src|data-href)$/i;
                for (const element of root.querySelectorAll('*')) {
                    for (const attribute of [...element.attributes]) {
                        const name = attribute.name;
                        if (/^on/i.test(name) || name.toLowerCase() === 'style' || sensitiveName.test(name)) {
                            element.removeAttribute(name);
                            continue;
                        }
                        if (/^(?:srcset|data-srcset)$/i.test(name)) {
                            element.removeAttribute(name);
                            continue;
                        }
                        if (urlName.test(name)) {
                            try {
                                const parsed = new URL(attribute.value, document.baseURI);
                                if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
                                    parsed.search = '';
                                    parsed.hash = '';
                                    element.setAttribute(name, parsed.href);
                                }
                            } catch (_) {
                                element.removeAttribute(name);
                            }
                        }
                    }
                }
                return '<!doctype html>\\n' + root.outerHTML;
            }"""
        )
        return str(result or "")

    def _article_html_fallback_artifact(self, page, response) -> dict[str, Any]:
        """Return HTML only when the browser has a real readable article.

        A missing PDF does not imply that every resulting browser page is safe
        to parse.  In particular, do not turn a publisher 429/403 response, a
        thin error page, or a login shell into an apparently successful HTML
        artifact.  The page has already passed the interaction-shell wait; this
        final artifact gate protects the PDF→HTML fallback itself.
        """
        status_code = int(response.status) if response is not None else 200
        if status_code == HTTPStatus.TOO_MANY_REQUESTS:
            raise WorkerFailure(
                "rate_limited",
                "Publisher rate limited the authorized browser request; wait briefly before retrying.",
            )
        if status_code >= HTTPStatus.BAD_REQUEST:
            raise WorkerFailure(
                "browser_article_unavailable",
                "Authorized browser page did not return a readable article.",
            )
        html = self._sanitized_article_html(page)
        if not text_looks_like_article(html):
            raise WorkerFailure(
                "browser_article_not_fulltext",
                "Authorized browser page did not contain a complete readable article.",
            )
        return self._artifact(
            status_code=status_code,
            content_type="text/html; charset=utf-8",
            body=html.encode("utf-8"),
        )

    def _pdf_artifact(self, context, page, article_url: str) -> dict[str, Any]:
        html = page.evaluate("document.documentElement.outerHTML")
        candidates: list[str] = [
            *_publisher_pdf_candidates(article_url),
            *_article_pdf_candidates(html, article_url),
        ]
        if "/pdf" in article_url.lower() or article_url.lower().endswith(".pdf"):
            candidates.insert(0, article_url)
        seen: set[str] = set()
        for raw_candidate in candidates:
            candidate = _normalise_pdf_candidate(raw_candidate, article_url)
            if not candidate:
                continue
            if not allowed_url(candidate):
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            # Playwright's request context shares this persistent profile's
            # cookies, but avoids Chrome's built-in PDF viewer navigation.
            try:
                response = context.request.get(candidate, headers={"Referer": article_url}, timeout=90_000)
                payload = response.body()
                content_type = str(response.headers.get("content-type") or "application/pdf").lower()
                if response.ok and payload.startswith(b"%PDF"):
                    return self._artifact(status_code=response.status, content_type=content_type, body=payload)
            except PlaywrightError:
                pass
            # Some publishers validate the browser's challenge state on their
            # PDF route. A fixed same-page fetch keeps that request inside the
            # already-authorized tab without exposing session data anywhere.
            page_pdf = self._pdf_from_authorized_page(page, candidate)
            if page_pdf is not None:
                status_code, page_content_type, page_payload = page_pdf
                if page_payload.startswith(b"%PDF"):
                    return self._artifact(
                        status_code=status_code,
                        content_type=page_content_type,
                        body=page_payload,
                    )
        raise WorkerFailure("browser_pdf_not_available", "Authorized page did not return a publisher PDF.")

    @staticmethod
    def _pdf_from_authorized_page(page, candidate: str) -> tuple[int, str, bytes] | None:
        try:
            result = page.evaluate(
                """async (url) => {
                    try {
                        const response = await fetch(url, { credentials: 'include', redirect: 'follow' });
                        const length = Number.parseInt(response.headers.get('content-length') || '0', 10);
                        if (Number.isFinite(length) && length > 30 * 1024 * 1024) {
                            return { status: response.status, contentType: response.headers.get('content-type') || '', tooLarge: true };
                        }
                        const bytes = new Uint8Array(await response.arrayBuffer());
                        let binary = '';
                        const chunkSize = 0x8000;
                        for (let offset = 0; offset < bytes.length; offset += chunkSize) {
                            binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
                        }
                        return {
                            status: response.status,
                            contentType: response.headers.get('content-type') || '',
                            bodyB64: btoa(binary),
                        };
                    } catch (_) {
                        return null;
                    }
                }""",
                candidate,
            )
            if not isinstance(result, dict) or result.get("tooLarge") or not isinstance(result.get("bodyB64"), str):
                return None
            return (
                int(result.get("status") or 0),
                str(result.get("contentType") or "application/pdf").lower(),
                base64.b64decode(result["bodyB64"], validate=True),
            )
        except (PlaywrightError, ValueError, TypeError):
            return None

    @staticmethod
    def _artifact(*, status_code: int, content_type: str, body: bytes) -> dict[str, Any]:
        if len(body) > MAX_ARTIFACT_BYTES:
            raise WorkerFailure("browser_artifact_too_large", "Browser artifact exceeds the 30 MiB relay limit.")
        return {
            "status_code": int(status_code),
            "headers": {"content-type": content_type},
            "body_b64": base64.b64encode(body).decode("ascii"),
        }


WORKER: BrowserWorker | None = None


def _ieee_arnumber(url: str) -> str:
    parsed = urlparse(url)
    if not (parsed.hostname or "").lower().endswith("ieeexplore.ieee.org"):
        return ""
    for pattern in (r"/document/(\d+)", r"[?&]arnumber=(\d+)"):
        match = re.search(pattern, url, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _article_doi(url: str) -> str:
    """Extract a DOI only from an approved publisher article URL.

    This deliberately does not inspect browser credentials or create arbitrary
    download URLs: it merely derives documented publisher PDF routes from the
    DOI already present in the requested article URL.
    """
    path = unquote(urlparse(url).path)
    match = re.search(r"/doi/(?:full/|abs/|epdf/)?(10\.\d{4,9}/[^?#]+)", path, flags=re.IGNORECASE)
    return match.group(1).rstrip("/") if match else ""


def _publisher_pdf_candidates(article_url: str) -> list[str]:
    """Return fixed, same-publisher PDF endpoints for supported journals.

    Each pattern is a publisher-native article representation rather than a
    generic proxy or a guessed third-party asset. The request context still
    carries only the user-owned browser session and success still requires the
    publisher to authorize the PDF.
    """
    parsed = urlparse(article_url)
    host = (parsed.hostname or "").lower()
    doi = _article_doi(article_url)
    candidates: list[str] = []
    if doi and (host == "onlinelibrary.wiley.com" or host.endswith(".wiley.com")):
        candidates.append(f"https://onlinelibrary.wiley.com/doi/pdfdirect/{doi}")
        candidates.append(f"https://onlinelibrary.wiley.com/doi/pdf/{doi}")
    elif doi and (host == "www.tandfonline.com" or host.endswith(".tandfonline.com")):
        candidates.append(f"https://www.tandfonline.com/doi/pdf/{doi}")
        candidates.append(f"https://www.tandfonline.com/doi/epdf/{doi}")
    elif doi and (host == "pubs.acs.org" or host.endswith(".acs.org")):
        candidates.append(f"https://pubs.acs.org/doi/pdf/{doi}")
        candidates.append(f"https://pubs.acs.org/doi/epdf/{doi}")
    elif host == "pubs.rsc.org":
        # RSC's landing pages often omit a conventional citation_pdf_url, but
        # expose the same article through this documented representation.
        match = re.search(
            r"/en/content/article(?:landing|html|pdf)/(\d{4})/([a-z]+)/([a-z0-9]+)",
            parsed.path,
            flags=re.IGNORECASE,
        )
        if match:
            year, journal, article_id = match.groups()
            candidates.append(
                f"https://pubs.rsc.org/en/content/articlepdf/{year}/{journal}/{article_id}"
            )
    elif host == "link.springer.com":
        # Springer article identifiers are normally their DOI suffix and its
        # PDF endpoint accepts the complete DOI path.
        springer_doi = doi
        if not springer_doi:
            match = re.search(r"/article/(10\.\d{4,9}/[^?#/]+)", unquote(parsed.path), flags=re.IGNORECASE)
            springer_doi = match.group(1) if match else ""
        if springer_doi:
            candidates.append(f"https://link.springer.com/content/pdf/{springer_doi}.pdf")
    elif host == "www.sciencedirect.com" or host.endswith(".sciencedirect.com"):
        # ScienceDirect's reader frequently renders the PDF action client-side
        # instead of advertising a citation_pdf_url in the initial document.
        # Its first-party PII representation stays on the already-authorized
        # publisher origin and is still accepted only after a real PDF check.
        match = re.search(r"/science/article/pii/(S[0-9A-Z]{8,})", parsed.path, flags=re.IGNORECASE)
        if match:
            pii = match.group(1).upper()
            candidates.append(
                f"https://www.sciencedirect.com/science/article/pii/{pii}/pdfft?isDTMRedir=true&download=true"
            )
    ieee_arnumber = _ieee_arnumber(article_url)
    if ieee_arnumber:
        candidates.append(
            "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=" + ieee_arnumber + "&ref="
        )
    return candidates


class _ArticlePdfLinkParser(HTMLParser):
    """Collect standard PDF representations from an already-authorized page.

    It intentionally ignores challenges, forms, iframes, and browser session
    state. The only input is the article document that the account holder can
    already view; the caller still enforces the publisher allowlist and checks
    that any response really is a PDF.
    """

    _VALUE_ATTRIBUTES = ("href", "data-pdf-url", "data-download-url", "data-url")

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.candidates: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        values = {str(key or "").lower(): str(value or "").strip() for key, value in attrs}
        if tag.lower() == "meta":
            name = values.get("name", "").lower()
            property_name = values.get("property", "").lower()
            if name in {"citation_pdf_url", "pdf_url"} or property_name == "citation_pdf_url":
                self._append(values.get("content", ""))
            return
        if tag.lower() == "link":
            rel = values.get("rel", "").lower()
            media_type = values.get("type", "").lower()
            if "pdf" in media_type or ("alternate" in rel and "pdf" in values.get("href", "").lower()):
                self._append(values.get("href", ""))
            return
        for attribute in self._VALUE_ATTRIBUTES:
            self._append_if_pdf_like(values.get(attribute, ""))

    def _append_if_pdf_like(self, value: str) -> None:
        lowered = value.lower()
        if any(marker in lowered for marker in (".pdf", "/pdf", "pdf?", "pdf/", "epdf", "stamppdf", "download")):
            self._append(value)

    def _append(self, value: str) -> None:
        candidate = str(value or "").strip()
        if candidate:
            self.candidates.append(candidate)


def _article_pdf_candidates(html: str, article_url: str) -> list[str]:
    """Return the page-advertised PDF endpoints, resolved against its URL."""
    parser = _ArticlePdfLinkParser()
    try:
        parser.feed(html)
        parser.close()
    except (ValueError, AssertionError):
        # Some publisher HTML is malformed. Fixed native endpoints remain a
        # fallback even if its HTML cannot be tokenized fully.
        pass
    candidates: list[str] = []
    seen: set[str] = set()
    for raw_candidate in parser.candidates:
        candidate = _normalise_pdf_candidate(raw_candidate, article_url)
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        candidates.append(candidate)
    return candidates


def _normalise_pdf_candidate(raw_candidate: str, article_url: str) -> str:
    """Resolve a page-advertised URL without accepting executable schemes."""
    candidate = unescape(str(raw_candidate or "")).strip()
    if not candidate or candidate.lower().startswith(("data:", "javascript:", "mailto:")):
        return ""
    return urljoin(article_url, candidate)


class Handler(BaseHTTPRequestHandler):
    server_version = "MdteroBrowserWorker/0.1"

    def do_GET(self) -> None:
        if self.path != "/health":
            self._write(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        self._write(HTTPStatus.OK, {"status": "ok", "session_active": bool(WORKER and WORKER.session_active)})

    def do_POST(self) -> None:
        if self.path not in {"/v1/fetch", "/v1/prepare"}:
            self._write(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        if not TOKEN or not hmac.compare_digest(self.headers.get("Authorization", "").removeprefix("Bearer ").strip(), TOKEN):
            self._write(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized", "reason_code": "browser_relay_unauthorized"})
            return
        try:
            if WORKER is None:
                raise WorkerFailure("browser_relay_starting", "Authorized browser worker is starting.")
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(min(length, 16 * 1024)).decode("utf-8"))
            if self.path == "/v1/prepare":
                result = WORKER.prepare(
                    url=str(payload.get("url") or ""),
                    timeout_seconds=int(payload.get("timeout") or 120),
                )
            else:
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
        except Exception as exc:
            logging.exception("Authorized browser worker failed: %s", type(exc).__name__)
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
    WORKER = BrowserWorker()
    atexit.register(WORKER.close)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
