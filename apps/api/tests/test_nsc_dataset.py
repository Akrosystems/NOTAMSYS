"""Structural integrity checks for the NSC dataset (app/data/nsc/*.json).
Content correctness for VERIFIED_VISUAL rows is established by visually
reading the rendered source PDF page (see services/rules.py's dataset
docstring and the source_revision note in the dataset file itself); these
tests guard the dataset's shape, not a second copy of the source data."""

from app.services.rules import get_catalog

VALID_PURPOSE = {"K", "BO", "NBO", "M"}
VALID_TRAFFIC = {"I", "V", "IV", "K"}
VALID_SCOPE = {"A", "E", "W", "AE", "AW", "K"}
VALID_VERIFICATION_STATUS = {"HAND_CURATED", "VERIFIED_VISUAL", "TRANSCRIBED_UNVERIFIED"}

# Categories fully transcribed and visually verified on 2026-08-15 against
# rendered Doc 8126 Appendix G pages at 220dpi. Each entry guards against a
# future edit silently reintroducing an unverified or missing subject.
VERIFIED_CATEGORIES: dict[str, set[str]] = {
    "M": {
        "MA", "MB", "MC", "MD", "MG", "MH", "MK", "MM", "MN",
        "MO", "MP", "MR", "MS", "MT", "MU", "MW", "MX", "MY",
    },
    "L": {
        "LA", "LB", "LC", "LD", "LE", "LF", "LG", "LH", "LI", "LJ", "LK", "LL",
        "LM", "LP", "LR", "LS", "LT", "LU", "LV", "LW", "LX", "LY", "LZ",
    },
    "C": {"CA", "CB", "CC", "CD", "CE", "CG", "CL", "CM", "CP", "CR", "CS", "CT"},
    "F": {
        "FA", "FB", "FC", "FD", "FE", "FF", "FG", "FH", "FI", "FJ",
        "FL", "FM", "FO", "FP", "FS", "FT", "FU", "FW", "FZ",
    },
    "I": {"IC", "ID", "IG", "II", "IL", "IM", "IN", "IO", "IS", "IT", "IU", "IW", "IX", "IY"},
    "G": {"GA", "GW"},
    "N": {"NA", "NB", "ND", "NF", "NL", "NM", "NN", "NT", "NV", "NX"},
    "A": {
        "AA", "AC", "AD", "AE", "AF", "AH", "AL", "AN", "AO",
        "AP", "AR", "AT", "AU", "AV", "AX", "AZ",
    },
    "S": {
        "SA", "SB", "SC", "SE", "SF", "SL", "SO", "SP", "SS", "ST", "SU", "SV", "SY",
    },
    "P": {
        "PA", "PB", "PC", "PD", "PE", "PF", "PH", "PI", "PK", "PL",
        "PM", "PN", "PO", "PR", "PT", "PU", "PX", "PZ",
    },
    "R": {"RA", "RD", "RM", "RO", "RP", "RR", "RT"},
    "W": {
        "WA", "WB", "WC", "WD", "WE", "WF", "WG", "WH", "WJ", "WL",
        "WM", "WP", "WR", "WS", "WT", "WU", "WV", "WW", "WY",
    },
    "O": {"OA", "OB", "OE", "OL", "OR"},
    "K": {"KK"},
}


def test_every_rule_has_valid_qualifiers() -> None:
    for rule in get_catalog().rules:
        assert rule.purpose in VALID_PURPOSE, f"{rule.q_code}: bad purpose {rule.purpose!r}"
        assert rule.traffic in VALID_TRAFFIC, f"{rule.q_code}: bad traffic {rule.traffic!r}"
        assert rule.scope in VALID_SCOPE, f"{rule.q_code}: bad scope {rule.scope!r}"
        assert rule.verification_status in VALID_VERIFICATION_STATUS


def test_every_rule_has_a_source_citation() -> None:
    for rule in get_catalog().rules:
        assert rule.source, f"{rule.q_code} has no source citation"


def test_every_rule_has_well_formed_codes() -> None:
    for rule in get_catalog().rules:
        assert len(rule.subject_code) == 2 and rule.subject_code.isupper()
        assert len(rule.condition_code) == 2 and rule.condition_code.isupper()
        assert rule.q_code == f"Q{rule.subject_code}{rule.condition_code}"


def test_no_duplicate_q_codes() -> None:
    q_codes = [rule.q_code for rule in get_catalog().rules]
    assert len(q_codes) == len(set(q_codes)), "duplicate subject/condition combination in dataset"


def test_verified_categories_are_complete_and_fully_verified() -> None:
    all_subject_codes = {rule.subject_code for rule in get_catalog().rules}
    for prefix, expected_subjects in VERIFIED_CATEGORIES.items():
        actual_subjects = {code for code in all_subject_codes if code.startswith(prefix)}
        assert actual_subjects == expected_subjects, f"category {prefix} subject set drifted"
    for rule in get_catalog().rules:
        for expected_subjects in VERIFIED_CATEGORIES.values():
            if rule.subject_code in expected_subjects:
                assert rule.verification_status == "VERIFIED_VISUAL", rule.q_code
