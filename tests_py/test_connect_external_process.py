from __future__ import annotations

import subprocess
import sys
import threading
import time
from unittest.mock import MagicMock

import pytest

from mdtero import _external_process as external


@pytest.fixture
def frozen_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", "C:\\temporary\\bundle", raising=False)
    directory = {"value": sys._MEIPASS}
    trace = []

    def set_directory(value):
        directory["value"] = value
        trace.append(value)
        return True

    monkeypatch.setattr(external, "_dll_api", lambda: set_directory)
    return directory, trace


def test_frozen_windows_restores_before_caller_can_use_child(monkeypatch, frozen_windows):
    directory, trace = frozen_windows
    child = MagicMock()
    env = {"PATH": "C:\\temporary\\bundle;C:\\temporary\\bundle\\libraries;C:\\Windows\\System32", "SELECTED": "retained"}

    def spawn(*args, **kwargs):
        assert directory["value"] is None
        assert kwargs["env"] == {"PATH": "C:\\Windows\\System32", "SELECTED": "retained"}
        return child

    monkeypatch.setattr(subprocess, "Popen", spawn)
    assert external.popen(["trusted-node.exe"], env=env) is child
    assert trace == [None, sys._MEIPASS]
    assert directory["value"] == sys._MEIPASS
    assert env["PATH"].startswith("C:\\temporary\\bundle;")


def test_frozen_spawn_failure_still_restores_dll_search(monkeypatch, frozen_windows):
    directory, trace = frozen_windows
    monkeypatch.setattr(subprocess, "Popen", MagicMock(side_effect=OSError("synthetic spawn failure")))
    with pytest.raises(OSError):
        external.popen(["trusted-node.exe"])
    assert directory["value"] == sys._MEIPASS and trace == [None, sys._MEIPASS]


def test_frozen_empty_child_environment_does_not_inherit_parent_secrets(monkeypatch, frozen_windows):
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-synthetic-secret")
    spawn = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(subprocess, "Popen", spawn)
    external.popen(["trusted-node.exe"], env={})
    assert spawn.call_args.kwargs["env"] == {}


def test_failed_restore_reaps_the_child_before_returning_error(monkeypatch, frozen_windows):
    child = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: child)
    monkeypatch.setattr(external, "_dll_api", lambda: lambda value: value is None)
    with pytest.raises(external.ExternalProcessError, match="restore"):
        external.popen(["trusted-node.exe"])
    child.kill.assert_called_once()
    child.wait.assert_called_once_with(timeout=5)


def test_failed_dll_reset_cannot_launch_any_child(monkeypatch, frozen_windows):
    spawn = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", spawn)
    monkeypatch.setattr(external, "_dll_api", lambda: lambda value: False)
    with pytest.raises(external.ExternalProcessError, match="prepare"):
        external.popen(["trusted-node.exe"])
    spawn.assert_not_called()


def test_concurrent_spawns_cannot_interleave_process_global_dll_windows(monkeypatch, frozen_windows):
    directory, trace = frozen_windows

    def spawn(*args, **kwargs):
        assert directory["value"] is None
        time.sleep(0.02)
        assert directory["value"] is None
        return MagicMock()

    monkeypatch.setattr(subprocess, "Popen", spawn)
    errors = []

    def start():
        try:
            external.popen(["trusted-node.exe"])
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=start) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
    assert not errors and all(not thread.is_alive() for thread in threads)
    assert trace == [None, sys._MEIPASS] * 3


def test_run_waits_with_the_original_dll_directory_restored(monkeypatch, frozen_windows):
    directory, _ = frozen_windows
    child = MagicMock()
    child.__enter__.return_value = child
    child.args = ["trusted-node.exe"]
    child.poll.return_value = 0

    def communicate(*args, **kwargs):
        assert directory["value"] == sys._MEIPASS
        return "v22.19.0\n", ""

    child.communicate.side_effect = communicate
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: child)
    result = external.run(child.args, capture_output=True, text=True, timeout=5)
    assert result.stdout == "v22.19.0\n" and result.returncode == 0


def test_real_probe_output_input_and_nonzero_checks_match_subprocess_run():
    result = external.run([sys.executable, "-c", "import sys;sys.stdout.write(sys.stdin.read())"],
                          input="synthetic probe", capture_output=True, text=True, check=True, timeout=3)
    assert result.stdout == "synthetic probe" and result.stderr == "" and result.returncode == 0
    with pytest.raises(subprocess.CalledProcessError) as caught:
        external.run([sys.executable, "-c", "import sys;sys.stderr.write('synthetic failure');sys.exit(7)"],
                     capture_output=True, text=True, check=True, timeout=3)
    assert caught.value.returncode == 7 and caught.value.stderr == "synthetic failure"


def test_real_probe_timeout_reaps_the_child(monkeypatch):
    children = []
    original = external.popen

    def capture(*args, **kwargs):
        child = original(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(external, "popen", capture)
    with pytest.raises(subprocess.TimeoutExpired):
        external.run([sys.executable, "-c", "import time;time.sleep(30)"], capture_output=True, timeout=0.1)
    assert len(children) == 1 and children[0].poll() is not None
