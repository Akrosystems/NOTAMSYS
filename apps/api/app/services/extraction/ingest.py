"""Turn an attachment's raw bytes into per-page text, using a PDF's text
layer directly where one exists and falling back to OCR (rasterize + the
configured OcrEngine) only for scanned pages/photographs that have none.
"""

from dataclasses import dataclass

from app.services.extraction.ocr import OcrEngine


@dataclass(frozen=True)
class Page:
    number: int
    text: str
    source: str  # "text_layer" | "ocr" | "plain_text"


def extract_pages(content: bytes, media_type: str, engine: OcrEngine) -> list[Page]:
    if media_type == "application/pdf":
        return _extract_pdf_pages(content, engine)
    if media_type.startswith("image/"):
        tokens = engine.recognize_page(content)
        return [Page(number=1, text=" ".join(token.text for token in tokens), source="ocr")]
    if media_type.startswith("text/"):
        return [Page(number=1, text=content.decode("utf-8", errors="replace"), source="plain_text")]
    raise ValueError(f"Unsupported attachment media type for extraction: {media_type}")


def _extract_pdf_pages(content: bytes, engine: OcrEngine) -> list[Page]:
    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover - exercised only without the ocr extra
        raise RuntimeError(
            "PDF extraction requires the 'ocr' optional dependency group "
            '(pip install -e ".[ocr]").'
        ) from exc

    pages: list[Page] = []
    with pymupdf.open(stream=content, filetype="pdf") as document:
        for index, page in enumerate(document, start=1):
            text = page.get_text().strip()
            if text:
                pages.append(Page(number=index, text=text, source="text_layer"))
                continue
            pixmap = page.get_pixmap(dpi=200)
            image_bytes = pixmap.tobytes("png")
            tokens = engine.recognize_page(image_bytes)
            pages.append(
                Page(number=index, text=" ".join(token.text for token in tokens), source="ocr")
            )
    return pages
