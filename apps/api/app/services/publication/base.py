import uuid
from dataclasses import dataclass
from typing import Protocol

from app.models import Notam


@dataclass(frozen=True)
class OutboundMessage:
    channel: str
    destination: str
    body: str
    request_id: uuid.UUID | None = None


@dataclass(frozen=True)
class DeliveryReceipt:
    status: str  # "acknowledged" | "sent" | "failed"
    external_reference: str | None = None
    detail: str | None = None


class PublicationAdapter(Protocol):
    channel: str
    # If False, `send()` succeeding is itself terminal success. If True,
    # a "sent" receipt means dispatched-but-unconfirmed -- the delivery
    # stays pending until something (a human, a future integration) acks it.
    requires_acknowledgement: bool

    def prepare(self, notam: Notam) -> OutboundMessage: ...

    async def send(self, message: OutboundMessage) -> DeliveryReceipt: ...
