import smtplib
import uuid
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

from app.core.config import settings
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


class PullQueueAftnAdapter:
    """Real AFTN dispatch for a NOTAMSYS deployment that isn't co-located
    with the Comsoft/CADAS terminal -- e.g. this app hosted on Render while
    the terminal is an on-prem Linux box ATSEP controls. FileDropAftnAdapter
    above assumes a shared filesystem between this process and the terminal,
    which doesn't exist across that boundary (and Render's local disk is
    wiped on every redeploy regardless -- see docs/DEPLOYMENT.md).

    Instead of writing anywhere, this just builds and ITA-2-validates the
    envelope and returns "sent" -- dispatch_delivery persists the envelope
    body onto the delivery row, and app/aftn_bridge.py (run by ATSEP on
    their own box, see docs/AFTN_BRIDGE.md) polls GET /aftn/outbox for it,
    writes it to the directory Comsoft actually watches, and acknowledges
    it back. Still "sent", never "acknowledged" here -- nothing in this
    process can confirm an operator actually transmitted it, same honest
    limit FileDropAftnAdapter already had."""

    channel = "AFTN"
    requires_acknowledgement = True

    def prepare(self, notam: Notam) -> OutboundMessage:
        body = build_envelope(notam.formatted_message)
        return OutboundMessage(
            channel=self.channel,
            destination="DGAANOTA/DGAANOTB/DGAANOTC",
            body=body,
            request_id=notam.request_id,
        )

    async def send(self, message: OutboundMessage) -> DeliveryReceipt:
        return DeliveryReceipt(status="sent")


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


class SmtpEmailAdapter:
    """Real outbound email for the EMAIL channel. `smtplib` is synchronous --
    calls block the event loop briefly, same tradeoff already accepted for
    MinioStorage's client. Acceptable at current volume (one message per
    publish); revisit with a thread offload if that changes.

    registry.build_adapter only constructs this once SMTP settings are
    present -- if the channel is set to real but the settings are missing,
    the caller falls back to UnconfiguredAdapter's honest failure instead of
    reaching this class at all."""

    channel = "EMAIL"
    requires_acknowledgement = False

    def __init__(self, destination: str) -> None:
        self.destination = destination

    def prepare(self, notam: Notam) -> OutboundMessage:
        return OutboundMessage(
            channel=self.channel,
            destination=self.destination,
            body=notam.formatted_message,
            request_id=notam.request_id,
        )

    async def send(self, message: OutboundMessage) -> DeliveryReceipt:
        identifier = message.body.splitlines()[0].lstrip("(").strip() if message.body else "NOTAM"
        email = EmailMessage()
        email["Subject"] = f"NOTAM Distribution -- {identifier}"
        email["From"] = settings.smtp_from_address or settings.smtp_username or "notamsys@localhost"
        email["To"] = message.destination
        email["Message-Id"] = make_msgid()
        email.set_content(message.body)
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
                if settings.smtp_use_tls:
                    client.starttls()
                if settings.smtp_username and settings.smtp_password:
                    client.login(settings.smtp_username, settings.smtp_password)
                client.send_message(email)
        except (smtplib.SMTPException, OSError) as exc:
            return DeliveryReceipt(status="failed", detail=f"SMTP send failed: {exc}")
        return DeliveryReceipt(status="acknowledged", external_reference=email["Message-Id"])


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
