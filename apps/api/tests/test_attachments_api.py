import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_session
from app.core.security import hash_password
from app.main import app
from app.models import Role, User


def test_attachment_upload_list_download_round_trip(tmp_path, monkeypatch) -> None:
    from app.api import router as router_module
    from app.services.storage import EvidenceStorage

    monkeypatch.setattr(router_module, "storage", EvidenceStorage(root=tmp_path / "evidence"))

    database = tmp_path / "attachments.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            session.add(
                User(
                    email="officer@example.com",
                    full_name="Test Officer",
                    role=Role.AIS_OFFICER,
                    password_hash=hash_password("SafePassword!26"),
                )
            )
            await session.commit()

    async def override_session():
        async with sessions() as session:
            yield session

    asyncio.run(prepare())
    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            token = client.post(
                "/api/v1/auth/login",
                json={"email": "officer@example.com", "password": "SafePassword!26"},
            ).json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            request_response = client.post(
                "/api/v1/requests",
                headers=headers,
                json={
                    "source": "portal",
                    "originator_name": "Ghana Airports Company",
                    "location_indicator": "DGAA",
                    "raw_text": "Taxiway M closed due work in progress.",
                },
            )
            assert request_response.status_code == 201
            request_id = request_response.json()["id"]

            upload_response = client.post(
                f"/api/v1/requests/{request_id}/attachments",
                headers=headers,
                files={
                    "file": ("request-form.pdf", b"%PDF-1.4 fake content", "application/pdf")
                },
            )
            assert upload_response.status_code == 201
            attachment_id = upload_response.json()["id"]

            listing = client.get(f"/api/v1/requests/{request_id}/attachments", headers=headers)
            assert listing.status_code == 200
            assert [row["id"] for row in listing.json()] == [attachment_id]

            unauthenticated_listing = client.get(f"/api/v1/requests/{request_id}/attachments")
            assert unauthenticated_listing.status_code == 401

            download = client.get(f"/api/v1/attachments/{attachment_id}/content", headers=headers)
            assert download.status_code == 200
            assert download.content == b"%PDF-1.4 fake content"
            assert download.headers["content-type"].startswith("application/pdf")

            unauthenticated_download = client.get(f"/api/v1/attachments/{attachment_id}/content")
            assert unauthenticated_download.status_code == 401
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
