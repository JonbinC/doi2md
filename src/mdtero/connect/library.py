"""Typed adapters over backend PR #43 library HTTP contracts."""

from __future__ import annotations

from typing import Any, Literal

import httpx

from mdtero.client import MdteroApiError, MdteroClient

ExportFormat = Literal["bibtex", "csl_json", "markdown", "markdown_zip"]
TagMatch = Literal["all", "any"]


class LibraryClient:
    """Reuse MdteroClient auth; do not invent a second library store."""

    def __init__(self, client: MdteroClient | None = None) -> None:
        self.client = client or MdteroClient()

    def session_summary(self) -> dict[str, Any]:
        cfg = self.client.config
        authenticated = bool(cfg.effective_api_key)
        return {
            "authenticated": authenticated,
            "api_base_url": cfg.api_base_url,
            "auth_source": cfg.api_key_source if authenticated else None,
            "site_base_url": cfg.site_base_url,
            "cloud_committed": authenticated,
        }

    def list_documents(self) -> dict[str, Any]:
        payload = self.client._request("GET", "/api/v1/documents")
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise MdteroApiError({"message": "Library listing returned an unexpected payload.", "reason_code": "invalid_library_payload"})
        papers = [_normalize_paper(item) for item in items if isinstance(item, dict)]
        return {"items": papers, "count": len(papers)}

    def list_tags(self, *, after: str = "", limit: int = 200, project_id: int | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"after": after, "limit": max(1, min(int(limit), 200))}
        if project_id is not None:
            params["project_id"] = int(project_id)
        return self.client._request("GET", "/api/v1/library/tags", params=params)

    def tagged_documents(
        self,
        tags: list[str],
        *,
        match: TagMatch = "all",
        limit: int = 100,
        offset: int = 0,
        project_id: int | None = None,
    ) -> dict[str, Any]:
        params: list[tuple[str, Any]] = [("match", match), ("limit", max(1, min(int(limit), 200))), ("offset", max(0, int(offset)))]
        for tag in tags:
            params.append(("tag", tag))
        if project_id is not None:
            params.append(("project_id", int(project_id)))
        return self.client._request("GET", "/api/v1/library/tagged-documents", params=params)

    def update_tags(
        self,
        *,
        document_ids: list[int],
        add: list[str] | None = None,
        remove: list[str] | None = None,
        dry_run: bool,
    ) -> dict[str, Any]:
        # REST dry_run defaults to false server-side; Connect always sends it explicitly.
        body = {
            "document_ids": [int(value) for value in document_ids],
            "add": list(add or []),
            "remove": list(remove or []),
            "dry_run": bool(dry_run),
        }
        return self.client._request("POST", "/api/v1/library/tags/batch", json=body)

    def export_selection(self, *, document_ids: list[int], format: ExportFormat | str = "bibtex") -> dict[str, Any]:
        allowed: set[str] = {"bibtex", "csl_json", "markdown", "markdown_zip"}
        if format not in allowed:
            raise ValueError("Unsupported export format. Use bibtex, csl_json, markdown, or markdown_zip.")
        response = self.client._raw_request(
            "POST",
            "/api/v1/library/export",
            json={"document_ids": [int(value) for value in document_ids], "format": format},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise MdteroApiError(_error_payload(exc)) from exc
        filename = _filename_from_disposition(response.headers.get("content-disposition"), format, document_ids)
        return {
            "filename": filename,
            "media_type": response.headers.get("content-type") or "application/octet-stream",
            "export_label": response.headers.get("x-mdtero-export") or format,
            "data": response.content,
            "images_included": False,
        }

    def import_bibliography(
        self,
        *,
        content: str,
        format: str = "auto",
        dry_run: bool = True,
        request_id: str | None = None,
        project_id: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "content": content,
            "format": format,
            "dry_run": bool(dry_run),
        }
        if request_id:
            body["request_id"] = request_id
        if project_id is not None:
            body["project_id"] = int(project_id)
        return self.client._request("POST", "/api/v1/library/import", json=body)


def _normalize_paper(item: dict[str, Any]) -> dict[str, Any]:
    document_id = int(item.get("document_id") or item.get("id") or 0)
    authors = item.get("authors")
    if isinstance(authors, list):
        author_text = ", ".join(str(part) for part in authors if str(part).strip())
    else:
        author_text = str(authors or "").strip()
    tags = item.get("tags") if isinstance(item.get("tags"), list) else []
    status = str(item.get("status") or item.get("content_status") or "")
    if item.get("has_saved_text") is False and not status:
        status = "metadata"
    elif item.get("has_saved_text") is True and not status:
        status = "source ready"
    return {
        "id": document_id,
        "document_id": document_id,
        "title": str(item.get("title") or "Untitled"),
        "authors": author_text,
        "year": item.get("year"),
        "venue": item.get("venue") or "",
        "doi": item.get("doi") or "",
        "status": status,
        "tags": [str(tag) for tag in tags if str(tag).strip()],
        "has_saved_text": bool(item.get("has_saved_text")),
        "updated_at": item.get("updated_at"),
    }


def _filename_from_disposition(header: str | None, format: str, document_ids: list[int]) -> str:
    defaults = {
        "bibtex": "mdtero-references.bib",
        "csl_json": "mdtero-references.json",
        "markdown_zip": "mdtero-markdown-text-only.zip",
        "markdown": f"mdtero{document_ids[0]}.md" if document_ids else "mdtero-export.md",
    }
    fallback = defaults.get(format, "mdtero-export.bin")
    if not header:
        return fallback
    marker = "filename="
    lowered = header.lower()
    index = lowered.find(marker)
    if index < 0:
        return fallback
    raw = header[index + len(marker) :].strip().strip("\"'")
    return raw.split(";", 1)[0].strip() or fallback


def _error_payload(exc: httpx.HTTPStatusError) -> dict[str, Any]:
    response = exc.response
    detail: Any = None
    try:
        detail = response.json()
    except Exception:
        detail = {"message": response.text[:300]}
    if isinstance(detail, dict) and isinstance(detail.get("detail"), dict):
        detail = detail["detail"]
    if not isinstance(detail, dict):
        detail = {"message": str(detail)}
    detail.setdefault("status_code", response.status_code)
    return detail
