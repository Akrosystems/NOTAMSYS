"""Tests for the pure-PIL half of TesseractOcr's preprocessing --
preprocess_for_ocr() itself needs no tesseract binary, unlike the
OSD-based rotation fix in TesseractOcr.recognize_page(), which does and so
can only be verified against a real deployment (see docs/DEPLOYMENT.md /
the commit history for that live verification)."""

from PIL import Image

from app.services.extraction.ocr import preprocess_for_ocr


def _solid_image(width: int, height: int, color: int = 200) -> Image.Image:
    return Image.new("RGB", (width, height), (color, color, color))


def test_preprocess_converts_to_grayscale() -> None:
    result = preprocess_for_ocr(_solid_image(1600, 1200))
    assert result.mode == "L"


def test_preprocess_upscales_small_images() -> None:
    result = preprocess_for_ocr(_solid_image(600, 400))
    assert result.width >= 1500
    # Aspect ratio preserved.
    assert abs(result.height / result.width - 400 / 600) < 0.01


def test_preprocess_leaves_already_large_images_unscaled() -> None:
    result = preprocess_for_ocr(_solid_image(2000, 1500))
    assert result.width == 2000
    assert result.height == 1500


def test_preprocess_applies_exif_orientation() -> None:
    """A real phone photo rotated via EXIF metadata (pixels stored
    landscape, tagged "rotate 90") should come out portrait after
    preprocessing -- this is the free, always-correct half of orientation
    handling; the other half (no EXIF tag at all) needs Tesseract's OSD
    and the real binary, so it isn't covered here."""
    image = _solid_image(400, 300)
    exif = image.getexif()
    exif[0x0112] = 6  # Orientation tag: "Rotate 90 CW"
    image.info["exif"] = exif.tobytes()

    result = preprocess_for_ocr(image)
    # Post-rotation the image is portrait (300x400) before the
    # upscale-if-small step scales it further -- aspect ratio is what
    # actually proves the rotation happened.
    assert result.height > result.width
