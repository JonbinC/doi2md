from __future__ import annotations

from typing import Any

from ..discovery_http import discovery_item, encode_query, http_get_json, normalize_doi

DEFAULT_API_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"


def search(query: str, *, limit: int = 10, page: int = 1, **_: Any) -> dict[str, Any]:
    per_page = max(1, min(int(limit or 10), 100))
    page_number = max(1, int(page or 1))
    params = {
        "query": str(query).strip(),
        "pageSize": str(per_page),
        "page": str(page_number),
        "format": "json",
        "resultType": "core",
    }
    url = f"{DEFAULT_API_BASE}/search?{encode_query(params)}"
    payload = http_get_json(url, provider="europepmc")
    result_list = (
        (payload.get("resultList") or {}).get("result")
        if isinstance(payload.get("resultList"), dict)
        else []
    )
    rows = result_list if isinstance(result_list, list) else []
    items = [_normalize(row) for row in rows if isinstance(row, dict)]
    return {"items": [item for item in items if item.get("title")], "authenticated": False}


def _normalize(item: dict[str, Any]) -> dict[str, Any]:
    pmid = str(item.get("pmid") or "").strip() or None
    pmcid = str(item.get("pmcid") or "").strip() or None
    doi = normalize_doi(item.get("doi"))
    paper_id = pmcid or pmid or doi or str(item.get("id") or "").strip() or None
    authors = []
    author_string = str(item.get("authorString") or "").strip()
    if author_string:
        authors = [part.strip() for part in author_string.split(",") if part.strip()]
    pdf = None
    if str(item.get("isOpenAccess") or "").lower() in {"y", "true", "1"} and pmcid:
        pdf = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"
    source_url = None
    if pmid:
        source_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    elif pmcid:
        source_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/"
    elif doi:
        source_url = f"https://doi.org/{doi}"
    year = item.get("pubYear")
    try:
        year = int(year) if year is not None else None
    except (TypeError, ValueError):
        year = None
    citation_count = int(item.get("citedByCount") or 0)
    row = discovery_item(
        source="europepmc",
        external_id=paper_id,
        title=str(item.get("title") or "").strip(),
        authors=authors,
        year=year,
        venue=str(item.get("journalTitle") or "").strip() or None,
        abstract_preview=str(item.get("abstractText") or "").strip() or None,
        citation_count=citation_count,
        doi=doi,
        source_url=source_url,
        open_access_pdf_url=pdf,
    )
    row["pmid"] = pmid
    row["pmcid"] = pmcid.upper() if pmcid else None
    row["entity_type"] = "publication"
    row["citation_count_source"] = "europepmc"
    row["citation_counts"] = {"europepmc": citation_count}
    return row
