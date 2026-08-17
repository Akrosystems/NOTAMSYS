import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Role(str, enum.Enum):
    ORIGINATOR = "originator"
    AIS_OFFICER = "ais_officer"
    AIS_SPECIALIST = "ais_specialist"
    NOF_MANAGER = "nof_manager"
    QMS_AUDITOR = "qms_auditor"
    SYSTEM_ADMIN = "system_admin"


class RequestSource(str, enum.Enum):
    PORTAL = "portal"
    EMAIL = "email"
    AFTN = "aftn"
    UPLOAD = "upload"
    HAND_DELIVERY = "hand_delivery"
    RAW_TEXT = "raw_text"


class WorkflowStatus(str, enum.Enum):
    RECEIVED = "received"
    TRIAGE = "triage"
    DRAFT = "draft"
    REVIEW = "review"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class NotamSeries(str, enum.Enum):
    A = "A"
    B = "B"


class NotamKind(str, enum.Enum):
    NEW = "NOTAMN"
    REPLACE = "NOTAMR"
    CANCEL = "NOTAMC"


class ExtractionStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ExtractorKind(str, enum.Enum):
    REGEX = "regex"
    GRAMMAR = "grammar"
    MODEL = "model"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    role: Mapped[Role] = mapped_column(Enum(Role, name="user_role"), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    organization: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NotamRequest(Base):
    __tablename__ = "notam_requests"
    __table_args__ = (Index("ix_notam_requests_status_received", "status", "received_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    request_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    source: Mapped[RequestSource] = mapped_column(Enum(RequestSource, name="request_source"))
    status: Mapped[WorkflowStatus] = mapped_column(
        Enum(WorkflowStatus, name="workflow_status"), default=WorkflowStatus.RECEIVED, index=True
    )
    originator_name: Mapped[str] = mapped_column(String(200))
    originator_email: Mapped[str | None] = mapped_column(String(320))
    originator_reference: Mapped[str | None] = mapped_column(String(120))
    location_indicator: Mapped[str] = mapped_column(String(4), index=True)
    raw_text: Mapped[str] = mapped_column(Text)
    requested_series: Mapped[NotamSeries | None] = mapped_column(
        Enum(NotamSeries, name="notam_series")
    )
    safety_critical: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    acknowledgement_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extracted_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    extraction_confidence: Mapped[int | None] = mapped_column(Integer)
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    assigned_to: Mapped[User | None] = relationship(foreign_keys=[assigned_to_id])
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )
    notam: Mapped["Notam | None"] = relationship(back_populates="request", uselist=False)


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notam_requests.id", ondelete="CASCADE")
    )
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    request: Mapped[NotamRequest] = relationship(back_populates="attachments")


class Notam(Base):
    __tablename__ = "notams"
    __table_args__ = (
        Index("uq_notams_series_number_year", "series", "serial_number", "year", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notam_requests.id", ondelete="CASCADE"), unique=True
    )
    series: Mapped[NotamSeries] = mapped_column(Enum(NotamSeries, name="notam_series"))
    kind: Mapped[NotamKind] = mapped_column(Enum(NotamKind, name="notam_kind"))
    serial_number: Mapped[int] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer)
    replaces_notam_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("notams.id"))
    fir: Mapped[str] = mapped_column(String(4), default="DGAC")
    q_code: Mapped[str] = mapped_column(String(5))
    traffic: Mapped[str] = mapped_column(String(2))
    purpose: Mapped[str] = mapped_column(String(3))
    scope: Mapped[str] = mapped_column(String(2))
    lower_limit: Mapped[str] = mapped_column(String(3), default="000")
    upper_limit: Mapped[str] = mapped_column(String(3), default="999")
    coordinates_radius: Mapped[str] = mapped_column(String(15))
    item_a: Mapped[str] = mapped_column(String(8))
    item_b: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    item_c: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    item_c_qualifier: Mapped[str | None] = mapped_column(String(4))
    item_d: Mapped[str | None] = mapped_column(Text)
    item_e: Mapped[str] = mapped_column(Text)
    item_f: Mapped[str | None] = mapped_column(String(40))
    item_g: Mapped[str | None] = mapped_column(String(40))
    formatted_message: Mapped[str] = mapped_column(Text)
    aixm_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Real, namespaced AIXM 5.1.1 Event XML (services/aixm/builder.py) --
    # aixm_payload above stays a lightweight dict for UI summaries.
    aixm_xml: Mapped[str | None] = mapped_column(Text)
    validation_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ruleset_version: Mapped[str] = mapped_column(String(40), default="8126-2022.2")
    prepared_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    request: Mapped[NotamRequest] = relationship(back_populates="notam")
    prepared_by: Mapped[User] = relationship(foreign_keys=[prepared_by_id])
    approved_by: Mapped[User | None] = relationship(foreign_keys=[approved_by_id])

    @property
    def identifier(self) -> str:
        return f"{self.series.value}{self.serial_number:04d}/{self.year % 100:02d}"


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_entity", "entity_type", "entity_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID] = mapped_column(index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    from_state: Mapped[str | None] = mapped_column(String(40))
    to_state: Mapped[str | None] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    actor: Mapped[User] = relationship()


class PublicationDelivery(Base):
    __tablename__ = "publication_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    notam_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("notams.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(40))
    destination: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    external_reference: Mapped[str | None] = mapped_column(String(200))
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    attachment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("attachments.id", ondelete="CASCADE"), index=True
    )
    engine: Mapped[str] = mapped_column(String(40))
    engine_version: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[ExtractionStatus] = mapped_column(
        Enum(ExtractionStatus, name="extraction_status"),
        default=ExtractionStatus.PENDING,
        index=True,
    )
    page_count: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    attachment: Mapped[Attachment] = relationship()
    fields: Mapped[list["ExtractedField"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class ExtractedField(Base):
    __tablename__ = "extracted_fields"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extraction_runs.id", ondelete="CASCADE"), index=True
    )
    field_name: Mapped[str] = mapped_column(String(60))
    raw_text: Mapped[str | None] = mapped_column(Text)
    normalized_value: Mapped[str | None] = mapped_column(Text)
    # 0-100. Deliberately never treated as "auto-accept" -- see
    # services/extraction/pipeline.py -- a human always confirms a field
    # before it can influence a NOTAM draft.
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    page: Mapped[int | None] = mapped_column(Integer)
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    extractor: Mapped[ExtractorKind] = mapped_column(Enum(ExtractorKind, name="extractor_kind"))
    accepted_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[ExtractionRun] = relationship(back_populates="fields")


class RuleVersion(Base):
    __tablename__ = "rule_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(String(40), unique=True)
    source_document: Mapped[str] = mapped_column(String(200))
    # Text, not a short varchar: in practice this holds a full provenance
    # note (what was transcribed/verified and when), not a short tag like
    # "Rev 3" -- SQLite never enforces VARCHAR(80) so this went unnoticed
    # until run against real Postgres.
    source_revision: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64))
    rules: Mapped[dict[str, Any]] = mapped_column(JSON)
    verified_rule_count: Mapped[int] = mapped_column(Integer, default=0)
    total_rule_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    approved_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OrgSettings(Base):
    """Singleton row (the app always fetches-or-creates the first one, see
    _get_org_settings in api/router.py) holding admin-editable platform
    branding. Deliberately separate from Settings in core/config.py, which
    is env-var-based and immutable at runtime -- this is the one piece of
    genuinely live, DB-backed, admin-editable configuration."""

    __tablename__ = "org_settings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_name: Mapped[str] = mapped_column(String(80), default="NOTAMSYS")
    org_subtitle: Mapped[str] = mapped_column(String(120), default="Accra NOF")
    description: Mapped[str | None] = mapped_column(Text)
    logo_object_key: Mapped[str | None] = mapped_column(String(255))
    logo_media_type: Mapped[str | None] = mapped_column(String(100))
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AipDataset(Base):
    """A versioned batch of AIP-derived reference data (FIRs, aerodromes,
    runways). Exactly one dataset is `active` at a time -- see
    services/aip/. Records within it carry their own `provenance` because a
    dataset can mix genuinely AIP-sourced facts with unverified seed
    placeholders; never assume everything in an active dataset is
    equally authoritative."""

    __tablename__ = "aip_datasets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(String(40), unique=True)
    source: Mapped[str] = mapped_column(String(40))  # "seed" | "eaip" | "aixm"
    effective_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checksum: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Fir(Base):
    __tablename__ = "firs"
    __table_args__ = (Index("uq_firs_dataset_icao", "dataset_id", "icao_code", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("aip_datasets.id", ondelete="CASCADE"), index=True
    )
    icao_code: Mapped[str] = mapped_column(String(4))
    name: Mapped[str] = mapped_column(String(200))
    # Where this fact came from -- e.g. "existing seed data" vs a real AIP
    # citation. Never fabricated; null coordinates elsewhere in this module
    # follow the same "null over invented" rule this field documents.
    provenance: Mapped[str] = mapped_column(String(200))


class Aerodrome(Base):
    __tablename__ = "aerodromes"
    __table_args__ = (
        Index("uq_aerodromes_dataset_icao", "dataset_id", "icao_code", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("aip_datasets.id", ondelete="CASCADE"), index=True
    )
    icao_code: Mapped[str] = mapped_column(String(4), index=True)
    iata_code: Mapped[str | None] = mapped_column(String(3))
    name: Mapped[str] = mapped_column(String(200))
    fir_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("firs.id"))
    # ARP = aerodrome reference point. Left null rather than guessed when a
    # real AIP source isn't available -- see docs/reference and the AIP
    # access note in project memory.
    arp_latitude: Mapped[float | None] = mapped_column()
    arp_longitude: Mapped[float | None] = mapped_column()
    elevation_ft: Mapped[int | None] = mapped_column(Integer)
    provenance: Mapped[str] = mapped_column(String(200))

    fir: Mapped[Fir | None] = relationship()


class Runway(Base):
    __tablename__ = "runways"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    aerodrome_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("aerodromes.id", ondelete="CASCADE"), index=True
    )
    designator: Mapped[str] = mapped_column(String(10))  # e.g. "03/21"
    length_ft: Mapped[int | None] = mapped_column(Integer)
    provenance: Mapped[str] = mapped_column(String(200))


class AirspaceRef(Base):
    __tablename__ = "airspace_refs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("aip_datasets.id", ondelete="CASCADE"), index=True
    )
    designator: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(40))  # e.g. "CTR", "TMA", "FIR"
    fir_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("firs.id"))
    provenance: Mapped[str] = mapped_column(String(200))
