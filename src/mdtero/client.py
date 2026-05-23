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
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            return {
                "route_kind": "server",
                "acquisition_mode": "legacy_parse",
                "requires_raw_upload": False,
                "action_hint": "Production backend has not enabled /api/v1/route yet; using legacy /tasks/parse.",
                "server_entrypoint": "/tasks/parse",
                "upload_entrypoint": "/tasks/parse-upload-v2",
                "client_command": f"mdtero parse {input_value}",
                "legacy_fallback": True,
            }

    def parse(self, input_value: str) -> dict[str, Any]:
        return self._request_with_fallback("POST", "/api/v1/tasks/parse", "/tasks/parse", json={"input": input_value})

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
            return self._request_with_fallback("POST", "/api/v1/tasks/upload", "/tasks/parse-upload-v2", data=data, files=files)

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
            return self._request_with_fallback("POST", "/api/v1/tasks/upload", "/tasks/parse-upload-v2", data=data, files=files)

    def task(self, task_id: str) -> dict[str, Any]:
        return self._request_with_fallback("GET", f"/api/v1/tasks/{task_id}", f"/tasks/{task_id}")

    def download(self, task_id: str, artifact: str, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        response = self._raw_request_with_fallback("GET", f"/api/v1/tasks/{task_id}/download/{artifact}", f"/tasks/{task_id}/download/{artifact}")
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
        except (httpx.HTTPError, ValueError) as exc:
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
        return self._request_with_fallback("GET", "/api/v1/discovery/search", "/me/discovery/search", params={"query": query, "limit": limit})

    def translate_text(self, markdown: str, *, filename: str = "paper.md", target_language: str = "zh-CN") -> dict[str, Any]:
        return self._request_with_fallback(
            "POST",
            "/api/v1/tasks/translate",
            "/tasks/translate",
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
        if not source_path:
            raise ValueError("translation_source_artifact_missing")
        return self.translate_server_path(source_path, target_language=target_language)

    def translate_server_path(self, source_markdown_path: str, *, target_language: str = "zh-CN") -> dict[str, Any]:
        return self._request_with_fallback(
            "POST",
            "/api/v1/tasks/translate",
            "/tasks/translate",
            json={
                "source_markdown_path": source_markdown_path,
                "target_language": target_language,
                "mode": "full",
            },
        )

    def create_project(self, name: str, *, description: str | None = None) -> dict[str, Any]:
        return self._request_with_fallback("POST", "/api/v1/projects", "/projects", json={"name": name, "description": description})

    def import_task_to_project(self, project_id: str, task_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/projects/{project_id}/tasks/{task_id}/import")

    def rag_build(self, project_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/projects/{project_id}/rag/build")

    def rag_query(self, project_id: str, question: str) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/projects/{project_id}/rag/query", json={"question": question})

    def rag_status(self, project_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/projects/{project_id}/rag/status")

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(method, self._url(path), headers=self._headers(), **kwargs)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Mdtero API returned a non-object payload")
        return payload

    def _request_with_fallback(self, method: str, primary_path: str, fallback_path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            return self._request(method, primary_path, **kwargs)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            return self._request(method, fallback_path, **kwargs)

    def _raw_request_with_fallback(self, method: str, primary_path: str, fallback_path: str, **kwargs: Any) -> httpx.Response:
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.request(method, self._url(primary_path), headers=self._headers(), **kwargs)
            if response.status_code == 404:
                response = client.request(method, self._url(fallback_path), headers=self._headers(), **kwargs)
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
        "next_commands": ["mdtero doctor --json", "mdtero login --api-key <key>", "mdtero discover \"<topic>\" --json"],
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
            payload["action_hint"] = "Authenticate with `mdtero login --api-key <key>` or run `mdtero setup`, then rerun `mdtero doctor --json` before server OpenAlex discovery."
            payload["next_commands"] = ["mdtero login --api-key <key>", "mdtero doctor --json", "mdtero discover \"<topic>\" --json"]
    else:
        payload["detail"] = str(exc)
    return payload


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
