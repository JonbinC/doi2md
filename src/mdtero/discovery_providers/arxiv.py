from __future__ import annotations

import re
from typing import Any
from xml.etree import ElementTree as ET

from ..discovery_http import discovery_item, encode_query, extract_doi, http_get_bytes

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"
DEFAULT_API_BASE = "http://export.arxiv.org/api/query"


def search(query: str, *, limit: int = 10, page: int = 1, **_: Any) -> dict[str, Any]:
    per_page = max(1, min(int(limit or 10), 50))
    start = (max(1, int(page or 1)) - 1) * per_page
    params = {
        "search_query": f"all:{str(query).strip()}",
        "start": str(start),
        "max_results": str(per_page),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    url = f"{DEFAULT_API_BASE}?{encode_query(params)}"
    raw = http_get_bytes(url, headers={"Accept": "application/atom+xml"}, provider="arxiv")
    root = ET.fromstring(raw)
    items = []
    for entry in root.findall(f"{ATOM}entry"):
        item = _normalize(entry)
        if item.get("title"):
            items.append(item)
    return {"items": items, "authenticated": False}


def _normalize(entry: ET.Element) -> dict[str, Any]:
    title = _text(entry.find(f"{ATOM}title"))
    summary = _text(entry.find(f"{ATOM}summary"))
    entry_id = _text(entry.find(f"{ATOM}id"))
    paper_id = entry_id.rstrip("/").rsplit("/", 1)[-1] if entry_id else None
    authors = [_text(author.find(f"{ATOM}name")) for author in entry.findall(f"{ATOM}author")]
    authors = [name for name in authors if name]
    published = _text(entry.find(f"{ATOM}published"))
    year = int(published[:4]) if published and published[:4].isdigit() else None
    pdf_url = None
    for link in entry.findall(f"{ATOM}link"):
        if link.attrib.get("type") == "application/pdf" or link.attrib.get("title") == "pdf":
            pdf_url = link.attrib.get("href")
            break
    doi = _text(entry.find(f"{ARXIV_NS}doi")) or extract_doi(summary) or extract_doi(entry_id)
    categories = [cat.attrib.get("term") for cat in entry.findall(f"{ATOM}category") if cat.attrib.get("term")]
    return discovery_item(
        source="arxiv",
        external_id=paper_id,
        title=re.sub(r"\s+", " ", title),
        authors=authors,
        year=year,
        venue="arXiv",
        abstract_preview=re.sub(r"\s+", " ", summary) if summary else None,
        doi=doi,
        source_url=entry_id or (f"https://arxiv.org/abs/{paper_id}" if paper_id else None),
        open_access_pdf_url=pdf_url or (f"https://arxiv.org/pdf/{paper_id}.pdf" if paper_id else None),
        extra={"categories": categories} if categories else None,
    )


def _text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return "".join(node.itertext()).strip()
