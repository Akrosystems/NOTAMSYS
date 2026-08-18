import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_session
from app.core.security import create_token, hash_password
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
                    email="officer@example.com",
                    full_name="Test Officer",
                    role=Role.AIS_OFFICER,
                    password_hash=hash_password("SafePassword!26"),
                )
            )
            await session.commit()

    asyncio.run(prepare())
    return engine, sessions


def test_refresh_token_mints_a_new_working_access_token(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path, "auth_refresh.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"email": "officer@example.com", "password": "SafePassword!26"},
            )
            refresh_token = login.json()["refresh_token"]

            refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
            assert refreshed.status_code == 200
            new_access_token = refreshed.json()["access_token"]
            assert new_access_token

            # The new access token actually works against a real endpoint.
            me = client.get(
                "/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access_token}"}
            )
            assert me.status_code == 200
            assert me.json()["email"] == "officer@example.com"
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_refresh_rejects_an_access_token_used_as_a_refresh_token(tmp_path) -> None:
    """The two token types are distinguished by a "type" claim -- an access
    token must not work as a refresh token even though both are valid JWTs
    signed with the same secret."""
    engine, sessions = _prepare(tmp_path, "auth_refresh_wrong_type.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"email": "officer@example.com", "password": "SafePassword!26"},
            )
            access_token = login.json()["access_token"]

            refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
            assert refreshed.status_code == 401
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_refresh_rejects_garbage_tokens_and_unknown_users(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path, "auth_refresh_invalid.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            garbage = client.post(
                "/api/v1/auth/refresh", json={"refresh_token": "not-a-real-jwt"}
            )
            assert garbage.status_code == 401

            forged = create_token("00000000-0000-0000-0000-000000000000", "refresh")
            unknown_user = client.post("/api/v1/auth/refresh", json={"refresh_token": forged})
            assert unknown_user.status_code == 401
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_refresh_rejects_a_deactivated_users_token(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path, "auth_refresh_deactivated.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"email": "officer@example.com", "password": "SafePassword!26"},
            )
            refresh_token = login.json()["refresh_token"]

        async def deactivate() -> None:
            async with sessions() as session:
                user = await session.scalar(
                    select(User).where(User.email == "officer@example.com")
                )
                user.is_active = False
                await session.commit()

        asyncio.run(deactivate())

        with TestClient(app) as client:
            deactivated = client.post(
                "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
            )
            assert deactivated.status_code == 401
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
