from app.models import NotamKind
from app.services.rules import find_rule, validate_selection


def test_finds_taxiway_closed_rule() -> None:
    rule = find_rule("taxiway", "closed")
    assert rule is not None
    assert rule.q_code == "QMXLC"
    assert rule.scope == "A"


def test_rejects_incorrect_qualifier_combination() -> None:
    # MX/LC's correct purpose is BO per Doc 8126 III-App G-26 (visually
    # verified 2026-08-15, rendered at 220dpi) -- "M" was an error in the
    # original hand-curated starter data, corrected during the M-category
    # transcription pass. This case now exercises that corrected value.
    result = validate_selection("MX", "LC", "IV", "M", "A")
    assert result["valid"] is False
    assert any("Purpose must be BO" in error for error in result["errors"])


def test_cancel_requires_original_qualifiers() -> None:
    result = validate_selection("MR", "LC", "IV", "NB", "A", NotamKind.CANCEL)
    assert result["valid"] is True
    assert result["warnings"]
