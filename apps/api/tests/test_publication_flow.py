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


def _approved_notam(
    client: TestClient, officer_headers: dict, specialist_headers: dict
) -> tuple[str, str]:
    """Returns (request_id, notam_id) for a request drafted, submitted, and approved."""
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
    draft = client.post(
        f"/api/v1/requests/{request_id}/draft", headers=officer_headers, json=_draft_payload()
    )
    assert draft.status_code == 200
    assert (
        client.post(f"/api/v1/requests/{request_id}/submit", headers=officer_headers).status_code
        == 200
    )
    approve = client.post(
        f"/api/v1/requests/{request_id}/approve",
        headers=specialist_headers,
        json={"comment": "Verified"},
    )
    assert approve.status_code == 200
    return request_id, approve.json()["id"]


def test_simulated_sync_publish_reaches_published_with_real_dispatch_work(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path, "pub_sim.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            officer_headers = _login(client, "officer@example.com")
            specialist_headers = _login(client, "specialist@example.com")
            request_id, notam_id = _approved_notam(client, officer_headers, specialist_headers)

            published = client.post(
                f"/api/v1/requests/{request_id}/publish", headers=officer_headers
            )
            assert published.status_code == 200
            assert published.json()["status"] == "published"

            deliveries_response = client.get(
                f"/api/v1/notams/{notam_id}/deliveries", headers=officer_headers
            )
            assert deliveries_response.status_code == 200
            deliveries = deliveries_response.json()
            assert {d["channel"] for d in deliveries} == {"AFTN", "GCAA_WEB", "EMAIL", "AIXM"}
            assert all(d["status"] == "acknowledged" for d in deliveries)
            aftn_delivery = next(d for d in deliveries if d["channel"] == "AFTN")
            assert aftn_delivery["external_reference"].startswith("SIM-")
            aixm_delivery = next(d for d in deliveries if d["channel"] == "AIXM")
            assert aixm_delivery["external_reference"]
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_async_adapters_mode_rolls_back_to_approved_when_a_channel_fails(
    tmp_path, monkeypatch
) -> None:
    from app.api import router as router_module

    monkeypatch.setattr(router_module.settings, "publication_mode", "async_adapters")
    monkeypatch.setattr(router_module.settings, "aftn_drop_dir", str(tmp_path / "aftn-outbox"))

    engine, sessions = _prepare(tmp_path, "pub_async.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            officer_headers = _login(client, "officer@example.com")
            specialist_headers = _login(client, "specialist@example.com")
            request_id, notam_id = _approved_notam(client, officer_headers, specialist_headers)

            published = client.post(
                f"/api/v1/requests/{request_id}/publish", headers=officer_headers
            )
            assert published.status_code == 200
            # GCAA_WEB/EMAIL have no live backend in async_adapters mode --
            # honest failure rolls the request back to APPROVED, not a fake PUBLISHED.
            assert published.json()["status"] == "approved"

            outbox_files = list((tmp_path / "aftn-outbox").glob("*.aftn.txt"))
            assert len(outbox_files) == 1
            assert "DGAANOTA" in outbox_files[0].read_text(encoding="utf-8")

            deliveries = client.get(
                f"/api/v1/notams/{notam_id}/deliveries", headers=officer_headers
            ).json()
            by_channel = {d["channel"]: d["status"] for d in deliveries}
            assert by_channel["AFTN"] == "sent"  # file-drop, awaiting confirmation
            assert by_channel["AIXM"] == "acknowledged"  # real, self-contained
            assert by_channel["GCAA_WEB"] == "failed"
            assert by_channel["EMAIL"] == "failed"
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_retry_delivery_requires_nof_manager(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path, "pub_retry_rbac.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            officer_headers = _login(client, "officer@example.com")
            specialist_headers = _login(client, "specialist@example.com")
            request_id, notam_id = _approved_notam(client, officer_headers, specialist_headers)
            client.post(f"/api/v1/requests/{request_id}/publish", headers=officer_headers)
            deliveries = client.get(
                f"/api/v1/notams/{notam_id}/deliveries", headers=officer_headers
            ).json()
            delivery_id = deliveries[0]["id"]

            forbidden = client.post(
                f"/api/v1/deliveries/{delivery_id}/retry", headers=officer_headers
            )
            assert forbidden.status_code == 403
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
