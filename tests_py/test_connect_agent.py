from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mdtero.connect.agent_runtime import AgentError, AgentRuntime, SDK_VERSION
from mdtero.connect import agent_runtime


class Keys:
    def __init__(self):
        self.keys = {"openai": "synthetic-provider-secret-not-real"}

    def get_key(self, provider):
        return self.keys.get(provider)


class SyntheticRuntime(AgentRuntime):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.receipts = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.delay = False
        self.fail = False

    def _dependency_info(self):
        return {"available": True, "node_version": "22.23.1", "sdk_version": SDK_VERSION, "models": {"openai": [{"id": "gpt-4.1-mini", "name": "Test model", "max_output_tokens": 4096}]}}

    def _execute_worker(self, payload, cancel_event, run_id):
        self.receipts.append(copy.deepcopy(payload))
        self.started.set()
        if self.delay:
            while not self.release.wait(0.01):
                if cancel_event.is_set():
                    return {"text": "Cancelled intermediate output must not be returned"}
        if self.fail:
            raise RuntimeError("Synthetic upstream leaked " + payload["api_key"])
        return {"text": "Metadata supports only the selected citation [1].", "usage": {"input": 10, "output": 9}, "engine": "pi", "scope": "selected_metadata"}


@pytest.fixture
def runtime():
    library = MagicMock()
    library.list_documents.return_value = {"items": [{"id": 1, "title": "Original metadata", "authors": ["Author"], "year": 2026, "doi": "10.0000/example", "venue": "Example", "full_text": "FULL TEXT MUST NEVER ENTER", "abstract": "PRIVATE ABSTRACT", "tags": ["private"]}, {"id": 2, "title": "Other paper"}]}
    instance = SyntheticRuntime(full_mode=True, providers=Keys(), library=library)
    yield instance
    instance.close()


def request(**overrides):
    return {"document_ids": [1], "prompt": "Compare the metadata evidence.", "provider": "openai", "model": "gpt-4.1-mini", "max_output_tokens": 512, **overrides}


def wait_run(runtime, run_id):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        result = runtime.get_run(run_id)
        if result["status"] != "running":
            return result
        time.sleep(0.01)
    pytest.fail("Run failed to stop")


def test_basic_mode_does_not_probe_or_launch_node():
    runtime = AgentRuntime(full_mode=False, providers=Keys(), library=MagicMock())
    runtime._dependency_info = MagicMock(side_effect=AssertionError("must not probe"))
    runtime.providers.get_key = MagicMock(side_effect=AssertionError("must not unlock or inspect provider keys"))
    status = runtime.status()
    runtime.providers.get_key.assert_not_called()
    assert all(row["configured"] is False and row["checked"] is False for row in status["providers"])
    assert status["mode"] == "basic" and not status["enabled"]
    assert status["reason_code"] == "full_mode_required"
    assert "synthetic-provider-secret" not in json.dumps(status)
    with pytest.raises(AgentError, match="--full"):
        runtime.prepare(request(full_mode=True))
    runtime._dependency_info.assert_not_called()


def test_full_status_is_real_dependencies_and_provider_keys(runtime):
    status = runtime.status()
    assert status["ready"] and status["engine"] == "pi"
    assert status["tools"] == []
    assert status["max_model_requests"] == 1
    assert status["full_text_included"] is False
    runtime.providers.keys.clear()
    assert runtime.status()["reason_code"] == "provider_key_missing"
    runtime._dependency_info = lambda: {"available": False, "reason_code": "agent_sdk_missing", "models": {}}
    assert runtime.status()["reason_code"] == "agent_sdk_missing"


@pytest.mark.parametrize("overrides,code", [
    ({"document_ids": []}, "invalid_document_selection"),
    ({"document_ids": [1] * 11}, "invalid_document_selection"),
    ({"document_ids": [1, 1]}, "invalid_document_selection"),
    ({"document_ids": [True]}, "invalid_document_selection"),
    ({"document_ids": ["1"]}, "invalid_document_selection"),
    ({"document_ids": [1, 99]}, "document_not_in_library"),
    ({"prompt": " "}, "invalid_agent_prompt"),
    ({"prompt": "x" * 4001}, "invalid_agent_prompt"),
    ({"model": "custom-not-catalog"}, "model_not_supported"),
    ({"provider": "shell"}, "provider_not_supported"),
    ({"max_output_tokens": 4097}, "invalid_output_budget"),
    ({"max_output_tokens": 127}, "invalid_output_budget"),
    ({"max_output_tokens": True}, "invalid_output_budget"),
    ({"base_url": "https://evil.invalid"}, "invalid_agent_request"),
    ({"api_key": "from-page"}, "invalid_agent_request"),
    ({"documents": [{"id": 1, "title": "Forged"}]}, "invalid_agent_request"),
])
def test_research_request_validation(runtime, overrides, code):
    with pytest.raises(AgentError) as exc:
        runtime.prepare(request(**overrides))
    assert exc.value.reason_code == code
    assert not runtime.receipts


def test_preview_owns_selection_and_has_explicit_data_and_budget(runtime):
    preview = runtime.prepare(request())
    assert preview["scope"] == "selected_metadata" and preview["model_requests"] == 1
    assert preview["full_text_included"] is False and preview["document_count"] == 1
    assert preview["max_output_tokens"] == 512
    assert preview["input_bytes"] > 0 and preview["expires_at"]
    assert preview["documents"] == [{"id": 1, "title": "Original metadata", "authors": "Author", "year": "2026", "venue": "Example", "doi": "10.0000/example"}]
    assert "PRIVATE ABSTRACT" not in json.dumps(preview)
    assert "FULL TEXT" not in json.dumps(preview)
    assert "private" not in json.dumps(preview)
    assert "synthetic-provider-secret" not in json.dumps(preview)
    assert not runtime.receipts


def test_preview_is_frozen_and_approval_can_only_be_used_once(runtime):
    preview = runtime.prepare(request())
    preview["documents"][0]["title"] = "Changed page preview"
    preview["prompt"] = "Changed user prompt"
    runtime.library.list_documents.return_value["items"][0]["title"] = "Changed library"
    result = runtime.execute(preview["approval_id"])
    assert result["status"] == "completed"
    assert runtime.receipts[0]["documents"][0]["title"] == "Original metadata"
    assert runtime.receipts[0]["prompt"] == "Compare the metadata evidence."
    assert runtime.receipts[0]["api_key"] == runtime.providers.keys["openai"]
    with pytest.raises(AgentError) as exc:
        runtime.start(preview["approval_id"])
    assert exc.value.reason_code == "agent_approval_invalid"
    assert len(runtime.receipts) == 1


def test_expired_or_guessed_approval_cannot_make_a_provider_request(runtime):
    preview = runtime.prepare(request())
    runtime._approvals[preview["approval_id"]]["deadline"] = time.monotonic() - 1
    for approval in (preview["approval_id"], "guessed"):
        with pytest.raises(AgentError) as exc:
            runtime.start(approval)
        assert exc.value.reason_code == "agent_approval_invalid"
    assert not runtime.receipts


def test_one_running_request_cancel_and_pending_approval_survives_busy(runtime):
    runtime.delay = True
    first = runtime.prepare(request())
    second = runtime.prepare(request(prompt="Another question"))
    started = runtime.start(first["approval_id"])
    assert runtime.started.wait(2)
    assert runtime.status()["active_run"]["run_id"] == started["run_id"]
    assert "api_key" not in json.dumps(runtime.status()["active_run"])
    with pytest.raises(AgentError) as exc:
        runtime.start(second["approval_id"])
    assert exc.value.reason_code == "agent_busy"
    assert runtime.cancel(started["run_id"])["status"] == "cancelled"
    runtime.release.set()
    deadline = time.monotonic() + 2
    while runtime._active_run and time.monotonic() < deadline:
        time.sleep(0.01)
    assert runtime.get_run(started["run_id"])["status"] == "cancelled"
    assert runtime.execute(second["approval_id"])["status"] == "completed"
    assert len(runtime.receipts) == 2


def test_key_removed_after_preview_fails_without_running_worker(runtime):
    preview = runtime.prepare(request())
    runtime.providers.keys.clear()
    result = runtime.execute(preview["approval_id"])
    assert result["status"] == "failed"
    assert result["error"]["reason_code"] == "provider_key_missing"
    assert not runtime.receipts


def test_provider_exception_cannot_reveal_key_or_body(runtime):
    runtime.fail = True
    result = runtime.execute(runtime.prepare(request())["approval_id"])
    assert result["status"] == "failed"
    assert result["error"]["reason_code"] == "agent_provider_failed"
    assert "synthetic-provider-secret" not in json.dumps(result)
    assert "Synthetic upstream leaked" not in json.dumps(result)


def node_runtime(runtime, tmp_path, script, **kwargs):
    if not shutil.which("node"):
        pytest.skip("Node is needed for subprocess lifecycle verification")
    (tmp_path / "worker.mjs").write_text(script)
    instance = AgentRuntime(full_mode=True, providers=runtime.providers, library=runtime.library, runtime_dir=tmp_path, **kwargs)
    instance._dependency_info = runtime._dependency_info
    return instance


def test_worker_key_only_on_stdin_and_environment_and_output_are_sanitized(runtime, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-secret-must-not-enter")
    monkeypatch.setenv("HTTP_PROXY", "http://proxy-must-not-enter")
    monkeypatch.setenv("NODE_OPTIONS", "--trace-warnings")
    script = """
let raw='';for await(const chunk of process.stdin)raw+=chunk;
const payload=JSON.parse(raw);
if(Object.keys(process.env).some(k=>['OPENAI_API_KEY','HTTP_PROXY','NODE_OPTIONS'].includes(k)))throw new Error('ambient leak');
if(process.argv.some(arg=>arg.includes(payload.api_key)))throw new Error('argv leak');
console.log(JSON.stringify({engine:'pi',text:'Selected metadata [1] '+payload.api_key,usage:{output:4,evil:payload.api_key},api_key:payload.api_key}));
"""
    instance = node_runtime(runtime, tmp_path, script)
    try:
        result = instance.execute(instance.prepare(request())["approval_id"])
        assert result["status"] == "completed" and "[redacted]" in result["text"]
        assert result["usage"] == {"output": 4}
        assert "api_key" not in result
        assert runtime.providers.keys["openai"] not in json.dumps(result)
        assert list(tmp_path.iterdir()) == [tmp_path / "worker.mjs"]
    finally:
        instance.close()


def test_real_worker_subprocess_is_killed_at_timeout(runtime, tmp_path):
    instance = node_runtime(runtime, tmp_path, "setInterval(()=>{},1000);", timeout_seconds=0.1)
    try:
        began = time.monotonic()
        result = instance.execute(instance.prepare(request())["approval_id"])
        assert result["status"] == "failed" and result["error"]["reason_code"] == "agent_timeout"
        assert time.monotonic() - began < 3
        assert not instance._processes
    finally:
        instance.close()


def test_real_worker_subprocess_can_be_cancelled(runtime, tmp_path):
    instance = node_runtime(runtime, tmp_path, "process.on('SIGTERM',()=>{});setInterval(()=>{},1000);", timeout_seconds=5)
    try:
        started = instance.start(instance.prepare(request())["approval_id"])
        deadline = time.monotonic() + 2
        while not instance._processes and time.monotonic() < deadline:
            time.sleep(0.01)
        process = instance._processes[started["run_id"]]
        assert instance.cancel(started["run_id"])["status"] == "cancelled"
        assert instance.get_run(started["run_id"])["status"] == "cancelled"
        process.wait(timeout=3)
        assert process.poll() is not None
    finally:
        instance.close()


def test_close_stops_runtime_and_clears_approvals(runtime):
    preview = runtime.prepare(request())
    runtime.close()
    assert not runtime._approvals
    assert runtime.status()["reason_code"] == "agent_closed"
    with pytest.raises(AgentError) as exc:
        runtime.start(preview["approval_id"])
    assert exc.value.reason_code == "agent_closed"


@pytest.fixture
def dependency_probe(tmp_path, monkeypatch):
    (tmp_path / "worker.mjs").write_text("synthetic SDK probe")
    node = tmp_path / "node"
    node.write_text("synthetic Node path")
    runtime = AgentRuntime(full_mode=True, providers=Keys(), library=MagicMock(), runtime_dir=tmp_path, node_executable=node)
    temporary = MagicMock()
    temporary.name = str(tmp_path / "probe-cwd")
    monkeypatch.setattr(agent_runtime.tempfile, "TemporaryDirectory", lambda **kwargs: temporary)
    command = MagicMock()
    monkeypatch.setattr(agent_runtime._external_process, "run", command)
    yield runtime, command, temporary
    runtime.close()


def node_version():
    return subprocess.CompletedProcess(["node", "--version"], 0, "v22.19.0\n", "")


def sdk_result(stdout, returncode=0):
    return subprocess.CompletedProcess(["node", "worker.mjs", "--check"], returncode, stdout, "synthetic-sdk-stderr-must-not-return")


def assert_safe_probe(info):
    text = json.dumps(info)
    assert "synthetic-sdk-secret-must-not-return" not in text
    assert "synthetic-sdk-stderr-must-not-return" not in text
    assert not any(key in info for key in ("stdout", "stderr", "error", "message", "path", "traceback"))


@pytest.mark.parametrize("stage", ["node_version", "sdk_execution"])
def test_dependency_timeouts_preserve_phase_without_exception_output(dependency_probe, stage):
    runtime, command, temporary = dependency_probe
    timeout = subprocess.TimeoutExpired(["synthetic-sdk-secret-must-not-return"], 15,
                                         output="synthetic-sdk-secret-must-not-return", stderr="synthetic-sdk-secret-must-not-return")
    command.side_effect = [timeout] if stage == "node_version" else [node_version(), timeout]
    info = runtime._dependency_info()
    assert info["probe_stage"] == stage and info["probe_code"] == "timeout"
    assert info["reason_code"] == "agent_sdk_missing"
    if stage == "sdk_execution":
        assert info["node_probe_exit_code"] == 0
        temporary.cleanup.assert_called_once()
    assert_safe_probe(info)


def test_dependency_setup_os_error_has_only_safe_numeric_code(dependency_probe, monkeypatch):
    runtime, command, _ = dependency_probe
    command.return_value = node_version()
    error = PermissionError(13, "synthetic-sdk-secret-must-not-return")
    monkeypatch.setattr(agent_runtime.tempfile, "TemporaryDirectory", MagicMock(side_effect=error))
    info = runtime._dependency_info()
    assert info["probe_stage"] == "sdk_setup" and info["probe_code"] == "os_error"
    assert info["probe_os_error"] == 13 and info["node_probe_exit_code"] == 0
    assert_safe_probe(info)


def test_dependency_cleanup_winerror_is_distinct_from_sdk_execution(dependency_probe):
    runtime, command, temporary = dependency_probe
    command.side_effect = [node_version(), sdk_result(json.dumps({"available": True, "sdk_version": SDK_VERSION, "models": {}}))]
    error = OSError(13, "synthetic-sdk-secret-must-not-return")
    error.winerror = 32
    temporary.cleanup.side_effect = error
    info = runtime._dependency_info()
    assert info["probe_stage"] == "sdk_cleanup" and info["probe_code"] == "os_error"
    assert info["probe_os_error"] == 32 and info["sdk_probe_exit_code"] == 0
    assert info["probe_stdout_bytes"] > 0 and info["probe_empty_output"] is False
    assert_safe_probe(info)


def test_dependency_cleanup_cannot_mask_the_original_execution_timeout(dependency_probe):
    runtime, command, temporary = dependency_probe
    command.side_effect = [node_version(), subprocess.TimeoutExpired(["node"], 15, output="synthetic-sdk-secret-must-not-return")]
    temporary.cleanup.side_effect = OSError(13, "synthetic-sdk-secret-must-not-return")
    info = runtime._dependency_info()
    assert info["probe_stage"] == "sdk_execution" and info["probe_code"] == "timeout"
    assert "probe_os_error" not in info
    assert_safe_probe(info)


@pytest.mark.parametrize("stdout,code", [("", "invalid_json"), ("synthetic-sdk-secret-must-not-return", "invalid_json"), ("[]", "invalid_schema")])
def test_dependency_json_failures_reveal_only_size_and_empty_state(dependency_probe, stdout, code):
    runtime, command, _ = dependency_probe
    command.side_effect = [node_version(), sdk_result(stdout)]
    info = runtime._dependency_info()
    assert info["probe_stage"] == "sdk_json" and info["probe_code"] == code
    assert info["sdk_probe_exit_code"] == info["probe_exit_code"] == 0
    assert info["probe_stdout_bytes"] == len(stdout.encode())
    assert info["probe_empty_output"] is (stdout == "")
    assert_safe_probe(info)


@pytest.mark.parametrize("controlled", [False, True])
def test_nonzero_worker_output_accepts_only_fixed_stage_and_code(dependency_probe, controlled):
    runtime, command, _ = dependency_probe
    payload = {"probe_stage": "sdk_import" if controlled else "synthetic-sdk-secret-must-not-return",
               "probe_code": "ERR_DLOPEN_FAILED" if controlled else "synthetic-sdk-secret-must-not-return",
               "error": {"message": "synthetic-sdk-secret-must-not-return"}}
    command.side_effect = [node_version(), sdk_result(json.dumps(payload), 1)]
    info = runtime._dependency_info()
    assert info["probe_stage"] == ("sdk_import" if controlled else "sdk_json")
    assert info["probe_code"] == ("ERR_DLOPEN_FAILED" if controlled else "process_exit")
    assert info["node_probe_exit_code"] == 0 and info["sdk_probe_exit_code"] == info["probe_exit_code"] == 1
    assert_safe_probe(info)


def test_successful_dependency_probe_schema_and_timeouts_stay_unchanged(dependency_probe):
    runtime, command, _ = dependency_probe
    models = {"openai": [{"id": "synthetic-model"}]}
    command.side_effect = [node_version(), sdk_result(json.dumps({"available": True, "sdk_version": SDK_VERSION, "models": models}))]
    info = runtime._dependency_info()
    assert info == {"available": True, "node_version": "22.19.0", "sdk_version": SDK_VERSION, "models": models}
    assert [call.kwargs["timeout"] for call in command.call_args_list] == [5, 15]


def test_invalid_node_version_never_returns_raw_version_stdout(dependency_probe):
    runtime, command, temporary = dependency_probe
    command.return_value = sdk_result("synthetic-sdk-secret-must-not-return", 0)
    info = runtime._dependency_info()
    assert info["reason_code"] == "agent_node_unavailable"
    assert info["probe_stage"] == "node_version" and info["probe_code"] == "invalid_node_version"
    assert info["node_probe_exit_code"] == info["probe_exit_code"] == 0
    temporary.cleanup.assert_not_called()
    assert_safe_probe(info)
