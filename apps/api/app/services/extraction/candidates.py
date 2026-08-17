from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedFieldCandidate:
    """A single proposed field value. Never written to a NOTAM draft
    directly -- see services/extraction/pipeline.py and the
    /extraction/fields/{id}/accept endpoint, which requires an explicit
    human actor before a value is trusted."""

    field_name: str
    raw_text: str
    normalized_value: str | None
    confidence: int  # 0-100. Capped below 100 everywhere in this package --
    # a deterministic parser matching cleanly is still not a human decision.
    extractor: str  # "regex" | "grammar" | "model"
    page: int = 1
