import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_session
from app.core.security import hash_password
from app.main import app
from app.models import Aerodrome, AipDataset, Fir, Role, User


def _prepare(tmp_path):
    database = tmp_path / "aip_warning.db"
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
            dataset = AipDataset(version="warn-test-1", source="seed", checksum="x", active=True)
            session.add(dataset)
            await session.flush()
            fir = Fir(dataset_id=dataset.id, icao_code="DGAC", name="Accra FIR", provenance="t")
            session.add(fir)
            await session.flush()
            session.add(
                Aerodrome(
                    dataset_id=dataset.id,
                    icao_code="DGAA",
                    name="Kotoka International Airport, Accra",
                    fir_id=fir.id,
                    provenance="t",
                )
            )
            await session.commit()

    asyncio.run(prepare())
    return engine, sessions


def _draft_payload(item_a: str) -> dict[str, object]:
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
        "item_a": item_a,
        "item_b": "2026-08-17T06:00:00Z",
        "item_c": "2026-08-20T18:00:00Z",
        "item_e": "TWY M CLOSED DUE WIP.",
    }


def test_unknown_item_a_produces_a_warning_not_an_error(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path)

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

            request_id = client.post(
                "/api/v1/requests",
                headers=headers,
                json={
                    "source": "portal",
                    "originator_name": "Test Originator",
                    "location_indicator": "ZZZZ",
                    "raw_text": "Runway closed for maintenance.",
                },
            ).json()["id"]

            draft = client.post(
                f"/api/v1/requests/{request_id}/draft",
                headers=headers,
                json=_draft_payload("ZZZZ"),
            )
            assert draft.status_code == 200
            warnings = draft.json()["validation_result"]["warnings"]
            assert any("ZZZZ" in warning for warning in warnings)
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_known_item_a_produces_no_aip_warning(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path)

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

            request_id = client.post(
                "/api/v1/requests",
                headers=headers,
                json={
                    "source": "portal",
                    "originator_name": "Ghana Airports Company",
                    "location_indicator": "DGAA",
                    "raw_text": "Runway closed for maintenance.",
                },
            ).json()["id"]

            draft = client.post(
                f"/api/v1/requests/{request_id}/draft",
                headers=headers,
                json=_draft_payload("DGAA"),
            )
            assert draft.status_code == 200
            warnings = draft.json()["validation_result"]["warnings"]
            assert not any("not found in the active AIP" in warning for warning in warnings)
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
