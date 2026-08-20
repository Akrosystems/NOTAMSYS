"""OCR engine boundary. Pluggable so the process-wide default (local
Tesseract, per the locked "nothing leaves GCAA infrastructure" decision)
can be swapped without touching the pipeline that calls it.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OcrToken:
    text: str
    confidence: int  # 0-100, engine-reported
    bbox: tuple[int, int, int, int] | None = None  # (left, top, width, height) in pixels
    # (block, paragraph, line) from the engine's own layout segmentation --
    # not re-derived from bbox geometry, since Tesseract already computes
    # this more reliably than a top-coordinate heuristic would. Used to
    # rejoin tokens with real line breaks (see ingest.py) instead of
    # flattening a whole page into one space-joined string, which silently
    # broke every regex that relies on "until the next newline" to know
    # where one paper-form field ends and the next begins (confirmed live:
    # the originator-block fields on a real photographed form each bled
    # into the next one once line structure was lost).
    line_id: tuple[int, int, int] = (0, 0, 0)


class OcrEngine(Protocol):
    name: str

    def recognize_page(self, image_bytes: bytes) -> list[OcrToken]: ...


class NullOcr:
    """Deterministic, dependency-free engine for tests and for
    `ocr_engine=disabled`. Returns registered fixture tokens for a given
    image (keyed by content hash) and an empty list otherwise -- it never
    fabricates text, so a test using it can assert exactly what it wired up.
    """

    name = "null"

    def __init__(self, fixtures: dict[bytes, list[OcrToken]] | None = None) -> None:
        self._fixtures = fixtures or {}

    def register(self, image_bytes: bytes, tokens: list[OcrToken]) -> None:
        self._fixtures[image_bytes] = tokens

    def recognize_page(self, image_bytes: bytes) -> list[OcrToken]:
        return list(self._fixtures.get(image_bytes, []))


class TesseractOcr:
    """Local OCR via the `tesseract` binary through pytesseract. Requires
    both the `ocr` extra (pip install -e ".[ocr]") and the tesseract
    executable itself to be installed on the host -- the latter is not a
    Python dependency and must be provisioned by the office's IT team.
    """

    name = "tesseract"

    def __init__(self, version: str | None = None) -> None:
        self.version = version

    def recognize_page(self, image_bytes: bytes) -> list[OcrToken]:
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:  # pragma: no cover - exercised only without the ocr extra
            raise RuntimeError(
                "Tesseract OCR requires the 'ocr' optional dependency group "
                '(pip install -e ".[ocr]") and a local tesseract installation.'
            ) from exc
        import io

        image = Image.open(io.BytesIO(image_bytes))
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        tokens: list[OcrToken] = []
        for i, text in enumerate(data["text"]):
            if not text.strip():
                continue
            confidence = int(data["conf"][i]) if str(data["conf"][i]).lstrip("-").isdigit() else 0
            bbox = (data["left"][i], data["top"][i], data["width"][i], data["height"][i])
            line_id = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            tokens.append(OcrToken(text=text, confidence=max(confidence, 0), bbox=bbox, line_id=line_id))
        return tokens


def build_engine(engine_name: str) -> OcrEngine:
    if engine_name == "tesseract":
        return TesseractOcr()
    if engine_name in {"disabled", "null"}:
        return NullOcr()
    raise ValueError(f"Unknown OCR engine '{engine_name}'")
