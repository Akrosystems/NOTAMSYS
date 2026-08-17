import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_session
from app.core.security import hash_password
from app.main import app
from app.models import Role, User


def _prepare(tmp_path):
    database = tmp_path / "qline_checks.db"
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
    return engine, sessions


def _client_and_headers(client: TestClient) -> dict[str, str]:
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "officer@example.com", "password": "SafePassword!26"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _base_draft() -> dict[str, object]:
    return {
        "series": "A",
        "kind": "NOTAMN",
        "fir": "DGAC",
        "q_code": "QMXLC",
        "traffic": "IV",
        "purpose": "BO",
        "scope": "A",
        "lower_limit": "000",
        "upper_limit": "999",
        "coordinates_radius": "0536N00010W005",
        "item_a": "DGAA",
        "item_b": "2026-08-17T06:00:00Z",
        "item_c": "2026-08-20T18:00:00Z",
        "item_e": "TWY M CLOSED DUE WIP.",
    }


def _create_request(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/requests",
        headers=headers,
        json={
            "source": "portal",
            "originator_name": "Test Originator",
            "location_indicator": "DGAA",
            "raw_text": "Taxiway M closed due work in progress.",
        },
    )
    result: str = response.json()["id"]
    return result


def test_purpose_outside_the_closed_set_is_rejected(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path)

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            headers = _client_and_headers(client)
            request_id = _create_request(client, headers)
            payload = _base_draft()
            payload["purpose"] = "NB"  # not one of K, BO, NBO, M
            response = client.post(
                f"/api/v1/requests/{request_id}/draft", headers=headers, json=payload
            )
            assert response.status_code == 422
            assert "not valid" in str(response.json())
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_item_d_over_200_characters_is_rejected(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path)

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            headers = _client_and_headers(client)
            request_id = _create_request(client, headers)
            payload = _base_draft()
            payload["item_d"] = "x" * 201
            response = client.post(
                f"/api/v1/requests/{request_id}/draft", headers=headers, json=payload
            )
            assert response.status_code == 422
            assert "200 characters" in str(response.json())
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_notamr_referencing_a_nonexistent_notam_is_rejected(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path)

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            headers = _client_and_headers(client)
            request_id = _create_request(client, headers)
            payload = _base_draft()
            payload["kind"] = "NOTAMR"
            payload["replaces_notam_id"] = str(uuid.uuid4())
            response = client.post(
                f"/api/v1/requests/{request_id}/draft", headers=headers, json=payload
            )
            assert response.status_code == 422
            assert "was not found" in str(response.json())
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
