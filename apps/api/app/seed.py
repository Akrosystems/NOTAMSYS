import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import Base, SessionFactory, engine
from app.core.security import hash_password
from app.models import (
    Aerodrome,
    AipDataset,
    Fir,
    Notam,
    NotamKind,
    NotamRequest,
    NotamSeries,
    RequestSource,
    Role,
    RuleVersion,
    User,
    WorkflowStatus,
)
from app.schemas import NotamDraftCreate
from app.services.aip.loader import canonical_checksum as aip_checksum
from app.services.aip.loader import load_dataset_payload as load_aip_payload
from app.services.aixm.builder import build_event_xml
from app.services.formatter import build_aixm_event, format_notam
from app.services.rules import (
    RULESET_VERSION,
    canonical_checksum,
    load_dataset_payload,
    validate_selection,
)
from app.services.workflow import audit, next_serial

USERS = (
    ("officer@notamsys.app", "Eric Armah", Role.AIS_OFFICER),
    ("specialist@notamsys.app", "Josephine Appiah", Role.AIS_SPECIALIST),
    ("manager@notamsys.app", "Fidelia Kwei-Kumah", Role.NOF_MANAGER),
    ("qms@notamsys.app", "Nana Mensah", Role.QMS_AUDITOR),
    ("admin@notamsys.app", "System Administrator", Role.SYSTEM_ADMIN),
)

# Each sample NotamRequest below that starts life in REVIEW/CHANGES_REQUESTED
# status needs a matching prepared Notam -- otherwise a specialist opening it
# sees "No NOTAM has been prepared for this request yet" with nothing to
# review, even though the workflow claims one is pending their approval.
# Both drafts reuse Q-code/traffic/purpose/scope combinations already
# verified against the real ruleset (see tests/test_workflow_api.py and
# tests/test_rules.py) rather than inventing new ones.
SAMPLE_NOTAM_DRAFTS = {
    "REQ-0826-046": NotamDraftCreate(
        series=NotamSeries.A,
        kind=NotamKind.NEW,
        fir="DGAC",
        q_code="QMXLC",
        traffic="IV",
        purpose="BO",
        scope="A",
        lower_limit="000",
        upper_limit="999",
        coordinates_radius="0536N00010W005",
        item_a="DGAA",
        item_b=datetime(2026, 8, 17, 6, 0, tzinfo=UTC),
        item_c=datetime(2026, 8, 20, 18, 0, tzinfo=UTC),
        item_e="TWY M CLOSED DUE WIP.",
    ),
    "REQ-0826-045": NotamDraftCreate(
        series=NotamSeries.B,
        kind=NotamKind.NEW,
        fir="DGAC",
        q_code="QMRLC",
        traffic="IV",
        purpose="NBO",
        scope="A",
        lower_limit="000",
        upper_limit="999",
        coordinates_radius="0933N00052W005",
        item_a="DGLE",
        item_b=datetime(2026, 8, 17, 6, 0, tzinfo=UTC),
        item_c=datetime(2026, 8, 24, 18, 0, tzinfo=UTC),
        item_e="RWY 05/23 STRIP WORK IN PROGRESS.",
    ),
}


async def seed() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with SessionFactory() as session:
        existing = await session.scalar(select(User).limit(1))
        if not existing:
            await _seed_users_and_reference_data(session)
        # Independently idempotent, not gated behind `existing` -- so a second
        # `python -m app.seed` run against an already-seeded database (e.g.
        # backfilling production after datasets or functions were added) still
        # fills these in instead of being a permanent no-op.
        await _seed_aip_reference_data(session)
        await _seed_sample_notam_drafts(session)
        await _seed_email_intake_user(session)
        await session.commit()


async def _seed_aip_reference_data(session: AsyncSession) -> None:
    aip_payload = load_aip_payload("ghana_aip_2026.json")
    version = aip_payload["version"]
    existing = await session.scalar(select(AipDataset).where(AipDataset.version == version))
    if existing and existing.active:
        return

    # Deactivate older datasets
    all_datasets = (await session.scalars(select(AipDataset))).all()
    for ds in all_datasets:
        ds.active = False

    if existing:
        existing.active = True
        await session.flush()
        return

    aip_dataset = AipDataset(
        version=version,
        source=aip_payload["source"],
        checksum=aip_checksum(aip_payload),
        active=True,
    )
    session.add(aip_dataset)
    await session.flush()

    firs_by_code: dict[str, Fir] = {}
    for row in aip_payload["firs"]:
        fir = Fir(
            dataset_id=aip_dataset.id,
            icao_code=row["icao_code"],
            name=row["name"],
            provenance=row["provenance"],
        )
        session.add(fir)
        firs_by_code[row["icao_code"]] = fir
    await session.flush()

    for row in aip_payload["aerodromes"]:
        session.add(
            Aerodrome(
                dataset_id=aip_dataset.id,
                icao_code=row["icao_code"],
                iata_code=row.get("iata_code"),
                name=row["name"],
                fir_id=firs_by_code[row["fir_code"]].id if row.get("fir_code") else None,
                arp_latitude=row.get("arp_latitude"),
                arp_longitude=row.get("arp_longitude"),
                elevation_ft=row.get("elevation_ft"),
                provenance=row["provenance"],
            )
        )
    await session.flush()


async def _seed_users_and_reference_data(session: AsyncSession) -> None:
    records = [
        User(
            email=email,
            full_name=name,
            role=role,
            password_hash=hash_password("Notamsys!2026"),
            organization="GCAA AIS",
        )
        for email, name, role in USERS
    ]
    portal_user = User(
        email=settings.public_portal_email,
        full_name="Public Portal Service",
        role=Role.ORIGINATOR,
        # Random, never communicated -- this account exists only so
        # anonymous public submissions have a created_by_id to point to;
        # it is never meant to be logged into interactively.
        password_hash=hash_password(uuid.uuid4().hex + uuid.uuid4().hex),
        organization="GCAA public portal",
    )
    records.append(portal_user)
    session.add_all(records)
    await session.flush()

    nof_manager = next(record for record in records if record.role == Role.NOF_MANAGER)
    dataset = load_dataset_payload()
    rule_rows = dataset["rules"]
    verified = sum(
        1
        for row in rule_rows
        if row.get("verification_status") in {"HAND_CURATED", "VERIFIED_VISUAL"}
    )
    session.add(
        RuleVersion(
            version=RULESET_VERSION,
            source_document=dataset["source_document"],
            source_revision=dataset["source_revision"],
            checksum=canonical_checksum(dataset),
            rules=dataset,
            verified_rule_count=verified,
            total_rule_count=len(rule_rows),
            active=True,
            approved_by_id=nof_manager.id,
        )
    )

    aip_payload = load_aip_payload("ghana_aip_2026.json")
    aip_dataset = AipDataset(
        version=aip_payload["version"],
        source=aip_payload["source"],
        checksum=aip_checksum(aip_payload),
        active=True,
    )
    session.add(aip_dataset)
    await session.flush()
    firs_by_code: dict[str, Fir] = {}
    for row in aip_payload["firs"]:
        fir = Fir(
            dataset_id=aip_dataset.id,
            icao_code=row["icao_code"],
            name=row["name"],
            provenance=row["provenance"],
        )
        session.add(fir)
        firs_by_code[row["icao_code"]] = fir
    await session.flush()
    for row in aip_payload["aerodromes"]:
        session.add(
            Aerodrome(
                dataset_id=aip_dataset.id,
                icao_code=row["icao_code"],
                iata_code=row.get("iata_code"),
                name=row["name"],
                fir_id=firs_by_code[row["fir_code"]].id if row.get("fir_code") else None,
                arp_latitude=row.get("arp_latitude"),
                arp_longitude=row.get("arp_longitude"),
                elevation_ft=row.get("elevation_ft"),
                provenance=row["provenance"],
            )
        )

    now = datetime.now(UTC)
    samples = [
        NotamRequest(
            request_number="REQ-0826-047",
            source=RequestSource.EMAIL,
            status=WorkflowStatus.DRAFT,
            originator_name="AFRIQIYAH Operations",
            originator_email="ops@example.com",
            originator_reference="OPS/NTM/0826/17",
            location_indicator="DGAC",
            raw_text="Temporary restricted area due unmanned aircraft flight.",
            requested_series=NotamSeries.A,
            assigned_to_id=records[0].id,
            created_by_id=records[0].id,
            received_at=now - timedelta(minutes=14),
        ),
        NotamRequest(
            request_number="REQ-0826-046",
            source=RequestSource.UPLOAD,
            status=WorkflowStatus.REVIEW,
            originator_name="Ghana Airports Company",
            location_indicator="DGAA",
            raw_text="Taxiway M closed due to work in progress.",
            requested_series=NotamSeries.A,
            assigned_to_id=records[0].id,
            created_by_id=records[0].id,
            received_at=now - timedelta(minutes=25),
        ),
        NotamRequest(
            request_number="REQ-0826-045",
            source=RequestSource.PORTAL,
            status=WorkflowStatus.CHANGES_REQUESTED,
            originator_name="Tamale Airport",
            location_indicator="DGLE",
            raw_text="Work in progress on runway 05/23 strip.",
            requested_series=NotamSeries.B,
            assigned_to_id=records[0].id,
            created_by_id=records[0].id,
            received_at=now - timedelta(minutes=41),
        ),
    ]
    session.add_all(samples)
    await session.flush()


async def _seed_sample_notam_drafts(session: AsyncSession) -> None:
    officer = await session.scalar(select(User).where(User.email == "officer@notamsys.app"))
    specialist = await session.scalar(select(User).where(User.email == "specialist@notamsys.app"))
    if officer is None or specialist is None:
        # No seeded users to attribute this to -- nothing to backfill yet.
        return

    for request_number, draft in SAMPLE_NOTAM_DRAFTS.items():
        request = await session.scalar(
            select(NotamRequest)
            .where(NotamRequest.request_number == request_number)
            .options(selectinload(NotamRequest.notam))
        )
        if request is None or request.notam is not None:
            continue

        validation = validate_selection(
            draft.q_code[1:3], draft.q_code[3:5], draft.traffic, draft.purpose, draft.scope, draft.kind
        )
        year = draft.item_b.year
        serial = await next_serial(session, draft.series.value, year)
        identifier = f"{draft.series.value}{serial:04d}/{year % 100:02d}"
        notam = Notam(
            request_id=request.id,
            series=draft.series,
            kind=draft.kind,
            serial_number=serial,
            year=year,
            prepared_by_id=officer.id,
            fir=draft.fir,
            q_code=draft.q_code,
            traffic=draft.traffic,
            purpose=draft.purpose,
            scope=draft.scope,
            lower_limit=draft.lower_limit,
            upper_limit=draft.upper_limit,
            coordinates_radius=draft.coordinates_radius,
            item_a=draft.item_a,
            item_b=draft.item_b,
            item_c=draft.item_c,
            item_c_qualifier=draft.item_c_qualifier,
            item_d=draft.item_d,
            item_e=draft.item_e.upper(),
            item_f=draft.item_f,
            item_g=draft.item_g,
            aip_supplement_reference=draft.aip_supplement_reference,
            formatted_message=format_notam(draft, serial, year),
            validation_result=validation,
            ruleset_version=RULESET_VERSION,
            aixm_payload=build_aixm_event(draft, identifier),
            aixm_xml=build_event_xml(draft, identifier),
        )
        session.add(notam)
        await session.flush()
        await audit(
            session,
            "notam",
            notam.id,
            "draft_saved",
            officer.id,
            payload={"identifier": identifier, "ruleset": RULESET_VERSION},
        )
        await audit(
            session,
            "notam_request",
            request.id,
            "submitted_for_review",
            officer.id,
            WorkflowStatus.DRAFT,
            WorkflowStatus.REVIEW,
        )
        if request.status == WorkflowStatus.CHANGES_REQUESTED:
            await audit(
                session,
                "notam_request",
                request.id,
                "changes_requested",
                specialist.id,
                WorkflowStatus.REVIEW,
                WorkflowStatus.CHANGES_REQUESTED,
                payload={"comment": "Confirm exact closure hours with Tamale ATC before resubmitting."},
            )


async def _seed_email_intake_user(session: AsyncSession) -> None:
    """app/email_poller.py attributes every request it ingests to this
    account, same reasoning as the public-portal service user above --
    never meant to be logged into interactively."""
    existing = await session.scalar(
        select(User).where(User.email == settings.email_intake_service_email)
    )
    if existing is not None:
        return
    session.add(
        User(
            email=settings.email_intake_service_email,
            full_name="Email Intake Service",
            role=Role.ORIGINATOR,
            password_hash=hash_password(uuid.uuid4().hex + uuid.uuid4().hex),
            organization="GCAA email intake",
        )
    )


if __name__ == "__main__":
    asyncio.run(seed())
