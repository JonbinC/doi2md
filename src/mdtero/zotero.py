from __future__ import annotations

from typing import Any

from .config import MdteroConfig
from .projects import PaperRecord


def make_zotero_client(config: MdteroConfig) -> Any:
    if not config.zotero.library_id or not config.zotero.api_key:
        raise RuntimeError("Configure Zotero with ZOTERO_LIBRARY_ID/ZOTERO_API_KEY or mdtero config before import.")
    try:
        from pyzotero import zotero
    except Exception as exc:  # pragma: no cover - optional import
        raise RuntimeError("pyzotero is required for Zotero import.") from exc
    return zotero.Zotero(config.zotero.library_id, config.zotero.library_type, config.zotero.api_key)


def list_zotero_items(client: Any, *, collection_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    if collection_id:
        items = client.collection_items_top(collection_id)
    else:
        items = client.top(limit=limit)
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def paper_from_zotero_item(item: dict[str, Any]) -> PaperRecord | None:
    data = item.get("data")
    if not isinstance(data, dict):
        return None
    title = str(data.get("title") or "").strip()
    doi = str(data.get("DOI") or data.get("doi") or "").strip()
    url = str(data.get("url") or "").strip()
    input_value = doi or url
    if not input_value:
        return None
    return PaperRecord(input=input_value, title=title or None, doi=doi or None, source="zotero")

