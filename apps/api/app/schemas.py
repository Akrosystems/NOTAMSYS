import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import (
    ExtractionStatus,
    ExtractorKind,
    LimitType,
    LocationType,
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


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenRead(BaseModel):
    access_token: str
    token_type: str = "bearer"


class NotamRequestCreate(BaseModel):
    """Mirrors GCAA-AIS-NTM-FR01 (NOTAM Request Form) field-for-field. See
    that form's Item A)-G) and the originator block at the bottom."""

    source: RequestSource = RequestSource.PORTAL
    originator_name: str = Field(min_length=2, max_length=200)
    originator_email: EmailStr | None = None
    originator_organisation: str | None = Field(default=None, max_length=200)
    originator_phone: str | None = Field(default=None, max_length=40)
    originator_reference: str | None = Field(default=None, max_length=120)
    # Item A)
    location_type: LocationType = LocationType.AD
    location_indicator: str = Field(min_length=1, max_length=60)
    # NOTAM N/R/C + the "NOTAM Series & No./Year" box next to R and C
    requested_kind: NotamKind = NotamKind.NEW
    referenced_notam_number: str | None = Field(default=None, max_length=40)
    # Item B)/C)
    start_at: datetime | None = None
    end_at: datetime | None = None
    end_confirmed: bool = False
    end_permanent: bool = False
    end_estimated: bool = False
    # Item D) (optional)
    periods_of_activity: str | None = Field(default=None, max_length=2000)
    # Item E) -- "Full Text" for New/Replacement or "First Line" for Cancel
    raw_text: str = Field(min_length=5, max_length=20_000)
    # Items F)/G) (optional)
    lower_limit_sfc: bool = False
    lower_limit_value: str | None = Field(default=None, max_length=10)
    lower_limit_type: LimitType | None = None
    upper_limit_unl: bool = False
    upper_limit_value: str | None = Field(default=None, max_length=10)
    upper_limit_type: LimitType | None = None
    requested_series: NotamSeries | None = None
    safety_critical: bool = False

    @field_validator("location_indicator")
    @classmethod
    def normalize_location(cls, value: str) -> str:
        return value.upper().strip()

    @model_validator(mode="after")
    def check_location_format(self) -> "NotamRequestCreate":
        # Only AD/FIR are ICAO 4-letter indicators; Airspace names are
        # free text on the paper form (e.g. "Accra TMA").
        if self.location_type in {LocationType.AD, LocationType.FIR} and (
            len(self.location_indicator) != 4 or not self.location_indicator.isalpha()
        ):
            raise ValueError(f"{self.location_type.value} location must be a 4-letter ICAO indicator")
        return self

    @model_validator(mode="after")
    def check_reference_required_for_replace_cancel(self) -> "NotamRequestCreate":
        if self.requested_kind in {NotamKind.REPLACE, NotamKind.CANCEL} and not self.referenced_notam_number:
            raise ValueError("Replace/Cancel requests must reference the NOTAM series & number/year being actioned")
        return self


class RequestRead(ORMModel):
    id: uuid.UUID
    request_number: str
    source: RequestSource
    status: WorkflowStatus
    originator_name: str
    originator_email: str | None
    originator_organisation: str | None
    originator_phone: str | None
    originator_reference: str | None
    location_type: LocationType
    location_indicator: str
    requested_kind: NotamKind
    referenced_notam_number: str | None
    start_at: datetime | None
    end_at: datetime | None
    end_confirmed: bool
    end_permanent: bool
    end_estimated: bool
    periods_of_activity: str | None
    raw_text: str
    lower_limit_sfc: bool
    lower_limit_value: str | None
    lower_limit_type: LimitType | None
    upper_limit_unl: bool
    upper_limit_value: str | None
    upper_limit_type: LimitType | None
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
    aip_supplement_reference: str | None = Field(default=None, max_length=80)


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
    aip_supplement_reference: str | None
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


class ExtractionPreviewField(BaseModel):
    field_name: str
    raw_text: str
    normalized_value: str | None
    confidence: int
    extractor: str
    page: int


class ExtractionPreviewResult(BaseModel):
    """Response for POST /extraction/preview -- a stateless read of a
    not-yet-submitted photo/scan, so an officer can pre-fill the intake
    form from a hard-copy GCAA-AIS-NTM-FR01 before creating the request.
    Nothing here is persisted (no Attachment, no ExtractionRun): the file
    is uploaded and extracted again for the permanent audit record once
    the officer actually submits, exactly as it already was before this
    endpoint existed."""

    fields: list[ExtractionPreviewField]
    page_count: int
    q_code_suggestions: list[dict[str, object]]


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


class AftnOutboxItem(ORMModel):
    """One pending AFTN envelope for app/aftn_bridge.py to pick up and hand
    to the real Comsoft/CADAS terminal. See docs/AFTN_BRIDGE.md."""

    id: uuid.UUID
    outbound_body: str


class AftnAckRequest(BaseModel):
    external_reference: str = Field(min_length=1, max_length=200)


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
