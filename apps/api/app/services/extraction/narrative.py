"""Suggests Q-code candidates for free-text NOTAM content (e.g. Item E / 'Full Text')
by blending deterministic lexical matching with fuzzy typo tolerance and semantic vector embeddings
against the active ICAO Doc 8126 selection-criteria catalog (services/rules.py).

Always returns a ranked list, never a single silent answer -- an AIS Officer picks
(or rejects all of) the suggestions.

Suggestion pipeline (three tiers, highest confidence first):
  1. Keyword rules  (keyword_rules.py) -- deterministic, location-noun + condition
     phrase matching with adjacency disambiguation.  Produces the top candidate
     with confidence 80-90 when both subject AND condition are matched.
  2. Lexical scoring -- two-sided word-overlap against all catalog rules.
  3. Semantic vector search (all-MiniLM-L6-v2) -- cosine similarity re-rank.
"""

from __future__ import annotations

import re

from app.services.extraction.fuzzy import (
    normalize_aviation_text,
)
from app.services.extraction.keyword_rules import score_narrative as keyword_score
from app.services.extraction.semantic import get_semantic_matcher
from app.services.rules import SelectionRule, get_catalog

_SCORE_CEILING = 4  # exact subject phrase (2) + exact condition phrase (2)

# Generic connective words carrying no topical signal
_STOPWORDS = {
    "a", "an", "the", "to", "of", "with", "and", "or", "in", "on", "at", "is",
    "are", "due", "for", "by", "as", "now", "not", "between", "from", "until",
}


def _content_words(phrase: str) -> set[str]:
    # Strip attached punctuation ("strip." at a sentence end, "runway," mid list)
    words = (re.sub(r"^\W+|\W+$", "", word) for word in phrase.split())
    return {word for word in words if word and word not in _STOPWORDS and len(word) >= 3}


_AIP_ARP_COORDINATES: dict[str, str] = {
    "DGAA": "0536N00010W",
    "DGAC": "0536N00010W",  # Accra FIR reference centre
    "DGLE": "0933N00052W",
    "DGSI": "0643N00135W",
    "DGAH": "0635N00032E",
    "DGSN": "0722N00220W",
    "DGTK": "0454N00147W",
    "DGLW": "1005N00230W",
    "DGLN": "1057N00105W",
    "DXXX": "0610N00115E",
    "DXNG": "0946N00106E",
    "DXAK": "0731N00111E",
    "DXSK": "0859N00109E",
    "DBBB": "0621N00223E",
    "DBBP": "0921N00237E",
    "DBBN": "1023N00122E",
    "DBBK": "1109N00256E",
    "DBBO": "1102N00058E",
}


def _default_radius(subject_code: str, scope: str) -> str:
    if subject_code in {"MR", "MX", "MW", "FA", "FF", "FG", "FL"} or scope == "A":
        return "005"
    if scope in {"E", "W"}:
        return "999"
    return "025"


def suggest_q_codes(
    narrative: str, limit: int = 5, location_indicator: str | None = None
) -> list[dict[str, object]]:
    """Generates ranked Q-code suggestions for free-text narrative using hybrid
    keyword-lexical-semantic scoring against the ICAO Doc 8126 catalog.
    Also provides default lower/upper limits (000/999) and computed
    coordinates/radius per Doc 8126 standards.
    """
    if not narrative or not narrative.strip():
        return []

    loc = (location_indicator or "DGAA").upper()
    arp_base = _AIP_ARP_COORDINATES.get(loc, "0536N00010W")

    # -----------------------------------------------------------------------
    # TIER 1: Deterministic keyword-rules engine
    # Runs on original narrative (pre-normalisation) so that phrases like
    # "RWY STRIP" survive abbreviation expansion.
    # -----------------------------------------------------------------------
    keyword_candidates = keyword_score(narrative)
    keyword_hits: dict[str, tuple[float, int, SelectionRule]] = {}
    for kc in keyword_candidates:
        q_code = f"Q{kc.subject_code}{kc.condition_code}"
        rule = get_catalog().find_by_qcode(q_code)
        if rule:
            # rank_boost 8-9 beats max lexical (4) + semantic (4) = 6
            rank_boost = kc.confidence / 10.0
            keyword_hits[q_code] = (rank_boost, kc.confidence, rule)

    # -----------------------------------------------------------------------
    # TIER 2: Deterministic lexical scoring (word-overlap)
    # -----------------------------------------------------------------------
    normalized_text = normalize_aviation_text(narrative.casefold(), apply_fuzzy=True)
    text_words = _content_words(normalized_text)

    lexical_scores: dict[str, tuple[int, SelectionRule]] = {}
    for rule in get_catalog().rules:
        subject, condition = rule.subject.casefold(), rule.condition.casefold()
        subject_score = 2 if subject in normalized_text else len(_content_words(subject) & text_words)
        condition_score = 2 if condition in normalized_text else len(_content_words(condition) & text_words)

        if subject_score > 0 and condition_score > 0:
            total_lexical = subject_score + condition_score
            lexical_scores[rule.q_code] = (total_lexical, rule)

    # -----------------------------------------------------------------------
    # TIER 3: Semantic vector search
    # -----------------------------------------------------------------------
    semantic_results = get_semantic_matcher().search(normalized_text, top_k=limit * 2)
    semantic_scores: dict[str, float] = {rule.q_code: score for rule, score in semantic_results}

    # -----------------------------------------------------------------------
    # Blend all three tiers
    # -----------------------------------------------------------------------
    all_q_codes = set(keyword_hits.keys()) | set(lexical_scores.keys()) | set(semantic_scores.keys())
    rules_by_code: dict[str, SelectionRule] = {
        rule.q_code: rule for rule in get_catalog().rules if rule.q_code in all_q_codes
    }

    scored_candidates: list[tuple[float, int, SelectionRule]] = []
    for q_code in all_q_codes:
        rule = rules_by_code.get(q_code)
        if not rule:
            continue

        # Keyword tier takes absolute priority when present
        if q_code in keyword_hits:
            rank, conf, _ = keyword_hits[q_code]
            lex_tuple = lexical_scores.get(q_code)
            if lex_tuple:
                rank += lex_tuple[0] * 0.2  # small lexical confirmation boost
            scored_candidates.append((rank, conf, rule))
            continue

        lexical_tuple = lexical_scores.get(q_code)
        raw_lex_score = lexical_tuple[0] if lexical_tuple else 0
        sem_score = semantic_scores.get(q_code, 0.0)

        if raw_lex_score > 0:
            # Cap lexical-only confidence below keyword tier
            base_conf = min(75, round(raw_lex_score / _SCORE_CEILING * 75))
            if sem_score > 0.5:
                final_conf = min(78, base_conf + round(sem_score * 5))
            else:
                final_conf = base_conf
            combined_rank = raw_lex_score + (sem_score * 2.0)
        else:
            final_conf = min(65, max(35, round(sem_score * 75)))
            combined_rank = sem_score * 2.0

        scored_candidates.append((combined_rank, final_conf, rule))

    scored_candidates.sort(key=lambda item: item[0], reverse=True)

    results: list[dict[str, object]] = []
    for rank, conf, rule in scored_candidates[:limit]:
        radius = _default_radius(rule.subject_code, rule.scope)
        coords_radius = f"{arp_base}{radius}"
        results.append(
            {
                "q_code": rule.q_code,
                "subject": rule.subject,
                "condition": rule.condition,
                "traffic": rule.traffic,
                "purpose": rule.purpose,
                "scope": rule.scope,
                "verification_status": rule.verification_status,
                "score": round(rank, 2),
                "confidence": conf,
                "lower_limit": "000",
                "upper_limit": "999",
                "radius": radius,
                "coordinates_radius": coords_radius,
            }
        )

    return results
