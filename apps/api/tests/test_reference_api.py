import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_session
from app.core.security import hash_password
from app.main import app
from app.models import Aerodrome, AipDataset, Fir, Role, User


def test_reference_endpoints(tmp_path) -> None:
    database = tmp_path / "reference.db"
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
            dataset = AipDataset(version="ref-test-1", source="seed", checksum="x", active=True)
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

            dataset_response = client.get("/api/v1/reference/datasets", headers=headers)
            assert dataset_response.status_code == 200
            assert dataset_response.json()["version"] == "ref-test-1"

            firs_response = client.get("/api/v1/reference/firs", headers=headers)
            assert firs_response.status_code == 200
            assert [f["icao_code"] for f in firs_response.json()] == ["DGAC"]

            aerodromes_response = client.get("/api/v1/reference/aerodromes", headers=headers)
            assert aerodromes_response.status_code == 200
            assert [a["icao_code"] for a in aerodromes_response.json()] == ["DGAA"]

            search_response = client.get(
                "/api/v1/reference/aerodromes", headers=headers, params={"q": "kotoka"}
            )
            assert len(search_response.json()) == 1

            found_response = client.get("/api/v1/reference/aerodromes/DGAA", headers=headers)
            assert found_response.status_code == 200
            assert found_response.json()["name"].startswith("Kotoka")

            missing_response = client.get("/api/v1/reference/aerodromes/ZZZZ", headers=headers)
            assert missing_response.status_code == 404

            assert client.get("/api/v1/reference/firs").status_code == 401
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
