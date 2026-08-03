"""Unified local access outlets: campus relay, CARSI session cookies, local proxy.

CARSI is treated as the China-institution twin of campus relay:
- campus relay = remote egress through a campus host
- CARSI = local Shibboleth/federated SSO cookies for publisher domains

Both are opt-in. Cookies never leave the machine.
"""

from __future__ import annotations

import json
import locale
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import AccessOutletConfig, MdteroConfig, config_dir


def carsi_cookies_path() -> Path:
    override = os.environ.get("MDTERO_CARSI_COOKIES_PATH")
    if override:
        return Path(override).expanduser().resolve()
    return config_dir() / "carsi_cookies.json"


def suggest_carsi_locale() -> bool:
    """Soft locale hint only — never auto-enable from IP/geo."""
    locale_values = [
        str(os.environ.get("LC_ALL") or ""),
        str(os.environ.get("LC_MESSAGES") or ""),
        str(os.environ.get("LANG") or ""),
        str(locale.getdefaultlocale()[0] or ""),
    ]
    if any(
        "zh_cn" in lang.lower() or lang.lower().startswith("zh-cn") or lang.lower().startswith("zh_hans")
        for lang in locale_values
    ):
        return True
    tz = str(os.environ.get("TZ") or "").strip()
    if tz in {"Asia/Shanghai", "Asia/Chongqing", "Asia/Urumqi", "Asia/Harbin"}:
        return True
    try:
        # Local timezone name when TZ is unset.
        if time.tzname and any("china" in str(name).lower() for name in time.tzname):
            return True
    except Exception:
        pass
    return False


def load_carsi_cookies(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or carsi_cookies_path()
    if not target.exists():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict) and row.get("name") and row.get("value") is not None]
    if isinstance(payload, dict):
        cookies = payload.get("cookies")
        if isinstance(cookies, list):
            return [row for row in cookies if isinstance(row, dict) and row.get("name") and row.get("value") is not None]
    return []


def save_carsi_cookies(cookies: list[dict[str, Any]], path: Path | None = None) -> Path:
    target = path or carsi_cookies_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    cleaned = []
    for row in cookies:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        cleaned.append(
            {
                "name": name,
                "value": str(row.get("value") if row.get("value") is not None else ""),
                "domain": str(row.get("domain") or "").strip().lstrip("."),
                "path": str(row.get("path") or "/").strip() or "/",
            }
        )
    target.write_text(json.dumps({"cookies": cleaned, "updated_at": int(time.time())}, indent=2) + "\n", encoding="utf-8")
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return target


def clear_carsi_cookies(path: Path | None = None) -> None:
    target = path or carsi_cookies_path()
    if target.exists():
        target.unlink()


def import_carsi_cookies_file(source: Path, *, dest: Path | None = None) -> Path:
    payload = json.loads(Path(source).expanduser().read_text(encoding="utf-8"))
    if isinstance(payload, list):
        cookies = payload
    elif isinstance(payload, dict) and isinstance(payload.get("cookies"), list):
        cookies = payload["cookies"]
    else:
        raise ValueError("Cookie file must be a JSON list or {\"cookies\": [...]} object.")
    return save_carsi_cookies(cookies, path=dest)


def cookie_header_for_url(url: str, cookies: list[dict[str, Any]]) -> str | None:
    host = urlparse(str(url or "").strip()).hostname or ""
    host = host.lower()
    if not host or not cookies:
        return None
    parts: list[str] = []
    for row in cookies:
        domain = str(row.get("domain") or "").strip().lower().lstrip(".")
        if not domain:
            continue
        if host == domain or host.endswith("." + domain):
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            parts.append(f"{name}={row.get('value')}")
    if not parts:
        return None
    return "; ".join(parts)


def access_status(config: MdteroConfig, *, relay_connected: bool | None = None) -> dict[str, Any]:
    access = config.access if isinstance(getattr(config, "access", None), AccessOutletConfig) else AccessOutletConfig()
    cookies = load_carsi_cookies()
    carsi_ready = bool(access.carsi_enabled and cookies)
    outlets = [
        {
            "outlet": "campus_relay",
            "kind": "remote_campus_egress",
            "enabled": True,  # availability is account/server-side; local serve is opt-in
            "ready": bool(relay_connected),
            "detail": "online" if relay_connected else "offline / not running",
        },
        {
            "outlet": "carsi",
            "kind": "local_sso_cookies",
            "enabled": bool(access.carsi_enabled),
            "ready": carsi_ready,
            "institution": access.carsi_institution,
            "entity_id": access.carsi_entity_id,
            "cookie_count": len(cookies),
            "detail": (
                f"{len(cookies)} local cookies"
                if carsi_ready
                else (
                    "enabled but no local cookies; import with `mdtero access carsi import-cookies`"
                    if access.carsi_enabled
                    else ("suggested for zh_CN locale" if suggest_carsi_locale() else "opt-in institutional SSO")
                )
            ),
        },
        {
            "outlet": "local_proxy",
            "kind": "http_proxy",
            "enabled": bool(config.effective_proxy_url) or bool(config.campus_proxy_required),
            "ready": bool(config.effective_proxy_url),
            "detail": "configured" if config.effective_proxy_url else ("required" if config.campus_proxy_required else "optional"),
        },
    ]
    return {
        "outlets": outlets,
        "carsi_suggested": suggest_carsi_locale() and not access.carsi_enabled,
        "note": "CARSI is the local-cookie twin of campus relay; both stay on-device / opt-in.",
    }


def doctor_access_row(config: MdteroConfig, *, relay_connected: bool | None = None) -> tuple[str, str, str]:
    status = access_status(config, relay_connected=relay_connected)
    carsi = next((row for row in status["outlets"] if row["outlet"] == "carsi"), {})
    if carsi.get("ready"):
        state = "ready"
    elif carsi.get("enabled"):
        state = "enabled"
    elif status.get("carsi_suggested"):
        state = "suggested"
    else:
        state = "optional"
    detail_parts = [
        f"relay={'online' if relay_connected else 'offline'}",
        f"carsi={state}",
        f"proxy={'on' if config.effective_proxy_url else 'off'}",
    ]
    if status.get("carsi_suggested"):
        detail_parts.append("try `mdtero access carsi enable`")
    return ("Access outlets", state if state != "optional" else "optional", "; ".join(detail_parts))
