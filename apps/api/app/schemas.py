import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import (
    ExtractionStatus,
    ExtractorKind,
    NotamKind,
    NotamSeries,
    RequestSource,
    Role,
    WorkflowStatus,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserRead(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    organization: str | None
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    role: Role
    organization: str | None = Field(default=None, max_length=200)
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    role: Role | None = None
    is_active: bool | None = None


class BrandingRead(BaseModel):
    org_name: str
    org_subtitle: str
    description: str | None
    logo_url: str | None


class BrandingUpdate(BaseModel):
    org_name: str | None = Field(default=None, min_length=1, max_length=80)
    org_subtitle: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserRead


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class NotamRequestCreate(BaseModel):
    source: RequestSource = RequestSource.PORTAL
    originator_name: str = Field(min_length=2, max_length=200)
    originator_email: EmailStr | None = None
    originator_reference: str | None = Field(default=None, max_length=120)
    location_indicator: str = Field(min_length=4, max_length=4)
    raw_text: str = Field(min_length=5, max_length=20_000)
    requested_series: NotamSeries | None = None
    safety_critical: bool = False

    @field_validator("location_indicator")
    @classmethod
    def normalize_location(cls, value: str) -> str:
        value = value.upper().strip()
        if not value.isalpha():
            raise ValueError("Location indicator must contain four letters")
        return value


class RequestRead(ORMModel):
    id: uuid.UUID
    request_number: str
    source: RequestSource
    status: WorkflowStatus
    originator_name: str
    originator_email: str | None
    originator_reference: str | None
    location_indicator: str
    raw_text: str
    requested_series: NotamSeries | None
    safety_critical: bool
    acknowledgement_sent_at: datetime | None
    extracted_data: dict[str, Any]
    extraction_confidence: int | None
    assigned_to_id: uuid.UUID | None
    received_at: datetime
    updated_at: datetime


class QLineInput(BaseModel):
    fir: str = Field(default="DGAC", min_length=4, max_length=4)
    q_code: str = Field(min_length=5, max_length=5, pattern=r"^Q[A-Z]{4}$")
    traffic: str = Field(min_length=1, max_length=2)
    purpose: str = Field(min_length=1, max_length=3)
    scope: str = Field(min_length=1, max_length=2)
    lower_limit: str = Field(default="000", pattern=r"^\d{3}$")
    upper_limit: str = Field(default="999", pattern=r"^\d{3}$")
    coordinates_radius: str = Field(pattern=r"^\d{4}[NS]\d{5}[EW]\d{3}$")


class NotamDraftCreate(QLineInput):
    series: NotamSeries
    kind: NotamKind
    replaces_notam_id: uuid.UUID | None = None
    item_a: str = Field(min_length=4, max_length=8)
    item_b: datetime
    item_c: datetime | None = None
    item_c_qualifier: str | None = Field(default=None, pattern=r"^(EST|PERM)?$")
    item_d: str | None = None
    item_e: str = Field(min_length=3, max_length=1000)
    item_f: str | None = Field(default=None, max_length=40)
    item_g: str | None = Field(default=None, max_length=40)


class NotamRead(ORMModel):
    id: uuid.UUID
    request_id: uuid.UUID
    series: NotamSeries
    kind: NotamKind
    serial_number: int
    year: int
    fir: str
    q_code: str
    traffic: str
    purpose: str
    scope: str
    lower_limit: str
    upper_limit: str
    coordinates_radius: str
    item_a: str
    item_b: datetime
    item_c: datetime | None
    item_c_qualifier: str | None
    item_d: str | None
    item_e: str
    item_f: str | None
    item_g: str | None
    formatted_message: str
    aixm_payload: dict[str, Any] | None
    aixm_xml: str | None
    validation_result: dict[str, Any]
    ruleset_version: str
    approved_by_id: uuid.UUID | None
    approved_at: datetime | None
    published_at: datetime | None


class AttachmentRead(ORMModel):
    id: uuid.UUID
    request_id: uuid.UUID
    filename: str
    media_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


class ExtractedFieldRead(ORMModel):
    id: uuid.UUID
    run_id: uuid.UUID
    field_name: str
    raw_text: str | None
    normalized_value: str | None
    confidence: int
    page: int | None
    extractor: ExtractorKind
    accepted_by_id: uuid.UUID | None
    accepted_at: datetime | None


class ExtractionRunRead(ORMModel):
    id: uuid.UUID
    attachment_id: uuid.UUID
    engine: str
    status: ExtractionStatus
    page_count: int | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    fields: list[ExtractedFieldRead] = []


class FieldAcceptRequest(BaseModel):
    value: str | None = Field(default=None, max_length=2000)


class FirRead(ORMModel):
    id: uuid.UUID
    icao_code: str
    name: str
    provenance: str


class AerodromeRead(ORMModel):
    id: uuid.UUID
    icao_code: str
    iata_code: str | None
    name: str
    fir_id: uuid.UUID | None
    arp_latitude: float | None
    arp_longitude: float | None
    elevation_ft: int | None
    provenance: str


class AipDatasetRead(ORMModel):
    id: uuid.UUID
    version: str
    source: str
    effective_date: datetime | None
    checksum: str
    active: bool
    created_at: datetime


class PublicationDeliveryRead(ORMModel):
    id: uuid.UUID
    notam_id: uuid.UUID
    channel: str
    destination: str
    status: str
    external_reference: str | None
    attempted_at: datetime | None
    acknowledged_at: datetime | None
    response_payload: dict[str, Any]


class RuleVersionRead(ORMModel):
    id: uuid.UUID
    version: str
    source_document: str
    source_revision: str
    checksum: str
    verified_rule_count: int
    total_rule_count: int
    notes: str | None
    active: bool
    approved_by_id: uuid.UUID
    approved_at: datetime


class ReviewAction(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


class ValidationRequest(BaseModel):
    subject: str | None = None
    condition: str | None = None
    q_code: str | None = Field(default=None, pattern=r"^Q[A-Z]{4}$")
    traffic: str
    purpose: str
    scope: str
    kind: NotamKind = NotamKind.NEW

    @model_validator(mode="after")
    def check_subject_source(self) -> "ValidationRequest":
        if not self.q_code and not (self.subject and self.condition):
            raise ValueError("Provide either q_code or both subject and condition")
        return self


class DashboardSummary(BaseModel):
    requests_in_queue: int
    awaiting_specialist: int
    published_today: int
    estimated_due: int
    first_pass_quality: float
