from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from unittest.mock import MagicMock

import pytest

from mdtero.config import MdteroConfig
from mdtero.client import MdteroClient
from mdtero.connect.relay_runtime import RelayError, RelayRuntime


SECRET = "synthetic-relay-account-key"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def relay(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    (runtime / "relay").mkdir(parents=True)
    (runtime / "relay" / ("mdtero-relay.exe" if os.name == "nt" else "mdtero-relay")).write_bytes(b"synthetic trusted program")
    worker = tmp_path / "synthetic_child.py"
    receipt = tmp_path / "receipt.json"
    worker.write_text('''import json,os,pathlib,signal,sys,time
env=os.environ
assert env['MDTERO_API_KEY']=='synthetic-relay-account-key'
assert env['MDTERO_LOCAL_BROWSER']=='off' and env['MDTERO_DISABLE_LOCAL_ACCESS']=='1'
for key in ('OPENAI_API_KEY','VOYAGE_API_KEY','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','MDTERO_BROWSER_WORKER_URL','MDTERO_BROWSER_WORKER_TOKEN','MDTERO_FORCE_LOCAL_ACCESS'):
 assert key not in env,key
assert not any('synthetic-relay-account-key' in arg for arg in sys.argv)
config=pathlib.Path(env['MDTERO_RELAY_CONFIG_DIR'])/'config.json'
assert json.loads(config.read_text())=={'local_browser':'off'}
pathlib.Path(sys.argv[1]).write_text(json.dumps({'args':sys.argv[2:],'policy':str(config),'pid':os.getpid()}))
signal.signal(signal.SIGTERM,lambda *args:None)
while True:time.sleep(0.1)
''')
    for key in ("OPENAI_API_KEY", "VOYAGE_API_KEY", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "MDTERO_BROWSER_WORKER_URL", "MDTERO_BROWSER_WORKER_TOKEN", "MDTERO_FORCE_LOCAL_ACCESS"):
        monkeypatch.setenv(key, "ambient-value-must-not-reach-relay")
    online = MagicMock(return_value=False)
    instance = RelayRuntime(config=MdteroConfig(api_key=SECRET, api_base_url="http://127.0.0.1:9"),
                            runtime_dir=runtime, online_check=online, stop_timeout=0.05)
    children = []

    def spawn(binary, env, directory):
        child = subprocess.Popen([sys.executable, str(worker), str(receipt), "serve", "--label", instance._label],
                                 env=env, cwd=directory, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        children.append(child)
        return child

    monkeypatch.setattr(instance, "_spawn", MagicMock(side_effect=spawn))
    yield instance, online, children, receipt
    instance.close()
    for child in children:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=3)


def wait_receipt(path, process):
    deadline = time.monotonic() + 3
    while not path.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert path.exists(), "Synthetic child did not validate the Relay environment"
    return json.loads(path.read_text())


def test_status_is_local_and_cannot_start_or_probe_relay(relay):
    runtime, online, children, _ = relay
    status = runtime.status()
    assert status["available"] and not status["running"]
    assert status["state"] == "stopped" and not status["browser_enabled"]
    assert status["confirmation_required"] and not status["auto_start"]
    assert not children
    online.assert_not_called()
    assert SECRET not in json.dumps(status)


@pytest.mark.parametrize("consent", [False, None, 1, "true"])
def test_start_requires_boolean_user_confirmation(relay, consent):
    runtime, online, children, _ = relay
    with pytest.raises(RelayError) as caught:
        runtime.start(consent)
    assert caught.value.reason_code == "relay_confirmation_required"
    assert not children
    online.assert_not_called()


def test_real_child_has_only_account_key_and_isolated_browser_off_policy(relay):
    runtime, online, children, receipt = relay
    assert runtime.start(True)["running"]
    child = children[-1]
    evidence = wait_receipt(receipt, child)
    policy = Path(evidence["policy"])
    assert policy.read_text() == '{"local_browser": "off"}'
    assert evidence["args"][:2] == ["serve", "--label"]
    assert SECRET not in receipt.read_text()
    assert runtime.start(True)["running"] and len(children) == 1
    assert runtime.stop()["state"] == "stopped"
    assert child.poll() is not None and not policy.exists()
    assert not runtime.stop()["running"]
    online.assert_called_once()


def test_stop_does_not_touch_an_unowned_process(relay):
    runtime, _, children, receipt = relay
    other = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        runtime.start(True)
        wait_receipt(receipt, children[-1])
        runtime.stop()
        assert children[-1].poll() is not None
        assert other.poll() is None
    finally:
        other.kill()
        other.wait(timeout=3)


@pytest.mark.parametrize("online_value,reason", [(True, "relay_external_online"), (None, "relay_status_unavailable"), ({}, "relay_status_unavailable"), ("false", "relay_status_unavailable")])
def test_existing_or_unknown_cloud_connection_is_never_replaced(relay, online_value, reason):
    runtime, online, children, _ = relay
    online.return_value = online_value
    with pytest.raises(RelayError) as caught:
        runtime.start(True)
    assert caught.value.reason_code == reason
    assert not children and runtime._temporary is None
    assert not runtime.status()["running"]


def test_restart_reapproves_stops_own_child_and_waits_for_old_cloud_connection(relay):
    runtime, online, children, receipt = relay
    runtime.start(True)
    first = children[-1]
    wait_receipt(receipt, first)
    with pytest.raises(RelayError):
        runtime.restart(False)
    assert first.poll() is None
    receipt.unlink()
    online.side_effect = [True, False]
    assert runtime.restart(True)["running"]
    assert first.poll() is not None and len(children) == 2
    wait_receipt(receipt, children[-1])


def test_restart_stays_stopped_when_cloud_cannot_be_verified(relay):
    runtime, online, children, receipt = relay
    runtime.start(True)
    wait_receipt(receipt, children[-1])
    online.return_value = None
    with pytest.raises(RelayError) as caught:
        runtime.restart(True)
    assert caught.value.reason_code == "relay_status_unavailable"
    assert children[-1].poll() is not None
    assert not runtime.status()["running"] and len(children) == 1


def test_unexpected_exit_is_reported_without_automatic_restart(relay):
    runtime, online, children, receipt = relay
    runtime.start(True)
    wait_receipt(receipt, children[-1])
    children[-1].kill()
    children[-1].wait(timeout=3)
    status = runtime.status()
    assert status["state"] == "failed" and status["reason_code"] == "relay_exited"
    assert len(children) == 1 and online.call_count == 1
    assert runtime._temporary is None


def test_close_stops_and_prevents_another_child(relay):
    runtime, _, children, receipt = relay
    runtime.start(True)
    wait_receipt(receipt, children[-1])
    runtime.close()
    assert children[-1].poll() is not None
    assert runtime.status()["state"] == "closed"
    with pytest.raises(RelayError) as caught:
        runtime.start(True)
    assert caught.value.reason_code == "relay_closed"
    assert len(children) == 1


def test_missing_bundle_or_account_cannot_reach_cloud(relay, monkeypatch):
    runtime, online, children, _ = relay
    runtime.runtime_dir = None
    with pytest.raises(RelayError) as caught:
        runtime.start(True)
    assert caught.value.reason_code == "relay_not_bundled"
    runtime.runtime_dir = Path(__file__).resolve().parent
    assert not runtime.status()["available"]
    online.assert_not_called()
    assert not children


def test_missing_account_never_checks_cloud_or_starts(relay, monkeypatch):
    runtime, online, children, _ = relay
    runtime.config.api_key = None
    monkeypatch.delenv("MDTERO_API_KEY", raising=False)
    with pytest.raises(RelayError) as caught:
        runtime.start(True)
    assert caught.value.reason_code == "auth_missing"
    online.assert_not_called()
    assert not children


def test_restart_does_not_override_a_connection_that_stays_online(relay):
    runtime, online, children, receipt = relay
    runtime.start(True)
    wait_receipt(receipt, children[-1])
    online.return_value = True
    began = time.monotonic()
    with pytest.raises(RelayError) as caught:
        runtime.restart(True)
    assert caught.value.reason_code == "relay_external_online"
    assert time.monotonic() - began < 5
    assert len(children) == 1 and children[0].poll() is not None
    assert not runtime.status()["running"]


def test_exit_during_terminate_still_reaps_and_removes_policy(relay, monkeypatch):
    runtime, _, children, receipt = relay
    runtime.start(True)
    evidence = wait_receipt(receipt, children[-1])
    child = children[-1]

    def exited_before_signal():
        child.kill()
        raise ProcessLookupError("Synthetic child exited before termination")

    monkeypatch.setattr(child, "terminate", exited_before_signal)
    assert runtime.stop()["state"] == "stopped"
    assert child.poll() is not None and not Path(evidence["policy"]).exists()


@pytest.mark.parametrize("payload,expected", [({}, None), (None, None), ({"connected": 1}, None), ({"connected": "false"}, None), ({"connected": False}, False), ({"connected": True}, True)])
def test_cloud_preflight_requires_an_explicit_boolean(relay, monkeypatch, payload, expected):
    runtime, _, _, _ = relay
    monkeypatch.setattr(MdteroClient, "_request", MagicMock(return_value=payload))
    assert runtime._cloud_online() is expected


def test_spawn_errors_cannot_return_raw_error_or_leave_config(relay, monkeypatch):
    runtime, _, _, _ = relay
    monkeypatch.setattr(runtime, "_spawn", MagicMock(side_effect=OSError(SECRET)))
    with pytest.raises(RelayError) as caught:
        runtime.start(True)
    assert caught.value.reason_code == "relay_start_failed"
    assert SECRET not in str(caught.value) and SECRET not in json.dumps(runtime.status())
    assert runtime._temporary is None


def test_start_and_close_are_serialized_around_process_registration(relay):
    runtime, _, children, _ = relay
    entered, release = threading.Event(), threading.Event()

    def delayed_cloud():
        entered.set()
        assert release.wait(timeout=3)
        return False

    runtime._online_check = delayed_cloud
    start = threading.Thread(target=lambda: runtime.start(True))
    close = threading.Thread(target=runtime.close)
    start.start()
    assert entered.wait(timeout=3)
    close.start()
    release.set()
    start.join(timeout=3)
    close.join(timeout=3)
    assert not start.is_alive() and not close.is_alive()
    assert len(children) == 1 and children[0].poll() is not None
    assert runtime.status()["state"] == "closed"


def test_actual_bundled_go_relay_without_key_cannot_start_browser(tmp_path):
    runtime_dir = ROOT / "connect" / "native" / "src-tauri" / "resources" / "runtime"
    runtime = RelayRuntime(config=MdteroConfig(), runtime_dir=runtime_dir)
    binary = runtime._binary()
    if binary is None:
        pytest.skip("Prepare the matching native runtime for this real Go executable probe")
    policy = tmp_path / "config.json"
    policy.write_text('{"local_browser":"off"}')
    child = runtime._spawn(binary, runtime._environment(tmp_path, ""), tmp_path)
    try:
        assert child.wait(timeout=5) == 1
        assert sorted(item.name for item in tmp_path.iterdir()) == ["config.json"]
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=3)
