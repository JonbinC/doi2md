"""Opt-in local Pi research; frozen metadata approval, one model request, no shell tools."""

from __future__ import annotations

import copy
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mdtero import _external_process

PROVIDERS = ("openai", "anthropic", "google", "openrouter")
SDK_VERSION = "1.3.0"
MAX_INPUT_BYTES = 65536
MAX_OUTPUT_TOKENS = 4096


class AgentError(ValueError):
    """Safe local error; never forwards provider response bodies or credentials."""

    def __init__(self, reason_code: str, hint: str) -> None:
        super().__init__(hint)
        self.reason_code = reason_code
        self.hint = hint


def agent_runtime_dir() -> Path:
    here = Path(__file__).resolve()
    candidates = [here.parent / "agent", here.parents[3] / "connect" / "agent"]
    for candidate in candidates:
        if (candidate / "worker.mjs").is_file():
            return candidate.resolve()
    # Status remains actionable in older/incomplete installations.
    return candidates[0]


class AgentRuntime:
    """Local runtime supervised by the Python bridge, disabled unless --full was used.

    ``providers`` supplies get_key(id), ``library`` is the existing LibraryClient.
    Browser input can never switch full mode, choose a process, or supply credentials.
    """

    def __init__(
        self,
        *,
        full_mode: bool = False,
        providers: Any,
        library: Any,
        runtime_dir: Path | None = None,
        node_executable: Path | None = None,
        timeout_seconds: float = 90,
        approval_ttl_seconds: float = 300,
    ) -> None:
        self.full_mode = bool(full_mode)
        self.providers = providers
        self.library = library
        self.runtime_dir = Path(runtime_dir or agent_runtime_dir()).resolve()
        # Native bundles supply their own absolute Node path. A missing bundled
        # runtime must never silently execute an unrelated program from PATH.
        self.node_executable = Path(node_executable) if node_executable is not None else None
        self.timeout_seconds = min(max(float(timeout_seconds), 0.05), 90)
        self.approval_ttl_seconds = min(max(float(approval_ttl_seconds), 0.01), 300)
        self._lock = threading.RLock()
        self._approvals: dict[str, dict[str, Any]] = {}
        self._runs: dict[str, dict[str, Any]] = {}
        self._active_run: str | None = None
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._dependencies: dict[str, Any] | None = None
        self._dependencies_checked_at = 0.0
        self._closed = False

    @staticmethod
    def _safe_env() -> dict[str, str]:
        # No inherited API keys, NODE_OPTIONS, proxies, or Pi configuration paths.
        allowed = ("PATH", "SystemRoot", "SYSTEMROOT", "WINDIR", "TMP", "TEMP", "TMPDIR", "LANG")
        env = {key: os.environ[key] for key in allowed if key in os.environ}
        env.update({"PI_OFFLINE": "1", "PI_TELEMETRY": "0"})
        return env

    def _dependency_info(self) -> dict[str, Any]:
        """Read-only Node/SDK/catalog probe. Never runs in the basic edition."""
        if self._dependencies is not None and time.monotonic() - self._dependencies_checked_at < 10:
            return copy.deepcopy(self._dependencies)
        node = self._node_path()
        info: dict[str, Any] = {"available": False, "node_version": None, "sdk_version": None, "models": {}}
        if not node:
            info["reason_code"] = "agent_node_missing"
            return info
        diagnostics: dict[str, Any] = {}
        stage = "node_version"

        def failure(reason: str, code: str, error: BaseException | None = None) -> None:
            info.update(diagnostics)
            info.update({"reason_code": reason, "probe_stage": stage, "probe_code": code})
            if isinstance(error, OSError):
                number = getattr(error, "winerror", None)
                if type(number) is not int:
                    number = error.errno
                if type(number) is int:
                    info["probe_os_error"] = number

        try:
            version = _external_process.run([node, "--version"], capture_output=True, text=True, timeout=5, env=self._safe_env(), check=False,
                                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            diagnostics["node_probe_exit_code"] = version.returncode
            match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)\s*", version.stdout)
            if not match or version.returncode:
                diagnostics["probe_exit_code"] = version.returncode
                failure("agent_node_unavailable", "process_exit" if version.returncode else "invalid_node_version")
                return info
            info["node_version"] = ".".join(match.groups())
            if tuple(map(int, match.groups())) < (22, 19, 0):
                info["reason_code"] = "agent_node_version"
                return info
            if not (self.runtime_dir / "worker.mjs").is_file():
                info["reason_code"] = "agent_runtime_missing"
                return info
            temporary = None
            primary: tuple[str, BaseException] | None = None
            stage = "sdk_setup"
            try:
                temporary = tempfile.TemporaryDirectory(prefix="mdtero-pi-probe-")
                stage = "sdk_execution"
                checked = _external_process.run(
                    [node, str(self.runtime_dir / "worker.mjs"), "--check"],
                    capture_output=True, text=True, timeout=15, cwd=temporary.name, env=self._safe_env(), check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                diagnostics["sdk_probe_exit_code"] = checked.returncode
                diagnostics["probe_exit_code"] = checked.returncode
                if isinstance(checked.stdout, str):
                    diagnostics["probe_stdout_bytes"] = len(checked.stdout.encode("utf-8"))
                    diagnostics["probe_empty_output"] = checked.stdout == ""
            except (OSError, subprocess.SubprocessError, ValueError, TypeError) as exc:
                primary = (stage, exc)
            finally:
                if temporary is not None:
                    try:
                        temporary.cleanup()
                    except (OSError, ValueError, TypeError) as exc:
                        # A cleanup failure must not hide the original timeout or
                        # process-creation error that caused the probe to fail.
                        if primary is None:
                            primary = ("sdk_cleanup", exc)
            if primary is not None:
                stage, error = primary
                raise error
            stage = "sdk_json"
            if not isinstance(checked.stdout, str):
                failure("agent_sdk_missing", "invalid_json")
                return info
            if diagnostics["probe_stdout_bytes"] > 1024 * 1024:
                failure("agent_sdk_missing", "oversized_output")
                return info
            payload = json.loads(checked.stdout)
            if not isinstance(payload, dict):
                failure("agent_sdk_missing", "invalid_schema")
                return info
            if checked.returncode:
                failure("agent_sdk_missing", "process_exit")
                if payload.get("probe_stage") in {"sdk_import", "catalog"}:
                    info["probe_stage"] = payload["probe_stage"]
                if payload.get("probe_code") in {"ENOENT", "ERR_MODULE_NOT_FOUND", "ERR_DLOPEN_FAILED", "MODULE_NOT_FOUND", "EPERM", "EACCES", "dependency_error"}:
                    info["probe_code"] = payload["probe_code"]
                return info
            if payload.get("sdk_version") != SDK_VERSION or not payload.get("available"):
                info["reason_code"] = "agent_dependency_version_mismatch"
                return info
            info.update({"available": True, "sdk_version": SDK_VERSION, "models": payload.get("models", {})})
        except subprocess.TimeoutExpired as exc:
            failure("agent_sdk_missing", "timeout", exc)
        except OSError as exc:
            failure("agent_sdk_missing", "os_error", exc)
        except json.JSONDecodeError:
            failure("agent_sdk_missing", "invalid_json")
        except subprocess.SubprocessError:
            failure("agent_sdk_missing", "process_error")
        except (ValueError, TypeError):
            failure("agent_sdk_missing", "dependency_error")
        self._dependencies = info
        self._dependencies_checked_at = time.monotonic()
        return copy.deepcopy(info)

    def _node_path(self) -> str | None:
        if self.node_executable is None:
            return shutil.which("node")
        path = self.node_executable
        if not path.is_absolute() or not path.is_file():
            return None
        return str(path.resolve())

    def _configured(self) -> list[dict[str, Any]]:
        result = []
        for provider in PROVIDERS:
            try:
                configured = bool(self.providers.get_key(provider))
            except Exception:
                configured = False
            result.append({"id": provider, "configured": configured})
        return result

    def status(self) -> dict[str, Any]:
        configured = self._configured() if self.full_mode else [{"id": provider, "configured": False, "checked": False} for provider in PROVIDERS]
        dependencies = self._dependency_info() if self.full_mode else {"available": False, "checked": False, "models": {}}
        ready = self.full_mode and bool(dependencies.get("available")) and any(item["configured"] for item in configured) and not self._closed
        reason = (
            "agent_closed" if self._closed else
            "full_mode_required" if not self.full_mode else
            dependencies.get("reason_code", "agent_dependencies_missing") if not dependencies.get("available") else
            "provider_key_missing" if not any(item["configured"] for item in configured) else None
        )
        public_dependencies = {key: value for key, value in dependencies.items() if key != "models"}
        return {
            "enabled": self.full_mode, "mode": "full" if self.full_mode else "basic", "engine": "pi",
            "ready": ready, "reason_code": reason, "dependencies": public_dependencies,
            "providers": configured, "models": dependencies.get("models", {}),
            "scope": "selected_metadata", "full_text_included": False, "tools": [],
            "max_documents": 10, "max_output_tokens": MAX_OUTPUT_TOKENS, "max_model_requests": 1,
            "approval_required": True,
            "active_run": self._active_run_summary(),
        }

    def _active_run_summary(self) -> dict[str, Any] | None:
        with self._lock:
            return copy.deepcopy(self._runs.get(self._active_run)) if self._active_run else None

    def _require_full(self) -> None:
        if not self.full_mode:
            raise AgentError("full_mode_required", "Start Mdtero Connect with --full to enable the local Pi runtime.")
        if self._closed:
            raise AgentError("agent_closed", "The local research runtime has stopped.")

    def _model(self, provider: str, model: str) -> dict[str, Any]:
        dependencies = self._dependency_info()
        if not dependencies.get("available"):
            raise AgentError(str(dependencies.get("reason_code") or "agent_dependencies_missing"), "Pi needs Node.js 22.19+ and the pinned local runtime dependencies.")
        for candidate in dependencies.get("models", {}).get(provider, []):
            if candidate.get("id") == model:
                return candidate
        raise AgentError("model_not_supported", "Choose a model listed in the local Pi catalog for this provider.")

    @staticmethod
    def _document(item: dict[str, Any], document_id: int) -> dict[str, Any]:
        authors = item.get("authors")
        if isinstance(authors, list):
            authors = ", ".join(str(value) for value in authors)
        year = item.get("year")
        return {
            "id": document_id,
            "title": str(item.get("title") or "Untitled")[:2000],
            "authors": str(authors or "")[:2000],
            "year": str(year)[:10] if year is not None else None,
            "venue": str(item.get("venue") or "")[:2000],
            "doi": str(item.get("doi") or "")[:2000],
        }

    def prepare(self, body: dict[str, Any]) -> dict[str, Any]:
        self._require_full()
        allowed = {"document_ids", "prompt", "provider", "model", "max_output_tokens"}
        if not isinstance(body, dict) or any(key not in allowed for key in body):
            raise AgentError("invalid_agent_request", "Only document IDs, question, provider, model, and output budget are accepted.")
        ids = body.get("document_ids")
        if not isinstance(ids, list) or not 1 <= len(ids) <= 10 or any(type(value) is not int or not 1 <= value <= 2**53 - 1 for value in ids) or len(set(ids)) != len(ids):
            raise AgentError("invalid_document_selection", "Select between 1 and 10 different documents from your library.")
        prompt = body.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
            raise AgentError("invalid_agent_prompt", "Enter a research question of at most 4,000 characters.")
        provider, model = body.get("provider"), body.get("model")
        if provider not in PROVIDERS:
            raise AgentError("provider_not_supported", "Choose OpenAI, Anthropic, Google, or OpenRouter for Pi research.")
        if not isinstance(model, str) or not model or len(model) > 300:
            raise AgentError("model_not_supported", "Choose a model from the local Pi catalog.")
        catalog_model = self._model(provider, model)
        budget = body.get("max_output_tokens", 1024)
        if type(budget) is not int or not 128 <= budget <= MAX_OUTPUT_TOKENS:
            raise AgentError("invalid_output_budget", "Choose an output budget between 128 and 4,096 tokens.")
        budget = min(budget, int(catalog_model.get("max_output_tokens") or MAX_OUTPUT_TOKENS))
        if not self.providers.get_key(provider):
            raise AgentError("provider_key_missing", "Configure a local key for the selected AI provider first.")
        listing = self.library.list_documents()
        owned = {int(item.get("id") or item.get("document_id") or 0): item for item in listing.get("items", []) if isinstance(item, dict)}
        if any(document_id not in owned for document_id in ids):
            raise AgentError("document_not_in_library", "Every selected document must belong to your current library.")
        documents = [self._document(owned[document_id], document_id) for document_id in ids]
        snapshot = {"provider": provider, "model": model, "prompt": prompt.strip(), "documents": documents, "max_output_tokens": budget}
        input_bytes = len(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        # Reserve room for the key in the worker's bounded stdin envelope.
        if input_bytes > MAX_INPUT_BYTES - 16384:
            raise AgentError("agent_input_too_large", "The selected metadata is too large. Choose fewer documents.")
        approval_id = secrets.token_urlsafe(32)
        expires_at = time.time() + self.approval_ttl_seconds
        with self._lock:
            self._require_full()
            self._purge_approvals()
            if len(self._approvals) >= 20:
                raise AgentError("agent_approval_limit", "Too many pending research previews. Wait for a preview to expire.")
            self._approvals[approval_id] = {"snapshot": copy.deepcopy(snapshot), "deadline": time.monotonic() + self.approval_ttl_seconds}
        return {
            **copy.deepcopy(snapshot), "approval_id": approval_id,
            "expires_at": datetime.fromtimestamp(expires_at, timezone.utc).isoformat(),
            "document_count": len(documents), "input_bytes": input_bytes,
            "scope": "selected_metadata", "full_text_included": False, "model_requests": 1,
        }

    def _purge_approvals(self) -> None:
        now = time.monotonic()
        self._approvals = {key: value for key, value in self._approvals.items() if value["deadline"] > now}

    def start(self, approval_id: str) -> dict[str, Any]:
        self._require_full()
        if not isinstance(approval_id, str) or not approval_id:
            raise AgentError("agent_approval_required", "Preview and approve the selected research request first.")
        with self._lock:
            self._require_full()
            self._purge_approvals()
            if self._active_run:
                raise AgentError("agent_busy", "One research request is already running. Cancel it or wait for it to finish.")
            approved = self._approvals.pop(approval_id, None)
            if not approved:
                raise AgentError("agent_approval_invalid", "The approval expired or was already used. Preview the request again.")
            run_id = secrets.token_urlsafe(24)
            cancel_event = threading.Event()
            self._runs[run_id] = {"run_id": run_id, "status": "running", "engine": "pi", "scope": "selected_metadata"}
            self._cancel_events[run_id] = cancel_event
            self._active_run = run_id
            # Retain a bounded set of results in memory; no transcript files.
            while len(self._runs) > 20:
                oldest = next(iter(self._runs))
                self._runs.pop(oldest)
                self._cancel_events.pop(oldest, None)
            thread = threading.Thread(target=self._run, args=(run_id, approved["snapshot"], cancel_event), daemon=True)
            thread.start()
        return {"run_id": run_id, "status": "running"}

    def _run(self, run_id: str, snapshot: dict[str, Any], cancel_event: threading.Event) -> None:
        result: dict[str, Any]
        try:
            if cancel_event.is_set():
                raise AgentError("agent_cancelled", "Research was cancelled.")
            key = self.providers.get_key(snapshot["provider"])
            if not key:
                raise AgentError("provider_key_missing", "The local provider key is no longer available.")
            payload = {**copy.deepcopy(snapshot), "api_key": key}
            try:
                output = self._execute_worker(payload, cancel_event, run_id)
            finally:
                payload.pop("api_key", None)
                key = None
            result = {"run_id": run_id, "status": "completed", **output}
        except AgentError as exc:
            result = {"run_id": run_id, "status": "failed", "error": {"reason_code": exc.reason_code, "message": exc.hint}}
        except Exception:
            result = {"run_id": run_id, "status": "failed", "error": {"reason_code": "agent_provider_failed", "message": "Pi research could not complete. Check local provider configuration and retry."}}
        with self._lock:
            if cancel_event.is_set():
                result = {"run_id": run_id, "status": "cancelled", "engine": "pi"}
            self._runs[run_id] = result
            self._processes.pop(run_id, None)
            if self._active_run == run_id:
                self._active_run = None

    def _execute_worker(self, payload: dict[str, Any], cancel_event: threading.Event, run_id: str) -> dict[str, Any]:
        node = self._node_path()
        if not node:
            raise AgentError("agent_node_missing", "Pi needs Node.js 22.19 or newer.")
        with tempfile.TemporaryDirectory(prefix="mdtero-pi-run-") as cwd:
            with self._lock:
                # Serialize spawn/registration with close(): shutdown must see
                # every child, and cannot permit a new child after its snapshot.
                if self._closed or cancel_event.is_set():
                    raise AgentError("agent_cancelled", "Research was cancelled.")
                process = _external_process.popen(
                    [node, str(self.runtime_dir / "worker.mjs")], stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                    cwd=cwd, env=self._safe_env(), encoding="utf-8",
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                self._processes[run_id] = process
            try:
                stdout, _ = process.communicate(json.dumps(payload, ensure_ascii=False), timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                raise AgentError("agent_timeout", "Research exceeded its local time limit and was stopped.") from None
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
            if cancel_event.is_set():
                raise AgentError("agent_cancelled", "Research was cancelled.")
            if len(stdout.encode("utf-8")) > 256 * 1024:
                raise AgentError("agent_invalid_response", "Pi returned an invalid response.")
            try:
                result = json.loads(stdout)
            except (ValueError, TypeError):
                raise AgentError("agent_invalid_response", "Pi returned an invalid response.") from None
            if not isinstance(result, dict) or process.returncode or result.get("error"):
                code = result.get("error", {}).get("reason_code") if isinstance(result, dict) and isinstance(result.get("error"), dict) else None
                allowed_codes = {"model_not_supported", "provider_key_missing", "agent_timeout", "agent_tools_disabled", "agent_dependency_version_mismatch"}
                raise AgentError(code if code in allowed_codes else "agent_provider_failed", "Pi research could not complete. Check local provider configuration and retry.")
            if result.get("engine") != "pi" or not isinstance(result.get("text"), str):
                raise AgentError("agent_invalid_response", "Pi returned an invalid response.")
            # Return only the documented schema. Never return a worker dump to the page.
            usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
            safe_usage = {name: value for name, value in usage.items() if name in {"input", "output", "cacheRead", "cacheWrite", "totalTokens"} and type(value) in {int, float} and value >= 0}
            return {
                "text": result["text"].replace(payload["api_key"], "[redacted]"), "usage": safe_usage, "engine": "pi", "sdk_version": SDK_VERSION,
                "provider": payload["provider"], "model": payload["model"],
                "scope": "selected_metadata", "full_text_included": False,
                "model_requests": 1, "max_output_tokens": payload["max_output_tokens"],
            }

    def get_run(self, run_id: str) -> dict[str, Any]:
        self._require_full()
        with self._lock:
            if not isinstance(run_id, str) or run_id not in self._runs:
                raise AgentError("agent_run_not_found", "The research request does not exist in this Connect session.")
            return copy.deepcopy(self._runs[run_id])

    def cancel(self, run_id: str) -> dict[str, Any]:
        self._require_full()
        with self._lock:
            if not isinstance(run_id, str) or run_id not in self._runs:
                raise AgentError("agent_run_not_found", "The research request does not exist in this Connect session.")
            if self._runs[run_id]["status"] != "running":
                return copy.deepcopy(self._runs[run_id])
            self._cancel_events[run_id].set()
            process = self._processes.get(run_id)
            if process is not None and process.poll() is None:
                process.terminate()
                # A provider/SDK must not hold shutdown hostage after SIGTERM.
                kill_timer = threading.Timer(1, self._kill_if_running, args=(process,))
                kill_timer.daemon = True
                kill_timer.start()
            self._runs[run_id] = {"run_id": run_id, "status": "cancelled", "engine": "pi"}
            return copy.deepcopy(self._runs[run_id])

    @staticmethod
    def _kill_if_running(process: subprocess.Popen[str]) -> None:
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass

    def execute(self, approval_id: str) -> dict[str, Any]:
        started = self.start(approval_id)
        deadline = time.monotonic() + self.timeout_seconds + 5
        while time.monotonic() < deadline:
            result = self.get_run(started["run_id"])
            if result["status"] != "running":
                return result
            time.sleep(0.01)
        return self.cancel(started["run_id"])

    def close(self) -> None:
        with self._lock:
            processes = list(self._processes.values())
            if self._active_run and not self._closed:
                self.cancel(self._active_run)
            self._approvals.clear()
            self._closed = True
        # A native parent can exit immediately after bridge.stop(). Do not rely
        # on a daemon timer surviving long enough to reap a stubborn Pi child.
        for process in processes:
            try:
                process.wait(timeout=1.2)
            except subprocess.TimeoutExpired:
                self._kill_if_running(process)
                try:
                    process.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            except OSError:
                pass
