"""Lightweight discovery relevance scoring and hard filtering.

baseline: bag-of-words token overlap (legacy).
denoise: concept-group coverage + score threshold (drop obvious off-topic hits).
"""

from __future__ import annotations

import re
from typing import Any

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+\-]{1,}")
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "of",
        "on",
        "or",
        "the",
        "to",
        "via",
        "with",
        "using",
        "review",
        "about",
        "over",
        "under",
        "between",
        "among",
        "vs",
        "versus",
    }
)

# Soft denoise default; --relax lowers this.
DEFAULT_DENOISE_MIN_SCORE = 0.34
RELAXED_DENOISE_MIN_SCORE = 0.2

# Keep common compounds together when peeling long stopword-free runs.
_COMPOUND_TAILS = frozenset(
    {
        ("energy", "storage"),
        ("heat", "storage"),
        ("thermal", "storage"),
        ("data", "center"),
        ("data", "centers"),
        ("machine", "learning"),
        ("computer", "interface"),
    }
)

# Lightweight chemical / material aliases for denoise matching.
_TOKEN_ALIASES: dict[str, tuple[str, ...]] = {
    "cacl2": ("cacl2", "calcium chloride", "ca cl2", "cacl₂"),
}

_SUBSCRIPT_TRANS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")


def _normalize_text(text: str) -> str:
    return str(text or "").lower().translate(_SUBSCRIPT_TRANS)


def tokenize_query(query: str) -> list[str]:
    return _TOKEN_RE.findall(_normalize_text(query))


def content_tokens(query: str) -> list[str]:
    return [token for token in tokenize_query(query) if token not in _STOPWORDS]


def _is_formula_token(token: str) -> bool:
    return bool(re.search(r"\d", token))


def extract_concept_groups(query: str) -> list[list[str]]:
    """Split query into concept groups on stopwords.

    Example: "liquid cooling for data center" ->
    [["liquid", "cooling"], ["data", "center"]].

    "CaCl2 thermochemical energy storage" ->
    [["cacl2"], ["thermochemical"], ["energy", "storage"]].
    """
    groups: list[list[str]] = []
    current: list[str] = []
    for token in tokenize_query(query):
        if token in _STOPWORDS:
            if current:
                groups.append(current)
                current = []
            continue
        current.append(token)
    if current:
        groups.append(current)
    if not groups:
        return [[token] for token in content_tokens(query)] if content_tokens(query) else []

    if len(groups) != 1:
        return groups

    tokens = groups[0]
    formulas = [[token] for token in tokens if _is_formula_token(token)]
    rest = [token for token in tokens if not _is_formula_token(token)]
    rebuilt: list[list[str]] = list(formulas)

    if not rest:
        return rebuilt or groups

    if len(rest) >= 4:
        if tuple(rest[-2:]) in _COMPOUND_TAILS:
            head = rest[:-2]
            if head:
                rebuilt.append(head)
            rebuilt.append(list(rest[-2:]))
        else:
            # "brain computer interface motor" -> core phrase + trailing qualifier.
            rebuilt.append(rest[:-1])
            rebuilt.append([rest[-1]])
    elif len(rest) == 3 and tuple(rest[-2:]) in _COMPOUND_TAILS:
        rebuilt.append([rest[0]])
        rebuilt.append(list(rest[-2:]))
    else:
        rebuilt.append(rest)
    return [group for group in rebuilt if group]


def item_haystack(item: dict[str, Any]) -> str:
    return _normalize_text(
        " ".join(
            str(value or "")
            for value in (
                item.get("title"),
                item.get("venue"),
                item.get("abstract_preview"),
                item.get("doi"),
                item.get("nct_id"),
            )
        )
    )


def _light_stem(token: str) -> str:
    text = str(token or "").strip().lower()
    for suffix in ("ing", "ed", "es", "s"):
        if len(text) > len(suffix) + 2 and text.endswith(suffix) and not text.endswith("ss"):
            return text[: -len(suffix)]
    return text


def _token_variants(token: str) -> list[str]:
    text = str(token or "").strip().lower()
    if not text:
        return []
    variants = [text]
    # Lightweight singular/plural: center <-> centers (not centered).
    if text.endswith("s") and len(text) > 3 and not text.endswith("ss"):
        variants.append(text[:-1])
    else:
        variants.append(text + "s")
    stem = _light_stem(text)
    if stem and stem != text:
        variants.append(stem)
        variants.append(stem + "ed")
        variants.append(stem + "ing")
    return list(dict.fromkeys(variants))


def _has_token(haystack: str, token: str) -> bool:
    """Word-boundary token match so `center` does not hit `centered`."""
    text = str(token or "").strip().lower()
    aliases = _TOKEN_ALIASES.get(text, ())
    candidates = list(dict.fromkeys([*_token_variants(text), *aliases]))
    for variant in candidates:
        if " " in variant:
            if _has_phrase(haystack, variant):
                return True
            continue
        if re.search(rf"(?<![a-z0-9+\-]){re.escape(variant)}(?![a-z0-9+\-])", haystack):
            return True
    return False


def _has_phrase(haystack: str, phrase: str) -> bool:
    text = str(phrase or "").strip().lower()
    if not text:
        return False
    if " " not in text:
        return _has_token(haystack, text)
    parts = text.split()
    # Allow each part's simple plural variant in phrase position.
    part_patterns = []
    for part in parts:
        alts = _token_variants(part)
        part_patterns.append("(?:" + "|".join(re.escape(alt) for alt in alts) + ")")
    pattern = r"(?<![a-z0-9+\-])" + r"[\s\-]+".join(part_patterns) + r"(?![a-z0-9+\-])"
    return bool(re.search(pattern, haystack))


def score_query_match_baseline(item: dict[str, Any], *, query: str) -> dict[str, Any]:
    tokens = content_tokens(query)
    if not tokens:
        return {}
    haystack = item_haystack(item)
    unique = list(dict.fromkeys(tokens))
    matched = sorted({token for token in unique if _has_token(haystack, token)})
    score = round(len(matched) / len(unique), 4)
    return {
        "query_match_score": score,
        "query_matched_terms": matched,
        "query_match_warning": "low_query_term_overlap" if score < 0.25 else None,
        "query_match_mode": "baseline",
        "concept_group_coverage": None,
    }


def score_query_match_denoise(item: dict[str, Any], *, query: str) -> dict[str, Any]:
    groups = extract_concept_groups(query)
    tokens = content_tokens(query)
    if not groups and not tokens:
        return {}
    haystack = item_haystack(item)
    matched_groups: list[str] = []
    structured = len(groups) >= 2
    for group in groups:
        phrase = " ".join(group)
        if len(group) >= 2:
            # Structured multi-concept queries: require contiguous phrase match.
            if structured and phrase and _has_phrase(haystack, phrase):
                matched_groups.append(phrase)
                continue
            if structured:
                continue
            # Single-run queries (e.g. "hvdc transmission grid"):
            # require the head token (often the distinctive acronym) plus majority coverage.
            token_hits = sum(1 for token in group if _has_token(haystack, token))
            need = max(2, (len(group) * 2 + 2) // 3)  # ~ceil(2/3)
            head_ok = _has_token(haystack, group[0])
            if (phrase and _has_phrase(haystack, phrase)) or (head_ok and token_hits >= need):
                matched_groups.append(phrase)
            continue
        if group and _has_token(haystack, group[0]):
            matched_groups.append(phrase)
    group_coverage = round(len(matched_groups) / len(groups), 4) if groups else 0.0
    unique = list(dict.fromkeys(tokens))
    matched_terms = sorted({token for token in unique if _has_token(haystack, token)})
    token_overlap = round(len(matched_terms) / len(unique), 4) if unique else 0.0
    # Prefer concept coverage; keep some token signal for ranking soft ties.
    score = round(0.7 * group_coverage + 0.3 * token_overlap, 4)
    warning = None
    if group_coverage < 0.5 or score < DEFAULT_DENOISE_MIN_SCORE:
        warning = "low_concept_group_coverage"
    return {
        "query_match_score": score,
        "query_matched_terms": matched_terms,
        "query_matched_groups": matched_groups,
        "query_match_warning": warning,
        "query_match_mode": "denoise",
        "concept_group_coverage": group_coverage,
        "concept_groups": [" ".join(group) for group in groups],
    }


def score_query_match(item: dict[str, Any], *, query: str, mode: str = "baseline") -> dict[str, Any]:
    normalized = str(mode or "baseline").strip().lower() or "baseline"
    if normalized == "denoise":
        return score_query_match_denoise(item, query=query)
    return score_query_match_baseline(item, query=query)


def relevance_threshold(*, mode: str, relax: bool = False) -> float | None:
    normalized = str(mode or "baseline").strip().lower() or "baseline"
    if normalized != "denoise":
        return None
    return RELAXED_DENOISE_MIN_SCORE if relax else DEFAULT_DENOISE_MIN_SCORE


def filter_by_relevance(
    items: list[dict[str, Any]],
    *,
    mode: str = "baseline",
    relax: bool = False,
    min_score: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Hard-drop weak matches in denoise mode. baseline is a no-op."""
    threshold = min_score if min_score is not None else relevance_threshold(mode=mode, relax=relax)
    groups_sample = None
    for item in items:
        if isinstance(item.get("concept_groups"), list):
            groups_sample = item.get("concept_groups")
            break
    meta: dict[str, Any] = {
        "relevance_mode": str(mode or "baseline").strip().lower() or "baseline",
        "relevance_relax": bool(relax),
        "relevance_min_score": threshold,
        "relevance_filtered_out": 0,
        "concept_groups": groups_sample,
    }
    if threshold is None:
        return list(items), meta

    kept: list[dict[str, Any]] = []
    dropped = 0
    for item in items:
        try:
            score = float(item.get("query_match_score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        coverage = item.get("concept_group_coverage")
        try:
            coverage_f = float(coverage) if coverage is not None else score
        except (TypeError, ValueError):
            coverage_f = score
        groups = item.get("concept_groups") if isinstance(item.get("concept_groups"), list) else []
        # Multi-concept queries: require every concept group (e.g. liquid cooling + data center).
        if len(groups) >= 2:
            if coverage_f >= 0.999:
                kept.append(item)
            else:
                dropped += 1
            continue
        # Keep if either blended score or raw group coverage clears the bar.
        if score >= threshold or coverage_f >= threshold:
            kept.append(item)
        else:
            dropped += 1
    meta["relevance_filtered_out"] = dropped
    return kept, meta
