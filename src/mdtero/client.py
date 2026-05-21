from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx

from .config import MdteroConfig, load_config


class MdteroClient:
    def __init__(self, config: MdteroConfig | None = None, *, timeout: float = 60.0) -> None:
        self.config = config or load_config()
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"X-Client-Channel": "python-tui"}
        if self.config.api_key:
            headers["Authorization"] = f"ApiKey {self.config.api_key}"
        return headers

    def _url(self, path: str) -> str:
        return f"{self.config.api_base_url.rstrip('/')}{path}"

    def route(self, input_value: str) -> dict[str, Any]:
        return self._request("POST", "/api/v1/route", json={"input": input_value})

    def parse(self, input_value: str) -> dict[str, Any]:
        return self._request("POST", "/api/v1/tasks/parse", json={"input": input_value})

    def upload(self, file_path: Path, *, source_input: str | None = None, source_doi: str | None = None) -> dict[str, Any]:
        data = {}
        if source_input:
            data["source_input"] = source_input
        if source_doi:
            data["source_doi"] = source_doi
        with file_path.open("rb") as handle:
            files = {"paper_file": (file_path.name, handle, _mime_type(file_path))}
            return self._request("POST", "/api/v1/tasks/upload", data=data, files=files)

    def task(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/tasks/{task_id}")

    def download(self, task_id: str, artifact: str, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.get(self._url(f"/api/v1/tasks/{task_id}/download/{artifact}"), headers=self._headers())
        response.raise_for_status()
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
        if self.config.has_semantic_scholar_key:
            return self._semantic_scholar_search(query, limit=limit)
        return self._request("GET", "/api/v1/discovery/search", params={"query": query, "limit": limit})

    def translate_text(self, markdown: str, *, filename: str = "paper.md", target_language: str = "zh-CN") -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/tasks/translate",
            json={
                "source_markdown_text": markdown,
                "source_markdown_filename": filename,
                "target_language": target_language,
                "mode": "full",
            },
        )

    def rag_build(self, project_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/projects/{project_id}/rag/build")

    def rag_query(self, project_id: str, question: str) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/projects/{project_id}/rag/query", json={"question": question})

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(method, self._url(path), headers=self._headers(), **kwargs)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Mdtero API returned a non-object payload")
        return payload

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
