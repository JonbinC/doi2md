"""Loopback-only Connect bridge security helpers."""

from __future__ import annotations

import hmac
import secrets
from typing import Iterable
from urllib.parse import urlsplit


LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
ZOTERO_LOCAL_HOST = "127.0.0.1"
ZOTERO_LOCAL_PORT = 23119
ZOTERO_LOCAL_BASE = f"http://{ZOTERO_LOCAL_HOST}:{ZOTERO_LOCAL_PORT}"


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_matches(expected: str | None, provided: str | None) -> bool:
    if not expected or not provided:
        return False
    return hmac.compare_digest(str(expected), str(provided))


def is_loopback_host(host: str | None) -> bool:
    cleaned = str(host or "").strip().lower()
    if not cleaned:
        return False
    # Strip IPv6 brackets and optional port.
    if cleaned.startswith("["):
        end = cleaned.find("]")
        cleaned = cleaned[1:end] if end > 1 else cleaned
    elif ":" in cleaned and cleaned.count(":") == 1:
        cleaned = cleaned.split(":", 1)[0]
    return cleaned in LOOPBACK_HOSTS


def origin_allowed(origin: str | None, *, port: int) -> bool:
    """Allow same-origin browser calls from the loopback Connect UI only."""
    if not origin:
        return False
    try:
        parts = urlsplit(origin)
        hostname = parts.hostname
        origin_port = parts.port
    except ValueError:
        return False
    if parts.scheme != "http" or parts.path not in {"", "/"} or parts.query or parts.fragment:
        return False
    if parts.username is not None or parts.password is not None or not is_loopback_host(hostname):
        return False
    return origin_port == int(port) or (origin_port is None and int(port) == 80)


def host_header_allowed(host: str | None, *, port: int) -> bool:
    cleaned = str(host or "").strip().lower()
    if not cleaned:
        return False
    if cleaned.startswith("["):
        # [::1]:port
        end = cleaned.find("]")
        if end < 0:
            return False
        hostname = cleaned[1:end]
        rest = cleaned[end + 1 :]
        if rest.startswith(":"):
            try:
                return hostname in LOOPBACK_HOSTS and int(rest[1:]) == int(port)
            except ValueError:
                return False
        return hostname in LOOPBACK_HOSTS and int(port) == 80
    if ":" in cleaned:
        hostname, _, port_text = cleaned.partition(":")
        try:
            return hostname in LOOPBACK_HOSTS and int(port_text) == int(port)
        except ValueError:
            return False
    return cleaned in LOOPBACK_HOSTS and int(port) == 80


def assert_loopback_bind(host: str) -> str:
    cleaned = str(host or "").strip().lower()
    if cleaned not in {"127.0.0.1", "::1"}:
        raise ValueError("Connect bridge must bind to 127.0.0.1 or ::1 only.")
    return cleaned


def approved_zotero_url(path: str = "/") -> str:
    """Return a fixed local Zotero connector URL. Callers cannot choose hosts."""
    suffix = path if str(path).startswith("/") else f"/{path}"
    # Block path traversal / scheme injection via the path argument.
    if "\\" in suffix or "://" in suffix or ".." in suffix.split("/"):
        raise ValueError("Invalid Zotero local path.")
    return f"{ZOTERO_LOCAL_BASE}{suffix}"


def reject_user_supplied_zotero_endpoint(value: str | None) -> None:
    """Refuse any caller-provided Zotero base URL to prevent SSRF/file proxies."""
    if value is not None and str(value).strip():
        raise ValueError("Zotero endpoint overrides are not accepted; Connect uses the approved loopback connector only.")


def redact_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for key, value in headers:
        lowered = key.lower()
        if lowered in {"authorization", "cookie", "x-api-key", "x-mdtero-csrf"}:
            redacted[key] = "[redacted]"
        else:
            redacted[key] = value
    return redacted
