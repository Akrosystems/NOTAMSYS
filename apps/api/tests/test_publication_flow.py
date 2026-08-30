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


def test_async_adapters_mode_stays_publishing_on_partial_channel_failure(
    tmp_path, monkeypatch
) -> None:
    """GCAA_WEB/EMAIL have no live backend in async_adapters mode and
    genuinely fail -- but AFTN/AIXM succeed, so this is a partial failure,
    not a total one. The request must stay PUBLISHING (not silently revert
    to APPROVED, which would hide the per-channel delivery table and make
    the already-correct Retry button unreachable -- confirmed live in a
    full browser walkthrough before this fix)."""
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
            assert published.json()["status"] == "publishing"

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

            # The failed channels are now retryable through the UI's normal
            # path -- the whole point of staying PUBLISHING.
            failed_id = next(d["id"] for d in deliveries if d["channel"] == "EMAIL")
            retry = client.post(
                f"/api/v1/deliveries/{failed_id}/retry", headers=officer_headers
            )
            # 403 here would mean NOF_MANAGER-only, which is correct RBAC --
            # this call just proves the delivery is reachable at all, which
            # it wasn't before this fix (the whole table was hidden).
            assert retry.status_code in (200, 403)
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_publish_reverts_to_approved_only_when_every_channel_fails(
    tmp_path, monkeypatch
) -> None:
    """Total failure (unlike the partial case above) has nothing to show or
    retry against, so reverting to APPROVED and asking the user to fix
    configuration and start over is still correct."""
    from app.api import router as router_module
    from app.models import PublicationDelivery

    async def fail_everything(session, delivery: PublicationDelivery, notam, *, simulated):
        delivery.status = "failed"
        delivery.response_payload = {"status": "failed", "detail": "forced failure for test"}

    monkeypatch.setattr(router_module, "dispatch_delivery", fail_everything)

    engine, sessions = _prepare(tmp_path, "pub_total_fail.db")

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            officer_headers = _login(client, "officer@example.com")
            specialist_headers = _login(client, "specialist@example.com")
            request_id, _ = _approved_notam(client, officer_headers, specialist_headers)

            published = client.post(
                f"/api/v1/requests/{request_id}/publish", headers=officer_headers
            )
            assert published.status_code == 200
            assert published.json()["status"] == "approved"
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_per_channel_mode_lets_aftn_go_real_while_email_stays_simulated(
    tmp_path, monkeypatch
) -> None:
    """The scenario this whole fix exists for: AFTN pointed at real
    (file-drop) while GCAA_WEB/Email stay simulated, all at once -- not
    expressible with the old single global publication_mode switch."""
    from app.api import router as router_module

    monkeypatch.setattr(router_module.settings, "aftn_mode", "async_adapters")
    monkeypatch.setattr(router_module.settings, "aftn_drop_dir", str(tmp_path / "aftn-outbox"))

    engine, sessions = _prepare(tmp_path, "pub_per_channel.db")

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
            # AFTN "sent" (file-drop, real) + everything else acknowledged
            # (still simulated) is not "all acknowledged", so it correctly
            # stays PUBLISHING rather than either reverting or falsely
            # claiming PUBLISHED.
            assert published.json()["status"] == "publishing"

            outbox_files = list((tmp_path / "aftn-outbox").glob("*.aftn.txt"))
            assert len(outbox_files) == 1

            deliveries = client.get(
                f"/api/v1/notams/{notam_id}/deliveries", headers=officer_headers
            ).json()
            by_channel = {d["channel"]: d["status"] for d in deliveries}
            assert by_channel["AFTN"] == "sent"
            assert by_channel["GCAA_WEB"] == "acknowledged"
            assert by_channel["EMAIL"] == "acknowledged"
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_retry_stays_publishing_when_one_channel_still_fails_after_retry(
    tmp_path, monkeypatch
) -> None:
    """The same bug as the partial-failure /publish case, one layer deeper:
    retrying one still-broken channel among several must not revert the
    whole request just because that one channel is still failing -- only a
    retry that leaves *every* channel failed should revert."""
    from app.api import router as router_module
    from app.core.security import hash_password
    from app.models import Role, User

    monkeypatch.setattr(router_module.settings, "publication_mode", "async_adapters")
    monkeypatch.setattr(router_module.settings, "aftn_drop_dir", str(tmp_path / "aftn-outbox"))

    engine, sessions = _prepare(tmp_path, "pub_retry_reconcile.db")

    async def add_manager() -> None:
        async with sessions() as session:
            session.add(
                User(
                    email="manager@example.com",
                    full_name="Test Manager",
                    role=Role.NOF_MANAGER,
                    password_hash=hash_password("SafePassword!26"),
                )
            )
            await session.commit()

    asyncio.run(add_manager())

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            officer_headers = _login(client, "officer@example.com")
            specialist_headers = _login(client, "specialist@example.com")
            manager_headers = _login(client, "manager@example.com")
            request_id, notam_id = _approved_notam(client, officer_headers, specialist_headers)

            published = client.post(
                f"/api/v1/requests/{request_id}/publish", headers=officer_headers
            )
            assert published.json()["status"] == "publishing"

            deliveries = client.get(
                f"/api/v1/notams/{notam_id}/deliveries", headers=officer_headers
            ).json()
            email_id = next(d["id"] for d in deliveries if d["channel"] == "EMAIL")

            # EMAIL has no live backend in async_adapters mode -- retrying it
            # fails again, exactly like a real retry against an unfixed
            # misconfiguration would. GCAA_WEB is still failed too (never
            # retried), so the overall set is still a partial failure.
            retry = client.post(
                f"/api/v1/deliveries/{email_id}/retry", headers=manager_headers
            )
            assert retry.status_code == 200
            assert retry.json()["status"] == "failed"

            request_after = client.get(
                f"/api/v1/requests/{request_id}", headers=officer_headers
            ).json()
            assert request_after["status"] == "publishing"
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_manual_publication_and_channel_acknowledgement(tmp_path) -> None:
    engine, sessions = _prepare(tmp_path, "pub_manual_ack.db")

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

            ack = client.post(
                f"/api/v1/deliveries/{delivery_id}/acknowledge", headers=officer_headers
            )
            assert ack.status_code == 200
            assert ack.json()["status"] == "acknowledged"

            mark_pub = client.post(
                f"/api/v1/requests/{request_id}/mark-published", headers=officer_headers
            )
            assert mark_pub.status_code == 200
            assert mark_pub.json()["status"] == "published"
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())

