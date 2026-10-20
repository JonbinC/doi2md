"""Pull an explicitly saved cloud project into a local Mdtero folder.

Push stays on `mdtero project ingest` / ChatGPT import. This module only copies
cloud document text down, and it skips a file whose checksum is unchanged.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable

from .projects import PaperRecord, add_paper, load_project


def pull_project_documents(
    root: Path,
    *,
    manifest: dict[str, Any],
    read_text: Callable[[int], str],
) -> dict[str, Any]:
    state = load_project(root)
    cloud_dir = root / ".mdtero" / "cloud"
    cloud_dir.mkdir(parents=True, exist_ok=True)
    pulled: list[dict[str, Any]] = []
    for item in manifest.get("items") or []:
        if not isinstance(item, dict):
            continue
        document_id = int(item["document_id"])
        archive = item.get("cloud_archive") if isinstance(item.get("cloud_archive"), dict) else {}
        checksum = str(archive.get("checksum") or "").strip()
        target = cloud_dir / f"{document_id}.md"
        stamp = cloud_dir / f"{document_id}.sha256"
        if checksum and target.is_file() and stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == checksum:
            pulled.append({"document_id": document_id, "status": "unchanged", "path": str(target)})
            continue
        text = read_text(document_id)
        if not str(text or "").strip():
            pulled.append({"document_id": document_id, "status": "empty", "path": None})
            continue
        target.write_text(text, encoding="utf-8")
        digest = checksum or hashlib.sha256(text.encode("utf-8")).hexdigest()
        stamp.write_text(digest + "\n", encoding="utf-8")
        paper_input = str(item.get("doi") or f"document:{document_id}")
        add_paper(
            root,
            PaperRecord(
                input=paper_input,
                status="saved",
                title=str(item.get("title") or "") or None,
                doi=str(item.get("doi") or "") or None,
                source="cloud_sync",
                artifact=str(target),
            ),
        )
        pulled.append({"document_id": document_id, "status": "pulled", "path": str(target), "checksum": digest})
    return {
        "project_id": manifest.get("project_id") or state.server_project_id,
        "direction": "cloud_to_local",
        "cloud_library": manifest.get("cloud_library"),
        "items": pulled,
    }
