"""Builds a real, namespaced AIXM 5.1.1 Event XML document (event-only
profile -- see package docstring) from a NOTAM draft. Complements, not
replaces, services/formatter.py:build_aixm_event() -- that hand-built dict
stays as the lightweight UI summary; this produces the actual XML."""

from datetime import UTC

from lxml import etree

from app.schemas import NotamDraftCreate
from app.services.aixm.geometry import geodesic_circle, parse_coordinates_radius

AIXM_NS = "http://www.aixm.aero/schema/5.1.1"
GML_NS = "http://www.opengis.net/gml/3.2"
# Fields Doc 8126's Part IV doesn't yet specify a binding for (see package
# docstring) live in this NOTAMSYS-owned extension namespace, not core AIXM.
NOTAMSYS_NS = "https://notamsys.app/extension/1.0"

NSMAP = {"aixm": AIXM_NS, "gml": GML_NS, "notamsys": NOTAMSYS_NS}


def _qname(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def _text_child(parent: etree._Element, tag: str, value: str) -> etree._Element:
    child = etree.SubElement(parent, _qname(NOTAMSYS_NS, tag))
    child.text = value
    return child


def _append_circle_geometry(
    parent: etree._Element, coordinates_radius: str, safe_id: str
) -> None:
    parsed = parse_coordinates_radius(coordinates_radius)
    circle = geodesic_circle(parsed.latitude, parsed.longitude, parsed.radius_nm)
    polygon = etree.SubElement(parent, _qname(GML_NS, "Polygon"))
    polygon.set(_qname(GML_NS, "id"), f"geom-{safe_id}")
    polygon.set("srsName", "urn:ogc:def:crs:EPSG::4326")
    exterior = etree.SubElement(polygon, _qname(GML_NS, "exterior"))
    ring = etree.SubElement(exterior, _qname(GML_NS, "LinearRing"))
    pos_list = etree.SubElement(ring, _qname(GML_NS, "posList"))
    # EPSG:4326's registry-defined axis order is latitude, longitude -- a
    # well-known GML gotcha, easy to get backwards.
    pos_list.text = " ".join(f"{lat:.6f} {lon:.6f}" for lon, lat in circle.exterior.coords)


def build_event_xml(draft: NotamDraftCreate, identifier: str) -> str:
    safe_id = identifier.replace("/", "-")
    event = etree.Element(_qname(AIXM_NS, "Event"), nsmap=NSMAP)
    event.set(_qname(GML_NS, "id"), f"event-{safe_id}")

    time_slice_wrapper = etree.SubElement(event, _qname(AIXM_NS, "timeSlice"))
    time_slice = etree.SubElement(time_slice_wrapper, _qname(AIXM_NS, "EventTimeSlice"))
    time_slice.set(_qname(GML_NS, "id"), f"ts-{safe_id}")

    valid_time = etree.SubElement(time_slice, _qname(GML_NS, "validTime"))
    period = etree.SubElement(valid_time, _qname(GML_NS, "TimePeriod"))
    period.set(_qname(GML_NS, "id"), f"vt-{safe_id}")
    begin = etree.SubElement(period, _qname(GML_NS, "beginPosition"))
    begin.text = draft.item_b.astimezone(UTC).isoformat()
    end = etree.SubElement(period, _qname(GML_NS, "endPosition"))
    if draft.item_c_qualifier != "PERM" and draft.item_c:
        end.text = draft.item_c.astimezone(UTC).isoformat()
    else:
        end.set("indeterminatePosition", "unknown")

    interpretation = etree.SubElement(time_slice, _qname(AIXM_NS, "interpretation"))
    interpretation.text = "PERMDELTA" if draft.item_c_qualifier == "PERM" else "TEMPDELTA"

    extension = etree.SubElement(time_slice, _qname(AIXM_NS, "extension"))
    details = etree.SubElement(extension, _qname(NOTAMSYS_NS, "NotamDetails"))
    _text_child(details, "identifier", identifier)
    _text_child(details, "qCode", draft.q_code)
    _text_child(details, "traffic", draft.traffic)
    _text_child(details, "purpose", draft.purpose)
    _text_child(details, "scope", draft.scope)
    _text_child(details, "fir", draft.fir)
    _text_child(details, "locationIndicator", draft.item_a)
    _text_child(details, "lowerLimit", draft.lower_limit)
    _text_child(details, "upperLimit", draft.upper_limit)
    _text_child(details, "text", draft.item_e)

    geometry_el = etree.SubElement(details, _qname(NOTAMSYS_NS, "geometry"))
    _append_circle_geometry(geometry_el, draft.coordinates_radius, safe_id)

    xml_bytes: bytes = etree.tostring(
        event, pretty_print=True, xml_declaration=True, encoding="UTF-8"
    )
    return xml_bytes.decode("utf-8")
