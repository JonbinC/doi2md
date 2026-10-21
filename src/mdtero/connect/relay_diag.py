"""Separate Relay transport, browser readiness, and per-article entitlement."""

from __future__ import annotations

from typing import Any

from mdtero.client import MdteroApiError, MdteroClient
from mdtero.local_access import local_access_status


def diagnose_relay(client: MdteroClient | None = None) -> dict[str, Any]:
    api = client or MdteroClient()
    local = local_access_status()
    cloud: dict[str, Any]
    try:
        cloud = api._request("GET", "/api/v1/relay/status")
    except MdteroApiError as exc:
        cloud = {
            "connected": False,
            "reason_code": (exc.payload or {}).get("reason_code") or "relay_status_failed",
            "action_hint": (exc.payload or {}).get("action_hint")
            or "Authenticate with `mdtero login` / `mdtero setup --api-key`, then retry.",
        }
    except Exception as exc:  # pragma: no cover - network edge
        cloud = {
            "connected": False,
            "reason_code": "relay_status_error",
            "error_type": type(exc).__name__,
        }

    connected = bool(cloud.get("connected"))
    capabilities = cloud.get("capabilities") if isinstance(cloud.get("capabilities"), list) else []
    browser_ready = "browser" in {str(item).lower() for item in capabilities} or bool(cloud.get("browser_ready"))
    return {
        "transport_online": connected,
        "browser_ready": bool(browser_ready),
        "article_entitlement": None,
        "local_access": {
            "status": local.get("status"),
            "binary": local.get("binary"),
            "platform": local.get("platform"),
            "action_hint": local.get("action_hint"),
        },
        "cloud_status": {
            "connected": connected,
            "reason_code": cloud.get("reason_code"),
            "action_hint": cloud.get("action_hint"),
            "capabilities": capabilities,
            "label": cloud.get("label") or cloud.get("device_label"),
            "egress_ip": _safe_egress(cloud),
        },
        "notes": [
            "transport_online means the campus Relay channel is registered; it is not a full-text entitlement.",
            "browser_ready means an authorized local browser profile can be used; institution passwords stay on-device.",
            "article_entitlement must be checked per DOI/URL; a prior paper check never transfers.",
        ],
    }


def probe_article_entitlement(client: MdteroClient, *, confirm_fulltext: bool = False) -> dict[str, Any]:
    """Optional closed-article probe via existing backend entitlement-check."""
    body = {"confirm_fulltext": bool(confirm_fulltext)}
    try:
        return client._request("POST", "/api/v1/relay/entitlement-check", json=body)
    except MdteroApiError as exc:
        return {
            "status": "failed",
            "reason_code": (exc.payload or {}).get("reason_code") or "entitlement_check_failed",
            "action_hint": (exc.payload or {}).get("action_hint") or str(exc),
        }


def _safe_egress(cloud: dict[str, Any]) -> str | None:
    outlet = cloud.get("outlet") if isinstance(cloud.get("outlet"), dict) else {}
    value = outlet.get("egress_ip") or cloud.get("egress_ip")
    text = str(value or "").strip()
    return text or None
