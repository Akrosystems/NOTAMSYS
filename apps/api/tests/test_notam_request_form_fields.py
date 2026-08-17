"""Item A)-G) and the originator block on GCAA-AIS-NTM-FR01 must round-trip
through POST /requests exactly -- this is what the digital intake form
replaces, so field parity with the paper form isn't optional.
"""

import asyncio

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
                    email="officer@notamsys.app",
                    full_name="Test Officer",
                    role=Role.AIS_OFFICER,
                    password_hash=hash_password("SafePassword!26"),
                )
            )
            await session.commit()

    asyncio.run(prepare())
    return engine, sessions


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "officer@notamsys.app", "password": "SafePassword!26"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_full_form_fields_round_trip(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path, "form_fields.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            headers = {"Authorization": f"Bearer {_login(client)}"}
            payload = {
                "source": "upload",
                "originator_name": "Kwame Mensah",
                "originator_email": "ops@example.com",
                "originator_organisation": "Ghana Airports Company",
                "originator_phone": "+233 302 000000",
                "originator_reference": "OPS/2026/014",
                "location_type": "AIRSPACE",
                "location_indicator": "Accra TMA",
                "requested_kind": "NOTAMN",
                "start_at": "2026-08-18T06:00:00Z",
                "end_at": "2026-08-20T18:00:00Z",
                "end_confirmed": True,
                "periods_of_activity": "DAILY 0600-1800",
                "raw_text": "Temporary restricted area for drone survey operations.",
                "lower_limit_sfc": True,
                "upper_limit_value": "5000",
                "upper_limit_type": "AGL",
                "requested_series": "A",
            }
            response = client.post("/api/v1/requests", headers=headers, json=payload)
            assert response.status_code == 201, response.text
            body = response.json()
            assert body["location_type"] == "AIRSPACE"
            assert body["location_indicator"] == "ACCRA TMA"
            assert body["originator_organisation"] == "Ghana Airports Company"
            assert body["originator_phone"] == "+233 302 000000"
            assert body["periods_of_activity"] == "DAILY 0600-1800"
            assert body["lower_limit_sfc"] is True
            assert body["upper_limit_value"] == "5000"
            assert body["upper_limit_type"] == "AGL"

            fetched = client.get(f"/api/v1/requests/{body['id']}", headers=headers)
            assert fetched.json()["originator_organisation"] == "Ghana Airports Company"
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_ad_location_must_be_four_letters(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path, "form_fields_ad.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            headers = {"Authorization": f"Bearer {_login(client)}"}
            response = client.post(
                "/api/v1/requests",
                headers=headers,
                json={
                    "originator_name": "Test",
                    "location_type": "AD",
                    "location_indicator": "Accra",
                    "raw_text": "Runway closed for resurfacing.",
                },
            )
            assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_replace_requires_referenced_notam_number(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path, "form_fields_replace.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            headers = {"Authorization": f"Bearer {_login(client)}"}
            rejected = client.post(
                "/api/v1/requests",
                headers=headers,
                json={
                    "originator_name": "Test",
                    "location_indicator": "DGAA",
                    "requested_kind": "NOTAMR",
                    "raw_text": "Extending the closure by 48 hours.",
                },
            )
            assert rejected.status_code == 422

            accepted = client.post(
                "/api/v1/requests",
                headers=headers,
                json={
                    "originator_name": "Test",
                    "location_indicator": "DGAA",
                    "requested_kind": "NOTAMR",
                    "referenced_notam_number": "A0123/26",
                    "raw_text": "Extending the closure by 48 hours.",
                },
            )
            assert accepted.status_code == 201
            assert accepted.json()["referenced_notam_number"] == "A0123/26"
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
