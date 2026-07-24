from __future__ import annotations

from mdtero.discovery_merge import deduplicate_discovery_records, prepare_discovery_record, strong_identifier


def test_prepare_extracts_source_identifiers():
    pubmed = prepare_discovery_record(
        {"source": "pubmed", "external_id": "12345", "title": "A", "doi": "10.1000/xyz"}
    )
    assert pubmed["pmid"] == "12345"
    assert pubmed["sources"] == ["pubmed"]
    assert pubmed["citation_counts"] == {}

    openalex = prepare_discovery_record(
        {
            "source": "openalex",
            "external_id": "W123",
            "title": "B",
            "citation_count": 9,
            "citation_count_source": "openalex",
        }
    )
    assert openalex["openalex_id"] == "W123"
    assert openalex["citation_counts"]["openalex"] == 9


def test_dedupe_by_doi_merges_provenance_and_citation_counts():
    merged = deduplicate_discovery_records(
        [
            {
                "source": "openalex",
                "title": "Shared",
                "doi": "10.1000/Shared",
                "year": 2024,
                "citation_count": 3,
                "citation_count_source": "openalex",
                "external_id": "W1",
            },
            {
                "source": "pubmed",
                "title": "Shared",
                "doi": "10.1000/shared",
                "year": 2024,
                "pmid": "999",
                "external_id": "999",
            },
            {
                "source": "europepmc",
                "title": "Shared",
                "doi": "10.1000/shared",
                "year": 2024,
                "citation_count": 11,
                "citation_count_source": "europepmc",
                "pmcid": "PMC1",
            },
        ]
    )
    assert len(merged) == 1
    row = merged[0]
    assert set(row["sources"]) == {"openalex", "pubmed", "europepmc"}
    assert row["pmid"] == "999"
    assert row["pmcid"] == "PMC1"
    assert row["citation_counts"]["openalex"] == 3
    assert row["citation_counts"]["europepmc"] == 11
    assert row["citation_count"] == 11
    assert row["citation_count_source"] == "europepmc"
    assert len(row["source_records"]) >= 2


def test_publication_and_trial_never_merge():
    merged = deduplicate_discovery_records(
        [
            {
                "entity_type": "publication",
                "source": "pubmed",
                "title": "Same Title",
                "year": 2020,
                "pmid": "1",
            },
            {
                "entity_type": "trial",
                "source": "clinicaltrials",
                "title": "Same Title",
                "year": 2020,
                "nct_id": "NCT01234567",
            },
        ]
    )
    assert len(merged) == 2
    assert {row["entity_type"] for row in merged} == {"publication", "trial"}


def test_identifier_conflict_recorded():
    merged = deduplicate_discovery_records(
        [
            {"source": "pubmed", "title": "T", "year": 2021, "doi": "10.1/a", "pmid": "1"},
            {"source": "europepmc", "title": "T", "year": 2021, "doi": "10.1/a", "pmid": "2"},
        ]
    )
    assert len(merged) == 1
    assert any(c.get("field") == "pmid" for c in merged[0]["conflicts"])


def test_strong_identifier_prefers_doi():
    assert strong_identifier({"doi": "10.1000/xyz.abc", "pmid": "1"}) == "DOI:10.1000/xyz.abc"
    assert strong_identifier({"arxiv_id": "1706.03762"}) == "ARXIV:1706.03762"
