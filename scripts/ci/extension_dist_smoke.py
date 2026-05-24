from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
EXTENSION_ROOT = REPO_ROOT / "extension"
DIST_ROOT = EXTENSION_ROOT / "dist"

REQUIRED_DIST_FILES = (
    "manifest.json",
    "background.js",
    "content.js",
    "popup.html",
    "popup.js",
    "options.html",
    "options.js",
    "styles.css",
    "assets/icon-16.png",
    "assets/icon-32.png",
    "assets/icon-48.png",
    "assets/icon-128.png",
)

FORBIDDEN_DIST_MARKERS = (
    "fetch_helper_source",
    "nativeMessaging",
    "connectNative",
    "initializeBrowserBridge",
    "mdtero.bridge.status",
    "parse-helper-bundle",
    "mdtero-install",
    "npx mdtero",
    "npm install -g",
    "elsevierApiKey",
    "wileyTdmToken",
    "springerOpenAccessApiKey",
)

POPUP_REQUIRED_MARKERS = (
    "Website OAuth",
    "Parse / Upload",
    "Translate",
    "Download",
    "local-file-input",
    "copy-cli-handoff",
    "/api/v1/tasks/translate",
    "/api/v1/tasks/upload",
    "/download/",
)

OPTIONS_REQUIRED_MARKERS = (
    "Website sign-in",
    "Connection guide",
    "Website OAuth is connected",
    "browser capture, upload, translation, and download settings",
)


def run_smoke(dist_root: Path = DIST_ROOT) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    for relative in REQUIRED_DIST_FILES:
        path = dist_root / relative
        if not path.exists():
            failures.append({"path": relative, "reason_code": "extension_dist_file_missing"})

    manifest = _read_manifest(dist_root / "manifest.json", failures)
    if manifest:
        _check_manifest(manifest, failures)

    text_files = [path for path in dist_root.rglob("*") if path.is_file() and path.suffix.lower() in {".js", ".html", ".css", ".json"}]
    combined = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in text_files)
    for marker in FORBIDDEN_DIST_MARKERS:
        if marker in combined:
            failures.append({"marker": marker, "reason_code": "extension_forbidden_marker_present"})

    _check_required_markers(dist_root, "popup", [dist_root / "popup.html", dist_root / "popup.js"], POPUP_REQUIRED_MARKERS, failures)
    _check_required_markers(dist_root, "options", [dist_root / "options.html", dist_root / "options.js"], OPTIONS_REQUIRED_MARKERS, failures)

    payload: dict[str, Any] = {
        "status": "failed" if failures else "succeeded",
        "reason_code": "extension_dist_smoke_failed" if failures else "extension_dist_smoke_succeeded",
        "dist_root": str(dist_root),
        "checked_files": len(REQUIRED_DIST_FILES),
        "failure_count": len(failures),
        "failures": failures,
        "action_hint": (
            "Rebuild the extension with `npm --prefix extension run build`, then rerun the public release gate."
            if failures
            else "Extension dist smoke completed."
        ),
        "next_commands": [
            "npm --prefix extension run build",
            "python3 scripts/ci/extension_dist_smoke.py",
        ],
    }
    return payload


def _read_manifest(path: Path, failures: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        failures.append({"path": "manifest.json", "reason_code": "extension_manifest_invalid_json", "message": str(exc)})
        return None
    return payload if isinstance(payload, dict) else None


def _check_manifest(manifest: dict[str, Any], failures: list[dict[str, Any]]) -> None:
    if manifest.get("manifest_version") != 3:
        failures.append({"path": "manifest.json", "reason_code": "extension_manifest_not_mv3"})
    permissions = manifest.get("permissions") or []
    if permissions != ["storage", "downloads", "tabs"]:
        failures.append({"path": "manifest.json", "reason_code": "extension_permissions_drifted", "permissions": permissions})
    if "nativeMessaging" in permissions:
        failures.append({"path": "manifest.json", "reason_code": "extension_native_messaging_present"})
    if manifest.get("background", {}).get("service_worker") != "background.js":
        failures.append({"path": "manifest.json", "reason_code": "extension_background_entry_missing"})
    if manifest.get("action", {}).get("default_popup") != "popup.html":
        failures.append({"path": "manifest.json", "reason_code": "extension_popup_entry_missing"})
    if manifest.get("options_page") != "options.html":
        failures.append({"path": "manifest.json", "reason_code": "extension_options_entry_missing"})
    content_scripts = manifest.get("content_scripts") or []
    if not any("https://mdtero.com/*" in (script.get("matches") or []) for script in content_scripts if isinstance(script, dict)):
        failures.append({"path": "manifest.json", "reason_code": "extension_auth_bridge_match_missing"})
    host_permissions = manifest.get("host_permissions") or []
    for forbidden in ("https://api.elsevier.com/*", "https://api.wiley.com/*", "https://api.springernature.com/*"):
        if forbidden in host_permissions:
            failures.append({"path": "manifest.json", "reason_code": "extension_direct_publisher_api_host_present", "host": forbidden})


def _check_required_markers(dist_root: Path, surface: str, paths: list[Path], markers: tuple[str, ...], failures: list[dict[str, Any]]) -> None:
    text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in paths if path.exists())
    for marker in markers:
        if marker not in text:
            failures.append({"surface": surface, "marker": marker, "reason_code": "extension_required_marker_missing"})


def main() -> int:
    payload = run_smoke()
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["status"] == "succeeded" else 1


if __name__ == "__main__":
    sys.exit(main())
