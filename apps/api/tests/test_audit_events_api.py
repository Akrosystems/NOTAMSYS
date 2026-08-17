import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_session
from app.core.security import hash_password
from app.main import app
from app.models import Role, User


def test_audit_events_are_recorded_and_listable(tmp_path) -> None:
    database = tmp_path / "audit.db"
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

    asyncio.run(prepare())

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            token = client.post(
                "/api/v1/auth/login",
                json={"email": "officer@example.com", "password": "SafePassword!26"},
            ).json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            client.post(
                "/api/v1/requests",
                headers=headers,
                json={
                    "source": "portal",
                    "originator_name": "Ghana Airports Company",
                    "location_indicator": "DGAA",
                    "raw_text": "Taxiway M closed due work in progress.",
                },
            )

            events = client.get("/api/v1/audit-events", headers=headers)
            assert events.status_code == 200
            body = events.json()
            assert len(body) >= 1
            assert body[0]["action"] == "request_received"
            assert body[0]["actor_name"] == "Test Officer"

            filtered = client.get(
                "/api/v1/audit-events",
                headers=headers,
                params={"entity_type": "notam_request"},
            )
            assert filtered.status_code == 200
            assert all(e["entity_type"] == "notam_request" for e in filtered.json())

            assert client.get("/api/v1/audit-events").status_code == 401
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
