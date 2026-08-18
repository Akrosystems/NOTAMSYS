"""Inbound NOTAM-request-by-email intake. Off by default -- poll_once()
refuses to run at all until NOTAMSYS_IMAP_HOST/USERNAME/PASSWORD are set.

Deliberately does not attempt to parse Item A-G out of the email body --
that's what the existing extraction pipeline (app/services/extraction) and
officer triage already do for uploaded documents, and this reuses that path
rather than duplicating it: any attachment lands as real evidence through
the same storage backend uploads use, immediately eligible for the same
"Run again" extraction a human-uploaded PDF gets. This module's only job is
turning an email into a RECEIVED request + evidence.

imaplib is synchronous. That's fine here specifically because this runs as
its own standalone process (app/email_poller.py), never inside the FastAPI
request-handling event loop -- unlike a blocking call inside an API
endpoint, there's no concurrent request it could stall.
"""

import imaplib
import uuid
from datetime import UTC, datetime
from email import message_from_bytes
from email.header import decode_header
from email.message import Message
from email.utils import parseaddr

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Attachment, NotamRequest, RequestSource, User, WorkflowStatus
from app.services.storage import storage
from app.services.workflow import audit


def _decode(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    return "".join(
        part.decode(encoding or "utf-8", errors="replace") if isinstance(part, bytes) else part
        for part, encoding in parts
    )


def _extract_body(message: Message) -> str:
    if not message.is_multipart():
        payload = message.get_payload(decode=True)
        if not payload:
            return ""
        return payload.decode(message.get_content_charset() or "utf-8", errors="replace")
    for part in message.walk():
        if part.get_content_type() == "text/plain" and not part.get_filename():
            payload = part.get_payload(decode=True)
            if payload:
                return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    return ""


def _extract_attachments(message: Message) -> list[tuple[str, bytes, str]]:
    if not message.is_multipart():
        return []
    found: list[tuple[str, bytes, str]] = []
    for part in message.walk():
        filename = part.get_filename()
        if filename and part.get_content_disposition() == "attachment":
            payload = part.get_payload(decode=True)
            if payload:
                found.append((_decode(filename), payload, part.get_content_type() or "application/octet-stream"))
    return found


async def _get_email_intake_actor(session: AsyncSession) -> User:
    actor = await session.scalar(
        select(User).where(User.email == settings.email_intake_service_email)
    )
    if actor is None:
        raise RuntimeError(
            f"Email intake service account {settings.email_intake_service_email} is not "
            "seeded -- run `python -m app.seed` against this database first."
        )
    return actor


async def poll_once(session: AsyncSession) -> int:
    """Connects, ingests every unseen message in the configured mailbox as a
    new NotamRequest (RECEIVED, source=EMAIL), marks each \\Seen so a repeat
    poll doesn't re-ingest it, then disconnects. Returns how many were
    created."""
    if not (settings.imap_host and settings.imap_username and settings.imap_password):
        raise RuntimeError(
            "IMAP is not configured -- set NOTAMSYS_IMAP_HOST/IMAP_USERNAME/IMAP_PASSWORD"
        )

    connection_cls = imaplib.IMAP4_SSL if settings.imap_use_ssl else imaplib.IMAP4
    connection = connection_cls(settings.imap_host, settings.imap_port)
    try:
        connection.login(settings.imap_username, settings.imap_password)
        connection.select(settings.imap_mailbox)
        status, data = connection.search(None, "UNSEEN")
        if status != "OK":
            raise RuntimeError(f"IMAP search failed: {status}")
        actor = await _get_email_intake_actor(session)
        created = 0
        for message_id in data[0].split():
            fetch_status, message_data = connection.fetch(message_id, "(RFC822)")
            if fetch_status != "OK" or not message_data or not isinstance(message_data[0], tuple):
                continue
            raw_message = message_data[0][1]
            parsed = message_from_bytes(raw_message)
            display_name, address = parseaddr(_decode(parsed.get("From")))
            subject = _decode(parsed.get("Subject")) or "(no subject)"
            body = _extract_body(parsed).strip() or "(empty message body -- see attachments)"
            now = datetime.now(UTC)
            request = NotamRequest(
                request_number=f"REQ-{now:%y%m}-{uuid.uuid4().hex[:5].upper()}",
                source=RequestSource.EMAIL,
                status=WorkflowStatus.RECEIVED,
                originator_name=display_name or address or "Unknown sender",
                originator_email=address or None,
                location_indicator="UNKNOWN",  # triage/extraction fills this in, not guessed here
                raw_text=f"Subject: {subject}\n\n{body}",
                created_by_id=actor.id,
                received_at=now,
            )
            session.add(request)
            await session.flush()
            for filename, payload, media_type in _extract_attachments(parsed):
                stored = await storage.put(request.id, filename, payload)
                session.add(
                    Attachment(
                        request_id=request.id,
                        filename=filename,
                        media_type=media_type,
                        size_bytes=stored.size,
                        object_key=stored.key,
                        sha256=stored.sha256,
                        uploaded_by_id=actor.id,
                    )
                )
            await audit(
                session,
                "notam_request",
                request.id,
                "request_received",
                actor.id,
                payload={"channel": "email_intake", "from": address},
            )
            connection.store(message_id, "+FLAGS", "\\Seen")
            created += 1
        await session.commit()
        return created
    finally:
        try:
            connection.close()
        except OSError:
            pass
        connection.logout()
