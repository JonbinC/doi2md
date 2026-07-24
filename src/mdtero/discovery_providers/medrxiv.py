from __future__ import annotations

from typing import Any

from . import biorxiv


def search(query: str, *, limit: int = 10, page: int = 1, **kwargs: Any) -> dict[str, Any]:
    return biorxiv.search(query, limit=limit, page=page, server="medrxiv", **kwargs)
