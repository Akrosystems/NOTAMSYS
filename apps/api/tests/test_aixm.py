from datetime import UTC, datetime

import pytest
from lxml import etree

from app.models import NotamKind, NotamSeries
from app.schemas import NotamDraftCreate
from app.services.aixm.builder import AIXM_NS, GML_NS, NOTAMSYS_NS, build_event_xml
from app.services.aixm.geometry import geodesic_circle, parse_coordinates_radius


def test_parse_coordinates_radius_matches_manual_conversion() -> None:
    parsed = parse_coordinates_radius("0536N00010W005")
    assert parsed.latitude == pytest.approx(5 + 36 / 60, abs=1e-6)
    assert parsed.longitude == pytest.approx(-(0 + 10 / 60), abs=1e-6)
    assert parsed.radius_nm == 5


def test_parse_coordinates_radius_rejects_malformed_input() -> None:
    with pytest.raises(ValueError):
        parse_coordinates_radius("not-a-coordinate")


def test_geodesic_circle_is_closed_and_centred() -> None:
    circle = geodesic_circle(5.6, -0.1667, 5)
    coords = list(circle.exterior.coords)
    assert coords[0] == pytest.approx(coords[-1])  # closed ring
    assert len(coords) > 8
    centroid = circle.centroid
    assert centroid.x == pytest.approx(-0.1667, abs=0.01)
    assert centroid.y == pytest.approx(5.6, abs=0.01)


def _sample_draft(**overrides: object) -> NotamDraftCreate:
    fields: dict[str, object] = {
        "series": NotamSeries.A,
        "kind": NotamKind.NEW,
        "fir": "DGAC",
        "q_code": "QMXLC",
        "traffic": "IV",
        "purpose": "BO",
        "scope": "A",
        "lower_limit": "000",
        "upper_limit": "999",
        "coordinates_radius": "0536N00010W005",
        "item_a": "DGAA",
        "item_b": datetime(2026, 8, 17, 6, tzinfo=UTC),
        "item_c": datetime(2026, 8, 20, 18, tzinfo=UTC),
        "item_e": "Taxiway M closed due to work in progress.",
    }
    fields.update(overrides)
    return NotamDraftCreate(**fields)


def test_build_event_xml_uses_correct_namespaces_and_is_well_formed() -> None:
    xml_text = build_event_xml(_sample_draft(), "A0165/26")
    root = etree.fromstring(xml_text.encode("utf-8"))
    assert root.tag == f"{{{AIXM_NS}}}Event"
    assert root.get(f"{{{GML_NS}}}id") == "event-A0165-26"

    identifier_el = root.find(f".//{{{NOTAMSYS_NS}}}identifier")
    assert identifier_el is not None
    assert identifier_el.text == "A0165/26"

    pos_list = root.find(f".//{{{GML_NS}}}posList")
    assert pos_list is not None
    assert pos_list.text
    values = [float(token) for token in pos_list.text.split()]
    assert len(values) % 2 == 0
    assert len(values) >= 16  # at least ~8 ring points


def test_build_event_xml_perm_has_indeterminate_end_position() -> None:
    xml_text = build_event_xml(
        _sample_draft(item_c=None, item_c_qualifier="PERM"), "A0165/26"
    )
    root = etree.fromstring(xml_text.encode("utf-8"))
    end_position = root.find(f".//{{{GML_NS}}}endPosition")
    assert end_position is not None
    assert end_position.get("indeterminatePosition") == "unknown"
    interpretation = root.find(f".//{{{AIXM_NS}}}interpretation")
    assert interpretation is not None
    assert interpretation.text == "PERMDELTA"
