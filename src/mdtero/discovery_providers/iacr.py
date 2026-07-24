from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

from ..discovery_http import discovery_item, encode_query, extract_doi, http_get_bytes

SEARCH_URL = "https://eprint.iacr.org/search"


class _ResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.entries: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._capture = ""
        self._in_dt = False
        self._in_dd = False
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "dt":
            self._in_dt = True
            self._buf = []
            self._current = {}
        elif tag == "dd":
            self._in_dd = True
            self._buf = []
        elif tag == "a" and self._in_dt and attr.get("href"):
            href = str(attr.get("href") or "")
            if re.search(r"/\d{4}/\d+", href):
                if self._current is not None:
                    self._current["url"] = href if href.startswith("http") else f"https://eprint.iacr.org{href}"
                    self._current["id"] = href.strip("/").split("/")[-2] + "/" + href.strip("/").split("/")[-1]

    def handle_data(self, data: str) -> None:
        if self._in_dt or self._in_dd:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "dt" and self._current is not None:
            self._current["title"] = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            self._in_dt = False
        elif tag == "dd" and self._current is not None:
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            self._current["snippet"] = text
            self.entries.append(self._current)
            self._current = None
            self._in_dd = False


def search(query: str, *, limit: int = 10, page: int = 1, **_: Any) -> dict[str, Any]:
    params = {"q": str(query).strip()}
    url = f"{SEARCH_URL}?{encode_query(params)}"
    raw = http_get_bytes(url, headers={"Accept": "text/html"}, provider="iacr")
    parser = _ResultParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    start = (max(1, int(page or 1)) - 1) * max(1, int(limit or 10))
    selected = parser.entries[start : start + max(1, min(int(limit or 10), 50))]
    items = []
    for entry in selected:
        paper_id = entry.get("id")
        landing = entry.get("url")
        pdf = f"https://eprint.iacr.org/{paper_id}.pdf" if paper_id else None
        year = None
        if paper_id and paper_id.split("/")[0].isdigit():
            year = int(paper_id.split("/")[0])
        items.append(
            discovery_item(
                source="iacr",
                external_id=paper_id,
                title=entry.get("title") or paper_id or "",
                year=year,
                venue="IACR ePrint",
                abstract_preview=entry.get("snippet"),
                doi=extract_doi(entry.get("snippet")),
                source_url=landing,
                open_access_pdf_url=pdf,
            )
        )
    return {"items": [item for item in items if item.get("title")], "authenticated": False}
