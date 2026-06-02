from __future__ import annotations

import json
import secrets
import threading
import urllib.parse
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass
class WebLoginResult:
    api_key: str
    prefix: str | None = None


def build_cli_login_url(site_base_url: str, *, callback_url: str, state: str) -> str:
    params = urllib.parse.urlencode({"cli_callback": callback_url, "cli_state": state})
    return f"{site_base_url.rstrip('/')}/auth?{params}"


def run_web_login(site_base_url: str, *, timeout_seconds: float = 180.0, open_browser: Any = webbrowser.open) -> WebLoginResult:
    state = secrets.token_urlsafe(24)
    event = threading.Event()
    result: dict[str, Any] = {}
    server = _CallbackServer(("127.0.0.1", 0), _make_callback_handler(state, event, result))
    callback_url = f"http://127.0.0.1:{server.server_port}/callback"
    url = build_cli_login_url(site_base_url, callback_url=callback_url, state=state)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        open_browser(url)
        if not event.wait(timeout_seconds):
            raise TimeoutError("Timed out waiting for Mdtero web login callback.")
        if result.get("error"):
            raise RuntimeError(str(result["error"]))
        api_key = str(result.get("api_key") or "").strip()
        if not api_key:
            raise RuntimeError("Mdtero web login callback did not include an API key.")
        return WebLoginResult(api_key=api_key, prefix=str(result.get("prefix") or "").strip() or None)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1.0)


class _CallbackServer(ThreadingHTTPServer):
    allow_reuse_address = True


def _make_callback_handler(expected_state: str, event: threading.Event, result: dict[str, Any]):
    class CallbackHandler(BaseHTTPRequestHandler):
        def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib handler API
            if urllib.parse.urlparse(self.path).path != "/callback":
                self._send_json(404, {"ok": False, "error": "not_found"})
                return
            self.send_response(204)
            self._send_cors_headers()
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            if urllib.parse.urlparse(self.path).path != "/callback":
                self._send_json(404, {"ok": False, "error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length") or "0")
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            except Exception:
                self._send_json(400, {"ok": False, "error": "invalid_json"})
                return
            if payload.get("state") != expected_state:
                result["error"] = "invalid_cli_state"
                event.set()
                self._send_json(403, {"ok": False, "error": "invalid_cli_state"})
                return
            result["api_key"] = payload.get("apiKey") or payload.get("api_key")
            result["prefix"] = payload.get("prefix")
            event.set()
            self._send_json(200, {"ok": True})

        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(body)

        def _send_cors_headers(self) -> None:
            origin = str(self.headers.get("Origin") or "").strip()
            if origin in {"https://mdtero.com", "http://localhost:5173", "http://127.0.0.1:5173"}:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")

    return CallbackHandler
