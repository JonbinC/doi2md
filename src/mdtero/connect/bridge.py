"""Loopback HTTP bridge for Mdtero Connect.

Binds only to 127.0.0.1 / ::1. Mutating calls require a CSRF token issued by
GET /connect/v1/session. The browser UI never receives the Mdtero API key.
"""

from __future__ import annotations

import json
import mimetypes
import socket
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from mdtero.client import MdteroApiError, MdteroClient
from mdtero.connect.library import LibraryClient
from mdtero.connect.providers import ProviderError, ProviderStore
from mdtero.connect.agent_runtime import AgentError, AgentRuntime
from mdtero.local_discovery import LocalDiscoveryError, search_local_discovery
from mdtero.connect.paths import app_static_dir
from mdtero.connect.relay_diag import diagnose_relay, probe_article_entitlement
from mdtero.connect.security import (
    assert_loopback_bind,
    csrf_matches,
    host_header_allowed,
    new_csrf_token,
    origin_allowed,
    reject_user_supplied_zotero_endpoint,
)
from mdtero.connect.zotero_local import (
    ZoteroLocalError,
    collection_items_preview,
    connector_status,
    items_to_import_payload,
    list_collections,
)


class _IPv6ThreadingHTTPServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6


class ConnectBridge:
    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        client: MdteroClient | None = None,
        static_dir: Path | None = None,
        full_mode: bool = False,
        providers: ProviderStore | None = None,
        agent_runtime: AgentRuntime | None = None,
    ) -> None:
        self.host = assert_loopback_bind(host)
        self.port = int(port)
        self.client = client or MdteroClient()
        self.library = LibraryClient(self.client)
        self.providers = providers or ProviderStore(config=self.client.config)
        self.agent_runtime = agent_runtime or AgentRuntime(full_mode=full_mode, providers=self.providers, library=self.library)
        self.static_dir = Path(static_dir) if static_dir else app_static_dir()
        self.csrf_token = new_csrf_token()
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        if self._httpd is None:
            raise RuntimeError("Connect bridge is not running")
        hostname = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{hostname}:{self._httpd.server_address[1]}"

    @property
    def bound_port(self) -> int:
        if self._httpd is None:
            raise RuntimeError("Connect bridge is not running")
        return int(self._httpd.server_address[1])

    def start(self) -> str:
        handler = _make_handler(self)
        server_type = _IPv6ThreadingHTTPServer if self.host == "::1" else ThreadingHTTPServer
        self._httpd = server_type((self.host, self.port), handler)
        # Refuse accidental non-loopback binds even if the constructor was bypassed.
        bound_host = self._httpd.server_address[0]
        assert_loopback_bind(str(bound_host))
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="mdtero-connect-bridge", daemon=True)
        self._thread.start()
        return self.base_url

    def stop(self) -> None:
        self.agent_runtime.close()
        self.providers.clear_session()
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def __enter__(self) -> "ConnectBridge":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


def _make_handler(bridge: ConnectBridge) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: object) -> None:  # noqa: A003
            # Avoid writing Authorization-bearing request lines to logs.
            return

        def do_OPTIONS(self) -> None:  # noqa: N802
            if not self._security_ok(require_csrf=False):
                return
            self.send_response(HTTPStatus.NO_CONTENT)
            self._cors_headers()
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            if path.startswith("/connect/v1/"):
                if not self._security_ok(require_csrf=False):
                    return
                self._dispatch_api("GET", path, parse_qs(parsed.query))
                return
            self._serve_static(path)

        def do_POST(self) -> None:  # noqa: N802
            # All early rejections leave the body unread. Close until the body
            # has been consumed so a keep-alive peer cannot reuse those bytes.
            close_after_body = self.close_connection
            self.close_connection = True
            parsed = urlparse(self.path)
            path = parsed.path
            if not path.startswith("/connect/v1/"):
                self._json(HTTPStatus.NOT_FOUND, {"reason_code": "not_found"})
                return
            if not self._security_ok(require_csrf=True):
                return
            # Reject ambiguous framing before reading the body. Close on an early
            # rejection so unread bytes cannot become another keep-alive request.
            lengths = self.headers.get_all("Content-Length") or []
            if self.headers.get("Transfer-Encoding") is not None or len(lengths) > 1:
                self._reject_body(HTTPStatus.BAD_REQUEST, "invalid_body_framing")
                return
            length_text = lengths[0].strip() if lengths else "0"
            if not length_text or not length_text.isascii() or not length_text.isdecimal():
                self._reject_body(HTTPStatus.BAD_REQUEST, "invalid_content_length")
                return
            # Compare the digit count first; Python limits huge integer strings.
            significant_length = length_text.lstrip("0") or "0"
            if len(significant_length) > 7:
                self._reject_body(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "body_too_large")
                return
            length = int(significant_length)
            if length > 2 * 1024 * 1024:
                self._reject_body(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "body_too_large")
                return
            raw = self.rfile.read(length) if length else b"{}"
            if length and len(raw) != length:
                self._reject_body(HTTPStatus.BAD_REQUEST, "incomplete_body")
                return
            self.close_connection = close_after_body
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._json(HTTPStatus.BAD_REQUEST, {"reason_code": "invalid_json"})
                return
            if not isinstance(body, dict):
                self._json(HTTPStatus.BAD_REQUEST, {"reason_code": "invalid_json_object"})
                return
            self._dispatch_api("POST", path, {}, body)

        def _reject_body(self, status: int, reason_code: str) -> None:
            self.close_connection = True
            self._json(status, {"reason_code": reason_code})

        def _security_ok(self, *, require_csrf: bool) -> bool:
            port = bridge.bound_port
            if not host_header_allowed(self.headers.get("Host"), port=port):
                self._json(HTTPStatus.FORBIDDEN, {"reason_code": "host_rejected"})
                return False
            origin = self.headers.get("Origin")
            if origin and not origin_allowed(origin, port=port):
                self._json(HTTPStatus.FORBIDDEN, {"reason_code": "origin_rejected"})
                return False
            # Same-origin navigations may omit Origin; require it for mutations.
            if require_csrf:
                if not origin:
                    self._json(HTTPStatus.FORBIDDEN, {"reason_code": "origin_required"})
                    return False
                token = self.headers.get("X-Mdtero-CSRF") or self.headers.get("x-mdtero-csrf")
                if not csrf_matches(bridge.csrf_token, token):
                    self._json(HTTPStatus.FORBIDDEN, {"reason_code": "csrf_rejected"})
                    return False
            return True

        def _dispatch_api(self, method: str, path: str, query: dict[str, list[str]], body: dict[str, Any] | None = None) -> None:
            body = body or {}
            try:
                if method == "GET" and path == "/connect/v1/session":
                    summary = bridge.library.session_summary()
                    agent_status = bridge.agent_runtime.status()
                    self._json(
                        HTTPStatus.OK,
                        {
                            **summary,
                            "csrf": bridge.csrf_token,
                            "bridge": {"host": bridge.host, "port": bridge.bound_port, "product": "mdtero-connect"},
                            "mode": "full" if agent_status.get("enabled") else "library",
                            "agent": agent_status,
                        },
                    )
                    return
                if method == "GET" and path == "/connect/v1/library/documents":
                    self._json(HTTPStatus.OK, bridge.library.list_documents())
                    return
                if method == "GET" and path == "/connect/v1/library/tags":
                    after = (query.get("after") or [""])[0]
                    limit = int((query.get("limit") or ["200"])[0])
                    self._json(HTTPStatus.OK, bridge.library.list_tags(after=after, limit=limit))
                    return
                if method == "GET" and path == "/connect/v1/library/tagged-documents":
                    tags = query.get("tag") or []
                    match = (query.get("match") or ["all"])[0]
                    if match not in {"all", "any"}:
                        self._json(HTTPStatus.BAD_REQUEST, {"reason_code": "invalid_match"})
                        return
                    self._json(HTTPStatus.OK, bridge.library.tagged_documents(tags, match=match))  # type: ignore[arg-type]
                    return
                if method == "POST" and path == "/connect/v1/library/tags/batch":
                    if "dry_run" not in body:
                        self._json(HTTPStatus.BAD_REQUEST, {"reason_code": "dry_run_required", "action_hint": "Send dry_run true for preview or false to apply."})
                        return
                    result = bridge.library.update_tags(
                        document_ids=list(body.get("document_ids") or []),
                        add=list(body.get("add") or []),
                        remove=list(body.get("remove") or []),
                        dry_run=bool(body.get("dry_run")),
                    )
                    self._json(HTTPStatus.OK, result)
                    return
                if method == "POST" and path == "/connect/v1/library/export":
                    exported = bridge.library.export_selection(
                        document_ids=list(body.get("document_ids") or []),
                        format=str(body.get("format") or "bibtex"),  # type: ignore[arg-type]
                    )
                    self._bytes(
                        HTTPStatus.OK,
                        exported["data"],
                        content_type=str(exported["media_type"]),
                        filename=str(exported["filename"]),
                        extra_headers={"X-Mdtero-Export": str(exported["export_label"])},
                    )
                    return
                if method == "GET" and path == "/connect/v1/relay/diagnostics":
                    self._json(HTTPStatus.OK, diagnose_relay(bridge.client))
                    return
                if method == "POST" and path == "/connect/v1/relay/entitlement-check":
                    self._json(
                        HTTPStatus.OK,
                        probe_article_entitlement(
                            bridge.client,
                            confirm_fulltext=bool(body.get("confirm_fulltext")),
                        ),
                    )
                    return
                if method == "GET" and path == "/connect/v1/zotero/status":
                    reject_user_supplied_zotero_endpoint(body.get("base_url") if body else None)
                    self._json(HTTPStatus.OK, connector_status())
                    return
                if method == "GET" and path == "/connect/v1/zotero/collections":
                    self._json(HTTPStatus.OK, list_collections())
                    return
                if method == "GET" and path.startswith("/connect/v1/zotero/collections/") and path.endswith("/items"):
                    key = path[len("/connect/v1/zotero/collections/") : -len("/items")]
                    self._json(HTTPStatus.OK, collection_items_preview(key))
                    return
                if method == "POST" and path == "/connect/v1/zotero/import":
                    # Metadata-only import through backend #43 import contract.
                    if "dry_run" not in body:
                        self._json(HTTPStatus.BAD_REQUEST, {"reason_code": "dry_run_required"})
                        return
                    items = body.get("items")
                    if not isinstance(items, list) or not items:
                        preview = collection_items_preview(str(body.get("collection_key") or ""))
                        items = [item.get("raw") or item for item in preview.get("items") or []]
                    content = items_to_import_payload([item for item in items if isinstance(item, dict)])
                    result = bridge.library.import_bibliography(
                        content=content,
                        format="zotero_json",
                        dry_run=bool(body["dry_run"]),
                        request_id=str(body["request_id"]) if body.get("request_id") else None,
                    )
                    self._json(HTTPStatus.OK, result)
                    return
                if method == "GET" and path == "/connect/v1/providers":
                    self._json(HTTPStatus.OK, bridge.providers.status())
                    return
                if method == "POST" and path == "/connect/v1/discovery/search":
                    query_text = body.get("query")
                    if not isinstance(query_text, str) or not 1 <= len(query_text.strip()) <= 500:
                        raise ValueError("Provide a search query of 1–500 characters.")
                    try:
                        result = search_local_discovery(
                            query_text.strip(), limit=8, page=1, providers="openalex", enrich="none",
                            openalex_api_key=bridge.providers.get_key("openalex"),
                            proxy_url=bridge.client.config.effective_proxy_url,
                        )
                    except LocalDiscoveryError:
                        self._json(HTTPStatus.BAD_GATEWAY, {"reason_code": "local_discovery_failed", "action_hint": "本机 OpenAlex 检索未成功。请检查网络、Key 或额度后重试；未转发到云端检索。"})
                        return
                    self._json(HTTPStatus.OK, result)
                    return
                if method == "POST" and path == "/connect/v1/providers/key":
                    self._json(HTTPStatus.OK, bridge.providers.set_key(body.get("provider"), body.get("key"), storage=body.get("storage", "session")))
                    return
                if method == "POST" and path == "/connect/v1/providers/clear":
                    self._json(HTTPStatus.OK, bridge.providers.clear_key(body.get("provider"), storage=body.get("storage", "session")))
                    return
                if method == "POST" and path == "/connect/v1/providers/check":
                    self._json(HTTPStatus.OK, bridge.providers.check(body.get("provider")))
                    return
                if method == "GET" and path == "/connect/v1/agent/status":
                    self._json(HTTPStatus.OK, bridge.agent_runtime.status())
                    return
                if method == "POST" and path == "/connect/v1/agent/prepare":
                    self._json(HTTPStatus.OK, bridge.agent_runtime.prepare(body))
                    return
                if method == "POST" and path == "/connect/v1/agent/runs":
                    if set(body) != {"approval_id"}:
                        raise ValueError("Start a reviewed plan using only its approval_id; prepare a new plan to change inputs.")
                    self._json(HTTPStatus.ACCEPTED, bridge.agent_runtime.start(body.get("approval_id")))
                    return
                if path.startswith("/connect/v1/agent/runs/"):
                    run_path = path.removeprefix("/connect/v1/agent/runs/")
                    if method == "GET" and "/" not in run_path:
                        self._json(HTTPStatus.OK, bridge.agent_runtime.get_run(run_path))
                        return
                    if method == "POST" and run_path.endswith("/cancel") and run_path.count("/") == 1:
                        self._json(HTTPStatus.OK, bridge.agent_runtime.cancel(run_path.removesuffix("/cancel")))
                        return
                self._json(HTTPStatus.NOT_FOUND, {"reason_code": "not_found"})
            except (ProviderError, AgentError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"reason_code": exc.reason_code, "action_hint": exc.hint})
            except ZoteroLocalError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"reason_code": exc.reason_code, "action_hint": str(exc)})
            except MdteroApiError as exc:
                status = int((exc.payload or {}).get("status_code") or HTTPStatus.BAD_GATEWAY)
                if status < 400 or status > 599:
                    status = HTTPStatus.BAD_GATEWAY
                self._json(status, exc.payload if isinstance(exc.payload, dict) else {"message": str(exc)})
            except ValueError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"reason_code": "invalid_request", "action_hint": str(exc)})
            except FileNotFoundError as exc:
                self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"reason_code": "ui_missing", "action_hint": str(exc)})
            except Exception as exc:  # pragma: no cover - defensive
                self._json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"reason_code": "bridge_error", "error_type": type(exc).__name__},
                )

        def _serve_static(self, path: str) -> None:
            relative = "index.html" if path in {"", "/"} else path.lstrip("/")
            if ".." in relative.split("/"):
                self._json(HTTPStatus.FORBIDDEN, {"reason_code": "path_rejected"})
                return
            target = (bridge.static_dir / relative).resolve()
            try:
                target.relative_to(bridge.static_dir.resolve())
            except ValueError:
                self._json(HTTPStatus.FORBIDDEN, {"reason_code": "path_rejected"})
                return
            if not target.is_file():
                self._json(HTTPStatus.NOT_FOUND, {"reason_code": "not_found"})
                return
            content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            data = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def _cors_headers(self) -> None:
            origin = self.headers.get("Origin")
            if origin and origin_allowed(origin, port=bridge.bound_port):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Mdtero-CSRF")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self._cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "private, no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if self.close_connection:
                self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)

        def _bytes(
            self,
            status: int,
            data: bytes,
            *,
            content_type: str,
            filename: str,
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self._cors_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Cache-Control", "private, no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for key, value in (extra_headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

    return Handler


def run_bridge(
    *,
    host: str = "127.0.0.1",
    port: int = 8741,
    open_browser: bool = True,
    forever: bool = True,
    full_mode: bool = False,
) -> ConnectBridge:
    bridge = ConnectBridge(host=host, port=port, full_mode=full_mode)
    url = bridge.start()
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    if forever:
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            bridge.stop()
    return bridge
