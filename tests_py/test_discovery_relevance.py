from __future__ import annotations

from mdtero.discovery_relevance import (
    extract_concept_groups,
    filter_by_relevance,
    score_query_match,
)


def test_extract_concept_groups_splits_on_stopwords():
    assert extract_concept_groups("liquid cooling for data center") == [
        ["liquid", "cooling"],
        ["data", "center"],
    ]


def test_extract_concept_groups_keeps_energy_storage_and_formula():
    assert extract_concept_groups("CaCl2 thermochemical energy storage") == [
        ["cacl2"],
        ["thermochemical"],
        ["energy", "storage"],
    ]


def test_denoise_matches_cacl2_alias_and_tes_phrase():
    scored = score_query_match(
        {
            "title": "Calcium chloride composites for thermochemical energy storage",
            "abstract_preview": "Hydration of CaCl2 salt hydrates for seasonal heat storage.",
        },
        query="CaCl2 thermochemical energy storage",
        mode="denoise",
    )
    assert scored["concept_group_coverage"] == 1.0
    kept, meta = filter_by_relevance(
        [{**scored, "title": "Calcium chloride composites for thermochemical energy storage"}],
        mode="denoise",
    )
    assert meta["relevance_filtered_out"] == 0
    assert len(kept) == 1


def test_denoise_keeps_on_topic_and_drops_soil_noise():
    query = "liquid cooling for data center"
    good = score_query_match(
        {
            "title": "Immersion liquid cooling for high-density data center servers",
            "abstract_preview": "Two-phase immersion cooling in hyperscale data centers.",
        },
        query=query,
        mode="denoise",
    )
    partial = score_query_match(
        {"title": "A Review of 775 Non-U.S. Data Centers"},
        query=query,
        mode="denoise",
    )
    bad = score_query_match(
        {
            "title": "Soil remediation and oil removal from contaminated land",
            "abstract_preview": "Geochemistry of petroleum hydrocarbon cleanup.",
        },
        query=query,
        mode="denoise",
    )
    assert good["concept_group_coverage"] == 1.0
    assert float(partial["concept_group_coverage"] or 0) < 1.0
    assert bad["query_match_score"] < 0.34
    kept, meta = filter_by_relevance(
        [
            {**good, "title": "Immersion liquid cooling for high-density data center servers"},
            {**partial, "title": "A Review of 775 Non-U.S. Data Centers"},
            {**bad, "title": "Soil remediation and oil removal from contaminated land"},
        ],
        mode="denoise",
    )
    assert meta["relevance_filtered_out"] == 2
    assert len(kept) == 1
    assert "liquid cooling" in kept[0]["title"].lower()


def test_baseline_does_not_hard_filter():
    items = [
        {
            "title": "Soil remediation and oil removal",
            "query_match_score": 0.1,
            "concept_group_coverage": 0.0,
        }
    ]
    kept, meta = filter_by_relevance(items, mode="baseline")
    assert len(kept) == 1
    assert meta["relevance_min_score"] is None


def test_token_match_uses_word_boundaries():
    query = "liquid cooling for data center"
    centered = score_query_match(
        {"title": "TSSC comet-centered data products from TESS"},
        query=query,
        mode="denoise",
    )
    assert "center" not in centered["query_matched_terms"]
    assert float(centered["query_match_score"] or 0) < 0.34


def test_denoise_matches_simple_plurals():
    scored = score_query_match(
        {"title": "Direct-to-Chip Liquid Cooling for Data Centers"},
        query="liquid cooling for data center",
        mode="denoise",
    )
    assert scored["concept_group_coverage"] == 1.0
    assert float(scored["query_match_score"] or 0) >= 0.8


def test_denoise_rejects_distant_token_coincidence():
    scored = score_query_match(
        {
            "title": "TSSC comet-centered data products from TESS",
            "abstract_preview": "The TESS Science Support Center created these data products.",
        },
        query="liquid cooling for data center",
        mode="denoise",
    )
    assert "data center" not in (scored.get("query_matched_groups") or [])
    assert float(scored["concept_group_coverage"] or 0) == 0.0
