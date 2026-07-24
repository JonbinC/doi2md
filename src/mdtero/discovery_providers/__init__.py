"""Local multi-source discovery providers (paper-search-mcp compatible coverage)."""

from __future__ import annotations

from typing import Any, Callable

from . import (
    arxiv,
    base_search,
    biorxiv,
    chemrxiv,
    citeseerx,
    clinicaltrials,
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
    "clinicaltrials": clinicaltrials.search,
    "clinicaltrials_gov": clinicaltrials.search,
}

# Default free-first publication profile. Semantic Scholar is enrich-only by default
# (rate-limit sensitive); pass it explicitly in --sources to fan-out search.
# Keep the default set lean: noisy/fragile sources stay available via --sources all.
FREE_CORE_PROVIDERS: tuple[str, ...] = (
    "openalex",
    "crossref",
    "arxiv",
    "pubmed",
    "europepmc",
    "pmc",
    "biorxiv",
    "dblp",
    "doaj",
    "zenodo",
    "chemrxiv",
)

TRIAL_PROVIDERS: tuple[str, ...] = ("clinicaltrials",)
DEFAULT_ENRICHERS: tuple[str, ...] = ("semantic_scholar",)

ALL_SEARCH_PROVIDERS: tuple[str, ...] = tuple(
    name
    for name in (
        *FREE_CORE_PROVIDERS,
        "medrxiv",
        "hal",
        "iacr",
        "openaire",
        "semantic_scholar",
        "core",
        "citeseerx",
        "base",
        "ssrn",
        "google_scholar",
        "unpaywall",
        "ieee",
        "acm",
        "clinicaltrials",
    )
    if name in PROVIDER_SEARCHERS
)

PROVIDER_ALIASES = {
    "s2": "semantic_scholar",
    "semantic": "semantic_scholar",
    "gs": "google_scholar",
    "scholar": "google_scholar",
    "ctg": "clinicaltrials",
    "clinicaltrials.gov": "clinicaltrials",
    "clinicaltrials_gov": "clinicaltrials",
}

PUBLICATION_ONLY_PROVIDERS = frozenset(
    name for name in PROVIDER_SEARCHERS if name not in {"clinicaltrials", "clinicaltrials_gov"}
)
TRIAL_ONLY_PROVIDERS = frozenset({"clinicaltrials", "clinicaltrials_gov"})


def resolve_provider_names(
    spec: str | None | tuple[str, ...] | list[str],
    *,
    entity_type: str = "publication",
) -> tuple[str, ...]:
    entity = str(entity_type or "publication").strip().lower()
    if entity not in {"publication", "trial"}:
        entity = "publication"
    if entity == "trial":
        defaults = TRIAL_PROVIDERS
    else:
        defaults = FREE_CORE_PROVIDERS

    if spec is None:
        return defaults
    if isinstance(spec, (tuple, list)):
        tokens = [str(item).strip().lower() for item in spec if str(item).strip()]
    else:
        text = str(spec).strip().lower()
        if not text or text in {"free", "free_core", "default"}:
            return defaults
        if text in {"all", "*"}:
            if entity == "trial":
                return TRIAL_PROVIDERS
            return tuple(name for name in ALL_SEARCH_PROVIDERS if name in PUBLICATION_ONLY_PROVIDERS)
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
        if entity == "trial" and name not in TRIAL_ONLY_PROVIDERS:
            continue
        if entity == "publication" and name in TRIAL_ONLY_PROVIDERS:
            continue
        seen.add(name)
        resolved.append(name)
    return tuple(resolved) if resolved else defaults


def resolve_enrichers(
    spec: str | None | tuple[str, ...] | list[str] | None,
    *,
    entity_type: str = "publication",
    selected_providers: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    entity = str(entity_type or "publication").strip().lower()
    if entity != "publication":
        return ()
    selected = set(selected_providers or ())
    if spec is None:
        # Default: enrich via S2 unless it was already used as a search fan-out source.
        return tuple(name for name in DEFAULT_ENRICHERS if name not in selected)
    if isinstance(spec, (tuple, list)):
        tokens = [str(item).strip().lower() for item in spec if str(item).strip()]
    else:
        text = str(spec).strip().lower()
        if not text or text in {"default", "auto"}:
            return tuple(name for name in DEFAULT_ENRICHERS if name not in selected)
        if text in {"none", "off", "false", "0"}:
            return ()
        tokens = [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]
    resolved: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        name = PROVIDER_ALIASES.get(token, token)
        if name not in {"semantic_scholar"} or name in seen:
            continue
        seen.add(name)
        resolved.append(name)
    return tuple(resolved)


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
            "enrich": True,
            "needs_key": False,
            "key_improves_quota": True,
            "default_role": "enrich",
            "notes": "Default enrich-only via strong IDs; pass in --sources to search",
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
        {
            "provider": "clinicaltrials",
            "search": True,
            "entity_type": "trial",
            "needs_key": False,
            "notes": "Trial registrations only; use --entity-type trial",
        },
    ]
