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

    asyncio.run(prepare())
    return engine, sessions


def _login(client: TestClient, email: str) -> dict[str, str]:
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "SafePassword!26"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _draft_payload() -> dict[str, object]:
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


def _publish_and_get_deliveries(
    client: TestClient, officer_headers: dict, specialist_headers: dict
) -> tuple[str, list[dict]]:
    request_id = client.post(
        "/api/v1/requests",
        headers=officer_headers,
        json={
            "source": "portal",
            "originator_name": "Ghana Airports Company",
            "location_indicator": "DGAA",
            "raw_text": "Taxiway M closed due work in progress.",
        },
    ).json()["id"]
    client.post(f"/api/v1/requests/{request_id}/draft", headers=officer_headers, json=_draft_payload())
    client.post(f"/api/v1/requests/{request_id}/submit", headers=officer_headers)
    approve = client.post(
        f"/api/v1/requests/{request_id}/approve", headers=specialist_headers, json={"comment": "ok"}
    )
    notam_id = approve.json()["id"]
    client.post(f"/api/v1/requests/{request_id}/publish", headers=officer_headers)
    deliveries = client.get(f"/api/v1/notams/{notam_id}/deliveries", headers=officer_headers).json()
    return request_id, deliveries


def test_aftn_bridge_endpoints_reject_missing_or_wrong_key(tmp_path, monkeypatch) -> None:
    from app.api import router as router_module

    monkeypatch.setattr(router_module.settings, "aftn_bridge_api_key", "correct-key")
    engine, sessions = _prepare(tmp_path, "aftn_auth.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/aftn/outbox").status_code == 401
            assert (
                client.get("/api/v1/aftn/outbox", headers={"X-API-Key": "wrong"}).status_code
                == 401
            )
            assert (
                client.get(
                    "/api/v1/aftn/outbox", headers={"X-API-Key": "correct-key"}
                ).status_code
                == 200
            )
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_aftn_bridge_unconfigured_key_returns_503(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path, "aftn_unconfigured.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/aftn/outbox", headers={"X-API-Key": "anything"})
            assert response.status_code == 503
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_aftn_outbox_lists_pending_envelope_and_ack_transitions_to_published(
    tmp_path, monkeypatch
) -> None:
    from app.api import router as router_module

    monkeypatch.setattr(router_module.settings, "aftn_bridge_api_key", "bridge-secret")
    monkeypatch.setattr(router_module.settings, "publication_mode", "async_adapters")
    monkeypatch.setattr(router_module.settings, "email_mode", "simulated_sync")
    monkeypatch.setattr(router_module.settings, "gcaa_web_mode", "simulated_sync")

    engine, sessions = _prepare(tmp_path, "aftn_outbox.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    headers = {"X-API-Key": "bridge-secret"}
    try:
        with TestClient(app) as client:
            officer_headers = _login(client, "officer@example.com")
            specialist_headers = _login(client, "specialist@example.com")
            request_id, deliveries = _publish_and_get_deliveries(
                client, officer_headers, specialist_headers
            )
            aftn_delivery = next(d for d in deliveries if d["channel"] == "AFTN")
            assert aftn_delivery["status"] == "sent"

            outbox = client.get("/api/v1/aftn/outbox", headers=headers)
            assert outbox.status_code == 200
            items = outbox.json()
            assert len(items) == 1
            assert items[0]["id"] == aftn_delivery["id"]
            assert "DGAANOTA" in items[0]["outbound_body"]

            ack = client.post(
                f"/api/v1/aftn/outbox/{aftn_delivery['id']}/ack",
                headers=headers,
                json={"external_reference": "20260818T0900-abcd1234.aftn.txt"},
            )
            assert ack.status_code == 200
            assert ack.json()["status"] == "acknowledged"

            # AFTN was the only channel still pending -- GCAA_WEB/EMAIL/AIXM
            # are all simulated and already acknowledged, so the ack should
            # have completed the reconciliation to PUBLISHED.
            outbox_after = client.get("/api/v1/aftn/outbox", headers=headers)
            assert outbox_after.json() == []

            request_after = client.get(
                f"/api/v1/requests/{request_id}", headers=officer_headers
            ).json()
            assert request_after["status"] == "published"
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
