"""Deterministic grammar/regex parsers for safety-critical NOTAM fields.

These own dates, coordinates, limits and location indicators precisely
because they are safety-critical: a statistical model never writes one of
these values directly (see services/extraction/narrative.py for the one
place a ranked, non-authoritative suggestion is offered instead).

Compliant with ICAO Doc 10066 (PANS-AIM), EUROCONTROL OPADD Ed 4.1, Ghana AIP
7th Edition (21 May 2026), and ASECNA eAIP Togo (eff. 06 AUG 2026) / Benin
(eff. 09 JUL 2026).
"""

from __future__ import annotations

import re

from app.services.extraction.candidates import ExtractedFieldCandidate

# Accra FIR (DGAC) authentic location indicators
# Sources:
#   Ghana: GCAA AIP 7th Edition (21 May 2026)
#   Togo:  ASECNA eAIP AD-2.DXXX / DXNG / DXAK / DXSK (eff. 06 AUG 2026)
#   Benin: ASECNA eAIP AD-2.DBBB / DBBP / DBBN / DBBK / DBBO (eff. 09 JUL 2026)
GHANA_LOCATION_INDICATORS = {
    # Ghana
    "DGAA": "Kotoka International Airport, Accra",
    "DGAH": "Ho Airport",
    "DGLE": "Tamale International Airport",
    "DGLN": "Navrongo Airstrip",
    "DGLW": "Wa Airport",
    "DGSI": "Kumasi / Prempeh I International Airport",
    "DGSN": "Sunyani Airport",
    "DGTK": "Takoradi Airport",
    "DGAC": "Accra FIR",
    # Togo (ASECNA eAIP)
    "DXXX": "Aéroport International Gnassingbé Eyadéma, Lomé",
    "DXNG": "Aéroport International de Niamtougou, Kara",
    "DXAK": "Aérodrome d'Atakpamé (Akpaka)",
    "DXSK": "Aérodrome de Sokodé",
    # Benin (ASECNA eAIP)
    "DBBB": "Aéroport International Cardinal Bernardin Gantin, Cotonou",
    "DBBP": "Aérodrome de Parakou",
    "DBBN": "Aérodrome de Natitingou (Boundétingou)",
    "DBBK": "Aérodrome de Kandi",
    "DBBO": "Aérodrome de Porga",
}

# Alias for clarity — the Accra FIR covers Ghana, Togo and Benin
ACCRA_FIR_LOCATION_INDICATORS = GHANA_LOCATION_INDICATORS

_LOCATION_INDICATOR = re.compile(
    r"(?:Location|AD|FIR|Aerodrome)\s*[:\-]?\s*([A-Z]{4})\b"
)
_DIRECT_GHANA_INDICATOR = re.compile(
    r"\b(" + "|".join(ACCRA_FIR_LOCATION_INDICATORS.keys()) + r")\b"
)
_DTG = re.compile(r"\b(\d{10})(EST|PERM)?\b")
_PAPER_FORM_DATE = re.compile(r"\b(\d{6})\b")
_PAPER_FORM_TIME = re.compile(r"\b(\d{2}):?(\d{2})\b")
_COORDINATES_RADIUS = re.compile(r"\b(\d{4}[NS]\d{5}[EW]\d{3})\b")
_SERIES_REFERENCE = re.compile(r"\b([A-RU-Z]\d{4}/\d{2})\b")
_LIMIT_EXPRESSION = re.compile(
    r"\b(SFC|UNL|FL\s?\d{2,3}|\d{3,5}\s?FT\s?(?:AGL|AMSL))\b", re.IGNORECASE
)
_RUNWAY_DESIGNATOR = re.compile(
    r"\b(?:RWY|RUNWAY)\s*(\d{2}[LCR]?/\d{2}[LCR]?|\d{2}[LCR]?)\b", re.IGNORECASE
)
_ORIGINATOR_LABELS = {
    "originator_name": re.compile(r"Name\s*[:\-]\s*([^\n\r]{2,120})"),
    "originator_organization": re.compile(
        r"Organi[sz]ation\s*[:\-]\s*([^\n\r]{2,120})"
    ),
    "originator_email": re.compile(r"Email\s*[:\-]\s*([^\s@]+@[^\s]+\.[^\s]+)"),
    "originator_reference": re.compile(
        r"Reference(?:\s*Number)?\s*[:\-]\s*([^\n\r]{2,80})"
    ),
}


def parse_location_indicators(text: str) -> list[ExtractedFieldCandidate]:
    candidates: list[ExtractedFieldCandidate] = []
    seen: set[str] = set()

    for match in _LOCATION_INDICATOR.finditer(text):
        code = match.group(1).upper()
        if code not in seen:
            seen.add(code)
            confidence = 85 if code in GHANA_LOCATION_INDICATORS else 75
            candidates.append(
                ExtractedFieldCandidate(
                    field_name="location_indicator",
                    raw_text=match.group(0),
                    normalized_value=code,
                    confidence=confidence,
                    extractor="grammar",
                )
            )

    return candidates


def parse_dtg(text: str) -> list[ExtractedFieldCandidate]:
    """10-digit YYMMDDHHMM, optionally suffixed EST/PERM (no space, per Doc
    8126 III-6 and Doc 10066 Appendix 2) -- an unambiguous, high-confidence structural match."""
    candidates: list[ExtractedFieldCandidate] = []
    for match in _DTG.finditer(text):
        digits, qualifier = match.group(1), match.group(2)
        candidates.append(
            ExtractedFieldCandidate(
                field_name="dtg",
                raw_text=match.group(0),
                normalized_value=f"{digits}{qualifier or ''}",
                confidence=85,
                extractor="regex",
            )
        )
    return candidates


def parse_paper_form_datetime(text: str) -> list[ExtractedFieldCandidate]:
    """The paper NOTAM Request Form (GCAA-AIS-NTM-FR01) splits a date-time
    into separate 'Date (YYMMDD)' and 'Time (HH:MM)' boxes. This looks for a
    6-digit date immediately followed by a 2:2-digit time within a short
    window and combines them into a DTG."""
    candidates: list[ExtractedFieldCandidate] = []
    for date_match in _PAPER_FORM_DATE.finditer(text):
        window = text[date_match.end() : date_match.end() + 20]
        time_match = _PAPER_FORM_TIME.search(window)
        if not time_match:
            continue
        combined = f"{date_match.group(1)}{time_match.group(1)}{time_match.group(2)}"
        candidates.append(
            ExtractedFieldCandidate(
                field_name="dtg",
                raw_text=date_match.group(0) + " " + time_match.group(0),
                normalized_value=combined,
                confidence=55,
                extractor="grammar",
            )
        )
    return candidates


def parse_coordinates_radius(text: str) -> list[ExtractedFieldCandidate]:
    return [
        ExtractedFieldCandidate(
            field_name="coordinates_radius",
            raw_text=match.group(0),
            normalized_value=match.group(1),
            confidence=90,
            extractor="regex",
        )
        for match in _COORDINATES_RADIUS.finditer(text)
    ]


def parse_series_reference(text: str) -> list[ExtractedFieldCandidate]:
    """A NOTAM identifier (e.g. A0161/26), used for NOTAMR/NOTAMC's
    'Reference NOTAM ID' field. Excludes S/T series letters per Doc 8126 & OPADD."""
    return [
        ExtractedFieldCandidate(
            field_name="replaces_notam_identifier",
            raw_text=match.group(0),
            normalized_value=match.group(1),
            confidence=80,
            extractor="regex",
        )
        for match in _SERIES_REFERENCE.finditer(text)
    ]


def parse_limit_expression(text: str, field_name: str = "limit") -> list[ExtractedFieldCandidate]:
    return [
        ExtractedFieldCandidate(
            field_name=field_name,
            raw_text=match.group(0),
            normalized_value=match.group(1).upper().replace(" ", ""),
            confidence=65,
            extractor="grammar",
        )
        for match in _LIMIT_EXPRESSION.finditer(text)
    ]


def parse_runways(text: str) -> list[ExtractedFieldCandidate]:
    """Extracts runway identifiers (e.g., RWY 03/21, RWY 05/23 per Ghana AIP AD 2)."""
    return [
        ExtractedFieldCandidate(
            field_name="runway",
            raw_text=match.group(0),
            normalized_value=match.group(1).upper(),
            confidence=80,
            extractor="regex",
        )
        for match in _RUNWAY_DESIGNATOR.finditer(text)
    ]


def parse_originator_block(text: str) -> list[ExtractedFieldCandidate]:
    candidates: list[ExtractedFieldCandidate] = []
    for field_name, pattern in _ORIGINATOR_LABELS.items():
        match = pattern.search(text)
        if match:
            candidates.append(
                ExtractedFieldCandidate(
                    field_name=field_name,
                    raw_text=match.group(0),
                    normalized_value=match.group(1).strip(),
                    confidence=65,
                    extractor="grammar",
                )
            )
    return candidates
