"""Field-anchored extraction for the physical NOTAM Request Form
(GCAA-AIS-NTM-FR01 Rev 1) -- see docs/reference/office-photos/. Anchoring to
this form's known label order is more reliable than free-form parsing for
the hardcopy/scanned intake path, which per the GCAA AIS Manual of
Operations Chapter 7 is the dominant intake mode (even AFTN/email requests
get transcribed onto this form by the receiving officer).

This is text-proximity based, not spatial/bbox anchoring -- we don't have a
rendered, labelled reference image to build true positional anchors from in
this environment. Confidence values reflect that limitation; see
services/extraction/pipeline.py for how these feed the accept-per-field flow.
"""

import re

from app.services.extraction.candidates import ExtractedFieldCandidate
from app.services.extraction.parsers import (
    parse_limit_expression,
    parse_location_indicators,
    parse_originator_block,
    parse_paper_form_datetime,
)

_ACTION_PATTERN = re.compile(r"\b(New|Replace|Cancel)\b", re.IGNORECASE)


def _slice_between(text: str, start_label: str, end_labels: list[str]) -> str | None:
    start = text.find(start_label)
    if start == -1:
        return None
    start += len(start_label)
    end = len(text)
    for label in end_labels:
        position = text.find(label, start)
        if position != -1:
            end = min(end, position)
    return text[start:end].strip(" :\n\r\t-")


def extract_form_fields(text: str) -> list[ExtractedFieldCandidate]:
    candidates: list[ExtractedFieldCandidate] = []
    candidates.extend(parse_location_indicators(text))

    action_match = _ACTION_PATTERN.search(text)
    if action_match:
        candidates.append(
            ExtractedFieldCandidate(
                field_name="action",
                raw_text=action_match.group(0),
                normalized_value=action_match.group(1).upper(),
                confidence=60,
                extractor="grammar",
            )
        )

    start_end_window = _slice_between(text, "Start time", ["Periods of Activity", "Full Text"])
    if start_end_window:
        datetimes = parse_paper_form_datetime(start_end_window)
        for index, field_name in enumerate(("item_b", "item_c")):
            if index < len(datetimes):
                candidates.append(
                    ExtractedFieldCandidate(
                        field_name=field_name,
                        raw_text=datetimes[index].raw_text,
                        normalized_value=datetimes[index].normalized_value,
                        confidence=datetimes[index].confidence,
                        extractor=datetimes[index].extractor,
                    )
                )

    full_text = _slice_between(text, "Full Text", ["Lower Limit", "Upper Limit", "Item G"])
    if full_text:
        candidates.append(
            ExtractedFieldCandidate(
                field_name="item_e",
                raw_text=full_text,
                normalized_value=full_text,
                confidence=50,
                extractor="grammar",
            )
        )

    lower_window = _slice_between(text, "Lower Limit", ["Upper Limit", "Item G"])
    if lower_window:
        for candidate in parse_limit_expression(lower_window, "item_f"):
            candidates.append(candidate)

    upper_window = _slice_between(text, "Upper Limit", ["Name", "Organisation"])
    if upper_window:
        for candidate in parse_limit_expression(upper_window, "item_g"):
            candidates.append(candidate)

    candidates.extend(parse_originator_block(text))
    return candidates
