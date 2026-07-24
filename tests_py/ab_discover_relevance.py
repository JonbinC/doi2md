#!/usr/bin/env python3
"""Simple A/B: baseline vs denoise on a handful of broad queries."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mdtero.local_discovery import search_local_discovery  # noqa: E402

DEFAULT_QUERIES = [
    "liquid cooling for data center",
    "HVDC transmission grid",
    "brain computer interface motor",
]

from mdtero.discovery_relevance import extract_concept_groups  # noqa: E402


def _on_topic(title: str, query: str) -> bool:
    """Title is on-topic if it covers at least half of the concept groups."""
    hay = title.lower()
    groups = extract_concept_groups(query)
    if not groups:
        return True
    hits = 0
    for group in groups:
        phrase = " ".join(group)
        if phrase and phrase in hay:
            hits += 1
            continue
        if group and all(re.search(rf"(?<![a-z0-9+\-]){re.escape(t)}(?![a-z0-9+\-])", hay) for t in group):
            hits += 1
    return hits / len(groups) >= 0.5


def _titles(result: dict, *, query: str) -> list[dict]:
    rows = []
    for item in result.get("items") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        rows.append(
            {
                "title": title,
                "score": item.get("query_match_score"),
                "coverage": item.get("concept_group_coverage"),
                "on_topic": _on_topic(title, query),
            }
        )
    return rows


def run_one(query: str, *, providers: str, limit: int, openalex_key: str | None, s2_key: str | None) -> dict:
    common = dict(
        query=query,
        limit=limit,
        providers=providers,
        enrich="none",
        openalex_api_key=openalex_key,
        semantic_scholar_api_key=s2_key,
    )
    baseline = search_local_discovery(**common, relevance="baseline")
    denoise = search_local_discovery(**common, relevance="denoise")
    b_rows = _titles(baseline, query=query)
    d_rows = _titles(denoise, query=query)
    return {
        "query": query,
        "baseline": {
            "count": len(b_rows),
            "on_topic": sum(1 for row in b_rows if row["on_topic"]),
            "avg_score": round(sum(float(r["score"] or 0) for r in b_rows) / max(len(b_rows), 1), 3),
            "titles": b_rows,
            "filtered_out": (baseline.get("relevance") or {}).get("relevance_filtered_out"),
        },
        "denoise": {
            "count": len(d_rows),
            "on_topic": sum(1 for row in d_rows if row["on_topic"]),
            "avg_score": round(sum(float(r["score"] or 0) for r in d_rows) / max(len(d_rows), 1), 3),
            "titles": d_rows,
            "filtered_out": (denoise.get("relevance") or {}).get("relevance_filtered_out"),
            "concept_groups": (denoise.get("relevance") or {}).get("concept_groups"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--providers", default="arxiv,crossref,pubmed")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    from mdtero.config import load_config

    cfg = load_config()
    academic = cfg.academic
    queries = args.query or DEFAULT_QUERIES
    report = {
        "providers": args.providers,
        "limit": args.limit,
        "cases": [
            run_one(
                query,
                providers=args.providers,
                limit=args.limit,
                openalex_key=getattr(academic, "openalex_api_key", None),
                s2_key=getattr(academic, "semantic_scholar_api_key", None),
            )
            for query in queries
        ],
    }
    total_b = sum(case["baseline"]["on_topic"] for case in report["cases"])
    total_d = sum(case["denoise"]["on_topic"] for case in report["cases"])
    total_b_n = sum(case["baseline"]["count"] for case in report["cases"])
    total_d_n = sum(case["denoise"]["count"] for case in report["cases"])
    report["summary"] = {
        "baseline_on_topic": f"{total_b}/{total_b_n}",
        "denoise_on_topic": f"{total_d}/{total_d_n}",
        "baseline_precision": round(total_b / max(total_b_n, 1), 3),
        "denoise_precision": round(total_d / max(total_d_n, 1), 3),
        "winner": (
            "denoise"
            if (total_d / max(total_d_n, 1)) > (total_b / max(total_b_n, 1))
            else ("tie" if total_d / max(total_d_n, 1) == total_b / max(total_b_n, 1) else "baseline")
        ),
    }

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps({"summary": report["summary"], "cases": [
        {
            "query": c["query"],
            "baseline_on_topic": f"{c['baseline']['on_topic']}/{c['baseline']['count']}",
            "denoise_on_topic": f"{c['denoise']['on_topic']}/{c['denoise']['count']}",
            "denoise_filtered_out": c["denoise"]["filtered_out"],
            "baseline_top": [t["title"][:90] for t in c["baseline"]["titles"][:5]],
            "denoise_top": [t["title"][:90] for t in c["denoise"]["titles"][:5]],
        }
        for c in report["cases"]
    ]}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
