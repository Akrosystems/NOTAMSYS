"""OCR engine boundary. Pluggable so the process-wide default (local
Tesseract, per the locked "nothing leaves GCAA infrastructure" decision)
can be swapped without touching the pipeline that calls it.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from PIL import Image


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


def preprocess_for_ocr(image: "Image.Image") -> "Image.Image":
    """Orientation-correct, grayscale and contrast-normalize before OCR --
    pure PIL, no tesseract binary involved, so this much of the pipeline is
    testable without one (unlike the OSD-based rotation fix below, which
    needs the real binary).

    Confirmed live against real phone photos: with none of this, OCR on a
    WhatsApp-compressed photo of a hand-filled form recognized almost
    nothing usable. A cloud-vision alternative was evaluated and rejected
    for a worse reason than accuracy -- it hallucinated fluent, plausible,
    completely wrong text instead of failing obviously, which is a more
    dangerous failure mode for a safety-of-flight document than Tesseract's
    garbled-but-visibly-wrong output. This preprocessing keeps everything
    local and pushes on Tesseract's own accuracy instead.
    """
    from PIL import ImageOps

    # Correct orientation the camera recorded in EXIF, if present -- many
    # messaging apps strip this tag, but it's a free, always-correct fix
    # when it survives. Residual rotation with no EXIF tag at all is
    # handled separately via Tesseract's own OSD (see recognize_page),
    # which needs the real binary and can't be covered by a PIL-only test.
    image = ImageOps.exif_transpose(image) or image
    image = image.convert("L")  # grayscale -- normalizes color/lighting noise
    image = ImageOps.autocontrast(image)  # stretches contrast for uneven lighting/shadows

    # Tesseract's accuracy drops sharply once character height falls much
    # below ~20-30px; a compressed phone photo of a full page can leave
    # individual characters only a few pixels tall.
    if image.width < 1500:
        scale = 1500 / image.width
        image = image.resize((round(image.width * scale), round(image.height * scale)))
    return image


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
        image = preprocess_for_ocr(image)

        # Correct residual rotation (a genuinely sideways photo with no
        # EXIF orientation tag) using Tesseract's own orientation-and-
        # script detection. Needs the osd traineddata file (see
        # apps/api/Dockerfile's tesseract-ocr-osd) and the real binary.
        # OSD needs enough recognizable text to work with and raises on
        # sparse/noisy input -- that failure means "couldn't tell", not an
        # error, so orientation is just left as-is rather than the whole
        # request failing.
        try:
            osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
            rotation = int(osd.get("rotate", 0) or 0)
            if rotation:
                image = image.rotate(-rotation, expand=True)
        except pytesseract.pytesseract.TesseractError:
            pass

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
