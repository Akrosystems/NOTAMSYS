from app.services import qline


def test_purpose_closed_set_rejects_arbitrary_combination() -> None:
    assert qline.validate_purpose("NB")


def test_purpose_closed_set_accepts_all_valid_values() -> None:
    for purpose in ("K", "BO", "NBO", "M"):
        assert qline.validate_purpose(purpose) == []


def test_lower_limit_rounds_down() -> None:
    assert qline.round_lower_limit_ft(1150) == 1100


def test_upper_limit_rounds_up() -> None:
    assert qline.round_upper_limit_ft(1150) == 1200


def test_limits_exact_hundred_unchanged() -> None:
    assert qline.round_lower_limit_ft(1200) == 1200
    assert qline.round_upper_limit_ft(1200) == 1200


def test_scope_aw_requires_activity_coordinates() -> None:
    assert qline.validate_scope_requirements("AW", item_a_count=1, has_activity_coordinates=False)
    assert (
        qline.validate_scope_requirements("AW", item_a_count=1, has_activity_coordinates=True)
        == []
    )


def test_scope_a_requires_exactly_one_aerodrome() -> None:
    assert qline.validate_scope_requirements("A", item_a_count=2, has_activity_coordinates=True)
    assert qline.validate_scope_requirements("A", item_a_count=1, has_activity_coordinates=True) == []


def test_scope_ew_requires_at_least_one_fir() -> None:
    assert qline.validate_scope_requirements("W", item_a_count=0, has_activity_coordinates=True)


def test_item_a_fir_cap() -> None:
    assert qline.validate_item_a(["DGAC"] * 8)
    assert qline.validate_item_a(["DGAC"] * 7) == []


def test_item_d_length_cap() -> None:
    assert qline.validate_item_d("x" * 201)
    assert qline.validate_item_d("x" * 200) == []
    assert qline.validate_item_d(None) == []


def test_item_b_rejects_wie_wef() -> None:
    assert qline.validate_item_b_text("WEF 260815")
    assert qline.validate_item_b_text("WIE immediately")
    assert qline.validate_item_b_text("FROM 260815") == []


def test_multi_fir_indicator() -> None:
    assert qline.multi_fir_indicator("dg") == "DGXX"


def test_default_radius_lookup() -> None:
    assert qline.default_radius_for("MX") == "005"
    assert qline.default_radius_for("zz") is None
