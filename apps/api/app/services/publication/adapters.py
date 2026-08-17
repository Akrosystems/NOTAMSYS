import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.models import Notam
from app.services.publication.aftn import build_envelope
from app.services.publication.base import DeliveryReceipt, OutboundMessage
from app.services.storage import storage


class SimulatedAftnAdapter:
    """Dev/test default for the AFTN channel. Builds and ITA-2-validates a
    real envelope -- genuine, testable work -- but doesn't attempt to send
    it anywhere, and acknowledges instantly. This is what keeps
    publication_mode="simulated_sync" behaviourally identical to the
    pre-Phase-5 placeholder while no longer doing *nothing*."""

    channel = "AFTN"
    requires_acknowledgement = False

    def prepare(self, notam: Notam) -> OutboundMessage:
        body = build_envelope(notam.formatted_message)
        return OutboundMessage(
            channel=self.channel,
            destination="DGAANOTA/DGAANOTB/DGAANOTC",
            body=body,
            request_id=notam.request_id,
        )

    async def send(self, message: OutboundMessage) -> DeliveryReceipt:
        return DeliveryReceipt(
            status="acknowledged", external_reference=f"SIM-{uuid.uuid4().hex[:10].upper()}"
        )


class FileDropAftnAdapter:
    """Writes the AFTN envelope to a watched directory for the office's
    Comsoft/CADAS terminal to pick up -- the realistic first real-world
    integration for an air-gapped AFTN workstation with no API. Delivery is
    "sent", never "acknowledged": nothing here confirms an operator actually
    transmitted it, which is the honest state until that confirmation loop
    is built."""

    channel = "AFTN"
    requires_acknowledgement = True

    def __init__(self, drop_dir: Path) -> None:
        self.drop_dir = drop_dir

    def prepare(self, notam: Notam) -> OutboundMessage:
        body = build_envelope(notam.formatted_message)
        return OutboundMessage(
            channel=self.channel,
            destination="DGAANOTA/DGAANOTB/DGAANOTC",
            body=body,
            request_id=notam.request_id,
        )

    async def send(self, message: OutboundMessage) -> DeliveryReceipt:
        self.drop_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}.aftn.txt"
        (self.drop_dir / filename).write_text(message.body, encoding="utf-8")
        return DeliveryReceipt(status="sent", external_reference=filename)


class AixmPublishAdapter:
    """Writes the NOTAM's real AIXM 5.1.1 Event XML (services/aixm) into
    evidence storage under a publications/ prefix -- a genuine artifact,
    standing in for a Digital NOTAM service submission until a real feed
    endpoint exists to submit it to."""

    channel = "AIXM"
    requires_acknowledgement = False

    def prepare(self, notam: Notam) -> OutboundMessage:
        return OutboundMessage(
            channel=self.channel,
            destination="digital-notam-service",
            body=notam.aixm_xml or "",
            request_id=notam.request_id,
        )

    async def send(self, message: OutboundMessage) -> DeliveryReceipt:
        if not message.body:
            return DeliveryReceipt(status="failed", detail="No AIXM XML available for this NOTAM")
        stored = await storage.put(
            message.request_id or uuid.uuid4(), "event.aixm.xml", message.body.encode("utf-8")
        )
        return DeliveryReceipt(status="acknowledged", external_reference=stored.key)


class SimulatedChannelAdapter:
    """Always-acknowledges stand-in for any channel, used only in
    publication_mode="simulated_sync" so dev/test doesn't require a real
    website CMS or SMTP relay. This is what /publish did unconditionally
    before Phase 5 -- now explicit, named, and opt-in rather than the only
    behaviour available."""

    def __init__(self, channel: str, destination: str) -> None:
        self.channel = channel
        self.destination = destination
        self.requires_acknowledgement = False

    def prepare(self, notam: Notam) -> OutboundMessage:
        return OutboundMessage(
            channel=self.channel,
            destination=self.destination,
            body=notam.formatted_message,
            request_id=notam.request_id,
        )

    async def send(self, message: OutboundMessage) -> DeliveryReceipt:
        return DeliveryReceipt(
            status="acknowledged", external_reference=f"SIM-{uuid.uuid4().hex[:10].upper()}"
        )


class UnconfiguredAdapter:
    """Placeholder for a channel with no live backend yet (the GCAA website
    CMS, an SMTP relay for the email distribution list). Fails clearly
    rather than pretending to succeed -- see docs/ARCHITECTURE.md's
    operational boundary stance."""

    def __init__(self, channel: str, destination: str) -> None:
        self.channel = channel
        self.destination = destination
        self.requires_acknowledgement = True

    def prepare(self, notam: Notam) -> OutboundMessage:
        return OutboundMessage(
            channel=self.channel,
            destination=self.destination,
            body=notam.formatted_message,
            request_id=notam.request_id,
        )

    async def send(self, message: OutboundMessage) -> DeliveryReceipt:
        return DeliveryReceipt(
            status="failed",
            detail=f"{self.channel} adapter has no live backend configured yet",
        )
