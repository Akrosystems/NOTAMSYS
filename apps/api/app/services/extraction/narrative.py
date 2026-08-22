"""Suggests Q-code candidates for free-text NOTAM content (e.g. Item E /
'Full Text') by matching against the active selection-criteria catalog
(services/rules.py). Always returns a ranked list, never a single silent
answer -- an AIS Officer picks (or rejects all of) the suggestions."""

import re

from app.services.rules import SelectionRule, get_catalog

_SCORE_CEILING = 4  # exact subject phrase (2) + exact condition phrase (2)

# Real NOTAM text -- AFTN messages and hand-filled paper forms alike -- is
# written in standard ICAO abbreviations, not the catalog's spelled-out
# subject/condition wording. Confirmed live against two real documents: "LOC
# ... U/S" and "WIP ... RWY ... STRIP" both scored zero against their correct
# rules (QILAS, QMWHW/QMRHW) until expanded, since neither "localizer" nor
# "unserviceable" nor "work in progress" ever appears verbatim in abbreviated
# text. Word-boundary expansion, not exhaustive Doc 8400 coverage -- scoped
# to abbreviations that actually map to this catalog's vocabulary.
_ABBREVIATIONS: dict[str, str] = {
    "rwy": "runway", "twy": "taxiway", "loc": "localizer", "u/s": "unserviceable",
    "wip": "work in progress", "apch": "approach", "arr": "arrival", "dep": "departure",
    "acft": "aircraft", "hel": "helicopter", "ops": "operations", "clsd": "closed",
    "avbl": "available", "mil": "military", "tempo": "temporary", "lgt": "lighting",
    "lts": "lights", "thr": "threshold", "twr": "aerodrome control tower",
    "bcn": "aerodrome beacon", "vasi": "visual approach slope indicator system",
    "gp": "glide path", "ndb": "non-directional radio beacon",
    "dme": "distance measuring equipment", "mkr": "marker", "ils": "instrument landing system",
    "obst": "obstacle", "svc": "service", "opr": "operating",
}
_ABBREVIATION_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(term) for term in sorted(_ABBREVIATIONS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# Generic connective words carry no topical signal -- without excluding
# them, two unrelated rules can each pick up a stray one-word overlap (e.g.
# "to" from "...changed to" and "ils" as a bare substring of "DME associated
# with ILS") and their scores sum past the noise floor together, exactly the
# false-positive pattern confirmed live: a real ILS-unserviceable NOTAM
# matched "DME associated with ILS / operating frequency(ies) changed to"
# at 45% confidence with zero genuine relevance.
_STOPWORDS = {
    "a", "an", "the", "to", "of", "with", "and", "or", "in", "on", "at", "is",
    "are", "due", "for", "by", "as", "now", "not",
}


def _expand_abbreviations(text: str) -> str:
    return _ABBREVIATION_PATTERN.sub(lambda match: _ABBREVIATIONS[match.group(0).lower()], text)


def _content_words(phrase: str) -> set[str]:
    # Strip attached punctuation ("strip." at a sentence end, "runway," mid
    # list) -- confirmed live: a real form reading "...RWY 05/23 STRIP."
    # failed to match the catalog's "strip or shoulder" subject purely
    # because the trailing period made "strip." != "strip".
    words = (re.sub(r"^\W+|\W+$", "", word) for word in phrase.split())
    return {word for word in words if word and word not in _STOPWORDS and len(word) >= 3}


def suggest_q_codes(narrative: str, limit: int = 3) -> list[dict[str, object]]:
    text = _expand_abbreviations(narrative.casefold())
    text_words = _content_words(text)
    scored: list[tuple[int, SelectionRule]] = []
    for rule in get_catalog().rules:
        subject, condition = rule.subject.casefold(), rule.condition.casefold()
        subject_score = 2 if subject in text else len(_content_words(subject) & text_words)
        condition_score = 2 if condition in text else len(_content_words(condition) & text_words)
        # Require real signal from *both* sides -- a match on only the
        # subject or only the condition means the other half was guessed,
        # which is exactly the coincidental-overlap failure mode above.
        if subject_score > 0 and condition_score > 0:
            scored.append((subject_score + condition_score, rule))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "q_code": rule.q_code,
            "subject": rule.subject,
            "condition": rule.condition,
            "traffic": rule.traffic,
            "purpose": rule.purpose,
            "scope": rule.scope,
            "verification_status": rule.verification_status,
            "score": score,
            "confidence": min(90, round(score / _SCORE_CEILING * 90)),
        }
        for score, rule in scored[:limit]
    ]
