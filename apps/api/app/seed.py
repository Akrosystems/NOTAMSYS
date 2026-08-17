import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import settings
from app.core.database import Base, SessionFactory, engine
from app.core.security import hash_password
from app.models import (
    Aerodrome,
    AipDataset,
    Fir,
    NotamRequest,
    NotamSeries,
    RequestSource,
    Role,
    RuleVersion,
    User,
    WorkflowStatus,
)
from app.services.aip.loader import canonical_checksum as aip_checksum
from app.services.aip.loader import load_dataset_payload as load_aip_payload
from app.services.rules import RULESET_VERSION, canonical_checksum, load_dataset_payload

USERS = (
    ("officer@notamsys.app", "Eric Armah", Role.AIS_OFFICER),
    ("specialist@notamsys.app", "Josephine Appiah", Role.AIS_SPECIALIST),
    ("manager@notamsys.app", "Fidelia Kwei-Kumah", Role.NOF_MANAGER),
    ("qms@notamsys.app", "Nana Mensah", Role.QMS_AUDITOR),
    ("admin@notamsys.app", "System Administrator", Role.SYSTEM_ADMIN),
)


async def seed() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with SessionFactory() as session:
        existing = await session.scalar(select(User).limit(1))
        if existing:
            return
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

        aip_payload = load_aip_payload()
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
                    name=row["name"],
                    fir_id=firs_by_code[row["fir_code"]].id if row.get("fir_code") else None,
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
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
