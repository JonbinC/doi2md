"""Exercise native exports and process cleanup without an account or paid API."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import queue
import selectors
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time


class SmokeError(RuntimeError):
    pass


def _environment(root: Path) -> dict[str, str]:
    allowed = ("SystemRoot", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "DISPLAY",
               "WAYLAND_DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR", "LANG",
               "LC_ALL", "GDK_BACKEND", "LIBGL_ALWAYS_SOFTWARE", "WEBKIT_DISABLE_COMPOSITING_MODE")
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env.update({"PATH": os.defpath, "MDTERO_CONFIG_DIR": str(root / "account"),
                "MDTERO_API_URL": "http://127.0.0.1:9", "MDTERO_SITE_URL": "https://example.invalid",
                "XDG_CONFIG_HOME": str(root / "config"), "XDG_DATA_HOME": str(root / "data"),
                "XDG_CACHE_HOME": str(root / "cache"), "APPDATA": str(root / "appdata"),
                "LOCALAPPDATA": str(root / "localappdata"),
                "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring"})
    config = root / "config"
    config.mkdir()
    downloads = root / "Downloads"
    downloads.mkdir()
    # An absolute user-dirs entry isolates exports without changing the user's
    # HOME. Rust's Linux download_dir honors this XDG configuration.
    (config / "user-dirs.dirs").write_text(f'XDG_DOWNLOAD_DIR="{downloads}"\n', encoding="utf-8")
    return env


@contextmanager
def _display(headless: bool, env: dict[str, str]):
    if not headless:
        yield env
        return
    if not sys.platform.startswith("linux"):
        raise SmokeError("headless_requires_linux")
    xvfb = shutil.which("Xvfb", path=os.defpath)
    if not xvfb:
        raise SmokeError("xvfb_unavailable")
    read_fd, write_fd = os.pipe()
    server = None
    try:
        server = subprocess.Popen([xvfb, "-displayfd", str(write_fd), "-screen", "0", "1280x900x24", "-nolisten", "tcp"],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  pass_fds=(write_fd,), env=env, start_new_session=True)
        os.close(write_fd)
        write_fd = -1
        with selectors.DefaultSelector() as selector:
            selector.register(read_fd, selectors.EVENT_READ)
            if not selector.select(timeout=10):
                raise SmokeError("xvfb_start_timeout")
        display = os.read(read_fd, 64).decode("ascii").strip()
        if not display.isdecimal() or server.poll() is not None:
            raise SmokeError("xvfb_start_failed")
        yield {**env, "DISPLAY": ":" + display}
    finally:
        os.close(read_fd)
        if write_fd != -1:
            os.close(write_fd)
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=3)


def _pid_running(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.WaitForSingleObject.restype = wintypes.DWORD
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return False
        try:
            return api.WaitForSingleObject(handle, 0) == 0x00000102  # WAIT_TIMEOUT
        finally:
            api.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        if sys.platform.startswith("linux"):
            try:
                state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].strip().split()[0]
                if state == "Z":
                    return False
            except (OSError, IndexError):
                pass
        return True
    except ProcessLookupError:
        return False


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def _wait_bridge_stopped(ready: dict, timeout: float = 8) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _port_open(ready["port"]) and not _pid_running(ready["pid"]):
            return True
        time.sleep(0.05)
    return False


def _cleanup_bridge(ready: dict | None) -> None:
    if not ready or not (_pid_running(ready["pid"]) or _port_open(ready["port"])):
        return
    if os.name != "nt":
        try:
            os.killpg(ready["pid"], signal.SIGKILL)
        except ProcessLookupError:
            pass
    # On Windows the killed native parent's Job closes all trusted descendants.


def _direct_children(pid: int) -> list[int]:
    if sys.platform.startswith("linux"):
        try:
            return [int(item) for item in Path(f"/proc/{pid}/task/{pid}/children").read_text().split()]
        except (OSError, ValueError):
            return []
    if os.name != "nt":
        try:
            output = subprocess.check_output(["/bin/ps", "-axo", "pid=,ppid="], text=True, timeout=2)
            return [int(fields[0]) for line in output.splitlines() if len(fields := line.split()) == 2 and int(fields[1]) == pid]
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return []


def _read_events(stream, events: queue.Queue) -> None:
    try:
        for line in stream:
            if len(line) > 8192:
                continue
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                events.put(value)
    finally:
        events.put(None)


def run_check(binary: Path, env: dict[str, str], *, timeout: float, crash: bool) -> dict:
    command = [str(binary)] + ([] if crash else ["--smoke-export"])
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                               env=env, start_new_session=os.name != "nt")
    events: queue.Queue = queue.Queue()
    threading.Thread(target=_read_events, args=(process.stdout, events), daemon=True).start()
    ready = None
    loaded = exported = False
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                event = events.get(timeout=min(0.2, max(0.001, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if event is None:
                break
            if event.get("event") == "bridge_ready":
                port, pid = event.get("port"), event.get("pid")
                if type(port) is not int or not 0 < port < 65536 or type(pid) is not int or pid <= 0:
                    raise SmokeError("invalid_native_ready_event")
                ready = {"port": port, "pid": pid}
                if crash:
                    process.kill()  # The actual native parent, never an xvfb-run wrapper.
                    process.wait(timeout=5)
                    break
            elif event.get("event") == "native_smoke_passed":
                loaded = event.get("webview_loaded") is True
            elif event.get("event") == "native_export_smoke_passed":
                exported = event.get("verified_bytes") is True
        else:
            raise SmokeError("native_smoke_timeout")
        if not ready:
            raise SmokeError("native_bridge_not_ready")
        if not crash:
            try:
                exit_code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                raise SmokeError("native_export_did_not_exit") from None
            if exit_code or not loaded or not exported:
                raise SmokeError("native_export_not_verified")
        if not _wait_bridge_stopped(ready):
            raise SmokeError("native_bridge_survived_parent")
        return {"check": "parent_crash" if crash else "native_export", "passed": True,
                "bridge_stopped": True, **({} if crash else {"webview_loaded": loaded, "verified_bytes": exported})}
    finally:
        children = _direct_children(process.pid) if process.poll() is None else []
        if process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        _cleanup_bridge(ready)
        if os.name != "nt":
            # Managed sidecars create their own process groups. Capture trusted
            # direct children before timeout cleanup, even if handshake never ran.
            for pid in children:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process.stdout:
            process.stdout.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--crash-check", action="store_true", help="Also kill a second native parent and verify automatic bridge cleanup.")
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()
    if not args.binary.is_file() or not math.isfinite(args.timeout) or args.timeout <= 0:
        print(json.dumps({"status": "failed", "reason_code": "invalid_smoke_arguments"}))
        return 1
    try:
        with tempfile.TemporaryDirectory(prefix="mdtero-native-smoke-") as temporary:
            with _display(args.headless, _environment(Path(temporary))) as env:
                checks = [run_check(args.binary.resolve(), env, timeout=args.timeout, crash=False)]
                if args.crash_check:
                    checks.append(run_check(args.binary.resolve(), env, timeout=args.timeout, crash=True))
        print(json.dumps({"status": "passed", "checks": checks}))
        return 0
    except (SmokeError, OSError, subprocess.SubprocessError) as exc:
        reason = str(exc) if isinstance(exc, SmokeError) else "native_smoke_process_failed"
        print(json.dumps({"status": "failed", "reason_code": reason}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
