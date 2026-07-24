"""ClinicalTrials.gov API v2 — trial registrations (not publications)."""

from __future__ import annotations

import re
from typing import Any

from ..discovery_http import discovery_item, encode_query, http_get_json

DEFAULT_API_BASE = "https://clinicaltrials.gov/api/v2"
_NCT_RE = re.compile(r"NCT\d{8}", re.I)


def search(query: str, *, limit: int = 10, page: int = 1, **_: Any) -> dict[str, Any]:
    per_page = max(1, min(int(limit or 10), 50))
    # ClinicalTrials.gov v2 uses token pages; we approximate page>1 by larger fetch + slice.
    page_number = max(1, int(page or 1))
    fetch_size = min(per_page * page_number, 100)
    params = {
        "query.term": str(query).strip(),
        "pageSize": str(fetch_size),
        "format": "json",
        "countTotal": "true",
    }
    url = f"{DEFAULT_API_BASE}/studies?{encode_query(params)}"
    payload = http_get_json(url, provider="clinicaltrials")
    studies = payload.get("studies") if isinstance(payload.get("studies"), list) else []
    start = (page_number - 1) * per_page
    sliced = studies[start : start + per_page]
    items = [_normalize(study) for study in sliced if isinstance(study, dict)]
    return {
        "items": [item for item in items if item.get("title")],
        "authenticated": False,
        "entity_type": "trial",
        "total": int(payload.get("totalCount") or 0),
    }


def _normalize(study: dict[str, Any]) -> dict[str, Any]:
    protocol = study.get("protocolSection") if isinstance(study.get("protocolSection"), dict) else {}
    identification = protocol.get("identificationModule") if isinstance(protocol.get("identificationModule"), dict) else {}
    status = protocol.get("statusModule") if isinstance(protocol.get("statusModule"), dict) else {}
    design = protocol.get("designModule") if isinstance(protocol.get("designModule"), dict) else {}
    conditions_module = protocol.get("conditionsModule") if isinstance(protocol.get("conditionsModule"), dict) else {}
    sponsors = protocol.get("sponsorCollaboratorsModule") if isinstance(protocol.get("sponsorCollaboratorsModule"), dict) else {}
    interventions_module = (
        protocol.get("armsInterventionsModule") if isinstance(protocol.get("armsInterventionsModule"), dict) else {}
    )

    nct_raw = str(identification.get("nctId") or "").strip()
    match = _NCT_RE.search(nct_raw)
    nct_id = match.group(0).upper() if match else nct_raw.upper() or None
    title = str(identification.get("officialTitle") or identification.get("briefTitle") or "").strip()
    lead = sponsors.get("leadSponsor") if isinstance(sponsors.get("leadSponsor"), dict) else {}
    conditions = [str(c).strip() for c in (conditions_module.get("conditions") or []) if str(c).strip()]
    interventions = []
    for row in interventions_module.get("interventions") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if name:
            interventions.append({"type": row.get("type"), "name": name})

    year = None
    start = status.get("startDateStruct") if isinstance(status.get("startDateStruct"), dict) else {}
    start_date = str(start.get("date") or "")
    if len(start_date) >= 4 and start_date[:4].isdigit():
        year = int(start_date[:4])

    item = discovery_item(
        source="clinicaltrials",
        external_id=nct_id,
        title=title,
        authors=[str(lead.get("name") or "").strip()] if lead.get("name") else [],
        year=year,
        venue="ClinicalTrials.gov",
        abstract_preview="; ".join(conditions[:8]) or None,
        doi=None,
        source_url=f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else None,
    )
    item["entity_type"] = "trial"
    item["nct_id"] = nct_id
    item["overall_status"] = status.get("overallStatus")
    item["study_type"] = design.get("studyType")
    item["conditions"] = conditions
    item["interventions"] = interventions
    item["sponsor"] = str(lead.get("name") or "").strip() or None
    item["parse_readiness"] = "metadata_only"
    item["parse_input_kind"] = None
    item["parse_input_value"] = None
    return item
