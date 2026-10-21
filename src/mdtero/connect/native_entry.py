"""Private stdio-supervised entry point for the Connect desktop bridge.

The native shell owns this process and its process group/job. This module never
opens a browser, chooses a public bind address, or searches PATH for bundled Node.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Any

from mdtero.client import MdteroClient
from mdtero.connect.agent_runtime import AgentRuntime
from mdtero.connect.bridge import ConnectBridge
from mdtero.connect.library import LibraryClient
from mdtero.connect.native_login import NativeLoginError, login_account
from mdtero.connect.providers import ProviderStore
from mdtero.connect.relay_runtime import RelayRuntime


class NativeStartupError(ValueError):
    def __init__(self, reason_code: str, hint: str) -> None:
        super().__init__(hint)
        self.reason_code = reason_code
        self.hint = hint


def _static_dir() -> Path:
    here = Path(__file__).resolve()
    candidates = [here.parent / "static"]
    if getattr(sys, "frozen", False):
        # PyInstaller places the executed entry script at _MEIPASS's root;
        # package data retains the mdtero/connect/static destination.
        bundle_root = getattr(sys, "_MEIPASS", None)
        candidates = [Path(bundle_root) / "mdtero" / "connect" / "static"] if bundle_root else []
    else:
        candidates.append(here.parents[3] / "connect" / "app")
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    raise NativeStartupError("native_ui_missing", "The bundled Connect UI is missing. Rebuild or reinstall this debug client.")


def _full_assets(runtime_dir: Path | None) -> tuple[Path, Path]:
    if runtime_dir is None or not runtime_dir.is_absolute() or not runtime_dir.is_dir():
        raise NativeStartupError("native_runtime_missing", "Full mode requires the bundled absolute runtime directory. Use the basic client or rebuild the full debug client.")
    runtime = runtime_dir.resolve()
    node = runtime / "node" / ("node.exe" if os.name == "nt" else "node")
    agent = runtime / "agent"
    if not node.is_file() or not node.resolve().is_relative_to(runtime):
        raise NativeStartupError("native_node_missing", "The bundled Node runtime is missing. Use the basic client or rebuild the full debug client.")
    if not (agent / "worker.mjs").is_file() or not (agent / "node_modules" / "@earendil-works" / "pi-coding-agent" / "package.json").is_file() or not agent.resolve().is_relative_to(runtime):
        raise NativeStartupError("native_agent_missing", "The bundled Pi dependencies are missing. Rebuild the full debug client with its pinned dependencies.")
    return agent, node


def _watch_parent(stopped: threading.Event) -> None:
    try:
        if sys.stdin is None:
            stopped.set()
            return
        while True:
            line = sys.stdin.readline()
            if not line or line.strip() == "shutdown":
                stopped.set()
                return
    except (OSError, ValueError):
        stopped.set()


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _windows_job_api() -> Any:
    import ctypes
    from ctypes import wintypes

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenJobObjectW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    api.OpenJobObjectW.restype = wintypes.HANDLE
    api.GetCurrentProcess.argtypes = []
    api.GetCurrentProcess.restype = wintypes.HANDLE
    api.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
    api.IsProcessInJob.restype = wintypes.BOOL
    api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    api.AssignProcessToJobObject.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    return api


def _join_parent_job(name: str | None) -> None:
    if sys.platform != "win32":
        if name:
            raise NativeStartupError("native_job_unsupported", "A Windows parent job cannot be used on this operating system.")
        return
    if not name:
        if getattr(sys, "frozen", False):
            raise NativeStartupError("native_job_required", "Open this bundled bridge through Mdtero Connect so its lifetime is supervised.")
        return
    if not name.startswith("Local\\MdteroConnect-") or len(name) > 200:
        raise NativeStartupError("native_job_invalid", "The native parent job name is invalid. Restart Mdtero Connect.")
    import ctypes
    from ctypes import wintypes

    try:
        api = _windows_job_api()
        # A onefile bootloader can start Python before Rust assigns the outer
        # bootloader to its Job. Join explicitly before any listener/worker starts.
        job = api.OpenJobObjectW(0x0001 | 0x0004, False, name)  # ASSIGN_PROCESS | QUERY
        if not job:
            raise NativeStartupError("native_job_unavailable", "The native parent has stopped. Restart Mdtero Connect.")
        try:
            current = api.GetCurrentProcess()
            joined = wintypes.BOOL()
            if not api.IsProcessInJob(current, job, ctypes.byref(joined)):
                raise NativeStartupError("native_job_assignment_failed", "Connect could not verify its supervised process lifetime. Restart the client.")
            if not joined.value and not api.AssignProcessToJobObject(job, current):
                raise NativeStartupError("native_job_assignment_failed", "Connect could not join its supervised process lifetime. Restart the client.")
        finally:
            # The Rust parent must own the persistent handle. Keeping a child
            # handle would defeat JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE on crashes.
            api.CloseHandle(job)
    except NativeStartupError:
        raise
    except Exception:
        raise NativeStartupError("native_job_assignment_failed", "Connect could not establish its supervised process lifetime. Restart the client.") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Supervised Mdtero Connect desktop bridge")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--login", action="store_true", help="Open account login in the system browser, verify and save it locally, then exit.")
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--job-name", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        _join_parent_job(args.job_name)
    except NativeStartupError as exc:
        _emit({"status": "error", "reason_code": exc.reason_code, "action_hint": exc.hint, "protocol": 1})
        return 1
    stopped = threading.Event()
    previous_handlers: dict[int, Any] = {}
    bridge: ConnectBridge | None = None
    # Register these before constructing dependencies, so a parent that closes
    # during startup cannot leave an unmanaged listening process behind.
    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.signal(signum, lambda *_: stopped.set())
    threading.Thread(target=_watch_parent, args=(stopped,), name="connect-native-parent", daemon=True).start()
    try:
        if args.login:
            if stopped.is_set():
                return 0
            login_account(stopped)
            _emit({"status": "authenticated", "product": "mdtero-connect", "protocol": 1})
            return 0
        if not 0 <= args.port <= 65535:
            raise NativeStartupError("native_port_invalid", "The local port must be between 0 and 65535.")
        # Native UI assets come from the reviewed application bundle, never an
        # inherited environment override or the caller's working directory.
        os.environ.pop("MDTERO_CONNECT_APP_DIR", None)
        runtime_kwargs: dict[str, Any] = {}
        if args.full:
            agent, node = _full_assets(args.runtime_dir)
            runtime_kwargs = {"runtime_dir": agent, "node_executable": node}
        if stopped.is_set():
            return 0
        client = MdteroClient()
        providers = ProviderStore(config=client.config)
        runtime = AgentRuntime(full_mode=args.full, providers=providers, library=LibraryClient(client), **runtime_kwargs)
        relay_runtime = RelayRuntime(config=client.config, runtime_dir=args.runtime_dir)
        bridge = ConnectBridge(host="127.0.0.1", port=args.port, client=client, static_dir=_static_dir(), providers=providers, agent_runtime=runtime, relay_runtime=relay_runtime)
        if stopped.is_set():
            return 0
        url = bridge.start()
        _emit({"status": "running", "url": url, "host": "127.0.0.1", "port": bridge.bound_port,
               "product": "mdtero-connect", "mode": "full" if args.full else "library", "protocol": 1})
        stopped.wait()
        return 0
    except (NativeStartupError, NativeLoginError) as exc:
        _emit({"status": "error", "reason_code": exc.reason_code, "action_hint": exc.hint, "protocol": 1})
        return 1
    except Exception:
        # Do not serialize exception bodies, provider errors, configuration or
        # inherited environment: the parent needs an actionable safe summary.
        _emit({"status": "error", "reason_code": "native_start_failed", "action_hint": "The local Connect bridge could not start. Close another debug client or rebuild this client.", "protocol": 1})
        return 1
    finally:
        if bridge is not None:
            bridge.stop()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
