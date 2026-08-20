import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_session
from app.core.security import hash_password
from app.main import app
from app.models import Role, User


def _build_pdf(text: str) -> bytes:
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text, fontsize=11)
    content = document.tobytes()
    document.close()
    return content


def _prepare_client(tmp_path, monkeypatch, *, extraction_enabled: bool):
    from app.api import router as router_module
    from app.services.storage import EvidenceStorage

    monkeypatch.setattr(router_module, "storage", EvidenceStorage(root=tmp_path / "evidence"))
    monkeypatch.setattr(router_module.settings, "extraction_enabled", extraction_enabled)

    database = tmp_path / "extraction.db"
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

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    return engine


def _login(client: TestClient) -> dict[str, str]:
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "officer@example.com", "password": "SafePassword!26"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_upload_triggers_extraction_when_enabled(tmp_path, monkeypatch) -> None:
    engine = _prepare_client(tmp_path, monkeypatch, extraction_enabled=True)
    try:
        with TestClient(app) as client:
            headers = _login(client)
            request_id = client.post(
                "/api/v1/requests",
                headers=headers,
                json={
                    "source": "portal",
                    "originator_name": "Ghana Airports Company",
                    "location_indicator": "DGAA",
                    "raw_text": "Taxiway M closed for scheduled maintenance.",
                },
            ).json()["id"]

            pdf_bytes = _build_pdf("Location: DGAA Full Text Taxiway M closed for maintenance.")
            upload = client.post(
                f"/api/v1/requests/{request_id}/attachments",
                headers=headers,
                files={"file": ("request-form.pdf", pdf_bytes, "application/pdf")},
            )
            assert upload.status_code == 201

            extraction = client.get(f"/api/v1/requests/{request_id}/extraction", headers=headers)
            assert extraction.status_code == 200
            body = extraction.json()
            assert body is not None
            assert body["status"] == "succeeded"
            assert body["fields"]
            field_id = next(
                f["id"] for f in body["fields"] if f["field_name"] == "location_indicator"
            )

            accept = client.post(
                f"/api/v1/extraction/fields/{field_id}/accept",
                headers=headers,
                json={},
            )
            assert accept.status_code == 200
            assert accept.json()["accepted_by_id"] is not None

            rerun = client.post(
                f"/api/v1/requests/{request_id}/extraction/rerun", headers=headers
            )
            assert rerun.status_code == 200
            assert rerun.json()["status"] == "succeeded"
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_preview_extraction_reads_a_photo_without_creating_a_request(tmp_path, monkeypatch) -> None:
    """The point of /extraction/preview: an officer photographs a hard-copy
    GCAA-AIS-NTM-FR01 and gets field candidates back before a NotamRequest
    exists at all -- no Attachment, no ExtractionRun, nothing persisted."""
    engine = _prepare_client(tmp_path, monkeypatch, extraction_enabled=True)
    try:
        with TestClient(app) as client:
            headers = _login(client)
            form_text = (
                "Location: DGAA\n"
                "New\n"
                "Name: Ghana Airports Company\n"
                "Organisation: GCAA AIS\n"
                "Full Text\n"
                "Taxiway M closed due to work in progress.\n"
                "Lower Limit\nSFC\n"
                "Upper Limit\nUNL\n"
            )
            pdf_bytes = _build_pdf(form_text)

            preview = client.post(
                "/api/v1/extraction/preview",
                headers=headers,
                files={"file": ("hardcopy.pdf", pdf_bytes, "application/pdf")},
            )
            assert preview.status_code == 200
            body = preview.json()
            assert body["page_count"] == 1
            field_names = {f["field_name"] for f in body["fields"]}
            assert "location_indicator" in field_names
            assert "originator_name" in field_names
            location = next(f for f in body["fields"] if f["field_name"] == "location_indicator")
            assert location["normalized_value"] == "DGAA"

            # Nothing was persisted -- no request, no attachment, no run.
            requests = client.get("/api/v1/requests", headers=headers).json()
            assert requests == []
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_preview_extraction_returns_409_when_disabled(tmp_path, monkeypatch) -> None:
    engine = _prepare_client(tmp_path, monkeypatch, extraction_enabled=False)
    try:
        with TestClient(app) as client:
            headers = _login(client)
            pdf_bytes = _build_pdf("Location: DGAA")
            preview = client.post(
                "/api/v1/extraction/preview",
                headers=headers,
                files={"file": ("hardcopy.pdf", pdf_bytes, "application/pdf")},
            )
            assert preview.status_code == 409
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_qcode_suggestions_ranks_matching_rule_first(tmp_path, monkeypatch) -> None:
    """Covers both the manually-typed and OCR-seeded Item E paths uniformly
    -- this endpoint works off whatever narrative text is currently in the
    form, not just an original upload, so it also applies to requests (like
    hand-delivered ones) that never went through /extraction/preview."""
    engine = _prepare_client(tmp_path, monkeypatch, extraction_enabled=True)
    try:
        with TestClient(app) as client:
            headers = _login(client)
            response = client.post(
                "/api/v1/rules/qcode-suggestions",
                headers=headers,
                json={"narrative": "Taxiway A1 closed due wip"},
            )
            assert response.status_code == 200
            suggestions = response.json()
            assert suggestions
            assert suggestions[0]["q_code"] == "QMXLC"
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_upload_does_not_extract_when_disabled(tmp_path, monkeypatch) -> None:
    engine = _prepare_client(tmp_path, monkeypatch, extraction_enabled=False)
    try:
        with TestClient(app) as client:
            headers = _login(client)
            request_id = client.post(
                "/api/v1/requests",
                headers=headers,
                json={
                    "source": "portal",
                    "originator_name": "Ghana Airports Company",
                    "location_indicator": "DGAA",
                    "raw_text": "Taxiway M closed for scheduled maintenance.",
                },
            ).json()["id"]

            pdf_bytes = _build_pdf("Location: DGAA Full Text Taxiway M closed for maintenance.")
            upload = client.post(
                f"/api/v1/requests/{request_id}/attachments",
                headers=headers,
                files={"file": ("request-form.pdf", pdf_bytes, "application/pdf")},
            )
            assert upload.status_code == 201

            extraction = client.get(f"/api/v1/requests/{request_id}/extraction", headers=headers)
            assert extraction.status_code == 200
            assert extraction.json() is None

            rerun = client.post(
                f"/api/v1/requests/{request_id}/extraction/rerun", headers=headers
            )
            assert rerun.status_code == 409
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())
