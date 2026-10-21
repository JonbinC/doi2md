"""Read-only access to the approved Zotero desktop connector on loopback."""

from __future__ import annotations

import json
from typing import Any

import httpx

from mdtero.connect.security import (
    ZOTERO_LOCAL_BASE,
    approved_zotero_url,
    reject_user_supplied_zotero_endpoint,
)


class ZoteroLocalError(RuntimeError):
    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


def connector_status(*, timeout: float = 2.0) -> dict[str, Any]:
    reject_user_supplied_zotero_endpoint(None)
    url = approved_zotero_url("/connector/ping")
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        return {
            "available": False,
            "base_url": ZOTERO_LOCAL_BASE,
            "reason_code": "zotero_connector_unreachable",
            "action_hint": "Open Zotero desktop with the local connector enabled, then retry.",
            "error": type(exc).__name__,
        }
    if response.status_code >= 400:
        return {
            "available": False,
            "base_url": ZOTERO_LOCAL_BASE,
            "reason_code": "zotero_connector_http_error",
            "status_code": response.status_code,
            "action_hint": "Zotero responded on loopback but the connector ping failed.",
        }
    return {
        "available": True,
        "base_url": ZOTERO_LOCAL_BASE,
        "reason_code": "ok",
        "status_code": response.status_code,
    }


def list_collections(*, timeout: float = 8.0) -> dict[str, Any]:
    """Best-effort collection listing through the local connector / API proxy.

    Zotero desktop versions differ. We try the connector collections endpoint
    first, then fall back to a clear unavailable reason without accepting a
    user-supplied host.
    """
    status = connector_status(timeout=min(timeout, 2.0))
    if not status.get("available"):
        return {"collections": [], **status}

    candidates = (
        "/connector/getSelectedCollection",
        "/api/users/0/collections",
    )
    last_error = "zotero_collections_unavailable"
    for path in candidates:
        url = approved_zotero_url(path)
        try:
            with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                response = client.get(url)
        except httpx.HTTPError:
            last_error = "zotero_collections_unreachable"
            continue
        if response.status_code >= 400:
            last_error = f"zotero_http_{response.status_code}"
            continue
        payload = _safe_json(response)
        collections = _normalize_collections(payload, path=path)
        if collections is not None:
            return {
                "available": True,
                "base_url": ZOTERO_LOCAL_BASE,
                "reason_code": "ok",
                "collections": collections,
                "source_path": path,
            }
        last_error = "zotero_collections_unrecognized"
    return {
        "available": True,
        "base_url": ZOTERO_LOCAL_BASE,
        "reason_code": last_error,
        "collections": [],
        "action_hint": "Connector is up, but collection listing is unavailable on this Zotero build. Use metadata export import as a fallback.",
    }


def collection_items_preview(collection_key: str, *, limit: int = 50, timeout: float = 10.0) -> dict[str, Any]:
    key = str(collection_key or "").strip()
    if not key or len(key) > 64 or any(ch in key for ch in "/\\?#"):
        raise ZoteroLocalError("invalid_collection", "Provide a valid Zotero collection key.")
    status = connector_status(timeout=min(timeout, 2.0))
    if not status.get("available"):
        return {"items": [], **status}

    path = f"/api/users/0/collections/{key}/items/top"
    url = approved_zotero_url(path)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            response = client.get(url, params={"limit": max(1, min(int(limit), 100))})
    except httpx.HTTPError as exc:
        raise ZoteroLocalError("zotero_items_unreachable", f"Could not read collection items: {type(exc).__name__}") from exc
    if response.status_code >= 400:
        raise ZoteroLocalError("zotero_items_http_error", f"Zotero returned HTTP {response.status_code} for collection items.")
    payload = _safe_json(response)
    items = _normalize_items(payload)[: max(1, min(int(limit), 100))]
    return {
        "available": True,
        "collection_key": key,
        "items": items,
        "count": len(items),
        "reason_code": "ok",
    }


def items_to_import_payload(items: list[dict[str, Any]]) -> str:
    """Serialize connector items as Zotero JSON for backend metadata-only import."""
    return json.dumps(items, ensure_ascii=False)


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return None


def _normalize_collections(payload: Any, *, path: str) -> list[dict[str, Any]] | None:
    if payload is None:
        return None
    if path.endswith("getSelectedCollection") and isinstance(payload, dict):
        key = str(payload.get("id") or payload.get("key") or "").strip()
        name = str(payload.get("name") or key or "Selected collection").strip()
        if not key:
            return []
        return [{"key": key, "name": name, "num_items": payload.get("numItems")}]
    rows = payload if isinstance(payload, list) else payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return None
    collections: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        data = row.get("data") if isinstance(row.get("data"), dict) else row
        key = str(row.get("key") or data.get("key") or "").strip()
        name = str(data.get("name") or key).strip()
        if not key:
            continue
        meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
        collections.append(
            {
                "key": key,
                "name": name,
                "parent_collection": data.get("parentCollection") or None,
                "num_items": meta.get("numItems"),
            }
        )
    return collections


def _normalize_items(payload: Any) -> list[dict[str, Any]]:
    rows = payload if isinstance(payload, list) else []
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        data = row.get("data") if isinstance(row.get("data"), dict) else row
        item_type = str(data.get("itemType") or "")
        if item_type in {"attachment", "note"}:
            continue
        key = str(row.get("key") or data.get("key") or "").strip()
        title = str(data.get("title") or "Untitled").strip()
        doi = str(data.get("DOI") or data.get("doi") or "").strip()
        date = str(data.get("date") or data.get("year") or "").strip()
        creators = data.get("creators") if isinstance(data.get("creators"), list) else []
        authors = []
        for creator in creators:
            if not isinstance(creator, dict):
                continue
            name = " ".join(part for part in [creator.get("firstName"), creator.get("lastName")] if part)
            name = name.strip() or str(creator.get("name") or "").strip()
            if name:
                authors.append(name)
        items.append(
            {
                "key": key,
                "title": title,
                "doi": doi,
                "date": date,
                "authors": authors,
                "itemType": item_type,
                "raw": row,
            }
        )
    return items
