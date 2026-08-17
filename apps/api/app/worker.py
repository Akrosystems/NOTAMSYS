import asyncio
import uuid

from celery import Celery

from app.core.config import settings
from app.core.database import SessionFactory
from app.models import Notam, PublicationDelivery
from app.services.extraction.orchestrator import run_extraction
from app.services.publication.orchestrator import dispatch_delivery
from app.services.storage import storage

celery = Celery("notamsys", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)


@celery.task(name="notamsys.extract_document")
def extract_document(request_id: str, attachment_id: str) -> dict[str, object]:
    """OCR/NLP extraction task. Persists an ExtractionRun and confidence-
    scored ExtractedField proposals via services/extraction/orchestrator.py;
    never advances the request workflow and never writes to a NOTAM draft
    directly -- a human must accept each field."""
    return asyncio.run(_extract_document_async(request_id, attachment_id))


async def _extract_document_async(request_id: str, attachment_id: str) -> dict[str, object]:
    async with SessionFactory() as session:
        run = await run_extraction(
            session, storage, uuid.UUID(request_id), uuid.UUID(attachment_id)
        )
        await session.commit()
        return {"run_id": str(run.id), "status": run.status.value}


@celery.task(name="notamsys.publish_delivery")
def publish_delivery(delivery_id: str) -> dict[str, str]:
    """Publication dispatch task. Real implementation via
    services/publication/orchestrator.py -- the router's /publish endpoint
    and this task both call the same dispatch_delivery() so there is one
    code path, whether a deployment queues this through Celery or (as the
    router does today, matching the extraction pipeline's design) calls it
    inline for reliability without a live broker."""
    return asyncio.run(_publish_delivery_async(delivery_id))


async def _publish_delivery_async(delivery_id: str) -> dict[str, str]:
    async with SessionFactory() as session:
        delivery = await session.get(PublicationDelivery, uuid.UUID(delivery_id))
        if delivery is None:
            return {"delivery_id": delivery_id, "status": "not_found"}
        notam = await session.get(Notam, delivery.notam_id)
        if notam is None:
            return {"delivery_id": delivery_id, "status": "notam_not_found"}
        await dispatch_delivery(
            session, delivery, notam, simulated=settings.publication_mode == "simulated_sync"
        )
        await session.commit()
        return {"delivery_id": delivery_id, "status": delivery.status}
