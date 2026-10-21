"""Real supervised bridge lifecycle tests; no desktop or institutional claims."""

from __future__ import annotations

import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlparse
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from mdtero.connect.agent_runtime import AgentRuntime, SDK_VERSION
from mdtero.auth import WebLoginCancelled, WebLoginResult, run_web_login
from mdtero.config import MdteroConfig
from mdtero.connect import native_entry, native_login


ROOT = Path(__file__).resolve().parents[1]
SECRET = "synthetic-native-key-not-a-real-credential"


@pytest.fixture
def native_process(tmp_path, monkeypatch):
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MDTERO_API_KEY", SECRET)
    monkeypatch.setenv("MDTERO_API_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("PYTHONPATH", str(ROOT / "src"))
    # Native entry must ignore this inherited override even in a repo checkout.
    override = tmp_path / "untrusted-ui"
    override.mkdir()
    (override / "index.html").write_text("UNTRUSTED_UI_SENTINEL")
    monkeypatch.setenv("MDTERO_CONNECT_APP_DIR", str(override))
    processes = []

    def launch(*args):
        process = subprocess.Popen(
            [sys.executable, "-m", "mdtero.connect.native_entry", *args],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", cwd=tmp_path,
        )
        processes.append(process)
        lines: queue.Queue[str] = queue.Queue()
        threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
        try:
            line = lines.get(timeout=10)
        except queue.Empty:
            pytest.fail("Native entry did not flush its startup protocol within 10 seconds")
        assert SECRET not in line
        return process, json.loads(line)

    yield launch
    for process in processes:
        if process.stdin and not process.stdin.closed:
            process.stdin.close()
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=4)
        for pipe in (process.stdout, process.stderr):
            if pipe:
                pipe.close()


@pytest.mark.parametrize("shutdown", ["command", "eof"])
def test_native_handshake_real_ui_secrets_and_parent_shutdown(native_process, shutdown):
    process, summary = native_process()
    assert summary == {
        "status": "running", "url": f"http://127.0.0.1:{summary['port']}",
        "host": "127.0.0.1", "port": summary["port"], "product": "mdtero-connect",
        "mode": "library", "protocol": 1,
    }
    assert 0 < summary["port"] < 65536
    with httpx.Client(base_url=summary["url"], trust_env=False, timeout=2) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "Mdtero Connect" in page.text and "UNTRUSTED_UI_SENTINEL" not in page.text
        assert "connect-src 'self'" in page.text
        session = client.get("/connect/v1/session")
        assert session.status_code == 200
        assert session.json()["agent"]["enabled"] is False
        assert SECRET not in session.text
        assert client.get("/connect/v1/session", headers={"Host": "evil.example"}).status_code == 403
        assert client.post("/connect/v1/library/tags/batch", json={"document_ids": [1], "dry_run": True}).status_code == 403
    if shutdown == "command":
        process.stdin.write("shutdown\n")
        process.stdin.flush()
    else:
        process.stdin.close()
    assert process.wait(timeout=5) == 0
    assert process.stdout.read() == ""
    assert SECRET not in process.stderr.read()
    with pytest.raises(httpx.TransportError):
        httpx.get(summary["url"] + "/connect/v1/session", trust_env=False, timeout=1)


@pytest.mark.skipif(os.name == "nt", reason="Windows native shell uses its JobObject/stdin lifecycle")
@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGINT])
def test_native_signals_gracefully_release_listener(native_process, signum):
    process, summary = native_process()
    process.send_signal(signum)
    assert process.wait(timeout=5) == 0
    with pytest.raises(httpx.TransportError):
        httpx.get(summary["url"], trust_env=False, timeout=1)


@pytest.mark.parametrize("arguments,reason", [
    (["--full"], "native_runtime_missing"),
    (["--full", "--runtime-dir", "relative-untrusted-path"], "native_runtime_missing"),
    (["--port", "-1"], "native_port_invalid"),
    (["--port", "65536"], "native_port_invalid"),
])
def test_native_invalid_startup_has_safe_actionable_protocol(native_process, arguments, reason):
    process, summary = native_process(*arguments)
    assert process.wait(timeout=5) == 1
    assert summary["status"] == "error" and summary["protocol"] == 1
    assert summary["reason_code"] == reason and summary["action_hint"]
    assert "Traceback" not in process.stderr.read()


def test_full_bundle_never_falls_back_to_path_node(native_process, tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    process, summary = native_process("--full", "--runtime-dir", str(runtime))
    assert process.wait(timeout=5) == 1
    assert summary["reason_code"] == "native_node_missing"


def test_full_bundle_requires_pinned_agent_dependencies(native_process, tmp_path):
    runtime = tmp_path / "runtime"
    (runtime / "node").mkdir(parents=True)
    (runtime / "node" / ("node.exe" if os.name == "nt" else "node")).write_bytes(b"unused synthetic runtime")
    process, summary = native_process("--full", "--runtime-dir", str(runtime))
    assert process.wait(timeout=5) == 1
    assert summary["reason_code"] == "native_agent_missing"


def test_native_parent_eof_during_startup_does_not_leave_process(tmp_path, monkeypatch):
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("PYTHONPATH", str(ROOT / "src"))
    process = subprocess.Popen(
        [sys.executable, "-m", "mdtero.connect.native_entry"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", cwd=tmp_path,
    )
    try:
        output, error = process.communicate(input="", timeout=5)
        assert process.returncode == 0
        assert "Traceback" not in error
        if output:
            summary = json.loads(output)
            with pytest.raises(httpx.TransportError):
                httpx.get(summary["url"], trust_env=False, timeout=1)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)


def test_basic_native_startup_does_not_run_node(native_process, tmp_path, monkeypatch):
    marker = tmp_path / "node-was-executed"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake = fake_bin / ("node.exe" if os.name == "nt" else "node")
    fake.write_text(f"#!/bin/sh\necho ran > '{marker}'\nexit 1\n")
    fake.chmod(0o700)
    monkeypatch.setenv("PATH", str(fake_bin))
    process, summary = native_process()
    assert summary["mode"] == "library"
    response = httpx.get(summary["url"] + "/connect/v1/agent/status", trust_env=False)
    assert response.json()["enabled"] is False
    process.stdin.close()
    assert process.wait(timeout=5) == 0
    assert not marker.exists()


def test_explicit_node_path_does_not_search_path(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", MagicMock(side_effect=AssertionError("PATH lookup forbidden")))
    runtime = AgentRuntime(full_mode=True, providers=MagicMock(), library=MagicMock(), node_executable=tmp_path / "missing-node")
    try:
        assert runtime._dependency_info()["reason_code"] == "agent_node_missing"
    finally:
        runtime.close()


def test_explicit_node_path_executes_pinned_worker_and_close_reaps_it(tmp_path, monkeypatch):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for the real subprocess shutdown check")
    worker = tmp_path / "worker.mjs"
    worker.write_text("process.on('SIGTERM',()=>{});process.stdin.resume();setInterval(()=>{},1000);")
    library = MagicMock()
    library.list_documents.return_value = {"items": [{"id": 1, "title": "Synthetic metadata"}]}
    providers = MagicMock()
    providers.get_key.return_value = SECRET
    runtime = AgentRuntime(full_mode=True, providers=providers, library=library, runtime_dir=tmp_path, node_executable=Path(node).resolve())
    runtime._dependency_info = lambda: {"available": True, "sdk_version": SDK_VERSION, "models": {"openai": [{"id": "synthetic-model"}]}}
    monkeypatch.setattr(shutil, "which", MagicMock(side_effect=AssertionError("PATH lookup forbidden")))
    preview = runtime.prepare({"document_ids": [1], "prompt": "Read selected metadata", "provider": "openai", "model": "synthetic-model", "max_output_tokens": 128})
    process = None
    try:
        started = runtime.start(preview["approval_id"])
        deadline = time.monotonic() + 3
        while not runtime._processes and time.monotonic() < deadline:
            time.sleep(0.01)
        process = runtime._processes[started["run_id"]]
        # Allow the synthetic worker to install its SIGTERM handler.
        time.sleep(0.15)
        runtime.close()
        assert process.poll() is not None
        assert runtime._runs[started["run_id"]]["status"] == "cancelled"
    finally:
        runtime.close()
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=3)


def test_close_during_worker_startup_prevents_a_late_child(tmp_path, monkeypatch):
    library = MagicMock()
    library.list_documents.return_value = {"items": [{"id": 1, "title": "Synthetic metadata"}]}
    providers = MagicMock()
    providers.get_key.return_value = SECRET
    runtime = AgentRuntime(full_mode=True, providers=providers, library=library, runtime_dir=tmp_path)
    runtime._dependency_info = lambda: {"available": True, "models": {"openai": [{"id": "synthetic-model"}]}}
    entered, release = threading.Event(), threading.Event()

    def delayed_node():
        entered.set()
        release.wait(timeout=3)
        return str(tmp_path / "node")

    runtime._node_path = delayed_node
    spawn = MagicMock(side_effect=AssertionError("Closed runtime must not spawn a late child"))
    monkeypatch.setattr(subprocess, "Popen", spawn)
    preview = runtime.prepare({"document_ids": [1], "prompt": "Read metadata", "provider": "openai", "model": "synthetic-model", "max_output_tokens": 128})
    try:
        started = runtime.start(preview["approval_id"])
        assert entered.wait(timeout=3)
        runtime.close()
        release.set()
        deadline = time.monotonic() + 3
        while runtime._active_run and time.monotonic() < deadline:
            time.sleep(0.01)
        assert runtime._active_run is None
        assert runtime._runs[started["run_id"]]["status"] == "cancelled"
        spawn.assert_not_called()
    finally:
        release.set()
        runtime.close()


def test_native_login_reuses_real_state_callback_and_verifies_before_saving(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "login-config"))
    monkeypatch.delenv("MDTERO_API_KEY", raising=False)
    seen = {}

    def browser(url):
        params = parse_qs(urlparse(url).query)
        seen["callback"] = params["cli_callback"][0]
        response = httpx.post(seen["callback"], json={"state": params["cli_state"][0], "apiKey": SECRET}, trust_env=False)
        assert response.status_code == 200

    def usage(self):
        assert self.config.api_key == SECRET
        assert not (tmp_path / "login-config" / "config.json").exists()
        seen["verified"] = True
        return {"email": "synthetic@example.test"}

    monkeypatch.setattr(native_login, "_open_browser", browser)
    monkeypatch.setattr(native_login.MdteroClient, "usage", usage)
    native_login.login_account(threading.Event(), timeout_seconds=3)
    saved = json.loads((tmp_path / "login-config" / "config.json").read_text())
    assert saved["api_key"] == SECRET and seen["verified"]
    assert capsys.readouterr().out == ""
    with pytest.raises(httpx.TransportError):
        httpx.post(seen["callback"], json={}, trust_env=False, timeout=1)


@pytest.mark.parametrize("error", [RuntimeError(SECRET), TimeoutError(SECRET)])
def test_native_login_failures_never_save_or_serialize_upstream_errors(monkeypatch, error):
    monkeypatch.setattr(native_login, "load_config", lambda: MdteroConfig())
    monkeypatch.setattr(native_login, "run_web_login", MagicMock(side_effect=error))
    saved = MagicMock()
    monkeypatch.setattr(native_login, "save_config", saved)
    with pytest.raises(native_login.NativeLoginError) as caught:
        native_login.login_account(threading.Event())
    assert SECRET not in str(caught.value)
    saved.assert_not_called()


def test_native_login_rejected_account_does_not_replace_saved_config(monkeypatch):
    cfg = MdteroConfig(api_key="existing-local-key")
    monkeypatch.setattr(native_login, "load_config", lambda: cfg)
    monkeypatch.setattr(native_login, "run_web_login", lambda *a, **k: WebLoginResult(api_key=SECRET))
    monkeypatch.setattr(native_login.MdteroClient, "usage", MagicMock(side_effect=RuntimeError(SECRET)))
    saved = MagicMock()
    monkeypatch.setattr(native_login, "save_config", saved)
    with pytest.raises(native_login.NativeLoginError) as caught:
        native_login.login_account(threading.Event())
    assert caught.value.reason_code == "native_login_verification_failed"
    assert SECRET not in str(caught.value)
    saved.assert_not_called()


def test_existing_oauth_helper_cancel_closes_callback_listener():
    stopped = threading.Event()
    seen = {}

    def browser(url):
        seen["callback"] = parse_qs(urlparse(url).query)["cli_callback"][0]
        stopped.set()

    began = time.monotonic()
    with pytest.raises(WebLoginCancelled):
        run_web_login("https://mdtero.com", open_browser=browser, cancel_event=stopped)
    assert time.monotonic() - began < 2
    with pytest.raises(httpx.TransportError):
        httpx.get(seen["callback"], trust_env=False, timeout=1)


@pytest.mark.parametrize("cancel_after_callback", [False, True])
def test_native_login_cancel_never_saves_account(monkeypatch, cancel_after_callback):
    stopped = threading.Event()
    monkeypatch.setattr(native_login, "load_config", lambda: MdteroConfig())

    def login(*args, **kwargs):
        stopped.set()
        if cancel_after_callback:
            return WebLoginResult(api_key=SECRET)
        raise WebLoginCancelled("cancelled")

    monkeypatch.setattr(native_login, "run_web_login", login)
    saved = MagicMock()
    monkeypatch.setattr(native_login, "save_config", saved)
    with pytest.raises(native_login.NativeLoginError) as caught:
        native_login.login_account(stopped)
    assert caught.value.reason_code == "native_login_cancelled"
    saved.assert_not_called()


@pytest.mark.parametrize("fail", [False, True])
def test_native_login_stdio_protocol_has_no_callback_url_or_credentials(monkeypatch, capsys, fail):
    monkeypatch.setattr(native_entry, "_watch_parent", lambda _: None)
    bridge = MagicMock(side_effect=AssertionError("Login mode must not create the library bridge"))
    monkeypatch.setattr(native_entry, "ConnectBridge", bridge)

    def login(stopped):
        if fail:
            raise native_login.NativeLoginError("native_login_failed", "Account login could not complete.")

    monkeypatch.setattr(native_entry, "login_account", login)
    assert native_entry.main(["--login"]) == (1 if fail else 0)
    output = capsys.readouterr()
    summary = json.loads(output.out)
    assert summary["protocol"] == 1
    assert summary["status"] == ("error" if fail else "authenticated")
    assert SECRET not in output.out and "http" not in output.out
    assert output.err == ""
    bridge.assert_not_called()


def test_frozen_entry_uses_explicit_bundled_static_directory(tmp_path, monkeypatch):
    static = tmp_path / "mdtero" / "connect" / "static"
    static.mkdir(parents=True)
    (static / "index.html").write_text("bundled UI")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(native_entry, "__file__", str(tmp_path / "native_entry.py"))
    monkeypatch.setenv("MDTERO_CONNECT_APP_DIR", str(tmp_path / "untrusted"))
    assert native_entry._static_dir() == static


def test_frozen_entry_never_falls_back_to_checkout_or_cwd(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    with pytest.raises(native_entry.NativeStartupError) as caught:
        native_entry._static_dir()
    assert caught.value.reason_code == "native_ui_missing"


@pytest.mark.parametrize("stop_mode", ["eof", "shutdown", "signal"])
def test_login_child_parent_cancel_stops_actual_callback_listener(tmp_path, monkeypatch, stop_mode):
    if stop_mode == "signal" and os.name == "nt":
        pytest.skip("Windows shell cancels via stdin and its JobObject")
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("PYTHONPATH", str(ROOT / "src"))
    opened = tmp_path / "opened-login-url"
    script = (
        "from pathlib import Path; from mdtero.connect import native_entry,native_login; "
        f"native_login._open_browser=lambda url: Path({str(opened)!r}).write_text(url); "
        "raise SystemExit(native_entry.main(['--login']))"
    )
    process = subprocess.Popen([sys.executable, "-c", script], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=tmp_path)
    try:
        deadline = time.monotonic() + 5
        while not opened.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert opened.exists(), "Login helper did not start its callback listener"
        callback = parse_qs(urlparse(opened.read_text()).query)["cli_callback"][0]
        assert httpx.get(callback, trust_env=False, timeout=1).status_code == 501
        if stop_mode == "eof":
            process.stdin.close()
        elif stop_mode == "shutdown":
            process.stdin.write("shutdown\n")
            process.stdin.flush()
        else:
            process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=4) == 1
        output = process.stdout.read()
        summary = json.loads(output)
        assert summary["status"] == "error" and summary["reason_code"] == "native_login_cancelled"
        assert "http" not in output and SECRET not in output
        assert not (tmp_path / "config" / "config.json").exists()
        assert process.stderr.read() == ""
        with pytest.raises(httpx.TransportError):
            httpx.get(callback, trust_env=False, timeout=1)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        for pipe in (process.stdin, process.stdout, process.stderr):
            if pipe and not pipe.closed:
                pipe.close()


def test_frozen_windows_bridge_requires_a_parent_job(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    with pytest.raises(native_entry.NativeStartupError) as caught:
        native_entry._join_parent_job(None)
    assert caught.value.reason_code == "native_job_required"


@pytest.mark.parametrize("already_joined", [False, True])
def test_windows_child_joins_named_job_and_immediately_releases_its_handle(monkeypatch, already_joined):
    import ctypes
    from ctypes import wintypes

    api = MagicMock()
    api.OpenJobObjectW.return_value = 123
    api.GetCurrentProcess.return_value = -1

    def membership(process, job, result):
        assert process == -1 and job == 123
        ctypes.cast(result, ctypes.POINTER(wintypes.BOOL))[0] = already_joined
        return True

    api.IsProcessInJob.side_effect = membership
    api.AssignProcessToJobObject.return_value = True
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(native_entry, "_windows_job_api", lambda: api)
    native_entry._join_parent_job("Local\\MdteroConnect-synthetic-parent")
    api.OpenJobObjectW.assert_called_once_with(5, False, "Local\\MdteroConnect-synthetic-parent")
    api.CloseHandle.assert_called_once_with(123)
    if already_joined:
        api.AssignProcessToJobObject.assert_not_called()
    else:
        api.AssignProcessToJobObject.assert_called_once_with(123, -1)


@pytest.mark.parametrize("failure", ["gone", "query", "assign"])
def test_windows_job_failure_cannot_start_library_or_login(monkeypatch, capsys, failure):
    api = MagicMock()
    api.OpenJobObjectW.return_value = 0 if failure == "gone" else 123
    api.IsProcessInJob.return_value = failure != "query"
    api.AssignProcessToJobObject.return_value = False
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(native_entry, "_windows_job_api", lambda: api)
    login = MagicMock(side_effect=AssertionError("Unsupervised login must not start"))
    bridge = MagicMock(side_effect=AssertionError("Unsupervised bridge must not start"))
    monkeypatch.setattr(native_entry, "login_account", login)
    monkeypatch.setattr(native_entry, "ConnectBridge", bridge)
    assert native_entry.main(["--login", "--job-name", "Local\\MdteroConnect-dead-parent"]) == 1
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "error"
    assert summary["reason_code"] == ("native_job_unavailable" if failure == "gone" else "native_job_assignment_failed")
    login.assert_not_called()
    bridge.assert_not_called()
    if failure != "gone":
        api.CloseHandle.assert_called_once_with(123)


@pytest.mark.skipif(os.name != "nt", reason="Requires the actual Windows JobObject kernel API")
def test_windows_parent_job_close_terminates_real_bridge(native_process):
    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [("ProcessTime", ctypes.c_int64), ("JobTime", ctypes.c_int64),
                    ("Flags", wintypes.DWORD), ("MinWorkingSet", ctypes.c_size_t),
                    ("MaxWorkingSet", ctypes.c_size_t), ("ActiveProcesses", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("Priority", wintypes.DWORD), ("Scheduling", wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperations", "WriteOperations", "OtherOperations", "ReadBytes", "WriteBytes", "OtherBytes")]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("Basic", BasicLimits), ("Io", IoCounters), ("ProcessMemory", ctypes.c_size_t),
                    ("JobMemory", ctypes.c_size_t), ("PeakProcessMemory", ctypes.c_size_t), ("PeakJobMemory", ctypes.c_size_t)]

    api = native_entry._windows_job_api()
    api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    api.CreateJobObjectW.restype = wintypes.HANDLE
    api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    api.SetInformationJobObject.restype = wintypes.BOOL
    name = f"Local\\MdteroConnect-pytest-{os.getpid()}-{time.time_ns()}"
    job = api.CreateJobObjectW(None, name)
    assert job, "Windows could not create the test parent job"
    limits = ExtendedLimits()
    limits.Basic.Flags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    try:
        assert api.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits))
        process, summary = native_process("--job-name", name)
        assert httpx.get(summary["url"] + "/connect/v1/session", trust_env=False).status_code == 200
        assert api.CloseHandle(job)
        job = None
        process.wait(timeout=5)
        with pytest.raises(httpx.TransportError):
            httpx.get(summary["url"], trust_env=False, timeout=1)
    finally:
        if job:
            api.CloseHandle(job)
