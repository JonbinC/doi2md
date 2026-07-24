"""Strong-identifier merge with provenance (inspired by nature-academic-search).

Keeps publication vs trial namespaces separate, preserves source_records/conflicts,
and never sums citation counts across databases.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from .discovery_http import normalize_doi

IDENTIFIER_FIELDS = (
    "doi",
    "pmid",
    "pmcid",
    "arxiv_id",
    "openalex_id",
    "semantic_scholar_id",
    "nct_id",
)

_ARXIV_RE = re.compile(r"(?:arxiv[:\s]+)?(\d{4}\.\d{4,5})(?:v\d+)?", re.I)
_NCT_RE = re.compile(r"NCT\d{8}", re.I)


def prepare_discovery_record(raw: Mapping[str, Any]) -> dict[str, Any]:
    record = dict(raw)
    entity_type = str(record.get("entity_type") or "publication").strip().lower()
    if entity_type not in {"publication", "trial", "preprint"}:
        entity_type = "publication"
    # preprint stays under publication merge namespace but keeps a subtype tag.
    merge_entity = "trial" if entity_type == "trial" else "publication"
    record["entity_type"] = entity_type
    record["_merge_entity"] = merge_entity

    source = str(record.get("source") or record.get("external_source") or "").strip().lower()
    record["source"] = source or record.get("source")
    external_id = str(record.get("external_id") or record.get("source_id") or "").strip() or None

    doi = normalize_doi(record.get("doi"))
    record["doi"] = doi

    pmid = _clean_id(record.get("pmid"))
    pmcid = _clean_id(record.get("pmcid"))
    arxiv_id = _normalize_arxiv_id(record.get("arxiv_id"))
    openalex_id = _normalize_openalex_id(record.get("openalex_id"))
    semantic_scholar_id = _clean_id(record.get("semantic_scholar_id"))
    nct_id = _normalize_nct_id(record.get("nct_id"))

    if source == "pubmed" and external_id and external_id.isdigit():
        pmid = pmid or external_id
    elif source == "openalex" and external_id:
        openalex_id = openalex_id or _normalize_openalex_id(external_id)
    elif source in {"arxiv"} and external_id:
        arxiv_id = arxiv_id or _normalize_arxiv_id(external_id)
    elif source in {"semantic_scholar", "semantic"} and external_id:
        semantic_scholar_id = semantic_scholar_id or external_id
    elif source in {"clinicaltrials", "clinicaltrials_gov"} and external_id:
        nct_id = nct_id or _normalize_nct_id(external_id)
    elif source in {"europepmc", "pmc"}:
        if external_id and external_id.upper().startswith("PMC"):
            pmcid = pmcid or external_id.upper()
        elif external_id and external_id.isdigit():
            pmid = pmid or external_id

    if doi and doi.lower().startswith("10.48550/arxiv."):
        arxiv_id = arxiv_id or _normalize_arxiv_id(doi.split("arxiv.", 1)[-1])

    # Pull identifiers nested under extra when providers stash them there.
    extra = record.get("extra") if isinstance(record.get("extra"), dict) else {}
    pmid = pmid or _clean_id(extra.get("pmid"))
    pmcid = pmcid or _clean_id(extra.get("pmcid"))
    arxiv_id = arxiv_id or _normalize_arxiv_id(extra.get("arxiv_id"))
    nct_id = nct_id or _normalize_nct_id(extra.get("nct_id"))

    record["pmid"] = pmid
    record["pmcid"] = pmcid.upper() if pmcid else None
    record["arxiv_id"] = arxiv_id
    record["openalex_id"] = openalex_id
    record["semantic_scholar_id"] = semantic_scholar_id
    record["nct_id"] = nct_id

    source_id = str(record.get("source_id") or external_id or "").strip() or None
    if not source_id:
        source_id = doi or pmid or pmcid or arxiv_id or openalex_id or semantic_scholar_id or nct_id
    record["source_id"] = source_id
    record["external_id"] = external_id or source_id

    sources = [str(s) for s in (record.get("sources") or []) if str(s).strip()]
    if source and source not in sources:
        sources.append(source)
    record["sources"] = sources
    record["source_records"] = _ensure_source_records(record)
    record.setdefault("conflicts", [])

    citation_source = str(record.get("citation_count_source") or source or "").strip()
    counts = dict(record.get("citation_counts") or {})
    if record.get("citation_count") is not None and citation_source:
        counts.setdefault(citation_source, int(record.get("citation_count") or 0))
        record["citation_count_source"] = citation_source
    record["citation_counts"] = counts
    return record


def deduplicate_discovery_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any] | None] = []
    key_to_group: dict[tuple[str, str], int] = {}

    for raw in records:
        record = prepare_discovery_record(raw)
        keys = _record_keys(record)
        matches = sorted({key_to_group[key] for key in keys if key in key_to_group})

        if not matches:
            target = len(groups)
            groups.append(record)
        else:
            target = matches[0]
            for duplicate_group in matches[1:]:
                duplicate = groups[duplicate_group]
                if duplicate is not None:
                    merge_discovery_records(groups[target], duplicate)  # type: ignore[arg-type]
                    groups[duplicate_group] = None
                    for key, group_index in tuple(key_to_group.items()):
                        if group_index == duplicate_group:
                            key_to_group[key] = target
            merge_discovery_records(groups[target], record)  # type: ignore[arg-type]

        current = groups[target]
        if current is not None:
            for key in _record_keys(current):
                key_to_group[key] = target

    return [record for record in groups if record is not None]


def merge_discovery_records(target: dict[str, Any], incoming: Mapping[str, Any]) -> None:
    prepared = prepare_discovery_record(incoming)
    for source in prepared.get("sources") or []:
        if source not in target["sources"]:
            target["sources"].append(source)

    for source_record in prepared.get("source_records") or []:
        if source_record not in target["source_records"]:
            target["source_records"].append(source_record)

    target_counts = target.setdefault("citation_counts", {})
    target_counts.update(prepared.get("citation_counts") or {})
    incoming_source = str(prepared.get("citation_count_source") or prepared.get("source") or "")
    incoming_count = int(prepared.get("citation_count") or 0)
    if prepared.get("citation_count") is not None and incoming_source:
        target_counts[incoming_source] = incoming_count
    target_count = int(target.get("citation_count") or 0)
    if incoming_count > target_count:
        target["citation_count"] = incoming_count
        target["citation_count_source"] = incoming_source

    for field in IDENTIFIER_FIELDS:
        kept = target.get(field)
        value = prepared.get(field)
        if kept not in (None, "") and value not in (None, "") and str(kept).lower() != str(value).lower():
            conflict = {
                "field": field,
                "kept": kept,
                "incoming": value,
                "source": prepared.get("source"),
            }
            if conflict not in target["conflicts"]:
                target["conflicts"].append(conflict)

    for key, value in prepared.items():
        if key in {
            "source",
            "sources",
            "source_records",
            "citation_count",
            "citation_count_source",
            "citation_counts",
            "conflicts",
            "_merge_entity",
        }:
            continue
        if value not in (None, "", [], {}) and target.get(key) in (None, "", [], {}):
            target[key] = value

    # Prefer higher query match when filling.
    try:
        if float(prepared.get("query_match_score") or 0) > float(target.get("query_match_score") or 0):
            target["query_match_score"] = prepared.get("query_match_score")
            target["query_matched_terms"] = prepared.get("query_matched_terms")
            target["query_match_warning"] = prepared.get("query_match_warning")
            for key in (
                "query_matched_groups",
                "query_match_mode",
                "concept_group_coverage",
                "concept_groups",
            ):
                if prepared.get(key) is not None:
                    target[key] = prepared.get(key)
    except (TypeError, ValueError):
        pass


def strong_identifier(record: Mapping[str, Any]) -> str | None:
    prepared = prepare_discovery_record(record)
    if prepared.get("doi"):
        return f"DOI:{prepared['doi']}"
    if prepared.get("arxiv_id"):
        return f"ARXIV:{prepared['arxiv_id']}"
    if prepared.get("pmid"):
        return f"PMID:{prepared['pmid']}"
    if prepared.get("semantic_scholar_id"):
        return str(prepared["semantic_scholar_id"])
    return None


def _record_keys(record: Mapping[str, Any]) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    merge_entity = str(record.get("_merge_entity") or ("trial" if record.get("entity_type") == "trial" else "publication"))
    fields = ("nct_id",) if merge_entity == "trial" else IDENTIFIER_FIELDS[:-1]
    for field in fields:
        value = record.get(field)
        if value:
            keys.append((f"{merge_entity}:{field}", str(value).lower()))
    if merge_entity == "publication":
        title = _normalize_title(str(record.get("title") or ""))
        year = record.get("year")
        if title and year not in (None, ""):
            keys.append((f"{merge_entity}:title_year", f"{title}:{year}"))
    return keys


def _ensure_source_records(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = [
        dict(item)
        for item in record.get("source_records") or []
        if isinstance(item, Mapping)
    ]
    source = record.get("source")
    source_id = record.get("source_id") or record.get("external_id")
    source_url = record.get("source_url")
    if source and (source_id or source_url):
        current = {
            "source": source,
            "source_id": str(source_id or ""),
            "source_url": str(source_url or ""),
        }
        if current not in records:
            records.append(current)
    return records


def _clean_id(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_arxiv_id(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = re.sub(r"^https?://arxiv\.org/(?:abs|pdf)/", "", text, flags=re.I)
    text = text.removesuffix(".pdf")
    match = _ARXIV_RE.search(text)
    if match:
        return match.group(1)
    text = re.sub(r"^arxiv:", "", text, flags=re.I)
    text = re.sub(r"v\d+$", "", text)
    return text or None


def _normalize_openalex_id(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.rstrip("/").rsplit("/", 1)[-1]
    return text.upper() if text else None


def _normalize_nct_id(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = _NCT_RE.search(text)
    return match.group(0).upper() if match else None


def _normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
