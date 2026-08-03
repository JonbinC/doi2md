"""Prepare the optional local access helper without exposing its internals.

The Python CLI remains the user-facing entry point.  On desktop installs this
module can fetch the small native Relay component and register it after the
user has authenticated.  Headless servers are deliberately left alone.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

from .config import MdteroConfig


RELAY_MANIFEST_URL = os.environ.get(
    "MDTERO_RELAY_MANIFEST_URL",
    "https://mdtero.com/releases/relay/manifest.json",
)
RELAY_BINARY_NAME = "mdtero-relay"


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _platform_key() -> str | None:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        arch = "amd64"
    elif machine in {"arm64", "aarch64"}:
        arch = "arm64"
    else:
        return None
    if system == "darwin":
        return f"darwin-{arch}"
    if system == "linux":
        return f"linux-{arch}"
    if system == "windows":
        return f"windows-{arch}"
    return None


def _desktop_environment() -> bool:
    if _truthy(os.environ.get("MDTERO_DISABLE_LOCAL_ACCESS")):
        return False
    if _truthy(os.environ.get("MDTERO_FORCE_LOCAL_ACCESS")):
        return True
    if _truthy(os.environ.get("MDTERO_HEADLESS")) or _truthy(os.environ.get("CI")):
        return False
    system = platform.system().lower()
    if system in {"darwin", "windows"}:
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _binary_candidates() -> list[Path]:
    candidates: list[Path] = []
    override = str(os.environ.get("MDTERO_RELAY_BINARY") or "").strip()
    if override:
        candidates.append(Path(override).expanduser())
    found = shutil.which(RELAY_BINARY_NAME)
    if found:
        candidates.append(Path(found))
    if platform.system().lower() == "windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / "Mdtero" / "bin" / "mdtero-relay.exe")
    else:
        candidates.append(Path.home() / ".local" / "bin" / RELAY_BINARY_NAME)
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = str(candidate.expanduser())
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(Path(resolved))
    return unique


def _relay_data_dir() -> Path:
    override = str(os.environ.get("MDTERO_RELAY_DATA_DIR") or "").strip()
    if override:
        return Path(override).expanduser()
    if platform.system().lower() == "windows":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(base) / "Mdtero" / "relay"
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / "mdtero-relay"


def _browser_candidates() -> list[str]:
    names: list[str] = []
    system = platform.system().lower()
    if system == "darwin":
        for path in (
            "/Applications/Google Chrome.app",
            "/Applications/Microsoft Edge.app",
            "/Applications/Chromium.app",
        ):
            if Path(path).exists():
                names.append(path)
    elif system == "windows":
        for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            root = os.environ.get(env_name)
            if not root:
                continue
            for relative in (
                "Google/Chrome/Application/chrome.exe",
                "Microsoft/Edge/Application/msedge.exe",
                "Chromium/Application/chrome.exe",
            ):
                path = Path(root) / relative
                if path.exists():
                    names.append(str(path))
    else:
        for name in ("google-chrome", "google-chrome-stable", "microsoft-edge", "chromium", "chromium-browser"):
            found = shutil.which(name)
            if found:
                names.append(found)
    return names


def local_access_status() -> dict[str, Any]:
    """Return a safe, non-secret local access capability summary."""

    binary = next((path for path in _binary_candidates() if path.is_file()), None)
    desktop = _desktop_environment()
    if _truthy(os.environ.get("MDTERO_DISABLE_LOCAL_ACCESS")):
        state = "disabled"
    elif not desktop:
        state = "not_applicable"
    else:
        state = "ready" if binary else "available"
    return {
        "status": state,
        "desktop": desktop,
        "platform": _platform_key(),
        "binary": str(binary) if binary else None,
        "browser_candidates": _browser_candidates(),
        "browser_extension_fallback": True,
        "action_hint": (
            "Local access helper is ready."
            if binary
            else ("The local access helper will be prepared after Mdtero sign-in." if desktop else "Server mode uses CLI/API routes." )
        ),
    }


def _safe_manifest() -> dict[str, Any]:
    request = urllib.request.Request(RELAY_MANIFEST_URL, headers={"User-Agent": "mdtero-cli-local-access"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("invalid local access release manifest")
    return payload


def _download_binary(manifest: dict[str, Any], target: Path) -> Path:
    key = _platform_key()
    if not key:
        raise RuntimeError("unsupported platform for local access helper")
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
    url = str(artifacts.get(key) or "").strip()
    if not url.startswith("https://"):
        raise RuntimeError("local access release has no secure platform artifact")
    checksums = manifest.get("sha256") if isinstance(manifest.get("sha256"), dict) else {}
    expected_hash = str(checksums.get(key) or "").strip().lower()
    with tempfile.TemporaryDirectory(prefix="mdtero-relay-") as temp_dir:
        archive_path = Path(temp_dir) / "relay.tgz"
        request = urllib.request.Request(url, headers={"User-Agent": "mdtero-cli-local-access"})
        with urllib.request.urlopen(request, timeout=120) as response, archive_path.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        if expected_hash:
            digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
            if digest != expected_hash:
                raise RuntimeError("local access release checksum mismatch")
        extract_root = Path(temp_dir) / "extract"
        extract_root.mkdir()
        with tarfile.open(archive_path, mode="r:gz") as archive:
            members = archive.getmembers()
            for member in members:
                destination = (extract_root / member.name).resolve()
                if not str(destination).startswith(str(extract_root.resolve()) + os.sep):
                    raise RuntimeError("local access release contains an unsafe path")
            archive.extractall(extract_root)
        binary_name = "mdtero-relay.exe" if platform.system().lower() == "windows" else RELAY_BINARY_NAME
        source = next((path for path in extract_root.rglob(binary_name) if path.is_file()), None)
        if source is None:
            raise RuntimeError("local access release did not contain its binary")
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_target = target.with_suffix(target.suffix + ".tmp")
        shutil.copy2(source, temp_target)
        if platform.system().lower() != "windows":
            temp_target.chmod(temp_target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        temp_target.replace(target)
        worker_source = extract_root / "browser_worker"
        if worker_source.is_dir() and (worker_source / "mdtero_browser_worker.py").is_file():
            worker_target = _relay_data_dir() / "browser_worker"
            if worker_target.exists():
                shutil.rmtree(worker_target)
            shutil.copytree(worker_source, worker_target)
            worker_target.chmod(0o700)
            for worker_file in worker_target.iterdir():
                if worker_file.is_file():
                    worker_file.chmod(0o600)
    return target


def _install_service(binary: Path, config: MdteroConfig) -> tuple[bool, str | None]:
    key = config.effective_api_key
    if not key:
        return False, "auth_required"
    environment = os.environ.copy()
    # The key travels through the child environment, never argv or printed output.
    environment["MDTERO_API_KEY"] = key
    environment["MDTERO_API_URL"] = config.api_base_url
    try:
        completed = subprocess.run(
            [str(binary), "install", "--browser=false"],
            env=environment,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False, "service_setup_failed"
    if completed.returncode != 0:
        return False, "service_setup_failed"
    return True, None


def ensure_local_access(config: MdteroConfig) -> dict[str, Any]:
    """Install and register the local helper when this is a desktop install."""

    status = local_access_status()
    if status["status"] in {"disabled", "not_applicable"}:
        return status
    if not status.get("desktop"):
        return status
    binary = Path(str(status.get("binary") or "")) if status.get("binary") else None
    try:
        if binary is None or not binary.is_file():
            binary = Path.home() / ("AppData/Local/Mdtero/bin/mdtero-relay.exe" if platform.system().lower() == "windows" else ".local/bin/mdtero-relay")
            binary = _download_binary(_safe_manifest(), binary)
        service_ready, reason = _install_service(binary, config)
    except Exception as exc:  # noqa: BLE001 - setup must remain usable if the helper is unavailable.
        status.update({"status": "unavailable", "reason_code": "local_access_prepare_failed", "error_type": type(exc).__name__})
        return status
    status["binary"] = str(binary)
    status["status"] = "ready" if service_ready else "installed"
    status["service"] = "ready" if service_ready else "not_configured"
    if reason:
        status["reason_code"] = reason
        status["action_hint"] = "Local access helper is installed; finish Mdtero sign-in to enable it." if reason == "auth_required" else "Local access helper could not start its background service."
    return status
