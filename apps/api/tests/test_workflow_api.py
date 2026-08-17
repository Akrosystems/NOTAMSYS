import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_session
from app.core.security import hash_password
from app.main import app
from app.models import Role, User


def test_officer_to_specialist_to_publication(tmp_path) -> None:
    database = tmp_path / "workflow.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            session.add_all(
                [
                    User(
                        email="officer@example.com",
                        full_name="Test Officer",
                        role=Role.AIS_OFFICER,
                        password_hash=hash_password("SafePassword!26"),
                    ),
                    User(
                        email="specialist@example.com",
                        full_name="Test Specialist",
                        role=Role.AIS_SPECIALIST,
                        password_hash=hash_password("SafePassword!26"),
                    ),
                ]
            )
            await session.commit()

    async def override_session():
        async with sessions() as session:
            yield session

    asyncio.run(prepare())
    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            officer = client.post(
                "/api/v1/auth/login",
                json={"email": "officer@example.com", "password": "SafePassword!26"},
            ).json()["access_token"]
            specialist = client.post(
                "/api/v1/auth/login",
                json={"email": "specialist@example.com", "password": "SafePassword!26"},
            ).json()["access_token"]
            officer_headers = {"Authorization": f"Bearer {officer}"}
            specialist_headers = {"Authorization": f"Bearer {specialist}"}

            request_response = client.post(
                "/api/v1/requests",
                headers=officer_headers,
                json={
                    "source": "portal",
                    "originator_name": "Ghana Airports Company",
                    "originator_email": "originator@example.com",
                    "originator_reference": "GACL/NTM/001",
                    "location_indicator": "DGAA",
                    "raw_text": "Taxiway M closed due work in progress.",
                    "requested_series": "A",
                },
            )
            assert request_response.status_code == 201
            request_id = request_response.json()["id"]

            draft_response = client.post(
                f"/api/v1/requests/{request_id}/draft",
                headers=officer_headers,
                json={
                    "series": "A",
                    "kind": "NOTAMN",
                    "fir": "DGAC",
                    "q_code": "QMXLC",
                    "traffic": "IV",
                    # BO per Doc 8126 III-App G-26 (visually verified 2026-08-15).
                    "purpose": "BO",
                    "scope": "A",
                    "lower_limit": "000",
                    "upper_limit": "999",
                    "coordinates_radius": "0536N00010W005",
                    "item_a": "DGAA",
                    "item_b": "2026-08-17T06:00:00Z",
                    "item_c": "2026-08-20T18:00:00Z",
                    "item_e": "TWY M CLOSED DUE WIP.",
                },
            )
            assert draft_response.status_code == 200
            assert draft_response.json()["q_code"] == "QMXLC"
            assert (
                client.post(
                    f"/api/v1/requests/{request_id}/submit", headers=officer_headers
                ).status_code
                == 200
            )
            assert (
                client.post(
                    f"/api/v1/requests/{request_id}/approve",
                    headers=specialist_headers,
                    json={"comment": "Source and draft independently verified."},
                ).status_code
                == 200
            )
            published = client.post(
                f"/api/v1/requests/{request_id}/publish", headers=officer_headers
            )
            assert published.status_code == 200
            assert published.json()["status"] == "published"
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
