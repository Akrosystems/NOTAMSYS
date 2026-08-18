"""Database-bound dispatch. api/router.py's /publish and /deliveries/{id}/retry
endpoints both call into this, so there is exactly one implementation of
what dispatching a channel actually does."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notam, PublicationDelivery
from app.services.publication.registry import build_adapter


async def dispatch_delivery(
    session: AsyncSession,
    delivery: PublicationDelivery,
    notam: Notam,
    *,
    simulated: bool,
) -> None:
    adapter = build_adapter(delivery.channel, delivery.destination, simulated=simulated)
    message = adapter.prepare(notam)
    delivery.outbound_body = message.body
    delivery.attempted_at = datetime.now(UTC)
    try:
        receipt = await adapter.send(message)
    except ValueError as exc:
        delivery.status = "failed"
        delivery.response_payload = {"error": str(exc)}
        return
    delivery.external_reference = receipt.external_reference
    delivery.response_payload = {"status": receipt.status, "detail": receipt.detail}
    if receipt.status == "failed":
        delivery.status = "failed"
    elif receipt.status == "acknowledged" or not adapter.requires_acknowledgement:
        delivery.status = "acknowledged"
        delivery.acknowledged_at = datetime.now(UTC)
    else:
        delivery.status = "sent"
