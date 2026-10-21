"""Explicitly approved, app-owned HTTP Relay process; no browser or service install."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from typing import Any, Callable
import uuid

from mdtero import _external_process
from mdtero.client import MdteroClient
from mdtero.config import MdteroConfig


class RelayError(ValueError):
    def __init__(self, reason_code: str, action_hint: str) -> None:
        super().__init__(action_hint)
        self.reason_code = reason_code
        self.action_hint = self.hint = action_hint


class RelayRuntime:
    def __init__(self, *, config: MdteroConfig, runtime_dir: Path | None = None,
                 online_check: Callable[[], bool | None] | None = None, stop_timeout: float = 2) -> None:
        self.config = config
        self.runtime_dir = Path(runtime_dir) if runtime_dir is not None else None
        self._online_check = online_check or self._cloud_online
        self._stop_timeout = min(max(float(stop_timeout), 0.05), 3)
        self._lock = threading.RLock()
        self._process: subprocess.Popen | None = None
        self._temporary: tempfile.TemporaryDirectory | None = None
        self._closed = False
        self._reason: str | None = None
        self._state = "stopped"
        self._label = "Mdtero Connect " + uuid.uuid4().hex[:12]

    def _binary(self) -> Path | None:
        runtime = self.runtime_dir
        if runtime is None or not runtime.is_absolute() or not runtime.is_dir():
            return None
        binary = runtime / "relay" / ("mdtero-relay.exe" if os.name == "nt" else "mdtero-relay")
        if not binary.is_file() or not binary.resolve().is_relative_to(runtime.resolve()):
            return None
        return binary.resolve()

    def _cloud_online(self) -> bool | None:
        try:
            value = MdteroClient(config=self.config, timeout=2)._request("GET", "/api/v1/relay/status")
        except Exception:
            return None
        if not isinstance(value, dict) or type(value.get("connected")) is not bool:
            return None
        return value["connected"]

    def _release_temporary(self) -> bool:
        if self._temporary is not None:
            try:
                self._temporary.cleanup()
            except OSError:
                return False
            self._temporary = None
        return True

    def _refresh(self) -> None:
        if self._process is not None and self._process.poll() is not None:
            self._process.wait()
            self._process = None
            self._release_temporary()
            self._state, self._reason = "failed", "relay_exited"

    def status(self) -> dict[str, Any]:
        with self._lock:
            self._refresh()
            available = self._binary() is not None
            running = self._process is not None
            reason = "relay_closed" if self._closed else "relay_not_bundled" if not available else self._reason
            hints = {
                "relay_closed": "Connect has stopped. Reopen the client before starting its Relay.",
                "relay_not_bundled": "This client has no bundled Relay. Use a native debug client with its runtime resources.",
                "relay_external_online": "Another Relay is already online for this account. Keep using it or stop it yourself before starting Connect Relay.",
                "relay_status_unavailable": "Connect could not verify that the account has no active Relay. Check connectivity and retry.",
                "relay_exited": "The Connect Relay process stopped. Review account connectivity, then explicitly start it again.",
                "relay_start_failed": "The bundled Relay could not start. Rebuild or reinstall this debug client.",
                "relay_stop_failed": "Connect could not finish stopping its Relay. Retry Stop or close the client.",
            }
            return {"available": available, "running": running, "managed_by_connect": running,
                    "state": "closed" if self._closed else "unavailable" if not available else self._state,
                    "browser_enabled": False, "auto_start": False, "confirmation_required": True,
                    "reason_code": reason, "action_hint": hints.get(reason, "Starting Relay lets this account send supported publisher HTTP requests through this computer. Online transport does not prove full-text entitlement.")}

    @staticmethod
    def _consent(allow_campus_transport: bool) -> None:
        if allow_campus_transport is not True:
            raise RelayError("relay_confirmation_required", "Explicitly allow this computer to carry the account's campus HTTP traffic before starting Relay.")

    def _preflight(self, *, wait_for_offline: bool = False) -> None:
        deadline = time.monotonic() + (2 if wait_for_offline else 0)
        while True:
            try:
                online = self._online_check()
            except Exception:
                online = None
            if online is False:
                return
            if online is not True:
                self._reason = "relay_status_unavailable"
                raise RelayError(self._reason, self.status()["action_hint"])
            if not wait_for_offline or time.monotonic() >= deadline:
                self._reason = "relay_external_online"
                raise RelayError(self._reason, self.status()["action_hint"])
            time.sleep(0.1)

    def _environment(self, directory: Path, key: str) -> dict[str, str]:
        # Deliberately exclude provider keys, proxies, browser tokens/CDP URLs,
        # profile paths, install flags and inherited Relay config directories.
        allowed = ("SystemRoot", "SYSTEMROOT", "WINDIR", "TMP", "TEMP", "TMPDIR", "LANG")
        env = {name: os.environ[name] for name in allowed if name in os.environ}
        env.update({"PATH": os.defpath, "MDTERO_API_KEY": key,
                    "MDTERO_API_URL": self.config.api_base_url.rstrip("/"),
                    "MDTERO_RELAY_CONFIG_DIR": str(directory), "MDTERO_LOCAL_BROWSER": "off",
                    "MDTERO_DISABLE_LOCAL_ACCESS": "1"})
        return env

    def _spawn(self, binary: Path, env: dict[str, str], directory: Path) -> subprocess.Popen:
        return _external_process.popen([str(binary), "serve", "--label", self._label],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                cwd=directory, env=env,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

    def _start(self, *, wait_for_offline: bool = False) -> dict[str, Any]:
        if self._closed:
            raise RelayError("relay_closed", self.status()["action_hint"])
        self._refresh()
        if self._process is not None:
            return self.status()
        binary = self._binary()
        if binary is None:
            raise RelayError("relay_not_bundled", self.status()["action_hint"])
        key = self.config.effective_api_key
        if not key:
            raise RelayError("auth_missing", "Sign in to the Mdtero account before starting its Relay.")
        self._preflight(wait_for_offline=wait_for_offline)
        temporary = tempfile.TemporaryDirectory(prefix="mdtero-connect-relay-")
        try:
            directory = Path(temporary.name)
            # Go's missing-config early return otherwise resets browser mode to
            # auto. This isolated file contains policy only, never credentials.
            policy = directory / "config.json"
            descriptor = os.open(policy, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump({"local_browser": "off"}, stream)
            self._process = self._spawn(binary, self._environment(directory, key), directory)
            self._temporary = temporary
            self._state, self._reason = "running", None
        except Exception:
            temporary.cleanup()
            self._state, self._reason = "failed", "relay_start_failed"
            raise RelayError(self._reason, self.status()["action_hint"]) from None
        return self.status()

    def start(self, allow_campus_transport: bool = False) -> dict[str, Any]:
        self._consent(allow_campus_transport)
        with self._lock:
            return self._start()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            process, self._process = self._process, None
            try:
                if process is not None:
                    if process.poll() is None:
                        try:
                            process.terminate()
                        except OSError:
                            pass
                    try:
                        process.wait(timeout=self._stop_timeout)
                    except subprocess.TimeoutExpired:
                        try:
                            process.kill()
                        except OSError:
                            pass
                        process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                # Preserve ownership if an OS process cannot yet be reaped;
                # callers can retry and the native parent still owns its Job/group.
                if process is not None and process.poll() is None:
                    self._process = process
            finally:
                cleaned = self._release_temporary() if self._process is None else False
                self._state, self._reason = ("stopped", None) if cleaned else ("failed", "relay_stop_failed")
            return self.status()

    def restart(self, allow_campus_transport: bool = False) -> dict[str, Any]:
        self._consent(allow_campus_transport)
        with self._lock:
            was_owned = self._process is not None
            self.stop()
            if self._process is not None:
                raise RelayError("relay_stop_failed", self.status()["action_hint"])
            return self._start(wait_for_offline=was_owned)

    def close(self) -> None:
        with self._lock:
            self.stop()
            self._closed = True
