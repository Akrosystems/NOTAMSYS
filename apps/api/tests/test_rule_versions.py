import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_session
from app.core.security import hash_password
from app.main import app
from app.models import Role, RuleVersion, User
from app.services.rules import canonical_checksum, load_dataset_payload


def _make_engine(tmp_path, name: str):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / name}")
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def test_activation_requires_nof_manager_role(tmp_path) -> None:
    engine, sessions = _make_engine(tmp_path, "rule_versions_rbac.db")
    dataset = load_dataset_payload()

    async def prepare() -> str:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            officer = User(
                email="officer@example.com",
                full_name="Test Officer",
                role=Role.AIS_OFFICER,
                password_hash=hash_password("SafePassword!26"),
            )
            manager = User(
                email="manager@example.com",
                full_name="Test Manager",
                role=Role.NOF_MANAGER,
                password_hash=hash_password("SafePassword!26"),
            )
            session.add_all([officer, manager])
            await session.flush()
            version = RuleVersion(
                version="8126-2022.1-rbac-test",
                source_document=dataset["source_document"],
                source_revision=dataset["source_revision"],
                checksum=canonical_checksum(dataset),
                rules=dataset,
                verified_rule_count=len(dataset["rules"]),
                total_rule_count=len(dataset["rules"]),
                active=False,
                approved_by_id=manager.id,
            )
            session.add(version)
            await session.commit()
            return str(version.id)

    version_id = asyncio.run(prepare())

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            officer_token = client.post(
                "/api/v1/auth/login",
                json={"email": "officer@example.com", "password": "SafePassword!26"},
            ).json()["access_token"]
            manager_token = client.post(
                "/api/v1/auth/login",
                json={"email": "manager@example.com", "password": "SafePassword!26"},
            ).json()["access_token"]

            forbidden = client.post(
                f"/api/v1/rules/versions/{version_id}/activate",
                headers={"Authorization": f"Bearer {officer_token}"},
            )
            assert forbidden.status_code == 403

            activated = client.post(
                f"/api/v1/rules/versions/{version_id}/activate",
                headers={"Authorization": f"Bearer {manager_token}"},
            )
            assert activated.status_code == 200
            assert activated.json()["active"] is True
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_activation_rejects_checksum_mismatch(tmp_path) -> None:
    engine, sessions = _make_engine(tmp_path, "rule_versions_checksum.db")
    dataset = load_dataset_payload()

    async def prepare() -> str:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            manager = User(
                email="manager@example.com",
                full_name="Test Manager",
                role=Role.NOF_MANAGER,
                password_hash=hash_password("SafePassword!26"),
            )
            session.add(manager)
            await session.flush()
            version = RuleVersion(
                version="8126-2022.1-tampered",
                source_document=dataset["source_document"],
                source_revision=dataset["source_revision"],
                checksum="0" * 64,
                rules=dataset,
                verified_rule_count=len(dataset["rules"]),
                total_rule_count=len(dataset["rules"]),
                active=False,
                approved_by_id=manager.id,
            )
            session.add(version)
            await session.commit()
            return str(version.id)

    version_id = asyncio.run(prepare())

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            manager_token = client.post(
                "/api/v1/auth/login",
                json={"email": "manager@example.com", "password": "SafePassword!26"},
            ).json()["access_token"]
            response = client.post(
                f"/api/v1/rules/versions/{version_id}/activate",
                headers={"Authorization": f"Bearer {manager_token}"},
            )
            assert response.status_code == 409
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
