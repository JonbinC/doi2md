"""CLI ↔ browser-extension handoff helpers.

Boundary:
- CLI-only when the route can fetch via server or local curl_cffi.
- When a browser session is required, CLI never silent-fails: it returns a
  structured extension_handoff and can open the install + article URLs.
"""

from __future__ import annotations

import webbrowser
from typing import Any
from urllib.parse import quote

EXTENSION_CHROME_WEBSTORE_URL = (
    "https://chromewebstore.google.com/detail/mdtero/knpihhcooldgedbklgjghebijcpejibp"
)
EXTENSION_DEV_ZIP_URL = "https://mdtero.com/downloads/mdtero-extension-dev.zip"
EXTENSION_INSTALL_DOC_URL = "https://mdtero.com/docs/install"

BROWSER_HANDOFF_REASON_CODES = {
    "browser_extension_required",
    "client_acquisition_browser_session_required",
    "client_acquisition_challenge_page",
    "publisher_blocked_remote_pdf",
    "publisher_blocked_remote_content",
    "client_acquisition_no_candidate_url",
}


def classify_acquisition_path(route: dict[str, Any] | None) -> str:
    """Return cli_server | cli_local | extension_required."""
    payload = dict(route or {})
    actions = {str(action) for action in payload.get("action_sequence") or []}
    top = str(payload.get("top_connector") or "").strip()
    if (
        payload.get("requires_browser_capture")
        or "fetch_browser_source" in actions
        or top == "ieee_html_document"
    ):
        return "extension_required"
    if payload.get("requires_raw_upload"):
        return "cli_local"
    return "cli_server"


def reason_needs_extension_handoff(reason_code: str | None) -> bool:
    return str(reason_code or "").strip() in BROWSER_HANDOFF_REASON_CODES


def preferred_open_url(route: dict[str, Any] | None, input_value: str) -> str:
    payload = dict(route or {})
    for key in ("best_oa_url", "source_url"):
        value = str(payload.get(key) or "").strip()
        if value.startswith("http"):
            return value
    for candidate in payload.get("client_handoff_candidates") or []:
        if not isinstance(candidate, dict):
            continue
        for key in ("artifact_url", "source_url", "url"):
            value = str(candidate.get(key) or "").strip()
            if value.startswith("http"):
                return value
    for candidate in payload.get("acquisition_candidates") or []:
        if not isinstance(candidate, dict):
            continue
        value = str(candidate.get("url") or candidate.get("pdf_url") or candidate.get("html_url") or "").strip()
        if value.startswith("http"):
            return value
    raw = str(input_value or "").strip()
    if raw.startswith("http"):
        return raw
    if raw.lower().startswith("10."):
        return f"https://doi.org/{quote(raw)}"
    return ""


def build_extension_handoff(
    *,
    input_value: str,
    route: dict[str, Any] | None = None,
    reason_code: str | None = None,
    action_hint: str | None = None,
) -> dict[str, Any]:
    open_url = preferred_open_url(route, input_value)
    acquisition_path = classify_acquisition_path(route)
    if reason_needs_extension_handoff(reason_code):
        acquisition_path = "extension_required"
    hint = (
        action_hint
        or "Install the Mdtero browser extension, open the article while logged into your publisher/campus session, then Parse from the extension popup."
    )
    return {
        "status": "extension_required" if acquisition_path == "extension_required" else acquisition_path,
        "acquisition_path": acquisition_path,
        "reason_code": reason_code or ("browser_extension_required" if acquisition_path == "extension_required" else None),
        "action_hint": hint,
        "input": input_value,
        "open_url": open_url or None,
        "install_url": EXTENSION_CHROME_WEBSTORE_URL,
        "extension": {
            "chrome_webstore_url": EXTENSION_CHROME_WEBSTORE_URL,
            "dev_zip_url": EXTENSION_DEV_ZIP_URL,
            "install_doc_url": EXTENSION_INSTALL_DOC_URL,
        },
        "steps": [
            "Install the Mdtero extension from the Chrome Web Store (or load the dev zip for local testing).",
            "Sign in to Mdtero Account from the extension popup.",
            "Open the article URL in the same browser with your publisher/campus login.",
            "Click Parse in the extension popup (or upload a saved PDF/EPUB/HTML/XML).",
            "Return to CLI with `mdtero status <task-id> --json` or continue via dashboard/MCP.",
        ],
        "next_commands": [
            f"mdtero parse --file <saved-browser-artifact.pdf|epub|html|xml> --trace --wait --timeout 600 --json",
            "mdtero status <task-id> --wait --timeout 600 --json",
        ],
        "cli_file_upload_command": "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json",
    }


def open_extension_handoff(handoff: dict[str, Any], *, open_install: bool = True) -> list[str]:
    """Open install + article URLs in the default browser. Returns opened URLs."""
    opened: list[str] = []
    extension = handoff.get("extension") if isinstance(handoff.get("extension"), dict) else {}
    if open_install:
        install_url = str(extension.get("chrome_webstore_url") or EXTENSION_CHROME_WEBSTORE_URL).strip()
        if install_url:
            webbrowser.open(install_url)
            opened.append(install_url)
    open_url = str(handoff.get("open_url") or "").strip()
    if open_url:
        webbrowser.open(open_url)
        opened.append(open_url)
    return opened


def attach_extension_handoff(
    payload: dict[str, Any],
    *,
    input_value: str,
    route: dict[str, Any] | None = None,
    reason_code: str | None = None,
    action_hint: str | None = None,
    open_browser: bool = False,
) -> dict[str, Any]:
    handoff = build_extension_handoff(
        input_value=input_value,
        route=route,
        reason_code=reason_code or payload.get("reason_code"),
        action_hint=action_hint or payload.get("action_hint"),
    )
    payload = dict(payload)
    payload["extension_handoff"] = handoff
    payload.setdefault("action_hint", handoff["action_hint"])
    payload.setdefault("reason_code", handoff.get("reason_code") or payload.get("reason_code"))
    next_commands = [str(item).strip() for item in payload.get("next_commands") or [] if str(item).strip()]
    for command in handoff.get("next_commands") or []:
        if command not in next_commands:
            next_commands.append(str(command))
    payload["next_commands"] = next_commands
    if open_browser or payload.get("open_extension_handoff"):
        payload["opened_urls"] = open_extension_handoff(handoff)
    return payload
