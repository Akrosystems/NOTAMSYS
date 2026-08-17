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
            session.add_all(
                [
                    User(
                        email="admin@notamsys.app",
                        full_name="System Administrator",
                        role=Role.SYSTEM_ADMIN,
                        password_hash=hash_password("SafePassword!26"),
                    ),
                    User(
                        email="officer@notamsys.app",
                        full_name="Test Officer",
                        role=Role.AIS_OFFICER,
                        password_hash=hash_password("SafePassword!26"),
                    ),
                ]
            )
            await session.commit()

    asyncio.run(prepare())
    return engine, sessions


def _login(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "SafePassword!26"}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_admin_can_create_list_and_update_users(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path, "admin_crud.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            token = _login(client, "admin@notamsys.app")
            headers = {"Authorization": f"Bearer {token}"}

            created = client.post(
                "/api/v1/admin/users",
                headers=headers,
                json={
                    "email": "specialist@notamsys.app",
                    "full_name": "New Specialist",
                    "role": "ais_specialist",
                    "password": "AnotherSafePass!26",
                },
            )
            assert created.status_code == 201
            body = created.json()
            assert body["role"] == "ais_specialist"
            assert body["is_active"] is True

            duplicate = client.post(
                "/api/v1/admin/users",
                headers=headers,
                json={
                    "email": "specialist@notamsys.app",
                    "full_name": "Duplicate",
                    "role": "ais_officer",
                    "password": "AnotherSafePass!26",
                },
            )
            assert duplicate.status_code == 409

            listing = client.get("/api/v1/admin/users", headers=headers)
            assert listing.status_code == 200
            emails = {row["email"] for row in listing.json()}
            assert "specialist@notamsys.app" in emails
            assert "admin@notamsys.app" in emails

            deactivated = client.patch(
                f"/api/v1/admin/users/{body['id']}",
                headers=headers,
                json={"is_active": False},
            )
            assert deactivated.status_code == 200
            assert deactivated.json()["is_active"] is False

            login_deactivated = client.post(
                "/api/v1/auth/login",
                json={"email": "specialist@notamsys.app", "password": "AnotherSafePass!26"},
            )
            assert login_deactivated.status_code == 401
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_admin_cannot_deactivate_own_account(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path, "admin_self.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            token = _login(client, "admin@notamsys.app")
            headers = {"Authorization": f"Bearer {token}"}
            me = client.get("/api/v1/auth/me", headers=headers).json()
            response = client.patch(
                f"/api/v1/admin/users/{me['id']}", headers=headers, json={"is_active": False}
            )
            assert response.status_code == 409
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_non_admin_forbidden_from_admin_endpoints(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path, "admin_forbidden.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            token = _login(client, "officer@notamsys.app")
            headers = {"Authorization": f"Bearer {token}"}
            assert client.get("/api/v1/admin/users", headers=headers).status_code == 403
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_admin_bypasses_manager_only_endpoint(tmp_path) -> None:
    """Confirms the SYSTEM_ADMIN superset bypass in require_roles() works on
    an endpoint that never explicitly lists SYSTEM_ADMIN -- e.g. rule
    version activation, which is normally NOF_MANAGER-only."""
    engine, sessions = _prepare(tmp_path, "admin_bypass.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            token = _login(client, "admin@notamsys.app")
            headers = {"Authorization": f"Bearer {token}"}
            import uuid

            response = client.post(
                f"/api/v1/rules/versions/{uuid.uuid4()}/activate", headers=headers
            )
            assert response.status_code != 403
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
