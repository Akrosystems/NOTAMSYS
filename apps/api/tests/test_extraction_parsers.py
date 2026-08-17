from app.services.extraction import form_template, narrative, parsers


def test_parse_location_indicator_requires_a_label() -> None:
    candidates = parsers.parse_location_indicators("Location: DGAA\nOther text FROM here")
    assert [c.normalized_value for c in candidates] == ["DGAA"]


def test_parse_dtg_captures_qualifier_suffix() -> None:
    candidates = parsers.parse_dtg("Valid from 2608170600 to 2608201800EST")
    values = [c.normalized_value for c in candidates]
    assert "2608170600" in values
    assert "2608201800EST" in values


def test_parse_paper_form_datetime_combines_date_and_time() -> None:
    candidates = parsers.parse_paper_form_datetime("Date (YYMMDD) 260817 Time (HH:MM) 06:00")
    assert candidates
    assert candidates[0].normalized_value == "2608170600"


def test_parse_coordinates_radius_matches_exact_grammar() -> None:
    candidates = parsers.parse_coordinates_radius("Centre point 0536N00010W005 approximate")
    assert [c.normalized_value for c in candidates] == ["0536N00010W005"]


def test_parse_series_reference_excludes_s_and_t() -> None:
    candidates = parsers.parse_series_reference("Replaces A0161/26 and cancels B0004/26")
    assert {c.normalized_value for c in candidates} == {"A0161/26", "B0004/26"}


def test_parse_limit_expression_variants() -> None:
    candidates = parsers.parse_limit_expression("Ceiling FL065 or 2000 FT AGL, floor SFC")
    values = {c.normalized_value for c in candidates}
    assert "FL065" in values
    assert "2000FTAGL" in values
    assert "SFC" in values


def test_parse_originator_block() -> None:
    text = "Name: John Mensah\nOrganisation: Ghana Airports Company\nEmail: j.mensah@example.com"
    candidates = parsers.parse_originator_block(text)
    values = {c.field_name: c.normalized_value for c in candidates}
    assert values["originator_name"] == "John Mensah"
    assert values["originator_organization"] == "Ghana Airports Company"
    assert values["originator_email"] == "j.mensah@example.com"


def test_form_template_extracts_action_and_full_text() -> None:
    text = (
        "Location: DGAA\n"
        "Action: New\n"
        "Start time Date (YYMMDD) 260817 Time (HH:MM) 06:00 "
        "End time Date (YYMMDD) 260820 Time (HH:MM) 18:00\n"
        "Periods of Activity: H24\n"
        "Full Text Taxiway M closed due to work in progress.\n"
        "Lower Limit SFC\n"
        "Upper Limit UNL\n"
        "Name: John Mensah"
    )
    candidates = form_template.extract_form_fields(text)
    by_field = {c.field_name: c.normalized_value for c in candidates}
    assert by_field["action"] == "NEW"
    assert by_field["item_b"] == "2608170600"
    assert by_field["item_e"].startswith("Taxiway M closed")
    assert by_field["item_f"] == "SFC"
    assert by_field["item_g"] == "UNL"
    assert by_field["originator_name"] == "John Mensah"


def test_narrative_suggests_ranked_q_codes_not_a_single_answer() -> None:
    suggestions = narrative.suggest_q_codes("Taxiway M closed for scheduled maintenance.")
    assert len(suggestions) >= 1
    assert suggestions[0]["q_code"] == "QMXLC"
    assert all(0 <= s["confidence"] <= 90 for s in suggestions)


def test_narrative_returns_empty_for_unmatched_text() -> None:
    assert narrative.suggest_q_codes("completely unrelated administrative memo") == []
