"""Deterministic grammar/regex parsers for safety-critical NOTAM fields.

These own dates, coordinates, limits and location indicators precisely
because they are safety-critical: a statistical model never writes one of
these values directly (see services/extraction/narrative.py for the one
place a ranked, non-authoritative suggestion is offered instead).
"""

import re

from app.services.extraction.candidates import ExtractedFieldCandidate

_LOCATION_INDICATOR = re.compile(
    r"(?:Location|AD|FIR|Aerodrome)\s*[:\-]?\s*([A-Z]{4})\b"
)
_DTG = re.compile(r"\b(\d{10})(EST|PERM)?\b")
_PAPER_FORM_DATE = re.compile(r"\b(\d{6})\b")
_PAPER_FORM_TIME = re.compile(r"\b(\d{2}):?(\d{2})\b")
_COORDINATES_RADIUS = re.compile(r"\b(\d{4}[NS]\d{5}[EW]\d{3})\b")
_SERIES_REFERENCE = re.compile(r"\b([A-RU-Z]\d{4}/\d{2})\b")
_LIMIT_EXPRESSION = re.compile(
    r"\b(SFC|UNL|FL\s?\d{2,3}|\d{3,5}\s?FT\s?(?:AGL|AMSL))\b", re.IGNORECASE
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
    return [
        ExtractedFieldCandidate(
            field_name="location_indicator",
            raw_text=match.group(0),
            normalized_value=match.group(1),
            confidence=75,
            extractor="grammar",
        )
        for match in _LOCATION_INDICATOR.finditer(text)
    ]


def parse_dtg(text: str) -> list[ExtractedFieldCandidate]:
    """10-digit YYMMDDHHMM, optionally suffixed EST/PERM (no space, per Doc
    8126 III-6) -- an unambiguous, high-confidence structural match."""
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
    window and combines them into a DTG -- a text-proximity heuristic, not a
    guarantee, so confidence is deliberately lower than parse_dtg()."""
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
    'Reference NOTAM ID' field. Excludes S/T series letters per Doc 8126."""
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
