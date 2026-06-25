from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlunparse

import httpx


CAMPUS_PROXY_CHECK_URL = "https://ifconfig.co/json"
SUPPORTED_PROXY_SCHEMES = frozenset({"http", "https", "socks4", "socks4a", "socks5", "socks5h"})


@dataclass(frozen=True)
class ProxySettings:
    proxy_url: str | None = None
    require_campus_proxy: bool = False

    @property
    def httpx_kwargs(self) -> dict[str, Any]:
        return {"proxy": self.proxy_url} if self.proxy_url else {}


class ProxyValidationError(RuntimeError):
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        super().__init__(str(payload.get("action_hint") or payload.get("reason_code") or "proxy validation failed"))


def normalize_proxy_url(raw: str | None) -> str | None:
    cleaned = str(raw or "").strip()
    if not cleaned:
        return None
    parsed = httpx.URL(cleaned)
    scheme = str(parsed.scheme or "").strip().lower()
    host = str(parsed.host or "").strip()
    if scheme not in SUPPORTED_PROXY_SCHEMES:
        raise ProxyValidationError(
            _proxy_failure_payload(
                "proxy_scheme_unsupported",
                action_hint=f"Use one of {', '.join(sorted(SUPPORTED_PROXY_SCHEMES))} for the proxy URL.",
                detail={"scheme": scheme or None},
            )
        )
    if not host:
        raise ProxyValidationError(
            _proxy_failure_payload(
                "proxy_url_invalid",
                action_hint="Proxy URL must include a host, for example socks5h://127.0.0.1:1080.",
            )
        )
    port = parsed.port
    if port is None:
        port = 443 if scheme == "https" else 1080 if scheme.startswith("socks") else 80
    userinfo = ""
    if parsed.username:
        password = parsed.password or ""
        userinfo = f"{parsed.username}:{password}@" if password else f"{parsed.username}@"
    normalized = urlunparse((scheme, f"{userinfo}{host}:{port}", "", "", "", ""))
    return normalized


def proxy_settings_from_config(config: Any | None) -> ProxySettings:
    if config is None:
        return ProxySettings()
    raw_proxy_url = str(getattr(config, "effective_proxy_url", None) or "").strip() or None
    proxy_url = None
    if raw_proxy_url:
        try:
            proxy_url = normalize_proxy_url(raw_proxy_url)
        except ProxyValidationError:
            proxy_url = raw_proxy_url
    require_campus_proxy = bool(getattr(config, "campus_proxy_required", False))
    return ProxySettings(proxy_url=proxy_url, require_campus_proxy=require_campus_proxy)


def assert_required_campus_proxy(settings: ProxySettings, *, timeout: float = 20.0, client_factory: Any | None = None) -> dict[str, Any] | None:
    if not settings.require_campus_proxy:
        return None
    if not settings.proxy_url:
        raise ProxyValidationError(_proxy_failure_payload("campus_proxy_missing", action_hint="MDTERO_REQUIRE_CAMPUS_PROXY is set, but no MDTERO_PROXY_URL/proxy_url is configured."))
    factory = client_factory or httpx.Client
    try:
        with factory(timeout=timeout, follow_redirects=True, **settings.httpx_kwargs) as client:
            response = client.get(CAMPUS_PROXY_CHECK_URL)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        raise ProxyValidationError(
            _proxy_failure_payload(
                "campus_proxy_check_failed",
                action_hint="Mdtero could not verify the required campus proxy outlet; stop paper acquisition and check the proxy URL.",
                detail={"error_type": exc.__class__.__name__, "message": str(exc)},
            )
        ) from exc
    if not _is_expected_campus_outlet(payload):
        raise ProxyValidationError(
            _proxy_failure_payload(
                "campus_proxy_outlet_mismatch",
                action_hint="Campus proxy outlet is not AS786/Jisc/Nottingham; stop paper acquisition before retrying.",
                detail=_proxy_public_summary(payload),
            )
        )
    return _proxy_public_summary(payload)


def _is_expected_campus_outlet(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    asn = str(payload.get("asn") or "").upper()
    org = str(payload.get("asn_org") or payload.get("org") or "").lower()
    city = str(payload.get("city") or "").lower()
    return asn == "AS786" and "jisc" in org and city == "nottingham"


def _proxy_public_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"raw_type": payload.__class__.__name__}
    return {
        "ip": payload.get("ip"),
        "asn": payload.get("asn"),
        "asn_org": payload.get("asn_org") or payload.get("org"),
        "city": payload.get("city"),
        "country": payload.get("country"),
    }


def _proxy_failure_payload(reason_code: str, *, action_hint: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "failed",
        "error_code": reason_code,
        "reason_code": reason_code,
        "action_hint": action_hint,
        "next_commands": [
            "curl --socks5-hostname <host:port> https://ifconfig.co/json",
            "MDTERO_PROXY_URL=socks5h://<host:port> MDTERO_REQUIRE_CAMPUS_PROXY=1 mdtero doctor --json",
        ],
    }
    if detail is not None:
        payload["detail"] = detail
    return payload
