from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from ..discovery_http import discovery_item, http_get_json, normalize_doi

SERVERS = {
    "biorxiv": "https://api.biorxiv.org/details/biorxiv",
    "medrxiv": "https://api.biorxiv.org/details/medrxiv",
}

# Official bioRxiv/medRxiv category tokens only. Free-text queries must not be sent as category=.
_KNOWN_CATEGORIES = {
    "animal_behavior_and_cognition",
    "biochemistry",
    "bioengineering",
    "bioinformatics",
    "biophysics",
    "cancer_biology",
    "cell_biology",
    "clinical_trials",
    "developmental_biology",
    "ecology",
    "epidemiology",
    "evolutionary_biology",
    "genetics",
    "genomics",
    "immunology",
    "microbiology",
    "molecular_biology",
    "neuroscience",
    "paleontology",
    "pathology",
    "pharmacology_and_toxicology",
    "physiology",
    "plant_biology",
    "scientific_communication_and_education",
    "synthetic_biology",
    "systems_biology",
    "zoology",
    "addiction_medicine",
    "allergy_and_immunology",
    "anesthesia",
    "cardiovascular_medicine",
    "dentistry_and_oral_medicine",
    "dermatology",
    "emergency_medicine",
    "endocrinology",
    "gastroenterology",
    "genetic_and_genomic_medicine",
    "geriatric_medicine",
    "health_economics",
    "health_informatics",
    "health_policy",
    "hematology",
    "hiv_aids",
    "infectious_diseases",
    "intensive_care_and_critical_care_medicine",
    "medical_education",
    "medical_ethics",
    "nephrology",
    "neurology",
    "nursing",
    "nutrition",
    "obstetrics_and_gynecology",
    "occupational_and_environmental_health",
    "oncology",
    "ophthalmology",
    "orthopedics",
    "otolaryngology",
    "pain_medicine",
    "palliative_medicine",
    "pathology",
    "pediatrics",
    "pharmacology_and_therapeutics",
    "primary_care_research",
    "psychiatry_and_clinical_psychology",
    "public_and_global_health",
    "radiology_and_imaging",
    "rehabilitation_medicine_and_physical_therapy",
    "respiratory_medicine",
    "rheumatology",
    "sexual_and_reproductive_health",
    "sports_medicine",
    "surgery",
    "transplantation",
    "urology",
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
    now = datetime.now(timezone.utc)
    end_date = now.strftime("%Y-%m-%d")
    start_date = (now - timedelta(days=max(1, int(days or 365)))).strftime("%Y-%m-%d")
    # BUGFIX: previous code stuffed free-text queries into ?category=, which returns empty/wrong.
    category = _category_token(query)
    tokens = _query_tokens(query)
    per_page = max(1, min(int(limit or 10), 100))
    page_number = max(1, int(page or 1))
    # Fetch a wider window then filter/rank locally by title/abstract overlap.
    cursor = 0
    matched: list[tuple[float, dict[str, Any]]] = []
    pages_fetched = 0
    while pages_fetched < 3 and len(matched) < per_page * page_number:
        url = f"{base}/{start_date}/{end_date}/{cursor}"
        if category:
            url += f"?category={category}"
        try:
            payload = http_get_json(url, provider=server)
        except Exception:
            if pages_fetched == 0 and server == "medrxiv":
                # Mac/DNS flakes against api.biorxiv.org/details/medrxiv occasionally; fail soft.
                raise
            break
        collection = payload.get("collection") if isinstance(payload.get("collection"), list) else []
        if not collection:
            break
        for row in collection:
            if not isinstance(row, dict):
                continue
            item = _normalize(row, server=server)
            if not item.get("title"):
                continue
            score = _match_score(item, tokens)
            if tokens and score <= 0:
                continue
            matched.append((score, item))
        cursor += 100
        pages_fetched += 1
        if len(collection) < 100:
            break

    matched.sort(key=lambda row: (-row[0], str(row[1].get("title") or "")))
    start = (page_number - 1) * per_page
    items = [item for _, item in matched[start : start + per_page]]
    return {"items": items, "authenticated": False}


def _category_token(query: str) -> str | None:
    text = str(query or "").strip().lower().replace(" ", "_").replace("-", "_")
    if text in _KNOWN_CATEGORIES:
        return text
    return None


def _query_tokens(query: str) -> list[str]:
    stop = {"and", "the", "for", "with", "from", "into", "via", "using", "review", "a", "an", "of", "on", "in"}
    return [
        token
        for token in re.findall(r"[a-z0-9][a-z0-9+\-]{1,}", str(query or "").lower())
        if token not in stop
    ]


def _match_score(item: dict[str, Any], tokens: list[str]) -> float:
    if not tokens:
        return 1.0
    haystack = " ".join(
        str(value or "")
        for value in (item.get("title"), item.get("abstract_preview"), item.get("doi"))
    ).lower()
    hits = sum(1 for token in tokens if token in haystack)
    return hits / len(tokens)


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
    row = discovery_item(
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
    row["entity_type"] = "preprint"
    return row
