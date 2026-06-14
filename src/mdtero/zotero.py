from __future__ import annotations

from html import escape
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
    zotero_key = str(item.get("key") or data.get("key") or "").strip() or None
    return PaperRecord(input=input_value, title=title or None, doi=doi or None, source="zotero", zotero_key=zotero_key)


def zotero_item_skip_reason(item: dict[str, Any]) -> dict[str, Any]:
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    key = str(item.get("key") or data.get("key") or "").strip() or None
    title = str(data.get("title") or "").strip() or None
    item_type = str(data.get("itemType") or item.get("itemType") or "").strip() or None
    doi = str(data.get("DOI") or data.get("doi") or "").strip()
    url = str(data.get("url") or "").strip()
    reason_code = "missing_data" if not data else "missing_doi_or_url"
    action_hint = (
        "Zotero item data was missing or malformed; skip this item or retry Zotero import."
        if reason_code == "missing_data"
        else "Add a DOI or URL to this Zotero item, or parse an authorized local attachment directly with `mdtero parse --file <paper.pdf>`."
    )
    return {
        "zotero_key": key,
        "title": title,
        "item_type": item_type,
        "doi_present": bool(doi),
        "url_present": bool(url),
        "reason_code": reason_code,
        "action_hint": action_hint,
    }


def build_sync_note(paper: PaperRecord) -> dict[str, Any]:
    task_id = escape(paper.task_id or "")
    title = escape(paper.title or paper.input)
    status = escape(paper.status or "unknown")
    reason = escape(paper.reason_code or "none")
    artifact = escape(paper.artifact or "paper_md")
    provider = escape(paper.provider or "unknown")
    strategy = escape(paper.parser_strategy or "unknown")
    note = "\n".join(
        [
            "<div data-mdtero-sync='true'>",
            f"<p><strong>Mdtero parse status:</strong> {status}</p>",
            f"<p><strong>Title:</strong> {title}</p>",
            f"<p><strong>Task:</strong> {task_id}</p>",
            f"<p><strong>Artifact:</strong> {artifact}</p>",
            f"<p><strong>Provider:</strong> {provider}</p>",
            f"<p><strong>Strategy:</strong> {strategy}</p>",
            f"<p><strong>Reason:</strong> {reason}</p>",
            "<p>Use <code>mdtero download &lt;task-id&gt; paper_md</code> to fetch the Markdown artifact.</p>",
            "</div>",
        ]
    )
    tags = ["mdtero"]
    if status:
        tags.append(f"mdtero:{status}")
    return {
        "itemType": "note",
        "parentItem": paper.zotero_key,
        "note": note,
        "tags": [{"tag": tag} for tag in tags],
    }


def sync_project_to_zotero(client: Any, papers: list[PaperRecord]) -> dict[str, Any]:
    synced: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for paper in papers:
        if paper.source != "zotero" or not paper.zotero_key:
            skipped.append({"input": paper.input, "reason_code": "not_zotero_item"})
            continue
        if paper.status != "succeeded" or not paper.task_id:
            skipped.append({"input": paper.input, "zotero_key": paper.zotero_key, "reason_code": "task_not_succeeded"})
            continue
        if paper.zotero_synced_task_id == paper.task_id:
            skipped.append({"input": paper.input, "zotero_key": paper.zotero_key, "reason_code": "already_synced"})
            continue
        response = client.create_items([build_sync_note(paper)])
        synced.append({"input": paper.input, "zotero_key": paper.zotero_key, "task_id": paper.task_id, "response": response})
        paper.zotero_synced_task_id = paper.task_id
    return {"synced_count": len(synced), "skipped_count": len(skipped), "synced": synced, "skipped": skipped}
