FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# tesseract-ocr is the actual OCR engine pytesseract shells out to -- a
# system binary, not a Python package, so it has to be installed here
# explicitly rather than via pip. tesseract-ocr-eng and tesseract-ocr-osd
# are listed explicitly rather than relied on as "Recommends" of
# tesseract-ocr, since --no-install-recommends would otherwise silently
# skip them: without -eng, every OCR call fails at runtime with a missing
# language-data error; without -osd, orientation detection (see
# services/extraction/ocr.py's image_to_osd call, which corrects a
# genuinely sideways phone photo with no EXIF orientation tag) silently
# no-ops instead of failing loudly, since that call's own error handling
# treats "OSD unavailable" the same as "OSD inconclusive".
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations
# .[ocr] pulls in pymupdf/pytesseract/pillow -- see pyproject.toml's ocr
# extras docstring for why this group exists and what still needs the
# tesseract binary above versus what's pure Python (PDF text-layer
# extraction only needs pymupdf, not tesseract at all).
RUN pip install --no-cache-dir ".[ocr]"
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
