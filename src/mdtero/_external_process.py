"""Start external programs without inheriting a frozen Windows DLL search path."""

from __future__ import annotations

from contextlib import contextmanager
import ctypes
import ntpath
import os
import subprocess
import sys
import threading
from typing import Any


_DLL_LOCK = threading.RLock()


class ExternalProcessError(OSError):
    """Fixed, credential-free error suitable for higher-level safe mapping."""


def _dll_api() -> Any:
    from ctypes import wintypes

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.SetDllDirectoryW.argtypes = [wintypes.LPCWSTR]
    api.SetDllDirectoryW.restype = wintypes.BOOL
    return api.SetDllDirectoryW


@contextmanager
def _external_dll_search():
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        yield
        return
    bundle = getattr(sys, "_MEIPASS", None)
    if not isinstance(bundle, str) or not bundle:
        raise ExternalProcessError("The frozen runtime DLL search path is unavailable.")
    # SetDllDirectory is process-global. Serialize our spawn windows and restore
    # immediately after CreateProcess, while HTTP/Agent work continues normally.
    with _DLL_LOCK:
        set_directory = _dll_api()
        if not set_directory(None):
            raise ExternalProcessError("Could not prepare the external process DLL search path.")
        try:
            yield
        finally:
            if not set_directory(bundle):
                raise ExternalProcessError("Could not restore the frozen runtime DLL search path.")


def popen(*args, **kwargs) -> subprocess.Popen:
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        bundle = getattr(sys, "_MEIPASS", None)
        if isinstance(bundle, str) and bundle:
            # Some frozen dependency hooks also prepend bundle DLL directories
            # to PATH. Remove those from the child's copy, never the parent env.
            source = kwargs.get("env")
            env = dict(os.environ if source is None else source)
            root = ntpath.normcase(ntpath.normpath(bundle)).rstrip("\\")
            if "PATH" in env:
                entries = env["PATH"].split(";")
                env["PATH"] = ";".join(entry for entry in entries
                    if (normalized := ntpath.normcase(ntpath.normpath(entry.strip('"')))) != root
                    and not normalized.startswith(root + "\\"))
            kwargs["env"] = env
    process = None
    try:
        with _external_dll_search():
            process = subprocess.Popen(*args, **kwargs)
        return process
    except BaseException:
        # If restoration failed after spawn, ownership never reaches the caller.
        # Reap the child here rather than leaving an unregistered model process.
        if process is not None:
            try:
                process.kill()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
        raise


def run(*args, input=None, capture_output=False, timeout=None, check=False, **kwargs) -> subprocess.CompletedProcess:
    """The subprocess.run operations used by probes, with only spawn sanitized."""
    if input is not None:
        if kwargs.get("stdin") is not None:
            raise ValueError("stdin and input arguments may not both be used")
        kwargs["stdin"] = subprocess.PIPE
    if capture_output:
        if kwargs.get("stdout") is not None or kwargs.get("stderr") is not None:
            raise ValueError("stdout and stderr arguments may not be used with capture_output")
        kwargs["stdout"] = kwargs["stderr"] = subprocess.PIPE
    with popen(*args, **kwargs) as process:
        try:
            stdout, stderr = process.communicate(input, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            exc.output, exc.stderr = process.communicate()
            raise
        except BaseException:
            process.kill()
            raise
        returncode = process.poll()
        if check and returncode:
            raise subprocess.CalledProcessError(returncode, process.args, output=stdout, stderr=stderr)
        return subprocess.CompletedProcess(process.args, returncode, stdout, stderr)
