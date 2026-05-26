from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx

from .acquisition import AcquiredArtifact, acquire_from_route, should_acquire_locally
from .config import MdteroConfig, load_config


class DiscoveryError(RuntimeError):
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        super().__init__(str(payload.get("message") or payload.get("error_code") or "discovery failed"))


class MdteroApiError(RuntimeError):
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        super().__init__(str(payload.get("message") or payload.get("error_code") or "Mdtero API request failed"))


class MdteroClient:
    def __init__(self, config: MdteroConfig | None = None, *, timeout: float = 60.0) -> None:
        self.config = config or load_config()
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"X-Client-Channel": "python-tui"}
        if self.config.effective_api_key:
            headers["Authorization"] = f"ApiKey {self.config.effective_api_key}"
        return headers

    def _url(self, path: str) -> str:
        return f"{self.config.api_base_url.rstrip('/')}{path}"

    def route(self, input_value: str) -> dict[str, Any]:
        try:
            return self._request("POST", "/api/v1/route", json={"input": input_value})
        except (MdteroApiError, httpx.HTTPStatusError) as exc:
            if _api_error_status_code(exc) != 404:
                raise
            return {
                "route_kind": "server",
                "acquisition_mode": "server_parse",
                "requires_raw_upload": False,
                "action_hint": "The backend route planner is not available; submit the DOI or URL directly to /api/v1/tasks/parse.",
                "server_entrypoint": "/api/v1/tasks/parse",
                "upload_entrypoint": "/api/v1/tasks/upload",
                "client_command": f"mdtero parse {input_value}",
                "route_planner_fallback": True,
            }

    def parse(self, input_value: str) -> dict[str, Any]:
        return self._request("POST", "/api/v1/tasks/parse", json={"input": input_value})

    def parse_with_route(self, input_value: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
        route = self.route(input_value)
        if should_acquire_locally(route, input_value):
            artifact = acquire_from_route(route, input_value, timeout=min(self.timeout, 45.0))
            acquisition = artifact.to_dict()
            try:
                result = self.upload_acquired(artifact, source_input=input_value)
            finally:
                artifact.path.unlink(missing_ok=True)
            result["route"] = route
            result["client_acquisition"] = acquisition
            return route, result, acquisition
        result = self.parse(input_value)
        result["route"] = route
        return route, result, None

    def upload(self, file_path: Path, *, source_input: str | None = None, source_doi: str | None = None) -> dict[str, Any]:
        data = {}
        if source_input:
            data["source_input"] = source_input
        if source_doi:
            data["source_doi"] = source_doi
        with file_path.open("rb") as handle:
            files = {"paper_file": (file_path.name, handle, _mime_type(file_path))}
            return self._request("POST", "/api/v1/tasks/upload", data=data, files=files)

    def upload_acquired(self, artifact: AcquiredArtifact, *, source_input: str | None = None, source_doi: str | None = None) -> dict[str, Any]:
        data = {
            "source_url": artifact.url,
            "source_input": source_input or artifact.url,
            "acquisition_mode": f"python_{artifact.source}",
            "artifact_kind": artifact.artifact_kind,
            "client_fetch_engine": artifact.source,
        }
        if source_doi:
            data["source_doi"] = source_doi
        with artifact.path.open("rb") as handle:
            files = {"paper_file": (artifact.path.name, handle, _mime_type(artifact.path))}
            return self._request("POST", "/api/v1/tasks/upload", data=data, files=files)

    def task(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/tasks/{task_id}")

    def download(self, task_id: str, artifact: str, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        response = self._raw_request("GET", f"/api/v1/tasks/{task_id}/download/{artifact}")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise FileNotFoundError(
                    f"artifact '{artifact}' is not available for task {task_id}; check `mdtero status {task_id} --json` for the task reason_code"
                ) from exc
            raise
        filename = _filename_from_disposition(response.headers.get("content-disposition"), artifact)
        target = output_dir / filename
        target.write_bytes(response.content)
        return target

    def wait(self, task_id: str, *, interval: float = 2.0, timeout: float = 600.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            task = self.task(task_id)
            if task.get("status") in {"succeeded", "failed", "cancelled"}:
                return task
            if time.monotonic() >= deadline:
                final_task = self.task(task_id)
                if final_task.get("status") in {"succeeded", "failed", "cancelled"}:
                    return final_task
                raise TimeoutError(f"timed out waiting for task {task_id}")
            time.sleep(interval)

    def discover(self, query: str, *, limit: int = 10) -> dict[str, Any]:
        local_failure: dict[str, Any] | None = None
        if self.config.has_semantic_scholar_key:
            try:
                return self._semantic_scholar_search(query, limit=limit)
            except (httpx.HTTPError, ValueError) as exc:
                local_failure = _local_semantic_scholar_failure(exc)
        try:
            result = self._server_discovery_search(query, limit=limit)
        except (MdteroApiError, httpx.HTTPError, ValueError) as exc:
            raise DiscoveryError(_discovery_failure_payload(exc, local_failure=local_failure)) from exc
        result.setdefault("source", "openalex_server")
        if local_failure:
            result["local_semantic_scholar_error"] = local_failure["error_type"]
            result["local_semantic_scholar_failure"] = local_failure
            result["discovery_fallback"] = {
                "from": "semantic_scholar_local",
                "to": "openalex_server",
                "reason_code": local_failure["reason_code"],
                "action_hint": "Local Semantic Scholar discovery failed; using the Mdtero server OpenAlex fallback for this query.",
            }
        return result

    def _server_discovery_search(self, query: str, *, limit: int) -> dict[str, Any]:
        return self._request("GET", "/api/v1/discovery/search", params={"query": query, "limit": limit})

    def translate_text(self, markdown: str, *, filename: str = "paper.md", target_language: str = "zh-CN") -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/tasks/translate",
            json={
                "source_markdown_path": "",
                "source_markdown_text": markdown,
                "source_markdown_filename": filename,
                "target_language": target_language,
                "mode": "full",
            },
        )

    def translate_task(self, task_id: str, *, target_language: str = "zh-CN", artifact: str = "paper_md") -> dict[str, Any]:
        task = self.task(task_id)
        source_path = translation_source_path_from_task(task, artifact=artifact)
        if source_path:
            return self.translate_server_path(source_path, target_language=target_language)

        downloadable = translation_source_download_artifact_from_task(task, artifact=artifact)
        if not downloadable:
            raise ValueError("translation_source_artifact_missing")
        artifact_key = str(downloadable.get("artifact") or artifact or "paper_md").strip() or "paper_md"
        response = self._raw_request("GET", f"/api/v1/tasks/{task_id}/download/{artifact_key}")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise ValueError("translation_source_artifact_missing") from exc
            raise
        markdown = response.text
        if not markdown.strip():
            raise ValueError("translation_source_artifact_empty")
        filename = _filename_from_disposition(response.headers.get("content-disposition"), artifact_key)
        descriptor_filename = str(downloadable.get("filename") or "").strip()
        if filename == f"{artifact_key}.bin" and descriptor_filename:
            filename = descriptor_filename
        return self.translate_text(markdown, filename=filename, target_language=target_language)

    def translate_server_path(self, source_markdown_path: str, *, target_language: str = "zh-CN") -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/tasks/translate",
            json={
                "source_markdown_path": source_markdown_path,
                "target_language": target_language,
                "mode": "full",
            },
        )

    def create_project(self, name: str, *, description: str | None = None) -> dict[str, Any]:
        return self._request("POST", "/api/v1/projects", json={"name": name, "description": description})

    def list_projects(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/projects")

    def import_task_to_project(self, project_id: str, task_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/projects/{project_id}/tasks/{task_id}/import")

    def rag_build(self, project_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/projects/{project_id}/rag/build")

    def rag_query(self, project_id: str, question: str) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/projects/{project_id}/rag/query", json={"question": question})

    def rag_status(self, project_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/projects/{project_id}/rag/status")

    def usage(self) -> dict[str, Any]:
        return self._request("GET", "/me/usage")

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(method, self._url(path), headers=self._headers(), **kwargs)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise MdteroApiError(api_failure_payload(exc, method=method, path=path)) from exc
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Mdtero API returned a non-object payload")
        return payload

    def _raw_request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.request(method, self._url(path), headers=self._headers(), **kwargs)
        return response

    def _semantic_scholar_search(self, query: str, *, limit: int) -> dict[str, Any]:
        headers = {"x-api-key": self.config.academic.semantic_scholar_api_key or ""}
        params = {"query": query, "limit": limit, "fields": "title,authors,year,url,externalIds,abstract"}
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get("https://api.semanticscholar.org/graph/v1/paper/search", headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        items = []
        for item in data.get("data") or []:
            external_ids = item.get("externalIds") or {}
            items.append(
                {
                    "title": item.get("title"),
                    "year": item.get("year"),
                    "doi": external_ids.get("DOI"),
                    "url": item.get("url"),
                    "authors": [author.get("name") for author in item.get("authors") or [] if author.get("name")],
                    "source": "semantic_scholar_local",
                }
            )
        return {"items": items, "source": "semantic_scholar_local"}


def _mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".pdf": "application/pdf",
        ".epub": "application/epub+zip",
        ".html": "text/html",
        ".htm": "text/html",
        ".xml": "application/xml",
    }.get(suffix, "application/octet-stream")


def _filename_from_disposition(content_disposition: str | None, artifact: str) -> str:
    if content_disposition:
        marker = "filename="
        for part in content_disposition.split(";"):
            part = part.strip()
            if part.lower().startswith(marker):
                return part[len(marker) :].strip('"') or f"{artifact}.bin"
    return f"{artifact}.bin"


def _local_semantic_scholar_failure(exc: Exception) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider": "semantic_scholar",
        "status": "failed",
        "error_type": exc.__class__.__name__,
        "reason_code": "semantic_scholar_local_failed",
        "action_hint": "Mdtero will fall back to server OpenAlex when available. Check the Semantic Scholar API key, rate limit, or network if you want local discovery.",
    }
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        payload["status_code"] = response.status_code
        if response.status_code == 401 or response.status_code == 403:
            payload["reason_code"] = "semantic_scholar_auth_failed"
            payload["action_hint"] = "Check the Semantic Scholar API key saved by `mdtero config academic`, or press Enter there to use server OpenAlex instead."
        elif response.status_code == 429:
            payload["reason_code"] = "semantic_scholar_rate_limited"
            payload["action_hint"] = "Semantic Scholar rate-limited local discovery. Wait and retry, or continue with the server OpenAlex fallback."
        else:
            payload["reason_code"] = "semantic_scholar_http_error"
        try:
            detail = response.json()
        except ValueError:
            detail = response.text[:300]
        payload["detail"] = detail
    elif isinstance(exc, httpx.TimeoutException):
        payload["reason_code"] = "semantic_scholar_timeout"
    elif isinstance(exc, httpx.ConnectError):
        payload["reason_code"] = "semantic_scholar_network_error"
    else:
        payload["detail"] = str(exc)
    return payload


def _discovery_failure_payload(exc: Exception, *, local_failure: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "failed",
        "error_code": "discovery_failed",
        "source": "openalex_server",
        "server_error": exc.__class__.__name__,
        "action_hint": "Check Mdtero API connectivity and whether server OpenAlex discovery is enabled.",
        "next_commands": ["mdtero doctor --json", "mdtero setup --api-key", "mdtero discover \"<topic>\" --json"],
    }
    if local_failure:
        payload["local_semantic_scholar_error"] = local_failure["error_type"]
        payload["local_semantic_scholar_failure"] = local_failure
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        payload["status_code"] = response.status_code
        try:
            detail = response.json()
        except ValueError:
            detail = response.text[:500]
        payload["detail"] = detail
        if isinstance(detail, dict) and detail.get("error_code"):
            payload["error_code"] = str(detail["error_code"])
        if response.status_code in {401, 403}:
            payload["error_code"] = "authentication_required" if response.status_code == 401 else "forbidden"
            payload["reason_code"] = "authentication_required" if response.status_code == 401 else "access_forbidden"
            payload["action_hint"] = "Run `mdtero setup` for browser OAuth, or `mdtero setup --api-key` for headless environments, then rerun `mdtero doctor --json` before server OpenAlex discovery."
            payload["next_commands"] = ["mdtero setup --api-key", "mdtero doctor --json", "mdtero discover \"<topic>\" --json"]
    else:
        payload["detail"] = str(exc)
    return payload


def _api_error_status_code(exc: Exception) -> int | None:
    if isinstance(exc, MdteroApiError):
        value = exc.payload.get("status_code")
        return int(value) if isinstance(value, int) else None
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    return None


def api_failure_payload(exc: httpx.HTTPStatusError, *, method: str, path: str) -> dict[str, Any]:
    response = exc.response
    try:
        detail: Any = response.json()
    except ValueError:
        detail = response.text[:500]
    reason_code = "api_request_failed"
    error_code = "api_request_failed"
    action_hint = "Run `mdtero doctor --json`, check the API base URL, then retry the command."
    next_commands = ["mdtero doctor --json"]
    if isinstance(detail, dict):
        nested = detail.get("detail") if isinstance(detail.get("detail"), dict) else detail
        if isinstance(nested, dict):
            reason_code = str(nested.get("reason_code") or nested.get("error_code") or reason_code)
            error_code = str(nested.get("error_code") or reason_code)
            action_hint = str(nested.get("action_hint") or action_hint)
            nested_commands = [str(command).strip() for command in nested.get("next_commands") or [] if str(command).strip()]
            if nested_commands:
                next_commands = nested_commands
    if response.status_code in {401, 403}:
        error_code = "authentication_required" if response.status_code == 401 else "forbidden"
        reason_code = "authentication_required" if response.status_code == 401 else "access_forbidden"
        action_hint = "Run `mdtero setup` for browser OAuth, or `mdtero setup --api-key` for headless environments, then rerun `mdtero doctor --json`."
        next_commands = ["mdtero setup --api-key", "mdtero doctor --json"]
    return {
        "status": "failed",
        "error_code": error_code,
        "reason_code": reason_code,
        "status_code": response.status_code,
        "method": method,
        "path": path,
        "detail": detail,
        "action_hint": action_hint,
        "next_commands": next_commands,
    }


def translation_source_path_from_task(task: dict[str, Any], *, artifact: str = "paper_md") -> str | None:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    candidates: list[Any] = []
    if artifact in artifacts:
        candidates.append(artifacts.get(artifact))
    if "paper_md" in artifacts and artifact != "paper_md":
        candidates.append(artifacts.get("paper_md"))
    for key in (artifact, "paper_md", "markdown_path", "source_markdown_path"):
        if key in result:
            candidates.append(result.get(key))
    for candidate in candidates:
        path = _artifact_path(candidate)
        if path:
            return path
    return None


def translation_source_download_artifact_from_task(task: dict[str, Any], *, artifact: str = "paper_md") -> dict[str, Any] | None:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    keys = _dedupe_artifact_keys([artifact, "paper_md"])

    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    for key in keys:
        if key in artifacts:
            descriptor = artifacts.get(key)
            payload = dict(descriptor) if isinstance(descriptor, dict) else {}
            payload.setdefault("artifact", key)
            return payload

    download_artifacts = result.get("download_artifacts")
    if isinstance(download_artifacts, list):
        for item in download_artifacts:
            if not isinstance(item, dict):
                continue
            key = str(item.get("artifact") or "").strip()
            if key in keys:
                return dict(item)
    elif isinstance(download_artifacts, dict):
        for key in keys:
            if key in download_artifacts:
                descriptor = download_artifacts.get(key)
                payload = dict(descriptor) if isinstance(descriptor, dict) else {}
                payload.setdefault("artifact", key)
                return payload
    return None


def _dedupe_artifact_keys(values: list[Any]) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = str(value or "").strip()
        if key and key not in seen:
            keys.append(key)
            seen.add(key)
    return keys


def _artifact_path(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, dict):
        for key in ("path", "source_markdown_path", "local_path"):
            cleaned = str(value.get(key) or "").strip()
            if cleaned:
                return cleaned
    return None
