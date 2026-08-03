"""Chromium native-messaging host for the Mdtero *dev* extension.

Chrome or Edge launches this process for stdio length-prefixed JSON. The CLI also uses
the same module to enqueue/wait on filesystem jobs under the mdtero config dir.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import config_dir
from .native_messaging_constants import DEV_EXTENSION_ID, NATIVE_HOST_NAME


def jobs_dir() -> Path:
    path = config_dir() / "native-jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_path(job_id: str) -> Path:
    return jobs_dir() / f"{job_id}.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_job(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _write_job(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def enqueue_capture_job(
    *,
    input_value: str,
    open_url: str | None = None,
    preferred_artifact: str = "html",
    timeout_seconds: float = 300.0,
    source: str = "cli",
) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    now = _utc_now()
    payload = {
        "job_id": job_id,
        "status": "pending",
        "input": str(input_value or "").strip(),
        "open_url": str(open_url or input_value or "").strip() or None,
        "preferred_artifact": preferred_artifact,
        "source": source,
        "created_at": now,
        "updated_at": now,
        "expires_at_epoch": time.time() + max(30.0, float(timeout_seconds)),
        "task_id": None,
        "error": None,
        "host_name": NATIVE_HOST_NAME,
    }
    _write_job(job_path(job_id), payload)
    return payload


def read_job(job_id: str) -> dict[str, Any] | None:
    return _read_job(job_path(job_id))


def list_pending_jobs(*, limit: int = 8) -> list[dict[str, Any]]:
    pending: list[dict[str, Any]] = []
    now = time.time()
    for path in sorted(jobs_dir().glob("*.json"), key=lambda item: item.stat().st_mtime):
        job = _read_job(path)
        if not job:
            continue
        expires = float(job.get("expires_at_epoch") or 0)
        if job.get("status") == "pending" and expires and expires < now:
            job["status"] = "failed"
            job["error"] = "capture_job_expired"
            job["updated_at"] = _utc_now()
            _write_job(path, job)
            continue
        if job.get("status") == "pending":
            pending.append(job)
        if len(pending) >= limit:
            break
    return pending


def claim_job(job_id: str) -> dict[str, Any] | None:
    path = job_path(job_id)
    job = _read_job(path)
    if not job or job.get("status") != "pending":
        return None
    job["status"] = "running"
    job["updated_at"] = _utc_now()
    _write_job(path, job)
    return job


def complete_job(
    job_id: str,
    *,
    task_id: str | None = None,
    error: str | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    path = job_path(job_id)
    job = _read_job(path)
    if not job:
        return None
    if error:
        job["status"] = "failed"
        job["error"] = str(error)
        job["task_id"] = task_id or job.get("task_id")
    else:
        job["status"] = "succeeded"
        job["error"] = None
        job["task_id"] = task_id
    if result is not None:
        job["result"] = result
    job["updated_at"] = _utc_now()
    _write_job(path, job)
    return job


def wait_for_job(job_id: str, *, timeout: float = 300.0, interval: float = 1.0) -> dict[str, Any]:
    deadline = time.time() + max(1.0, float(timeout))
    latest: dict[str, Any] | None = None
    while time.time() < deadline:
        latest = read_job(job_id)
        if latest and latest.get("status") in {"succeeded", "failed"}:
            return latest
        time.sleep(max(0.2, float(interval)))
    latest = latest or {"job_id": job_id, "status": "failed", "error": "capture_wait_timeout"}
    if latest.get("status") not in {"succeeded", "failed"}:
        latest = complete_job(job_id, error="capture_wait_timeout") or latest
    return latest


def _read_native_message() -> dict[str, Any] | None:
    raw_len = sys.stdin.buffer.read(4)
    if not raw_len or len(raw_len) < 4:
        return None
    length = struct.unpack("<I", raw_len)[0]
    if length <= 0 or length > 8 * 1024 * 1024:
        return None
    payload = sys.stdin.buffer.read(length)
    if len(payload) < length:
        return None
    data = json.loads(payload.decode("utf-8"))
    return data if isinstance(data, dict) else None


def _write_native_message(message: dict[str, Any]) -> None:
    encoded = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def handle_native_request(message: dict[str, Any]) -> dict[str, Any]:
    msg_type = str(message.get("type") or message.get("method") or "").strip()
    if msg_type in {"ping", "hello"}:
        return {
            "ok": True,
            "type": "pong",
            "host_name": NATIVE_HOST_NAME,
            "dev_extension_id": DEV_EXTENSION_ID,
            "pending_count": len(list_pending_jobs()),
        }
    if msg_type in {"dequeue", "poll"}:
        limit = int(message.get("limit") or 1)
        jobs = list_pending_jobs(limit=max(1, min(limit, 8)))
        claimed: list[dict[str, Any]] = []
        for job in jobs:
            claimed_job = claim_job(str(job.get("job_id") or ""))
            if claimed_job:
                claimed.append(claimed_job)
        return {"ok": True, "type": "dequeue_result", "jobs": claimed}
    if msg_type in {"complete", "finish"}:
        job_id = str(message.get("job_id") or "").strip()
        job = complete_job(
            job_id,
            task_id=str(message.get("task_id") or "").strip() or None,
            error=str(message.get("error") or "").strip() or None,
            result=message.get("result") if isinstance(message.get("result"), dict) else None,
        )
        return {"ok": bool(job), "type": "complete_result", "job": job}
    if msg_type == "status":
        job_id = str(message.get("job_id") or "").strip()
        return {"ok": True, "type": "status_result", "job": read_job(job_id)}
    return {"ok": False, "type": "error", "error": f"unknown_message_type:{msg_type or 'empty'}"}


def run_native_stdio_loop() -> int:
    while True:
        message = _read_native_message()
        if message is None:
            return 0
        try:
            response = handle_native_request(message)
        except Exception as exc:  # pragma: no cover - defensive host path
            response = {"ok": False, "type": "error", "error": str(exc)}
        _write_native_message(response)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mdtero-native-host")
    parser.add_argument("--ping", action="store_true", help="Print host identity and exit.")
    args = parser.parse_args(argv)
    if args.ping:
        print(
            json.dumps(
                {
                    "ok": True,
                    "host_name": NATIVE_HOST_NAME,
                    "dev_extension_id": DEV_EXTENSION_ID,
                    "jobs_dir": str(jobs_dir()),
                },
                ensure_ascii=False,
            )
        )
        return 0
    return run_native_stdio_loop()


if __name__ == "__main__":
    raise SystemExit(main())
