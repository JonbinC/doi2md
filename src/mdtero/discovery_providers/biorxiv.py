from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..discovery_http import discovery_item, http_get_json, normalize_doi

SERVERS = {
    "biorxiv": "https://api.biorxiv.org/details/biorxiv",
    "medrxiv": "https://api.biorxiv.org/details/medrxiv",
}


def search(
    query: str,
    *,
    limit: int = 10,
    page: int = 1,
    days: int = 365,
    server: str = "biorxiv",
    **_: Any,
) -> dict[str, Any]:
    base = SERVERS.get(server, SERVERS["biorxiv"])
    end_date = datetime.utcnow().strftime("%Y-%m-%d")
    start_date = (datetime.utcnow() - timedelta(days=max(1, int(days or 365)))).strftime("%Y-%m-%d")
    category = str(query or "").strip().lower().replace(" ", "_")
    cursor = (max(1, int(page or 1)) - 1) * 100
    url = f"{base}/{start_date}/{end_date}/{cursor}"
    if category:
        url += f"?category={category}"
    payload = http_get_json(url, provider=server)
    collection = payload.get("collection") if isinstance(payload.get("collection"), list) else []
    items = []
    for row in collection:
        if not isinstance(row, dict):
            continue
        item = _normalize(row, server=server)
        if item.get("title"):
            items.append(item)
        if len(items) >= max(1, min(int(limit or 10), 100)):
            break
    return {"items": items, "authenticated": False}


def _normalize(item: dict[str, Any], *, server: str) -> dict[str, Any]:
    doi = normalize_doi(item.get("doi"))
    version = str(item.get("version") or "1").strip() or "1"
    host = "www.biorxiv.org" if server == "biorxiv" else "www.medrxiv.org"
    landing = f"https://{host}/content/{doi}v{version}" if doi else None
    pdf = f"{landing}.full.pdf" if landing else None
    authors = [part.strip() for part in str(item.get("authors") or "").split(";") if part.strip()]
    year = None
    date_text = str(item.get("date") or "")
    if len(date_text) >= 4 and date_text[:4].isdigit():
        year = int(date_text[:4])
    return discovery_item(
        source=server,
        external_id=doi,
        title=str(item.get("title") or "").strip(),
        authors=authors,
        year=year,
        venue=server,
        abstract_preview=str(item.get("abstract") or "").strip() or None,
        doi=doi,
        source_url=landing,
        open_access_pdf_url=pdf,
        extra={"category": item.get("category")} if item.get("category") else None,
    )
