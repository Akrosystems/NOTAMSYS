"""Deterministic keyword-rules engine for ICAO Doc 8126 Q-code selection.

Runs *before* the semantic vector search (narrative.py) and produces
(subject_code, condition_code, confidence) candidates from explicit token
matching.  Handles the 70%+ of NOTAM narratives that use predictable
standard phrasing -- e.g. "EAST SIDE OF RWY STRIP, EQUIPMENT AND
PERSONNEL" -> QMWHW (strip or shoulder * work in progress).

Key insight missing from the semantic-only approach:
- "RWY STRIP" / "STRIP" is Doc 8126 subject MW (strip or shoulder)
  NOT MR (runway pavement).
- Adjacency markers ("east/west side of", "adjacent to", "beside")
  signal the subject is the surface *next to* the named feature, not the
  named feature itself.  Strip + adjacency -> MW, not MR.

Rule confidence levels (0-100, never 100 -- a human confirms):
  EXACT_PHRASE  : 88  (full subject + full condition phrase in text)
  TOKEN_MATCH   : 72  (all content words of subject + condition matched)
  PARTIAL_MATCH : 55  (subject matched, condition partially matched)
  CONDITION_ONLY: 45  (condition matched but subject ambiguous)
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Location-noun -> Doc 8126 subject codes
# Ordered from most-specific to most-generic (tried in order).
# Each entry: (patterns, primary_subject_code, alternate_codes)
# ---------------------------------------------------------------------------
LOCATION_SUBJECT_RULES: list[tuple[list[str], str, list[str]]] = [
    # Movement-area specifics (check before generic "runway")
    (["strip", "shoulder", "runway strip", "rwy strip"], "MW", ["MR"]),
    (["runway turning bay", "turning bay"], "MU", ["MR"]),
    (["rapid exit taxiway", "ret "], "MY", ["MX"]),
    (["stop bar", "stopbar"], "MO", []),
    (["stopway", "swy"], "MS", ["MR"]),
    (["clearway", "cwy"], "MC", []),
    (["threshold", "thr"], "MT", ["MR"]),
    (["taxiway", "twy", "taxi track"], "MX", []),
    (["apron", "parking area", "ramp"], "MN", ["MK"]),
    (["aircraft stands", "aircraft stand", "acft stands", "acft stand", "stands", "stand"], "MP", ["MN"]),
    (["daylight marking", "runway marking", "marking"], "MM", ["MR"]),
    (["runway", "rwy"], "MR", []),
    (["movement area", "manoeuvring area"], "MA", []),
    # Heliport / helicopter surfaces
    (["helipad", "helideck", "helicopter alighting", "alighting area"], "FH", []),
    (["heliport"], "FP", []),
    # Lighting
    (["approach lighting", "approach light", "als", "alsf", "malsr"], "LA", []),
    (["papi", "precision approach path indicator"], "LB", []),
    (["vasi", "visual approach slope"], "LB", []),
    (["runway light", "runway edge light", "redl", "reil"], "LR", []),
    (["taxiway light", "twy light", "tgl"], "LT", []),
    (["aerodrome beacon", "bcn"], "LE", []),
    (["obstacle light", "obstruction light"], "LO", []),
    # Navigation aids
    (["ils", "instrument landing system"], "IA", []),
    (["loc", "localizer", "localiser"], "IC", ["IA"]),
    (["glide path", "glide slope", "gp "], "ID", ["IA"]),
    (["vor", "vhf omnidirectional"], "NA", []),
    (["dme", "distance measuring"], "ND", []),
    (["ndb", "non-directional beacon"], "NB", []),
    (["tacan"], "NT", []),
    (["radar", "psr", "ssr", "mssr"], "OA", []),
    # ATS / comms
    (["atis", "automatic terminal information"], "CF", []),
    (["frequency", "freq"], "CA", []),
    # Aerodrome generic (check last)
    (["aerodrome", "airport", "ad "], "FA", []),
]

# ---------------------------------------------------------------------------
# Condition phrase -> Doc 8126 condition codes
# Primary operational status (LC/AS/AK/AO) takes precedence over background reasons
# (e.g. "CLOSED DUE TO WIP" -> LC (Closed), not HW (Work in progress), because
# operational closure determines PIB routing, Purpose BO/NBO, and pilot impact).
# ---------------------------------------------------------------------------
CONDITION_RULES: list[tuple[list[str], str]] = [
    # Closed / unavailable (Doc 8126 condition code LC) - takes operational precedence
    (["closed", "clsd", "not available", "unavailable", "not avbl",
      "temporarily closed", "temp clsd"], "LC"),
    # Unserviceable (Doc 8126 condition code AS)
    (["unserviceable", "u/s", "unserv", "out of service", "oos",
      "defective", "inoperative", "inop"], "AS"),
    # Resumed / restored (Doc 8126 condition code AK)
    (["resumed", "restored", "back in service", "serviceable",
      "returned to service", "operational again"], "AK"),
    # Available / operational (Doc 8126 condition code AO)
    (["available", "avbl", "operational", "in service",
      "commissioned", "activated"], "AO"),
    # Restricted / limited (Doc 8126 condition code RL)
    (["restricted", "restriction", "limited use", "partial"], "RL"),
    # Reduced / changed (Doc 8126 condition code AC)
    (["reduced", "shortened", "changed", "amended", "revised"], "AC"),
    # Work in progress / hazard (Doc 8126 condition code HW - applies when not closed)
    (["work in progress", "wip", "equipment and personnel", "presence of equipment",
      "presence of workers", "workers and vehicles", "personnel", "construction",
      "rehabilitation", "resurfacing", "milling", "painting", "marking work"], "HW"),
    # Obstacles
    (["obstacle", "obstruction", "obst", "crane", "tower erected",
      "structure", "antenna", "mast"], "OB"),
    # Danger / hazard (general)
    (["danger", "hazard", "risk", "caution", "ctn", "warning"], "OB"),
    # Military
    (["military", "mil ops", "military operations only"], "AM"),
    # Night / hours restriction
    (["night operation", "night only", "night ops"], "AN"),
]

# ---------------------------------------------------------------------------
# Adjacency markers: presence means the subject is the surface
# *adjacent to* the named location noun, not the noun itself.
# "EAST SIDE OF RWY STRIP" -> subject is STRIP (MW), not RWY (MR)
# ---------------------------------------------------------------------------
_ADJACENCY_PATTERN = re.compile(
    r"\b("
    r"east side of|west side of|north side of|south side of"
    r"|east of|west of|north of|south of"
    r"|adjacent to|beside|alongside|vicinity of"
    r"|near|on (the )?side of"
    r")\b",
    re.IGNORECASE,
)

# After adjacency-based re-mapping, if the primary match was MR (runway)
# but adjacency was detected, map to MW (strip/shoulder) instead.
_ADJACENCY_REMAP: dict[str, str] = {
    "MR": "MW",   # runway -> strip/shoulder
    "MX": "MN",   # taxiway -> apron (edge)
}

_CTN_PATTERN = re.compile(r"\b(ctn|caution|ctn advised|caution advised)\b", re.IGNORECASE)


@dataclass(frozen=True)
class KeywordCandidate:
    subject_code: str
    condition_code: str
    confidence: int  # 0-100
    matched_location: str
    matched_condition: str
    adjacency_detected: bool


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold().strip())


def _has_adjacency(text: str) -> bool:
    return bool(_ADJACENCY_PATTERN.search(text))


def _match_location(text: str) -> tuple[str, str, bool] | None:
    """Returns (subject_code, matched_phrase, adjacency_detected) or None."""
    adjacency = _has_adjacency(text)
    for patterns, primary, _alternates in LOCATION_SUBJECT_RULES:
        for phrase in patterns:
            if phrase in text:
                subject = primary
                if adjacency and subject in _ADJACENCY_REMAP:
                    subject = _ADJACENCY_REMAP[subject]
                return subject, phrase, adjacency
    return None


def _match_condition(text: str) -> tuple[str, str] | None:
    """Returns (condition_code, matched_phrase) or None."""
    for patterns, code in CONDITION_RULES:
        for phrase in patterns:
            if phrase in text:
                return code, phrase
    return None


def score_narrative(narrative: str) -> list[KeywordCandidate]:
    """Returns deterministic keyword candidates for the given narrative,
    ranked by confidence (highest first).
    """
    if not narrative or len(narrative.strip()) < 4:
        return []

    text = _normalize(narrative)
    ctn_reinforced = bool(_CTN_PATTERN.search(text))

    loc_result = _match_location(text)
    cond_result = _match_condition(text)

    if not loc_result and not cond_result:
        return []

    results: list[KeywordCandidate] = []

    if loc_result and cond_result:
        subject_code, loc_phrase, adjacency = loc_result
        condition_code, cond_phrase = cond_result
        base_conf = 80 if adjacency else 88
        if ctn_reinforced and condition_code in {"HW", "OB"}:
            base_conf = min(90, base_conf + 4)
        results.append(
            KeywordCandidate(
                subject_code=subject_code,
                condition_code=condition_code,
                confidence=base_conf,
                matched_location=loc_phrase,
                matched_condition=cond_phrase,
                adjacency_detected=adjacency,
            )
        )
    elif loc_result:
        subject_code, loc_phrase, adjacency = loc_result
        results.append(
            KeywordCandidate(
                subject_code=subject_code,
                condition_code="HW",
                confidence=48,
                matched_location=loc_phrase,
                matched_condition="(inferred)",
                adjacency_detected=adjacency,
            )
        )
    elif cond_result:
        condition_code, cond_phrase = cond_result
        results.append(
            KeywordCandidate(
                subject_code="FA",
                condition_code=condition_code,
                confidence=42,
                matched_location="(aerodrome generic)",
                matched_condition=cond_phrase,
                adjacency_detected=False,
            )
        )

    return results
