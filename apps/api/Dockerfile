FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# tesseract-ocr is the actual OCR engine pytesseract shells out to -- a
# system binary, not a Python package, so it has to be installed here
# explicitly rather than via pip. tesseract-ocr-eng is listed explicitly
# rather than relied on as a "Recommends" of tesseract-ocr, since
# --no-install-recommends would otherwise silently skip English trained
# data and every OCR call would fail at runtime with a missing-data error.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
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
