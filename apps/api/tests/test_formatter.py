from datetime import UTC, datetime

from app.models import NotamKind, NotamSeries
from app.schemas import NotamDraftCreate
from app.services.formatter import format_notam


def test_formats_icao_message() -> None:
    draft = NotamDraftCreate(
        series=NotamSeries.A,
        kind=NotamKind.NEW,
        fir="DGAC",
        q_code="QMXLC",
        traffic="IV",
        purpose="M",
        scope="A",
        lower_limit="000",
        upper_limit="999",
        coordinates_radius="0536N00010W005",
        item_a="DGAA",
        item_b=datetime(2026, 8, 17, 6, tzinfo=UTC),
        item_c=datetime(2026, 8, 20, 18, tzinfo=UTC),
        item_e="Taxiway M closed due to work in progress.",
    )
    message = format_notam(draft, 165, 2026)
    assert message.startswith("(A0165/26 NOTAMN")
    assert "Q)DGAC/QMXLC/IV/M/A/000/999/0536N00010W005" in message
    assert message.endswith(")")


def test_notamr_interpolates_the_replaced_identifier_not_a_ref_literal() -> None:
    draft = NotamDraftCreate(
        series=NotamSeries.A,
        kind=NotamKind.REPLACE,
        fir="DGAC",
        q_code="QMXLC",
        traffic="IV",
        purpose="BO",
        scope="A",
        lower_limit="000",
        upper_limit="999",
        coordinates_radius="0536N00010W005",
        item_a="DGAA",
        item_b=datetime(2026, 8, 17, 6, tzinfo=UTC),
        item_e="Taxiway M closed due to work in progress.",
    )
    message = format_notam(draft, 166, 2026, replaced_identifier="A0165/26")
    # Per Doc 8126: the replaced NOTAM's identifier follows the kind
    # directly, e.g. "(A0166/26 NOTAMR A0165/26" -- never a literal "REF".
    assert message.startswith("(A0166/26 NOTAMR A0165/26")
    assert "REF" not in message


def test_notamr_without_a_replaced_identifier_omits_the_relationship() -> None:
    draft = NotamDraftCreate(
        series=NotamSeries.A,
        kind=NotamKind.REPLACE,
        fir="DGAC",
        q_code="QMXLC",
        traffic="IV",
        purpose="BO",
        scope="A",
        lower_limit="000",
        upper_limit="999",
        coordinates_radius="0536N00010W005",
        item_a="DGAA",
        item_b=datetime(2026, 8, 17, 6, tzinfo=UTC),
        item_e="Taxiway M closed due to work in progress.",
    )
    message = format_notam(draft, 166, 2026)
    assert message.startswith("(A0166/26 NOTAMR\n")
