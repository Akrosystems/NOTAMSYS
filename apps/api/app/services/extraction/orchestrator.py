"""Database-bound wrapper around services/extraction/pipeline.py. Both the
HTTP-triggered synchronous path (api/router.py) and the Celery worker
(worker.py) call this, so there is exactly one code path that persists
extraction results -- never two implementations that could drift apart.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import (
    Attachment,
    ExtractedField,
    ExtractionRun,
    ExtractionStatus,
    ExtractorKind,
    NotamRequest,
)
from app.services.extraction.ocr import build_engine
from app.services.extraction.pipeline import run_pipeline
from app.services.storage import StorageBackend


async def run_extraction(
    session: AsyncSession,
    storage: StorageBackend,
    request_id: uuid.UUID,
    attachment_id: uuid.UUID,
) -> ExtractionRun:
    attachment = await session.get(Attachment, attachment_id)
    if attachment is None:
        raise ValueError("Attachment not found")

    engine = build_engine(settings.ocr_engine)
    run = ExtractionRun(
        attachment_id=attachment.id,
        engine=engine.name,
        status=ExtractionStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    session.add(run)
    await session.flush()

    try:
        content = await storage.get(attachment.object_key)
        result = run_pipeline(content, attachment.media_type, engine)
        for candidate in result.fields:
            session.add(
                ExtractedField(
                    run_id=run.id,
                    field_name=candidate.field_name,
                    raw_text=candidate.raw_text,
                    normalized_value=candidate.normalized_value,
                    confidence=candidate.confidence,
                    page=candidate.page,
                    extractor=ExtractorKind(candidate.extractor),
                )
            )
        run.status = ExtractionStatus.SUCCEEDED
        run.page_count = result.page_count
        run.finished_at = datetime.now(UTC)

        request = await session.get(NotamRequest, request_id)
        if request is not None:
            request.extracted_data = result.as_dict()
            request.extraction_confidence = result.overall_confidence
    except Exception as exc:  # noqa: BLE001 - any failure is recorded, never swallowed
        run.status = ExtractionStatus.FAILED
        run.error = str(exc)
        run.finished_at = datetime.now(UTC)

    await session.flush()
    return run
