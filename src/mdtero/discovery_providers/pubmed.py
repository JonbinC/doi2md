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
                "db": "pubmed",
                "term": str(query).strip(),
                "retmax": str(per_page),
                "retstart": str(retstart),
                "retmode": "xml",
                "sort": "relevance",
            }
        )
    )
    search_root = http_get_xml(search_url, provider="pubmed")
    ids = [node.text.strip() for node in search_root.findall(".//Id") if node.text and node.text.strip()]
    if not ids:
        return {"items": [], "authenticated": False}
    fetch_url = (
        f"{EUTILS}/efetch.fcgi?"
        + encode_query({"db": "pubmed", "id": ",".join(ids), "retmode": "xml"})
    )
    fetch_root = http_get_xml(fetch_url, provider="pubmed")
    items = []
    for article in fetch_root.findall(".//PubmedArticle"):
        item = _normalize(article)
        if item.get("title"):
            items.append(item)
    return {"items": items, "authenticated": False}


def _normalize(article: ET.Element) -> dict[str, Any]:
    pmid = _text(article.find(".//PMID"))
    title = _text(article.find(".//ArticleTitle"))
    authors = []
    for author in article.findall(".//Author"):
        last = _text(author.find("LastName"))
        initials = _text(author.find("Initials"))
        if last:
            authors.append(f"{last} {initials}".strip() if initials else last)
    abstract_parts = [_text(node) for node in article.findall(".//AbstractText")]
    abstract = " ".join(part for part in abstract_parts if part)
    year_text = _text(article.find(".//PubDate/Year"))
    year = int(year_text) if year_text.isdigit() else None
    doi = _text(article.find('.//ELocationID[@EIdType="doi"]')) or extract_doi(abstract)
    journal = _text(article.find(".//Journal/Title"))
    return discovery_item(
        source="pubmed",
        external_id=pmid or None,
        title=title,
        authors=authors,
        year=year,
        venue=journal or None,
        abstract_preview=abstract or None,
        doi=doi,
        source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
    )


def _text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return "".join(node.itertext()).strip()
