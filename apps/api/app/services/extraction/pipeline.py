"""Pure, DB-free orchestration: ingest -> parse -> narrative-suggest into a
single ExtractionResult. See services/extraction/orchestrator.py for the
database-bound wrapper that persists this as ExtractionRun/ExtractedField
rows and is what the API and Celery worker actually call.
"""

import dataclasses
from dataclasses import dataclass

from app.services.extraction.candidates import ExtractedFieldCandidate
from app.services.extraction.form_template import extract_form_fields
from app.services.extraction.ingest import extract_pages
from app.services.extraction.narrative import suggest_q_codes
from app.services.extraction.ocr import OcrEngine
from app.services.extraction.parsers import (
    parse_coordinates_radius,
    parse_dtg,
    parse_series_reference,
)


@dataclass(frozen=True)
class ExtractionResult:
    fields: list[ExtractedFieldCandidate]
    page_count: int
    q_code_suggestions: list[dict[str, object]]
    # What the engine actually recognized, concatenated across pages. Lets a
    # caller show "here's what was read" when field-anchored parsing finds
    # nothing to attach a value to -- the difference between "OCR read this
    # page fine but my regex didn't match" and "OCR produced garbage" is
    # otherwise invisible, both to an officer and to debugging a real
    # extraction failure after the fact.
    raw_text: str = ""

    @property
    def overall_confidence(self) -> int:
        if not self.fields:
            return 0
        return round(sum(field.confidence for field in self.fields) / len(self.fields))

    def as_dict(self) -> dict[str, object]:
        return {
            "fields": [dataclasses.asdict(field) for field in self.fields],
            "page_count": self.page_count,
            "q_code_suggestions": self.q_code_suggestions,
            "raw_text": self.raw_text,
        }


def run_pipeline(content: bytes, media_type: str, engine: OcrEngine) -> ExtractionResult:
    pages = extract_pages(content, media_type, engine)
    fields: list[ExtractedFieldCandidate] = []
    narrative_parts: list[str] = []
    for page in pages:
        if not page.text:
            continue
        narrative_parts.append(page.text)
        page_candidates: list[ExtractedFieldCandidate] = [
            *extract_form_fields(page.text),
            *parse_dtg(page.text),
            *parse_coordinates_radius(page.text),
            *parse_series_reference(page.text),
        ]
        fields.extend(dataclasses.replace(candidate, page=page.number) for candidate in page_candidates)

    suggestions = suggest_q_codes(" ".join(narrative_parts)) if narrative_parts else []
    return ExtractionResult(
        fields=fields,
        page_count=len(pages),
        q_code_suggestions=suggestions,
        raw_text="\n\n".join(narrative_parts),
    )
