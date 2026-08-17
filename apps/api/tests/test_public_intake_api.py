import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_session
from app.core.security import hash_password
from app.main import app
from app.models import Role, User


def _prepare(tmp_path, name: str):
    database = tmp_path / name
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            session.add(
                User(
                    email="portal@notamsys.app",
                    full_name="Public Portal Service",
                    role=Role.ORIGINATOR,
                    password_hash=hash_password(uuid.uuid4().hex),
                )
            )
            await session.commit()

    asyncio.run(prepare())
    return engine, sessions


def test_public_request_creation_requires_no_authentication(tmp_path, monkeypatch) -> None:
    from app.api import router as router_module
    from app.services.storage import EvidenceStorage

    monkeypatch.setattr(router_module, "storage", EvidenceStorage(root=tmp_path / "evidence"))

    engine, sessions = _prepare(tmp_path, "public_intake.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/public/requests",
                json={
                    "originator_name": "Ghana Airports Company",
                    "originator_email": "ops@example.com",
                    "location_indicator": "DGAA",
                    "raw_text": "Runway 03/21 closed for resurfacing work.",
                    "requested_series": "A",
                },
            )
            assert response.status_code == 201
            body = response.json()
            assert body["source"] == "portal"
            assert body["status"] == "received"

            upload = client.post(
                f"/api/v1/public/requests/{body['id']}/attachments",
                files={"file": ("evidence.pdf", b"%PDF-1.4 fake", "application/pdf")},
            )
            assert upload.status_code == 201
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_public_intake_disabled_returns_503(tmp_path, monkeypatch) -> None:
    from app.api import router as router_module

    monkeypatch.setattr(router_module.settings, "public_intake_enabled", False)

    engine, sessions = _prepare(tmp_path, "public_intake_disabled.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/public/requests",
                json={
                    "originator_name": "Ghana Airports Company",
                    "location_indicator": "DGAA",
                    "raw_text": "Runway 03/21 closed for resurfacing work.",
                },
            )
            assert response.status_code == 503
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_public_attachment_upload_rejects_requests_not_created_via_portal(
    tmp_path, monkeypatch
) -> None:
    from app.api import router as router_module
    from app.services.storage import EvidenceStorage

    monkeypatch.setattr(router_module, "storage", EvidenceStorage(root=tmp_path / "evidence"))

    engine, sessions = _prepare(tmp_path, "public_intake_ownership.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            random_id = uuid.uuid4()
            upload = client.post(
                f"/api/v1/public/requests/{random_id}/attachments",
                files={"file": ("evidence.pdf", b"%PDF-1.4 fake", "application/pdf")},
            )
            assert upload.status_code == 404
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
