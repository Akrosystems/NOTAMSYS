import pytest

from app.services.aip.loader import load_dataset_payload
from app.services.extraction.fuzzy import (
    fuzzy_correct_token,
    normalize_aviation_text,
)
from app.services.extraction.narrative import suggest_q_codes
from app.services.extraction.parsers import (
    parse_location_indicators,
    parse_runways,
)
from app.services.extraction.semantic import get_semantic_matcher


def test_ghana_aip_2026_dataset_contains_all_authentic_aerodromes() -> None:
    payload = load_dataset_payload("ghana_aip_2026.json")
    assert payload["version"] == "dgac-fir-2026.2"
    assert len(payload["firs"]) == 1
    assert payload["firs"][0]["icao_code"] == "DGAC"
    assert set(payload["firs"][0]["countries"]) == {"Ghana", "Togo", "Benin"}

    # General (GEN)
    assert "general" in payload
    assert len(payload["general"]["designated_authorities"]) >= 3
    assert len(payload["general"]["international_notam_offices"]) == 3

    # En-Route (ENR)
    assert len(payload["airspaces"]) == 5  # ACCRA, LOME, COTONOU, KUMASI, TAMALE TMAs
    assert len(payload["control_zones"]) == 8  # DGAA, DGSI, DGSN, DGLE, DGTK, DXXX, DXNG, DBBB CTRs
    assert len(payload["ats_routes"]) >= 5
    assert len(payload["significant_points"]) >= 10
    assert len(payload["navigation_warnings"]["prohibited_areas"]) == 3
    assert len(payload["navigation_warnings"]["restricted_areas"]) == 6
    assert len(payload["navigation_warnings"]["danger_areas"]) == 4

    aerodromes = {ad["icao_code"]: ad for ad in payload["aerodromes"]}
    assert len(aerodromes) == 17

    # --- GHANA AERODROMES (GCAA AIP 7th Ed) ---
    assert "DGAA" in aerodromes
    dgaa = aerodromes["DGAA"]
    assert dgaa["country"] == "Ghana"
    assert dgaa["iata_code"] == "ACC"
    assert dgaa["elevation_ft"] == 205
    assert dgaa["arp_latitude"] == pytest.approx(5.6044, rel=1e-3)
    assert "03/21" in dgaa["runways"]
    assert "ACC" in dgaa["navaids"]

    assert "DGLE" in aerodromes
    dgle = aerodromes["DGLE"]
    assert dgle["country"] == "Ghana"
    assert dgle["iata_code"] == "TML"
    assert dgle["elevation_ft"] == 549
    assert "05/23" in dgle["runways"]

    assert "DGSI" in aerodromes
    dgsi = aerodromes["DGSI"]
    assert dgsi["country"] == "Ghana"
    assert dgsi["iata_code"] == "KMS"
    assert "02/20" in dgsi["runways"]

    assert "DGSN" in aerodromes
    assert "DGTK" in aerodromes
    assert "DGAH" in aerodromes
    assert "DGLN" in aerodromes
    assert "DGLW" in aerodromes

    # --- TOGO AERODROMES (ASECNA eAIP eff. 06 AUG 2026) ---
    assert "DXXX" in aerodromes
    dxxx = aerodromes["DXXX"]
    assert dxxx["country"] == "Togo"
    assert dxxx["iata_code"] == "LFW"
    assert dxxx["elevation_ft"] == 72
    assert dxxx["arp_latitude"] == pytest.approx(6.1658, rel=1e-3)
    assert "04/22" in dxxx["runways"]
    assert "LM" in dxxx["navaids"]

    assert "DXNG" in aerodromes
    dxng = aerodromes["DXNG"]
    assert dxng["country"] == "Togo"
    assert dxng["iata_code"] == "LRL"
    assert dxng["elevation_ft"] == 1515
    assert "03/21" in dxng["runways"]

    assert "DXAK" in aerodromes
    assert "DXSK" in aerodromes

    # --- BENIN AERODROMES (ASECNA eAIP eff. 09 JUL 2026 / 14 MAY 2026) ---
    assert "DBBB" in aerodromes
    dbbb = aerodromes["DBBB"]
    assert dbbb["country"] == "Benin"
    assert dbbb["iata_code"] == "COO"
    assert dbbb["elevation_ft"] == 19
    assert dbbb["arp_latitude"] == pytest.approx(6.3564, rel=1e-3)
    assert "06/24" in dbbb["runways"]
    assert "CBB" in dbbb["navaids"]

    assert "DBBP" in aerodromes
    dbbp = aerodromes["DBBP"]
    assert dbbp["country"] == "Benin"
    assert dbbp["iata_code"] == "PKO"
    assert dbbp["elevation_ft"] == 1266
    assert "04/22" in dbbp["runways"]

    assert "DBBN" in aerodromes
    assert "DBBK" in aerodromes
    assert "DBBO" in aerodromes


def test_fuzzy_ocr_typo_correction() -> None:
    # Exact abbreviation
    assert fuzzy_correct_token("rwy") == "runway"
    assert fuzzy_correct_token("clsd") == "closed"
    assert fuzzy_correct_token("wip") == "work in progress"

    # OCR character substitutions
    assert fuzzy_correct_token("rwv") == "runway"
    assert fuzzy_correct_token("cls0") == "closed"
    assert fuzzy_correct_token("w1p") == "work in progress"
    assert fuzzy_correct_token("unserv1ceable") == "unserviceable"


def test_normalize_aviation_text_with_opadd_abbreviations() -> None:
    raw_text = "RWV 03/21 CLS0 DUE TO W1P IN VICINITY OF THR"
    normalized = normalize_aviation_text(raw_text)
    assert "runway" in normalized
    assert "closed" in normalized
    assert "work in progress" in normalized
    assert "threshold" in normalized


def test_runway_parsing() -> None:
    text = "Work in progress adjacent to RWY 03/21 and Runway 05."
    candidates = parse_runways(text)
    assert len(candidates) >= 2
    values = [c.normalized_value for c in candidates]
    assert "03/21" in values
    assert "05" in values


def test_location_indicators_with_ghana_aip_provenance() -> None:
    text = "Location: DGAA Location: DGLE Location: DXXX Location: DBBB Location: EGLL"
    candidates = parse_location_indicators(text)
    by_code = {c.normalized_value: c for c in candidates}

    assert "DGAA" in by_code
    assert by_code["DGAA"].confidence == 85  # Ghana AIP indicator bonus
    assert "DGLE" in by_code
    assert by_code["DGLE"].confidence == 85
    assert "DXXX" in by_code
    assert by_code["DXXX"].confidence == 85  # Togo (Accra FIR) ASECNA bonus
    assert "DBBB" in by_code
    assert by_code["DBBB"].confidence == 85  # Benin (Accra FIR) ASECNA bonus
    assert "EGLL" in by_code
    assert by_code["EGLL"].confidence == 75  # Standard 4-letter ICAO confidence


def test_semantic_rule_matching_free_text() -> None:
    matcher = get_semantic_matcher()
    results = matcher.search("Excavation and construction equipment operating near the runway strip", top_k=3)
    assert len(results) > 0
    top_rule, score = results[0]
    assert score > 0.4
    # Should match Work in progress or Movement area
    assert any(w in (top_rule.subject + " " + top_rule.condition).lower() for w in ["work in progress", "strip", "runway", "movement"])


def test_hybrid_narrative_scoring_q_code_suggestions() -> None:
    # 1. Standard abbreviated text
    suggestions_abbr = suggest_q_codes("RWY 03/21 CLSD DUE WIP")
    assert len(suggestions_abbr) >= 1
    assert any(s["q_code"].startswith("QM") for s in suggestions_abbr)

    # 2. Noisy OCR text recovered by fuzzy matching
    suggestions_noisy = suggest_q_codes("RWV 03/21 CLS0 DUE W1P")
    assert len(suggestions_noisy) >= 1
    assert any(s["q_code"].startswith("QM") for s in suggestions_noisy)

    # 3. Descriptive paraphrase
    suggestions_para = suggest_q_codes("Navigational beacon unserviceable for inspection")
    assert len(suggestions_para) >= 1
    assert any(s["q_code"].startswith("QN") or s["q_code"].startswith("QI") or s["q_code"].startswith("QG") for s in suggestions_para)

    # 4. Operational request form text: frequency now serviceable (GCAA-AIS-NTM-FR01 / A0167/26)
    suggs_form = suggest_q_codes("ACCRA 130.7 MHZ Frequency now serviceable and available for traffic", limit=3)
    assert len(suggs_form) >= 1
    assert suggs_form[0]["q_code"] == "QCAAK"
    assert suggs_form[0]["confidence"] >= 85

    # 5. Operational transmitted Item E text: VHF FREQ resumed normal operation
    suggs_tx = suggest_q_codes("VHF FREQ 130.9MHZ RESUMED NORMAL OPERATION.", limit=3)
    assert len(suggs_tx) >= 1
    assert suggs_tx[0]["q_code"] == "QCAAK"
    assert suggs_tx[0]["confidence"] >= 85

    # 6. Real-world GCAA hardcopy request: East side of runway strip equipment and personnel
    suggs_strip = suggest_q_codes(
        "ON EAST SIDE OF RWY 05/23 STRIP. PRESENCE OF EQUIPMENT AND PERSONNEL. CTN ADVISED.",
        location_indicator="DGLE",
        limit=3,
    )
    assert len(suggs_strip) >= 1
    assert suggs_strip[0]["q_code"] == "QMWHW"
    assert suggs_strip[0]["subject"] == "strip or shoulder"
    assert suggs_strip[0]["condition"] == "work in progress"
    assert suggs_strip[0]["confidence"] >= 80
    assert suggs_strip[0]["coordinates_radius"] == "0933N00052W005"

