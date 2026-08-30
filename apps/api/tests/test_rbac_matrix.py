"""Declarative RBAC matrix: for every mutating endpoint, confirm the roles
NOT in its allowed set are rejected with 403 -- and that being in the
allowed set is enough to get *past* the role check specifically (FastAPI
evaluates `require_roles` dependencies before the handler body runs, so a
random/nonexistent path id still reliably distinguishes "blocked by role"
from "blocked by not finding the resource"). SYSTEM_ADMIN is a universal
bypass in require_roles() (see app/dependencies.py) so it's always expected
to pass regardless of an entry's declared allowed_roles.
"""

import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_session
from app.core.security import hash_password
from app.main import app
from app.models import Role, User

ALL_ROLES = [
    Role.ORIGINATOR,
    Role.AIS_OFFICER,
    Role.AIS_SPECIALIST,
    Role.NOF_MANAGER,
    Role.QMS_AUDITOR,
    Role.SYSTEM_ADMIN,
]

# (method, path template, allowed roles, JSON body or None)
ENDPOINT_ROLE_MATRIX: list[tuple[str, str, set[Role], dict[str, object] | None]] = [
    ("POST", "/requests/{id}/acknowledge", {Role.AIS_OFFICER, Role.AIS_SPECIALIST, Role.NOF_MANAGER}, None),
    ("POST", "/requests/{id}/draft", {Role.AIS_OFFICER, Role.AIS_SPECIALIST, Role.NOF_MANAGER}, {"series": "A", "kind": "NOTAMN", "fir": "DGAC", "q_code": "QMXLC", "traffic": "IV", "purpose": "BO", "scope": "A", "coordinates_radius": "0536N00010W005", "item_a": "DGAA", "item_b": "2026-08-17T06:00:00Z", "item_e": "TEST"}),
    ("POST", "/requests/{id}/submit", {Role.AIS_OFFICER, Role.AIS_SPECIALIST, Role.NOF_MANAGER}, None),
    ("POST", "/requests/{id}/request-changes", {Role.AIS_SPECIALIST, Role.NOF_MANAGER}, {"comment": "test"}),
    ("POST", "/requests/{id}/approve", {Role.AIS_SPECIALIST, Role.NOF_MANAGER}, {"comment": "test"}),
    ("POST", "/requests/{id}/publish", {Role.AIS_OFFICER, Role.AIS_SPECIALIST, Role.NOF_MANAGER}, None),
    ("POST", "/rules/versions/{id}/activate", {Role.NOF_MANAGER}, None),
    ("POST", "/deliveries/{id}/retry", {Role.AIS_OFFICER, Role.AIS_SPECIALIST, Role.NOF_MANAGER}, None),
    ("POST", "/deliveries/{id}/acknowledge", {Role.AIS_OFFICER, Role.AIS_SPECIALIST, Role.NOF_MANAGER}, None),
    ("POST", "/requests/{id}/mark-published", {Role.AIS_OFFICER, Role.AIS_SPECIALIST, Role.NOF_MANAGER}, None),
    ("GET", "/admin/users", {Role.SYSTEM_ADMIN}, None),
    ("POST", "/admin/users", {Role.SYSTEM_ADMIN}, {"email": "new@example.com", "full_name": "New User", "role": "ais_officer", "password": "SafePassword!26"}),
    ("PATCH", "/admin/users/{id}", {Role.SYSTEM_ADMIN}, {"is_active": False}),
    ("PATCH", "/admin/branding", {Role.SYSTEM_ADMIN}, {"org_name": "Test Org"}),
    # Note: /users/presence (GET) and /users/heartbeat (POST) are role-unrestricted
    # (CurrentUser only, no require_roles) so all authenticated roles return 200 -- not in this matrix.
]


def test_rbac_matrix(tmp_path) -> None:
    database = tmp_path / "rbac_matrix.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            session.add_all(
                User(
                    email=f"{role.value}@example.com",
                    full_name=f"Test {role.value}",
                    role=role,
                    password_hash=hash_password("SafePassword!26"),
                )
                for role in ALL_ROLES
            )
            await session.commit()

    asyncio.run(prepare())

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            tokens = {
                role: client.post(
                    "/api/v1/auth/login",
                    json={"email": f"{role.value}@example.com", "password": "SafePassword!26"},
                ).json()["access_token"]
                for role in ALL_ROLES
            }

            failures = []
            for method, path_template, allowed_roles, body in ENDPOINT_ROLE_MATRIX:
                path = f"/api/v1{path_template.format(id=uuid.uuid4())}"
                for role in ALL_ROLES:
                    headers = {"Authorization": f"Bearer {tokens[role]}"}
                    response = client.request(method, path, headers=headers, json=body)
                    if role in allowed_roles or role == Role.SYSTEM_ADMIN:
                        if response.status_code == 403:
                            failures.append(
                                f"{method} {path_template}: role {role.value} should be "
                                f"allowed but got 403"
                            )
                    else:
                        if response.status_code != 403:
                            failures.append(
                                f"{method} {path_template}: role {role.value} should be "
                                f"rejected but got {response.status_code}"
                            )
            assert not failures, "\n".join(failures)
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
