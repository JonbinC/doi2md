from __future__ import annotations

import json
import struct

from mdtero.native_host import (
    complete_job,
    enqueue_capture_job,
    handle_native_request,
    list_pending_jobs,
    wait_for_job,
)


def test_enqueue_dequeue_complete_job_cycle(tmp_path, monkeypatch):
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path))
    job = enqueue_capture_job(
        input_value="https://ieeexplore.ieee.org/document/5206848",
        open_url="https://ieeexplore.ieee.org/document/5206848",
        timeout_seconds=60,
    )
    assert job["status"] == "pending"
    pending = handle_native_request({"type": "dequeue", "limit": 2})
    assert pending["ok"] is True
    assert len(pending["jobs"]) == 1
    assert pending["jobs"][0]["status"] == "running"
    done = handle_native_request(
        {
            "type": "complete",
            "job_id": job["job_id"],
            "task_id": "task-demo",
        }
    )
    assert done["ok"] is True
    assert done["job"]["status"] == "succeeded"
    assert done["job"]["task_id"] == "task-demo"
    assert wait_for_job(job["job_id"], timeout=1.0)["status"] == "succeeded"


def test_ping_and_list_pending(tmp_path, monkeypatch):
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path))
    enqueue_capture_job(input_value="10.1109/demo", open_url="https://doi.org/10.1109/demo")
    pong = handle_native_request({"type": "ping"})
    assert pong["ok"] is True
    assert pong["pending_count"] >= 1
    assert list_pending_jobs()


def test_complete_job_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path))
    job = enqueue_capture_job(input_value="10.1109/demo")
    finished = complete_job(job["job_id"], error="no_session")
    assert finished["status"] == "failed"
    assert finished["error"] == "no_session"
