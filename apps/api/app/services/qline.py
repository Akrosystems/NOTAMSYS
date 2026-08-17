"""Doc 8126 Part III Chapter 6 Q-line and NOTAM item construction rules.

Pure, deterministic validation helpers -- no database or workflow coupling.
Not yet wired into services/formatter.py or services/workflow.py; that
integration (including the NOTAMR/NOTAMC identifier-interpolation fix) is a
follow-up phase so it can be reviewed as its own, deliberate change against
the existing formatter test contract.
"""

import math
import re

VALID_PURPOSE_COMBINATIONS = frozenset({"K", "BO", "NBO", "M"})
MAX_ITEM_A_FIRS = 7
MAX_ITEM_D_LENGTH = 200
QFALT_FALLBACK_CODE = "QFALT"

_WIE_WEF_PATTERN = re.compile(r"\bW(?:IE|EF)\b", re.IGNORECASE)

# Doc 8126 Table III-6-1 standardized radius, by subject code. Populate as
# subjects are added to the selection-criteria dataset (services/rules.py);
# a subject with no entry here requires the operator to supply an explicit
# radius rather than falling back to a guessed default.
DEFAULT_RADIUS_NM: dict[str, str] = {
    "MR": "005",
    "MX": "005",
    "MW": "005",
    "FA": "005",
    "FF": "005",
    "RT": "025",
    "AF": "999",
}


def validate_purpose(purpose: str) -> list[str]:
    """Purpose qualifier is a closed set (Doc 8126 III-6.2.2): only K, BO,
    NBO and M are valid -- not an arbitrary subset of N/B/O/M letters."""
    if purpose not in VALID_PURPOSE_COMBINATIONS:
        allowed = ", ".join(sorted(VALID_PURPOSE_COMBINATIONS))
        return [f"Purpose '{purpose}' is not valid; only {allowed} are permitted"]
    return []


def round_lower_limit_ft(value_ft: float) -> int:
    """Lower limit rounds DOWN to the nearest 100 ft (Doc 8126 III-6)."""
    return int(math.floor(value_ft / 100.0) * 100)


def round_upper_limit_ft(value_ft: float) -> int:
    """Upper limit rounds UP to the nearest 100 ft (Doc 8126 III-6)."""
    return int(math.ceil(value_ft / 100.0) * 100)


def validate_scope_requirements(
    scope: str, item_a_count: int, has_activity_coordinates: bool
) -> list[str]:
    """Scope-dependent compulsory-field checks (Doc 8126 III-6.3.3).

    `has_activity_coordinates` should be True only when Item Q coordinates
    represent the actual activity location rather than the aerodrome
    reference point -- Scope AW requires the former.
    """
    errors: list[str] = []
    if scope == "A" and item_a_count != 1:
        errors.append("Scope A requires exactly one aerodrome indicator in Item A")
    if scope == "AW" and not has_activity_coordinates:
        errors.append(
            "Scope AW requires Item Q coordinates for the actual activity location, "
            "not the aerodrome reference point"
        )
    if scope in {"E", "W"} and item_a_count < 1:
        errors.append("Scope E/W requires at least one FIR indicator in Item A")
    return errors


def validate_item_a(indicators: list[str]) -> list[str]:
    """Item A may list at most 7 FIR indicators (AFTN line-length limit)."""
    if len(indicators) > MAX_ITEM_A_FIRS:
        return [
            f"Item A may not list more than {MAX_ITEM_A_FIRS} FIR indicators "
            "in a single NOTAM (AFTN line-length limit)"
        ]
    return []


def validate_item_d(item_d: str | None) -> list[str]:
    """Item D (schedule) must not exceed 200 characters; split into a
    follow-on NOTAM instead of truncating."""
    if item_d and len(item_d) > MAX_ITEM_D_LENGTH:
        return [f"Item D must not exceed {MAX_ITEM_D_LENGTH} characters; split into a follow-on NOTAM"]
    return []


def validate_item_b_text(item_b_source_text: str | None) -> list[str]:
    """WIE/WEF abbreviations must not be used in Item B (Doc 8126 III-6)."""
    if item_b_source_text and _WIE_WEF_PATTERN.search(item_b_source_text):
        return ["Item B must not use the WIE/WEF abbreviations"]
    return []


def multi_fir_indicator(nationality_prefix: str) -> str:
    """Doc 8126 III-6.4/5: an event spanning more than one FIR uses the
    issuing State's two-letter nationality prefix followed by XX, never a
    UIR indicator. All affected FIRs are then listed in Item A."""
    return f"{nationality_prefix.upper()[:2]}XX"


def default_radius_for(subject_code: str) -> str | None:
    return DEFAULT_RADIUS_NM.get(subject_code.upper())
