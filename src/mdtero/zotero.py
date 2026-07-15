from __future__ import annotations

import re
import shutil
from html import escape
from pathlib import Path
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


def default_zotero_storage_dir() -> Path:
    return Path.home() / "Zotero" / "storage"


def list_zotero_collections(client: Any) -> list[dict[str, Any]]:
    raw = client.collections()
    if not isinstance(raw, list):
        return []
    collections: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
        key = str(item.get("key") or data.get("key") or "").strip()
        if not key:
            continue
        name = str(data.get("name") or "").strip() or key
        parent = str(data.get("parentCollection") or "").strip() or None
        if parent in {"false", "0"}:
            parent = None
        collections.append(
            {
                "index": index,
                "key": key,
                "name": name,
                "parent_collection": parent,
                "num_items": _as_int(meta.get("numItems"), default=0),
                "num_collections": _as_int(meta.get("numCollections"), default=0),
            }
        )
    return collections


def resolve_collection_selector(
    collections: list[dict[str, Any]],
    selector: str | None,
) -> dict[str, Any] | None:
    """Resolve by 1-based index, exact key, exact name, or unique case-insensitive name substring."""
    cleaned = str(selector or "").strip()
    if not cleaned:
        return None
    if cleaned.isdigit():
        index = int(cleaned)
        for item in collections:
            if int(item.get("index") or 0) == index:
                return item
        return None
    key_hits = [item for item in collections if str(item.get("key") or "") == cleaned]
    if len(key_hits) == 1:
        return key_hits[0]
    exact_name = [item for item in collections if str(item.get("name") or "") == cleaned]
    if len(exact_name) == 1:
        return exact_name[0]
    lowered = cleaned.lower()
    name_hits = [item for item in collections if lowered in str(item.get("name") or "").lower()]
    if len(name_hits) == 1:
        return name_hits[0]
    return None


def list_zotero_items(client: Any, *, collection_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    if collection_id:
        items = client.collection_items_top(collection_id)
    else:
        items = client.top(limit=limit)
    if not isinstance(items, list):
        return []
    selected = [item for item in items if isinstance(item, dict)]
    if collection_id or limit <= 0:
        return selected
    return selected[:limit]


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
        else "Add a DOI or URL to this Zotero item, or parse an authorized local attachment with `mdtero zotero parse` / `mdtero parse --file <paper.pdf>`."
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


def list_item_pdf_attachments(client: Any, item: dict[str, Any]) -> list[dict[str, Any]]:
    parent_key = str(item.get("key") or "").strip()
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    title = str(data.get("title") or parent_key).strip()
    doi = str(data.get("DOI") or data.get("doi") or "").strip() or None
    url = str(data.get("url") or "").strip() or None
    try:
        children = client.children(parent_key)
    except Exception:
        children = []
    if not isinstance(children, list):
        return []
    attachments: list[dict[str, Any]] = []
    for child in children:
        if not isinstance(child, dict):
            continue
        child_data = child.get("data") if isinstance(child.get("data"), dict) else {}
        if str(child_data.get("itemType") or "") != "attachment":
            continue
        content_type = str(child_data.get("contentType") or "").lower()
        filename = str(child_data.get("filename") or child_data.get("title") or "").strip()
        if "pdf" not in content_type and not filename.lower().endswith(".pdf"):
            continue
        att_key = str(child.get("key") or child_data.get("key") or "").strip()
        if not att_key:
            continue
        attachments.append(
            {
                "parent_key": parent_key,
                "attachment_key": att_key,
                "title": title,
                "doi": doi,
                "url": url,
                "filename": filename or f"{att_key}.pdf",
                "content_type": content_type or "application/pdf",
                "link_mode": str(child_data.get("linkMode") or "").strip() or None,
            }
        )
    return attachments


def materialize_zotero_pdf(
    client: Any,
    attachment: dict[str, Any],
    *,
    output_dir: Path,
    storage_dir: Path | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    att_key = str(attachment.get("attachment_key") or "").strip()
    filename = _safe_filename(str(attachment.get("filename") or f"{att_key}.pdf"))
    if not filename.lower().endswith(".pdf"):
        filename = f"{filename}.pdf"
    dest = output_dir / f"{att_key}_{filename}"
    local_dir = (storage_dir or default_zotero_storage_dir()) / att_key
    if local_dir.is_dir():
        candidates = sorted(local_dir.glob("*.pdf"))
        if candidates:
            shutil.copy2(candidates[0], dest)
            return {
                "ok": True,
                "path": str(dest),
                "source": "local_storage",
                "attachment_key": att_key,
                "parent_key": attachment.get("parent_key"),
                "title": attachment.get("title"),
                "doi": attachment.get("doi"),
            }
    try:
        client.dump(att_key, path=str(output_dir), filename=dest.name)
    except Exception as exc:
        return {
            "ok": False,
            "attachment_key": att_key,
            "parent_key": attachment.get("parent_key"),
            "title": attachment.get("title"),
            "doi": attachment.get("doi"),
            "reason_code": "attachment_export_failed",
            "error": str(exc),
            "action_hint": "Ensure the PDF attachment is synced in Zotero desktop, or re-download it, then retry.",
        }
    if not dest.exists():
        # Some pyzotero versions write the provided filename into path without prefix handling.
        alt = output_dir / dest.name
        if not alt.exists():
            return {
                "ok": False,
                "attachment_key": att_key,
                "parent_key": attachment.get("parent_key"),
                "title": attachment.get("title"),
                "doi": attachment.get("doi"),
                "reason_code": "attachment_missing_after_dump",
                "action_hint": "Zotero API dump did not produce a PDF file. Open the item in Zotero and confirm the attachment downloads.",
            }
        dest = alt
    return {
        "ok": True,
        "path": str(dest),
        "source": "api_dump",
        "attachment_key": att_key,
        "parent_key": attachment.get("parent_key"),
        "title": attachment.get("title"),
        "doi": attachment.get("doi"),
    }


def export_collection_pdfs(
    client: Any,
    *,
    collection_id: str,
    output_dir: Path,
    limit: int = 50,
    storage_dir: Path | None = None,
) -> dict[str, Any]:
    items = list_zotero_items(client, collection_id=collection_id, limit=max(int(limit or 0), 0) or 10_000)
    if limit > 0:
        items = items[:limit]
    exported: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []
    for item in items:
        attachments = list_item_pdf_attachments(client, item)
        if not attachments:
            data = item.get("data") if isinstance(item.get("data"), dict) else {}
            skipped_items.append(
                {
                    "zotero_key": item.get("key"),
                    "title": (data.get("title") if isinstance(data, dict) else None),
                    "reason_code": "no_pdf_attachment",
                    "action_hint": "This item has no imported PDF attachment in Zotero.",
                }
            )
            continue
        # Prefer the first PDF attachment per parent item.
        result = materialize_zotero_pdf(
            client,
            attachments[0],
            output_dir=output_dir,
            storage_dir=storage_dir,
        )
        if result.get("ok"):
            exported.append(result)
        else:
            failed.append(result)
    return {
        "collection_id": collection_id,
        "item_count": len(items),
        "exported_count": len(exported),
        "failed_count": len(failed),
        "skipped_count": len(skipped_items),
        "exported": exported,
        "failed": failed,
        "skipped": skipped_items,
        "output_dir": str(output_dir),
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


def _as_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", name).strip().strip(".")
    return cleaned or "attachment.pdf"
