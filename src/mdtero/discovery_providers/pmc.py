from __future__ import annotations

from typing import Any
from xml.etree import ElementTree as ET

from ..discovery_http import discovery_item, encode_query, extract_doi, http_get_xml

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def search(query: str, *, limit: int = 10, page: int = 1, **_: Any) -> dict[str, Any]:
    per_page = max(1, min(int(limit or 10), 50))
    retstart = (max(1, int(page or 1)) - 1) * per_page
    search_url = (
        f"{EUTILS}/esearch.fcgi?"
        + encode_query(
            {
                "db": "pmc",
                "term": str(query).strip(),
                "retmax": str(per_page),
                "retstart": str(retstart),
                "retmode": "xml",
            }
        )
    )
    search_root = http_get_xml(search_url, provider="pmc")
    ids = [node.text.strip() for node in search_root.findall(".//Id") if node.text and node.text.strip()]
    if not ids:
        return {"items": [], "authenticated": False}
    summary_url = (
        f"{EUTILS}/esummary.fcgi?"
        + encode_query({"db": "pmc", "id": ",".join(ids), "retmode": "xml"})
    )
    summary_root = http_get_xml(summary_url, provider="pmc")
    items = []
    for doc in summary_root.findall(".//DocumentSummary"):
        item = _normalize(doc)
        if item.get("title"):
            items.append(item)
    return {"items": items, "authenticated": False}


def _normalize(doc: ET.Element) -> dict[str, Any]:
    uid = doc.attrib.get("uid") or _text(doc.find("Id"))
    pmcid = f"PMC{uid}" if uid and not str(uid).startswith("PMC") else str(uid or "")
    title = _text(doc.find("Title"))
    authors = [_text(name) for name in doc.findall(".//Author/Name")]
    authors = [name for name in authors if name]
    doi = _text(doc.find("DOI")) or extract_doi(_text(doc.find("ArticleIds")))
    pubdate = _text(doc.find("PubDate"))
    year = int(pubdate[:4]) if pubdate[:4].isdigit() else None
    return discovery_item(
        source="pmc",
        external_id=pmcid or None,
        title=title,
        authors=authors,
        year=year,
        venue=_text(doc.find("FullJournalName")) or _text(doc.find("Source")) or None,
        doi=doi,
        source_url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/" if pmcid else None,
        open_access_pdf_url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/" if pmcid else None,
    )


def _text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return "".join(node.itertext()).strip()
