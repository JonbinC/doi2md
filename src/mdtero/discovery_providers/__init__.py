"""Local multi-source discovery providers (paper-search-mcp compatible coverage)."""

from __future__ import annotations

from typing import Any, Callable

from . import (
    arxiv,
    base_search,
    biorxiv,
    chemrxiv,
    citeseerx,
    core,
    crossref,
    dblp,
    doaj,
    europepmc,
    google_scholar,
    hal,
    iacr,
    ieee,
    medrxiv,
    openaire,
    openalex,
    pmc,
    pubmed,
    semantic_scholar,
    ssrn,
    unpaywall,
    zenodo,
    acm,
)

ProviderFn = Callable[..., dict[str, Any]]

# Search providers absorbed from paper-search-mcp. Sci-Hub is download-only and never listed here.
PROVIDER_SEARCHERS: dict[str, ProviderFn] = {
    "openalex": openalex.search,
    "semantic_scholar": semantic_scholar.search,
    "semantic": semantic_scholar.search,
    "crossref": crossref.search,
    "arxiv": arxiv.search,
    "pubmed": pubmed.search,
    "europepmc": europepmc.search,
    "pmc": pmc.search,
    "biorxiv": biorxiv.search,
    "medrxiv": medrxiv.search,
    "dblp": dblp.search,
    "doaj": doaj.search,
    "zenodo": zenodo.search,
    "hal": hal.search,
    "iacr": iacr.search,
    "openaire": openaire.search,
    "chemrxiv": chemrxiv.search,
    "core": core.search,
    "citeseerx": citeseerx.search,
    "base": base_search.search,
    "ssrn": ssrn.search,
    "google_scholar": google_scholar.search,
    "unpaywall": unpaywall.search,
    "ieee": ieee.search,
    "acm": acm.search,
}

# Default free-first profile (no keys required). Keys only improve quotas where applicable.
FREE_CORE_PROVIDERS: tuple[str, ...] = (
    "openalex",
    "semantic_scholar",
    "crossref",
    "arxiv",
    "pubmed",
    "europepmc",
    "pmc",
    "biorxiv",
    "medrxiv",
    "dblp",
    "doaj",
    "zenodo",
    "hal",
    "iacr",
    "openaire",
    "chemrxiv",
)

ALL_SEARCH_PROVIDERS: tuple[str, ...] = tuple(
    name
    for name in (
        *FREE_CORE_PROVIDERS,
        "core",
        "citeseerx",
        "base",
        "ssrn",
        "google_scholar",
        "unpaywall",
        "ieee",
        "acm",
    )
    if name in PROVIDER_SEARCHERS
)

PROVIDER_ALIASES = {
    "s2": "semantic_scholar",
    "semantic": "semantic_scholar",
    "gs": "google_scholar",
    "scholar": "google_scholar",
}


def resolve_provider_names(spec: str | None | tuple[str, ...] | list[str]) -> tuple[str, ...]:
    if spec is None:
        return FREE_CORE_PROVIDERS
    if isinstance(spec, (tuple, list)):
        tokens = [str(item).strip().lower() for item in spec if str(item).strip()]
    else:
        text = str(spec).strip().lower()
        if not text or text in {"free", "free_core", "default"}:
            return FREE_CORE_PROVIDERS
        if text in {"all", "*"}:
            return ALL_SEARCH_PROVIDERS
        tokens = [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]
    resolved: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        name = PROVIDER_ALIASES.get(token, token)
        if name == "scihub" or name == "sci_hub":
            # Sci-Hub is download-only; ignore in search source lists.
            continue
        if name not in PROVIDER_SEARCHERS or name in seen:
            continue
        seen.add(name)
        resolved.append(name)
    return tuple(resolved) if resolved else FREE_CORE_PROVIDERS


def provider_capability_matrix() -> list[dict[str, Any]]:
    return [
        {
            "provider": "openalex",
            "search": True,
            "needs_key": False,
            "key_improves_quota": True,
            "notes": "Free tiny daily budget without key",
        },
        {
            "provider": "semantic_scholar",
            "search": True,
            "needs_key": False,
            "key_improves_quota": True,
            "notes": "Shared rate limit without key",
        },
        {"provider": "crossref", "search": True, "needs_key": False, "key_improves_quota": False},
        {"provider": "arxiv", "search": True, "needs_key": False, "key_improves_quota": False},
        {"provider": "pubmed", "search": True, "needs_key": False, "key_improves_quota": False},
        {"provider": "europepmc", "search": True, "needs_key": False, "key_improves_quota": False},
        {"provider": "pmc", "search": True, "needs_key": False, "key_improves_quota": False},
        {"provider": "biorxiv", "search": True, "needs_key": False, "key_improves_quota": False},
        {"provider": "medrxiv", "search": True, "needs_key": False, "key_improves_quota": False},
        {"provider": "dblp", "search": True, "needs_key": False, "key_improves_quota": False},
        {"provider": "doaj", "search": True, "needs_key": False, "key_improves_quota": True},
        {"provider": "zenodo", "search": True, "needs_key": False, "key_improves_quota": False},
        {"provider": "hal", "search": True, "needs_key": False, "key_improves_quota": False},
        {"provider": "iacr", "search": True, "needs_key": False, "key_improves_quota": False},
        {"provider": "openaire", "search": True, "needs_key": False, "key_improves_quota": False},
        {"provider": "chemrxiv", "search": True, "needs_key": False, "key_improves_quota": False},
        {"provider": "core", "search": True, "needs_key": False, "key_improves_quota": True},
        {"provider": "citeseerx", "search": True, "needs_key": False, "key_improves_quota": False},
        {
            "provider": "base",
            "search": True,
            "needs_key": False,
            "key_improves_quota": False,
            "notes": "May require institutional IP registration",
        },
        {"provider": "ssrn", "search": True, "needs_key": False, "key_improves_quota": False},
        {
            "provider": "google_scholar",
            "search": True,
            "needs_key": False,
            "needs_proxy": True,
            "notes": "Bot detection; use campus/proxy",
        },
        {
            "provider": "unpaywall",
            "search": True,
            "needs_key": False,
            "needs_email": True,
            "notes": "DOI lookup; requires email",
        },
        {"provider": "ieee", "search": True, "needs_key": True, "notes": "Disabled without IEEE API key"},
        {"provider": "acm", "search": True, "needs_key": True, "notes": "Disabled without ACM API key"},
        {
            "provider": "scihub",
            "search": False,
            "download": True,
            "default_enabled": False,
            "notes": "Optional download fallback only; never used in discover search",
        },
    ]
