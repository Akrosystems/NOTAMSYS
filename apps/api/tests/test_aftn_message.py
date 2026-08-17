import pytest

from app.services.publication.aftn import build_envelope, validate_ita2


def test_validate_ita2_accepts_clean_notam_text() -> None:
    text = "(A0165/26 NOTAMN\nQ)DGAC/QMXLC/IV/BO/A/000/999/0536N00010W005\nA)DGAA B)2608170600 C)2608201800\nE)TAXIWAY M CLOSED DUE WIP.)"
    assert validate_ita2(text) == []


def test_validate_ita2_rejects_lowercase_and_smart_punctuation() -> None:
    errors = validate_ita2("taxiway closed — confirm w/ tower")
    assert errors
    assert "outside the AFTN ITA-2 set" in errors[0]


def test_validate_ita2_rejects_overlong_lines() -> None:
    errors = validate_ita2("A" * 80)
    assert any("69-character" in error for error in errors)


def test_build_envelope_includes_addressees_and_body() -> None:
    envelope = build_envelope("E)TAXIWAY M CLOSED DUE WIP.")
    assert "DGAANOTA" in envelope
    assert "DGAANOTB" in envelope
    assert "DGAANOTC" in envelope
    assert "GG" in envelope.splitlines()[0]
    assert "TAXIWAY M CLOSED" in envelope


def test_build_envelope_raises_on_untransmittable_text() -> None:
    with pytest.raises(ValueError):
        build_envelope("taxiway closed — confirm with tower")
