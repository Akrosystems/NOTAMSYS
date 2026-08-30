"""Fuzzy OCR typo correction and ICAO Doc 8400 / EUROCONTROL OPADD Ed 4.1 abbreviation normalizer.

Uses RapidFuzz Levenshtein distance to resolve scanning artifacts and typographical errors
on hardcopy/faxed intake forms, mapping noisy tokens to standard aeronautical terminology
without altering numeric/coordinate safety fields or standard connective words.
"""

from __future__ import annotations

import re
from functools import lru_cache

try:
    from rapidfuzz.distance import Levenshtein
except ImportError:  # pragma: no cover
    Levenshtein = None  # type: ignore[assignment]


# Standard aviation abbreviations from ICAO Doc 8400 and EUROCONTROL OPADD Ed 4.1
# plus Ghana AIP specific location terms.
ICAO_OPADD_ABBREVIATIONS: dict[str, str] = {
    # Aerodrome & Surface
    "rwy": "runway",
    "twy": "taxiway",
    "txwy": "taxiway",
    "apron": "apron",
    "strip": "strip",
    "thr": "threshold",
    "tora": "take-off run available",
    "toda": "take-off distance available",
    "asda": "accelerate-stop distance available",
    "lda": "landing distance available",
    "cwy": "clearway",
    "swy": "stopway",
    "ad": "aerodrome",
    "fir": "flight information region",
    # Status & Operations
    "u/s": "unserviceable",
    "unserv": "unserviceable",
    "unserviceable": "unserviceable",
    "clsd": "closed",
    "wip": "work in progress",
    "ops": "operations",
    "opr": "operating",
    "oprid": "operational",
    "serviceable": "resumed normal operation serviceable",
    "servicable": "resumed normal operation serviceable",
    "resumed": "resumed normal operation",
    "avbl": "available",
    "unavbl": "unavailable",
    "tempo": "temporary",
    "perm": "permanent",
    "maint": "maintenance",
    "const": "construction",
    "calib": "calibration",
    "act": "active",
    "deg": "degraded",
    "lgt": "lighting",
    "lts": "lights",
    "flg": "flashing",
    "ser": "service",
    "svc": "service",
    "obst": "obstacle",
    "obstr": "obstruction",
    "rvr": "runway visual range",
    # Navigation, Radio & ATS Facilities
    "vhf": "air/ground facility vhf",
    "loc": "localizer",
    "localizer": "localizer",
    "gp": "glide path",
    "ils": "instrument landing system",
    "dme": "distance measuring equipment",
    "vor": "very high frequency omnidirectional radio range",
    "dvor": "doppler vor",
    "ndb": "non-directional radio beacon",
    "vasi": "visual approach slope indicator system",
    "papi": "precision approach path indicator",
    "mkr": "marker",
    "twr": "aerodrome control tower",
    "bcn": "aerodrome beacon",
    "app": "approach control",
    "acc": "area control centre",
    "atis": "automatic terminal information service",
    "awos": "automated weather observing system",
    "met": "meteorological",
    "volmet": "volmet meteorological broadcast",
    "rad": "radar",
    # Procedures & Movement
    "apch": "approach",
    "arr": "arrival",
    "dep": "departure",
    "acft": "aircraft",
    "hel": "helicopter",
    "mil": "military",
    "civ": "civil",
    "fl": "flight level",
    "alt": "altitude",
    "elev": "elevation",
    "freq": "air/ground facility frequency",
    "frequency": "air/ground facility frequency",
    "wi": "within",
    "btn": "between",
    "wef": "with effect from",
    "til": "until",
    "dist": "distance",
    "dim": "dimensions",
    "exp": "expected",
    "info": "information",
    # Ghana AIP locations
    "kotoka": "kotoka international airport accra",
    "accra": "accra",
    "tamale": "tamale airport",
    "kumasi": "kumasi airport",
    "sunyani": "sunyani airport",
    "takoradi": "takoradi airport",
    "wa": "wa airport",
    "ho": "ho airport",
    "navrongo": "navrongo airstrip",
}

# Standard English stopwords that must never be altered by fuzzy matching
STOPWORDS = {
    "a", "an", "the", "to", "of", "with", "and", "or", "in", "on", "at", "is",
    "are", "due", "for", "by", "as", "now", "not", "from", "between", "until",
    "into", "over", "all", "out", "new", "under", "per",
}

# Pre-compiled regex for known canonical abbreviations
_ABBREVIATION_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(ICAO_OPADD_ABBREVIATIONS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


@lru_cache(maxsize=1024)
def fuzzy_correct_token(word: str) -> str:
    """Corrects single-token OCR corruptions using exact matching, digit substitution,

    and Levenshtein distance.
    """
    cleaned = word.lower().strip(".,;:()[]{}'\"/-")
    if not cleaned or len(cleaned) < 2:
        return word

    if cleaned in STOPWORDS:
        return word

    if cleaned in ICAO_OPADD_ABBREVIATIONS:
        return ICAO_OPADD_ABBREVIATIONS[cleaned]

    # Attempt OCR digit substitutions
    if any(ch.isdigit() for ch in cleaned):
        for ocr_map in [
            {"0": "o", "1": "i", "5": "s", "8": "b"},
            {"0": "o", "1": "l", "5": "s", "8": "b"},
        ]:
            substituted = "".join(ocr_map.get(ch, ch) for ch in cleaned)
            if substituted in ICAO_OPADD_ABBREVIATIONS:
                return ICAO_OPADD_ABBREVIATIONS[substituted]

    # Don't fuzzy match tokens that are strictly numeric (e.g. runway numbers '03/21', FL '245')
    if re.match(r"^\d+(?:/\d+)?$", cleaned):
        return word

    # Levenshtein distance check against known aviation terms
    if Levenshtein is not None and len(cleaned) >= 3:
        best_cand: str | None = None
        min_dist = 999
        for abbr, full_phrase in ICAO_OPADD_ABBREVIATIONS.items():
            if abs(len(abbr) - len(cleaned)) <= 1:
                dist = Levenshtein.distance(cleaned, abbr)
                if dist < min_dist:
                    min_dist = dist
                    best_cand = full_phrase
        if min_dist <= 1 and best_cand is not None:
            return best_cand

    return word


def normalize_aviation_text(text: str, apply_fuzzy: bool = True) -> str:
    """Normalizes raw OCR/extracted narrative by expanding ICAO/OPADD abbreviations

    and correcting OCR noise.
    """
    if not text:
        return ""

    if not apply_fuzzy or Levenshtein is None:
        return _ABBREVIATION_PATTERN.sub(
            lambda match: ICAO_OPADD_ABBREVIATIONS[match.group(0).lower()], text
        )

    # Word-by-word token normalization
    tokens = text.split()
    corrected_tokens: list[str] = []
    for token in tokens:
        m = re.match(r"^(\W*)([\w/]+)(\W*)$", token)
        if m:
            prefix, core, suffix = m.groups()
            corrected_core = fuzzy_correct_token(core)
            corrected_tokens.append(f"{prefix}{corrected_core}{suffix}")
        else:
            corrected_tokens.append(token)

    return " ".join(corrected_tokens)
