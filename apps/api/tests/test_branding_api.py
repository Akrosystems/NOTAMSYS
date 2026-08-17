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


def test_branding_defaults_are_public_and_unauthenticated(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path, "branding_defaults.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/branding")
            assert response.status_code == 200
            body = response.json()
            assert body["org_name"] == "NOTAMSYS"
            assert body["org_subtitle"] == "Accra NOF"
            assert body["logo_url"] is None
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_admin_can_update_branding_text_fields(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path, "branding_update.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            token = _login(client, "admin@notamsys.app")
            headers = {"Authorization": f"Bearer {token}"}
            response = client.patch(
                "/api/v1/admin/branding",
                headers=headers,
                json={"org_name": "GCAA NOTAM Office", "org_subtitle": "Kotoka NOF", "description": "Test description"},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["org_name"] == "GCAA NOTAM Office"
            assert body["org_subtitle"] == "Kotoka NOF"
            assert body["description"] == "Test description"

            public = client.get("/api/v1/branding")
            assert public.json()["org_name"] == "GCAA NOTAM Office"
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_non_admin_cannot_update_branding(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path, "branding_forbidden.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            token = _login(client, "officer@notamsys.app")
            headers = {"Authorization": f"Bearer {token}"}
            response = client.patch(
                "/api/v1/admin/branding", headers=headers, json={"org_name": "Hijacked"}
            )
            assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_admin_can_upload_and_fetch_logo(tmp_path, monkeypatch) -> None:
    from app.api import router as router_module
    from app.services.storage import EvidenceStorage

    monkeypatch.setattr(router_module, "storage", EvidenceStorage(root=tmp_path / "evidence"))

    engine, sessions = _prepare(tmp_path, "branding_logo.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            token = _login(client, "admin@notamsys.app")
            headers = {"Authorization": f"Bearer {token}"}

            tiny_png = bytes.fromhex(
                "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
                "de0000000c4944415478da6360000002000100ffff03000006000557bfabd400"
                "0000004945454e42"
            )
            upload = client.post(
                "/api/v1/admin/branding/logo",
                headers=headers,
                files={"file": ("logo.png", tiny_png, "image/png")},
            )
            assert upload.status_code == 201
            body = upload.json()
            assert body["logo_url"] is not None

            fetched = client.get("/api/v1/branding/logo")
            assert fetched.status_code == 200
            assert fetched.headers["content-type"] == "image/png"
            assert fetched.content == tiny_png

            rejected = client.post(
                "/api/v1/admin/branding/logo",
                headers=headers,
                files={"file": ("evil.pdf", b"%PDF-1.4", "application/pdf")},
            )
            assert rejected.status_code == 415

            removed = client.delete("/api/v1/admin/branding/logo", headers=headers)
            assert removed.status_code == 200
            assert removed.json()["logo_url"] is None
            assert client.get("/api/v1/branding").json()["logo_url"] is None
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_non_admin_cannot_remove_logo(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path, "branding_logo_forbidden.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            token = _login(client, "officer@notamsys.app")
            headers = {"Authorization": f"Bearer {token}"}
            response = client.delete("/api/v1/admin/branding/logo", headers=headers)
            assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
