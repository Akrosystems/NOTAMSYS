import asyncio
from email.message import EmailMessage

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import Attachment, NotamRequest, User
from app.seed import _seed_email_intake_user
from app.services.intake import email_poller


def _build_raw_email(with_attachment: bool = False) -> bytes:
    message = EmailMessage()
    message["From"] = "Ghana Airports Company <ops@example.com>"
    message["To"] = "aisnotam@caa.gov.gh"
    message["Subject"] = "Taxiway M closure"
    message.set_content("Taxiway M closed due to work in progress. Effective immediately.")
    if with_attachment:
        message.add_attachment(
            b"%PDF-1.4 fake evidence content",
            maintype="application",
            subtype="pdf",
            filename="evidence.pdf",
        )
    return bytes(message)


class _FakeImapConnection:
    """Stands in for imaplib.IMAP4_SSL. Serves one canned unseen message
    (with an id in `pending`) and records which ones get marked \\Seen."""

    pending: list[bytes] = []
    seen: list[bytes] = []

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

    def login(self, username: str, password: str) -> None:
        pass

    def select(self, mailbox: str) -> None:
        pass

    def search(self, charset, criteria):
        ids = b" ".join(str(i).encode() for i in range(len(_FakeImapConnection.pending)))
        return "OK", [ids]

    def fetch(self, message_id: bytes, parts: str):
        index = int(message_id)
        raw = _FakeImapConnection.pending[index]
        return "OK", [(b"1 (RFC822 {%d}" % len(raw), raw)]

    def store(self, message_id: bytes, flags_op: str, flags: str) -> None:
        _FakeImapConnection.seen.append(message_id)

    def close(self) -> None:
        pass

    def logout(self) -> None:
        pass


def _prepare(tmp_path, name: str):
    database = tmp_path / name
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            await _seed_email_intake_user(session)
            await session.commit()

    asyncio.run(prepare())
    return engine, sessions


def test_poll_once_refuses_to_run_without_imap_settings(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(email_poller.settings, "imap_host", None)
    engine, sessions = _prepare(tmp_path, "email_unconfigured.db")

    async def run() -> None:
        async with sessions() as session:
            with pytest.raises(RuntimeError, match="not configured"):
                await email_poller.poll_once(session)

    try:
        asyncio.run(run())
    finally:
        asyncio.run(engine.dispose())


def test_poll_once_ingests_message_with_attachment_as_evidence(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(email_poller.settings, "imap_host", "mail.example.com")
    monkeypatch.setattr(email_poller.settings, "imap_username", "aisnotam@caa.gov.gh")
    monkeypatch.setattr(email_poller.settings, "imap_password", "secret")

    _FakeImapConnection.pending = [_build_raw_email(with_attachment=True)]
    _FakeImapConnection.seen = []
    monkeypatch.setattr(email_poller.imaplib, "IMAP4_SSL", _FakeImapConnection)

    engine, sessions = _prepare(tmp_path, "email_ingest.db")

    async def run() -> int:
        async with sessions() as session:
            return await email_poller.poll_once(session)

    try:
        created = asyncio.run(run())
        assert created == 1
        assert _FakeImapConnection.seen == [b"0"]

        async def check() -> None:
            async with sessions() as session:
                request = await session.scalar(select(NotamRequest))
                assert request is not None
                assert request.source.value == "email"
                assert request.status.value == "received"
                assert request.originator_name == "Ghana Airports Company"
                assert request.originator_email == "ops@example.com"
                assert "Taxiway M closed" in request.raw_text
                assert "Taxiway M closure" in request.raw_text  # subject line included

                attachment = await session.scalar(select(Attachment))
                assert attachment is not None
                assert attachment.filename == "evidence.pdf"
                assert attachment.request_id == request.id

                actor = await session.scalar(
                    select(User).where(User.email == "email-intake@notamsys.app")
                )
                assert request.created_by_id == actor.id

        asyncio.run(check())
    finally:
        asyncio.run(engine.dispose())


def test_poll_once_is_idempotent_when_no_unseen_messages_remain(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(email_poller.settings, "imap_host", "mail.example.com")
    monkeypatch.setattr(email_poller.settings, "imap_username", "aisnotam@caa.gov.gh")
    monkeypatch.setattr(email_poller.settings, "imap_password", "secret")

    _FakeImapConnection.pending = []
    _FakeImapConnection.seen = []
    monkeypatch.setattr(email_poller.imaplib, "IMAP4_SSL", _FakeImapConnection)

    engine, sessions = _prepare(tmp_path, "email_idempotent.db")

    async def run() -> int:
        async with sessions() as session:
            return await email_poller.poll_once(session)

    try:
        assert asyncio.run(run()) == 0
    finally:
        asyncio.run(engine.dispose())
