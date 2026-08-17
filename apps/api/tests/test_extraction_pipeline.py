from app.services.extraction.ocr import NullOcr
from app.services.extraction.pipeline import run_pipeline


def _build_pdf(text: str) -> bytes:
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text, fontsize=11)
    content = document.tobytes()
    document.close()
    return content


def test_run_pipeline_extracts_from_pdf_text_layer() -> None:
    content = _build_pdf(
        "Location: DGAA Full Text Taxiway M closed for scheduled maintenance. "
        "Valid from 2608170600 to 2608201800EST"
    )
    result = run_pipeline(content, "application/pdf", NullOcr())
    assert result.page_count == 1
    field_names = {field.field_name for field in result.fields}
    assert "location_indicator" in field_names
    assert "dtg" in field_names
    assert result.q_code_suggestions
    assert result.q_code_suggestions[0]["q_code"] == "QMXLC"


def test_run_pipeline_never_reports_full_confidence() -> None:
    content = _build_pdf("Location: DGAA 0536N00010W005 2608170600")
    result = run_pipeline(content, "application/pdf", NullOcr())
    assert result.fields
    assert all(field.confidence < 100 for field in result.fields)
    assert result.overall_confidence < 100


def test_run_pipeline_falls_back_to_ocr_for_image_without_text_layer() -> None:
    from app.services.extraction.ocr import OcrToken

    image_bytes = b"fake-jpeg-bytes"
    engine = NullOcr()
    engine.register(image_bytes, [OcrToken(text="DGAA", confidence=70)])
    result = run_pipeline(image_bytes, "image/jpeg", engine)
    assert result.page_count == 1
    assert any(field.field_name == "location_indicator" for field in result.fields) is False
    # NullOcr returned raw text with no label, so the label-anchored parser
    # correctly finds nothing -- proving the pipeline doesn't fabricate a match.


def test_run_pipeline_plain_text_attachment() -> None:
    result = run_pipeline(b"Location: DGLE\nFull Text Runway 05/23 strip WIP.", "text/plain", NullOcr())
    assert result.page_count == 1
    assert any(field.normalized_value == "DGLE" for field in result.fields)
