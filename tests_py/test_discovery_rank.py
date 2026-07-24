from __future__ import annotations

from mdtero.discovery_rank import is_supplementary_doi, rank_discovery_items, sanitize_discovery_item


def test_is_supplementary_doi():
    assert is_supplementary_doi("10.1039/d4sc01234a.s001")
    assert is_supplementary_doi("10.1000/foo/suppl")
    assert not is_supplementary_doi("10.1038/s41586-023-00000-0")


def test_sanitize_rejects_si_doi_and_falls_back_to_url():
    item = sanitize_discovery_item(
        {
            "source": "chemrxiv",
            "doi": "10.26434/chemrxiv-2024-abcd.s001",
            "source_url": "https://chemrxiv.org/engage/chemrxiv/article-details/abc",
            "open_access_pdf_url": None,
            "parse_input_kind": "doi",
            "parse_input_value": "10.26434/chemrxiv-2024-abcd.s001",
            "parse_readiness": "ready_via_doi",
        }
    )
    assert item["doi"] is None
    assert item["doi_quality"] == "supplementary"
    assert item["parse_input_kind"] == "url"
    assert item["parse_input_value"].startswith("https://chemrxiv.org/")


def test_sanitize_arxiv_prefers_arxiv_doi():
    item = sanitize_discovery_item(
        {
            "source": "arxiv",
            "external_id": "1706.03762v7",
            "doi": "10.1145/something.publisher",
            "source_url": "https://arxiv.org/abs/1706.03762v7",
            "open_access_pdf_url": "https://arxiv.org/pdf/1706.03762.pdf",
        }
    )
    assert item["doi"] == "10.48550/arXiv.1706.03762"
    assert item["publisher_doi"] == "10.1145/something.publisher"
    assert item["parse_input_value"] == "10.48550/arXiv.1706.03762"
    assert item["external_id"] == "1706.03762"


def test_rank_prefers_oa_pdf_and_sinks_si():
    ranked = rank_discovery_items(
        [
            {
                "title": "SI trap",
                "source": "crossref",
                "doi": "10.1000/paper.s001",
                "parse_readiness": "ready_via_doi",
                "parse_input_value": "10.1000/paper.s001",
            },
            {
                "title": "Zenodo PDF",
                "source": "zenodo",
                "doi": "10.5281/zenodo.1",
                "open_access_pdf_url": "https://zenodo.org/records/1/files/paper.pdf",
                "source_url": "https://zenodo.org/records/1",
                "parse_readiness": "ready_via_doi",
                "parse_input_value": "10.5281/zenodo.1",
                "query_match_score": 0.5,
            },
        ]
    )
    assert ranked[0]["title"] == "Zenodo PDF"
    assert ranked[0]["parse_input_value"].endswith(".pdf")
    assert ranked[-1]["doi_quality"] == "supplementary"


def test_rank_prefers_multi_source_and_citations_over_weak_arxiv():
    ranked = rank_discovery_items(
        [
            {
                "title": "Weak arxiv match",
                "source": "arxiv",
                "sources": ["arxiv"],
                "doi": "10.48550/arXiv.9999.99999",
                "arxiv_id": "9999.99999",
                "parse_readiness": "ready_via_doi",
                "parse_input_value": "10.48550/arXiv.9999.99999",
                "open_access_pdf_url": "https://arxiv.org/pdf/9999.99999.pdf",
                "query_match_score": 0.1,
                "citation_count": 0,
            },
            {
                "title": "Landmark deep learning",
                "source": "pubmed",
                "sources": ["pubmed", "crossref"],
                "doi": "10.1038/nature14539",
                "parse_readiness": "ready_via_doi",
                "parse_input_value": "10.1038/nature14539",
                "query_match_score": 0.6,
                "citation_count": 70000,
                "citation_counts": {"crossref": 70000},
            },
        ]
    )
    assert ranked[0]["title"] == "Landmark deep learning"
