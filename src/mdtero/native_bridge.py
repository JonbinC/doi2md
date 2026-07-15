"""Install/diagnose the Chrome native-messaging host and enqueue capture jobs."""

from __future__ import annotations

import json
import os
import shutil
import sys
import webbrowser
from pathlib import Path
from typing import Any

from .native_host import (
    enqueue_capture_job,
    jobs_dir,
    read_job,
    wait_for_job,
)
from .native_messaging_constants import DEV_EXTENSION_ID, DEV_EXTENSION_PUBLIC_KEY, NATIVE_HOST_NAME


def host_launcher_path() -> Path:
    return Path(config_native_dir()) / "mdtero-native-host"


def host_manifest_name() -> str:
    return f"{NATIVE_HOST_NAME}.json"


def config_native_dir() -> Path:
    from .config import config_dir

    path = config_dir() / "native-host"
    path.mkdir(parents=True, exist_ok=True)
    return path


def chrome_native_messaging_dirs() -> list[Path]:
    home = Path.home()
    dirs: list[Path] = []
    if sys.platform == "darwin":
        dirs.extend(
            [
                home / "Library/Application Support/Google/Chrome/NativeMessagingHosts",
                home / "Library/Application Support/Chromium/NativeMessagingHosts",
                home / "Library/Application Support/Microsoft Edge/NativeMessagingHosts",
            ]
        )
    elif sys.platform.startswith("linux"):
        dirs.extend(
            [
                home / ".config/google-chrome/NativeMessagingHosts",
                home / ".config/chromium/NativeMessagingHosts",
                home / ".config/microsoft-edge/NativeMessagingHosts",
            ]
        )
    elif os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData/Local")
        dirs.extend(
            [
                local / "Google/Chrome/User Data/NativeMessagingHosts",
                local / "Chromium/User Data/NativeMessagingHosts",
                local / "Microsoft/Edge/User Data/NativeMessagingHosts",
            ]
        )
    return dirs


def write_host_launcher() -> Path:
    launcher = host_launcher_path()
    # Prefer the same interpreter running mdtero.
    python = Path(sys.executable).resolve()
    # Copy a minimal importable package into a stable config path so Chrome can
    # launch the host even when the developer checkout lived under /tmp.
    import shutil

    source_pkg = Path(__file__).resolve().parent
    installed_root = config_native_dir() / "py"
    installed_pkg = installed_root / "mdtero"
    if installed_pkg.exists():
        shutil.rmtree(installed_pkg)
    installed_pkg.mkdir(parents=True, exist_ok=True)
    for name in (
        "__init__.py",
        "config.py",
        "native_host.py",
        "native_messaging_constants.py",
        "native_bridge.py",
    ):
        src = source_pkg / name
        if src.exists():
            shutil.copy2(src, installed_pkg / name)
    script = f"""#!/bin/sh
export PYTHONPATH="{installed_root}:$PYTHONPATH"
export PYTHONUNBUFFERED=1
exec "{python}" -c 'from mdtero.native_host import main; raise SystemExit(main())'
"""
    launcher.write_text(script, encoding="utf-8")
    launcher.chmod(0o755)
    try:
        # Avoid macOS quarantine blocking Chrome from executing the host wrapper.
        import subprocess

        subprocess.run(["xattr", "-d", "com.apple.quarantine", str(launcher)], check=False, capture_output=True)
        subprocess.run(["xattr", "-cr", str(installed_root)], check=False, capture_output=True)
    except Exception:
        pass
    env_hint = config_native_dir() / "README.txt"
    env_hint.write_text(
        "Chrome launches mdtero-native-host via this wrapper.\n"
        f"Host name: {NATIVE_HOST_NAME}\n"
        f"Dev extension id: {DEV_EXTENSION_ID}\n"
        f"Jobs dir: {jobs_dir()}\n"
        f"Package root: {installed_root}\n",
        encoding="utf-8",
    )
    return launcher


def build_host_manifest(*, extension_ids: list[str] | None = None) -> dict[str, Any]:
    ids = [str(item).strip() for item in (extension_ids or [DEV_EXTENSION_ID]) if str(item).strip()]
    if DEV_EXTENSION_ID not in ids:
        ids.insert(0, DEV_EXTENSION_ID)
    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique_ids: list[str] = []
    for item in ids:
        if item in seen:
            continue
        seen.add(item)
        unique_ids.append(item)
    return {
        "name": NATIVE_HOST_NAME,
        "description": "Mdtero CLI native host (dev extension capture bridge)",
        "path": str(host_launcher_path().resolve()),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{ext_id}/" for ext_id in unique_ids],
    }


def install_native_host(*, extension_ids: list[str] | None = None) -> dict[str, Any]:
    launcher = write_host_launcher()
    manifest = build_host_manifest(extension_ids=extension_ids)
    written: list[str] = []
    for directory in chrome_native_messaging_dirs():
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / host_manifest_name()
        target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        written.append(str(target))
    local_copy = config_native_dir() / host_manifest_name()
    local_copy.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "host_name": NATIVE_HOST_NAME,
        "dev_extension_id": DEV_EXTENSION_ID,
        "dev_extension_public_key_present": bool(DEV_EXTENSION_PUBLIC_KEY),
        "launcher": str(launcher),
        "manifests": written,
        "jobs_dir": str(jobs_dir()),
        "next_steps": [
            "Load the Mdtero *dev* extension unpacked (build with npm run build:dev).",
            "Confirm chrome://extensions ID matches the installed allowed_origins (or pass --extension-id).",
            "Keep Chrome open and signed into Mdtero + publisher/campus session.",
            "Run: mdtero capture <doi-or-url> --wait --json",
        ],
    }


def native_host_doctor() -> dict[str, Any]:
    launcher = host_launcher_path()
    manifests = []
    for directory in chrome_native_messaging_dirs():
        target = directory / host_manifest_name()
        manifests.append(
            {
                "path": str(target),
                "exists": target.exists(),
            }
        )
    return {
        "ok": launcher.exists() and any(item["exists"] for item in manifests),
        "host_name": NATIVE_HOST_NAME,
        "dev_extension_id": DEV_EXTENSION_ID,
        "launcher_exists": launcher.exists(),
        "launcher": str(launcher),
        "manifests": manifests,
        "jobs_dir": str(jobs_dir()),
        "python": sys.executable,
        "mdtero_module": bool(shutil.which("mdtero")) or True,
    }


def request_native_capture(
    *,
    input_value: str,
    open_url: str | None = None,
    timeout: float = 300.0,
    open_browser: bool = True,
    wait: bool = True,
    interval: float = 1.0,
) -> dict[str, Any]:
    doctor = native_host_doctor()
    job = enqueue_capture_job(
        input_value=input_value,
        open_url=open_url,
        timeout_seconds=timeout,
        source="cli",
    )
    opened: list[str] = []
    target_url = str(job.get("open_url") or input_value or "").strip()
    if open_browser and target_url.startswith("http"):
        webbrowser.open(target_url)
        opened.append(target_url)
    payload: dict[str, Any] = {
        "status": "pending",
        "transport": "native_messaging_job_queue",
        "host_name": NATIVE_HOST_NAME,
        "job_id": job["job_id"],
        "job": job,
        "opened_urls": opened,
        "host_doctor": doctor,
        "action_hint": (
            "Chrome native host job queued. Keep the Mdtero *dev* extension loaded and signed in; "
            "it will dequeue this job, capture HTML, and upload via /api/v1/tasks/upload."
        ),
    }
    if not wait:
        return payload
    finished = wait_for_job(job["job_id"], timeout=timeout, interval=interval)
    payload["job"] = finished
    payload["status"] = str(finished.get("status") or "failed")
    payload["task_id"] = finished.get("task_id")
    payload["error"] = finished.get("error")
    if payload["status"] == "succeeded" and payload.get("task_id"):
        payload["action_hint"] = f"Capture completed. Continue with `mdtero status {payload['task_id']} --wait --json`."
    elif payload["status"] != "succeeded":
        payload["action_hint"] = (
            "Native capture did not finish. Ensure the unpackaged/dev extension is loaded, "
            "signed into Mdtero, and the article page is open with institutional access; "
            "then retry or Parse from the popup."
        )
    return payload


def get_job(job_id: str) -> dict[str, Any] | None:
    return read_job(job_id)
