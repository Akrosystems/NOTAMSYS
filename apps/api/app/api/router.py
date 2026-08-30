import uuid
from dataclasses import asdict
from datetime import UTC, datetime, time
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_session
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.dependencies import get_current_user, require_roles, require_service_key
from app.models import (
    Aerodrome,
    Attachment,
    AuditEvent,
    ExtractedField,
    ExtractionRun,
    Fir,
    Notam,
    NotamKind,
    NotamRequest,
    NotamSeries,
    OrgSettings,
    PublicationDelivery,
    QCodeCorrection,
    RequestSource,
    Role,
    RuleVersion,
    User,
    WorkflowStatus,
)
from app.schemas import (
    AccessTokenRead,
    AerodromeRead,
    AftnAckRequest,
    AftnOutboxItem,
    AipDatasetRead,
    AttachmentRead,
    BrandingRead,
    BrandingUpdate,
    DashboardSummary,
    ExtractedFieldRead,
    ExtractionPreviewResult,
    ExtractionRunRead,
    FieldAcceptRequest,
    FirRead,
    LoginRequest,
    NotamDraftCreate,
    NotamRead,
    NotamRequestCreate,
    PublicationDeliveryRead,
    QCodeCorrectionCreate,
    QCodeCorrectionRead,
    QCodeSuggestionRequest,
    RefreshRequest,
    RequestRead,
    ReviewAction,
    RuleVersionRead,
    TokenPair,
    UserCreate,
    UserPresenceRead,
    UserRead,
    UserUpdate,
    ValidationRequest,
)
from app.services.aip.provider import default_provider
from app.services.extraction.narrative import suggest_q_codes
from app.services.extraction.ocr import build_engine
from app.services.extraction.orchestrator import run_extraction
from app.services.extraction.pipeline import run_pipeline
from app.services.publication.orchestrator import dispatch_delivery
from app.services.publication.registry import CHANNELS
from app.services.rules import canonical_checksum, get_catalog, reload_catalog, validate_selection
from app.services.storage import storage
from app.services.workflow import audit, create_draft, transition_request

router = APIRouter(prefix="/api/v1")
Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("/auth/login", response_model=TokenPair, tags=["authentication"])
async def login(payload: LoginRequest, session: Session) -> TokenPair:
    user = await session.scalar(select(User).where(User.email == payload.email.lower()))
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenPair(
        access_token=create_token(str(user.id)),
        refresh_token=create_token(str(user.id), "refresh"),
        user=UserRead.model_validate(user),
    )


@router.post("/auth/refresh", response_model=AccessTokenRead, tags=["authentication"])
async def refresh(payload: RefreshRequest, session: Session) -> AccessTokenRead:
    """Mints a new access token from a still-valid refresh token -- the
    piece that was missing entirely before: refresh tokens were issued at
    login and stored in a cookie, but nothing ever exchanged one for a new
    access token, so every session hard-expired after access_token_minutes
    (30 min) regardless of activity. Deliberately doesn't rotate the
    refresh token itself (no reuse-detection exists yet -- see
    docs/OPERATIONAL_BOUNDARY.md); it keeps its original 7-day expiry."""
    try:
        subject = decode_token(payload.refresh_token, expected_type="refresh")
        user = await session.get(User, uuid.UUID(subject))
    except (jwt.InvalidTokenError, ValueError):
        user = None
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return AccessTokenRead(access_token=create_token(str(user.id)))


@router.get("/auth/me", response_model=UserRead, tags=["authentication"])
async def me(user: CurrentUser) -> User:
    return user


def _notam_request_fields(payload: NotamRequestCreate) -> dict[str, object]:
    """Every NotamRequestCreate field that maps 1:1 onto a NotamRequest
    column, shared between the authenticated and public intake endpoints
    so the two paths can't silently drift out of field parity with each
    other (or with GCAA-AIS-NTM-FR01, which both replace)."""
    return {
        "originator_name": payload.originator_name,
        "originator_email": payload.originator_email if payload.originator_email else None,
        "originator_organisation": payload.originator_organisation,
        "originator_phone": payload.originator_phone,
        "originator_reference": payload.originator_reference,
        "location_type": payload.location_type,
        "location_indicator": payload.location_indicator,
        "requested_kind": payload.requested_kind,
        "referenced_notam_number": payload.referenced_notam_number,
        "start_at": payload.start_at,
        "end_at": payload.end_at,
        "end_confirmed": payload.end_confirmed,
        "end_permanent": payload.end_permanent,
        "end_estimated": payload.end_estimated,
        "periods_of_activity": payload.periods_of_activity,
        "raw_text": payload.raw_text,
        "lower_limit_sfc": payload.lower_limit_sfc,
        "lower_limit_value": payload.lower_limit_value,
        "lower_limit_type": payload.lower_limit_type,
        "upper_limit_unl": payload.upper_limit_unl,
        "upper_limit_value": payload.upper_limit_value,
        "upper_limit_type": payload.upper_limit_type,
        "requested_series": payload.requested_series,
        "safety_critical": payload.safety_critical,
    }


@router.post("/requests", response_model=RequestRead, status_code=201, tags=["requests"])
async def create_request(
    payload: NotamRequestCreate,
    session: Session,
    user: CurrentUser,
) -> NotamRequest:
    now = datetime.now(UTC)
    request = NotamRequest(
        request_number=f"REQ-{now:%y%m}-{uuid.uuid4().hex[:5].upper()}",
        source=payload.source,
        created_by_id=user.id,
        assigned_to_id=user.id if user.role == Role.AIS_OFFICER else None,
        **_notam_request_fields(payload),
    )
    session.add(request)
    await session.flush()
    await audit(session, "notam_request", request.id, "request_received", user.id)
    await session.commit()
    await session.refresh(request)
    return request


async def _get_portal_user(session: AsyncSession) -> User:
    portal_user = await session.scalar(
        select(User).where(User.email == settings.public_portal_email)
    )
    if portal_user is None:
        raise HTTPException(
            status_code=503,
            detail="Public intake is not available: the portal service account is not seeded",
        )
    return portal_user


@router.post("/public/requests", response_model=RequestRead, status_code=201, tags=["public"])
async def create_public_request(payload: NotamRequestCreate, session: Session) -> NotamRequest:
    """Unauthenticated intake for the public NOTAM request form. Attributed
    to a seeded service account (see _get_portal_user) rather than requiring
    created_by_id to be nullable across the whole model for one path. No
    rate limiting exists yet -- see docs/SECURITY.md."""
    if not settings.public_intake_enabled:
        raise HTTPException(status_code=503, detail="Public NOTAM request intake is disabled")
    portal_user = await _get_portal_user(session)
    now = datetime.now(UTC)
    request = NotamRequest(
        request_number=f"REQ-{now:%y%m}-{uuid.uuid4().hex[:5].upper()}",
        source=RequestSource.PORTAL,
        created_by_id=portal_user.id,
        **_notam_request_fields(payload),
    )
    session.add(request)
    await session.flush()
    await audit(
        session,
        "notam_request",
        request.id,
        "request_received",
        portal_user.id,
        payload={"channel": "public_portal"},
    )
    await session.commit()
    await session.refresh(request)
    return request


@router.post("/public/requests/{request_id}/attachments", status_code=201, tags=["public"])
async def upload_public_attachment(
    request_id: uuid.UUID, session: Session, file: UploadFile = File(...)
) -> dict[str, object]:
    if not settings.public_intake_enabled:
        raise HTTPException(status_code=503, detail="Public NOTAM request intake is disabled")
    portal_user = await _get_portal_user(session)
    request = await session.get(NotamRequest, request_id)
    if (
        request is None
        or request.created_by_id != portal_user.id
        or request.status != WorkflowStatus.RECEIVED
    ):
        # Deliberately the same 404 whether the request doesn't exist, wasn't
        # created via the public portal, or has already moved past intake --
        # avoids leaking which requests exist to an anonymous caller.
        raise HTTPException(status_code=404, detail="Request not found")
    content = await file.read()
    try:
        stored = await storage.put(request.id, file.filename or "attachment", content)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    attachment = Attachment(
        request_id=request.id,
        filename=file.filename or "attachment",
        media_type=file.content_type or "application/octet-stream",
        size_bytes=stored.size,
        object_key=stored.key,
        sha256=stored.sha256,
        uploaded_by_id=portal_user.id,
    )
    session.add(attachment)
    await audit(
        session,
        "notam_request",
        request.id,
        "evidence_attached",
        portal_user.id,
        payload={"sha256": stored.sha256, "filename": attachment.filename, "channel": "public_portal"},
    )
    await session.commit()
    return {"id": attachment.id, "filename": attachment.filename, "sha256": stored.sha256}


@router.get("/requests", response_model=list[RequestRead], tags=["requests"])
async def list_requests(
    session: Session,
    _: CurrentUser,
    status_filter: WorkflowStatus | None = Query(default=None, alias="status"),
    search: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[NotamRequest]:
    statement = select(NotamRequest).order_by(NotamRequest.received_at.desc()).limit(limit)
    if status_filter:
        statement = statement.where(NotamRequest.status == status_filter)
    if search:
        term = f"%{search}%"
        statement = statement.where(
            NotamRequest.request_number.ilike(term)
            | NotamRequest.originator_name.ilike(term)
            | NotamRequest.location_indicator.ilike(term)
        )
    return list(await session.scalars(statement))


@router.get("/requests/{request_id}", response_model=RequestRead, tags=["requests"])
async def get_request(request_id: uuid.UUID, session: Session, _: CurrentUser) -> NotamRequest:
    request = await session.get(NotamRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return request


async def _build_notam_read(
    notam: Notam,
    session: AsyncSession,
    request: NotamRequest | None = None,
    replacing_map: dict[uuid.UUID, Notam] | None = None,
    all_notams_by_id: dict[uuid.UUID, Notam] | None = None,
    deliveries_by_notam: dict[uuid.UUID, list[PublicationDelivery]] | None = None,
) -> NotamRead:
    now = datetime.now(UTC)

    # Check if replaced or cancelled by another published NOTAM
    replaces_ident = None
    if notam.replaces_notam_id:
        if all_notams_by_id and notam.replaces_notam_id in all_notams_by_id:
            replaces_ident = all_notams_by_id[notam.replaces_notam_id].identifier
        else:
            rep_target = await session.get(Notam, notam.replaces_notam_id)
            if rep_target:
                replaces_ident = rep_target.identifier

    replaced_by_ident = None
    superseding_notam = None
    if replacing_map and notam.id in replacing_map:
        superseding_notam = replacing_map[notam.id]
        replaced_by_ident = superseding_notam.identifier

    # Determine lifecycle status
    is_active = True
    if superseding_notam:
        is_active = False
        if superseding_notam.kind == NotamKind.CANCEL:
            lifecycle_status = "CANCELLED"
        else:
            lifecycle_status = "REPLACED"
    elif notam.kind == NotamKind.CANCEL:
        is_active = False
        lifecycle_status = "CANCELLATION_NOTICE"
    elif not notam.published_at:
        lifecycle_status = "PUBLISHING"
    elif notam.item_c_qualifier == "PERM":
        lifecycle_status = "PERM"
    elif notam.item_c_qualifier == "EST":
        if notam.item_c and notam.item_c < now:
            is_active = False
            lifecycle_status = "EST_EXPIRED"
        elif notam.item_c and (notam.item_c - now).total_seconds() < 48 * 3600:
            lifecycle_status = "EST_EXPIRING_SOON"
        else:
            lifecycle_status = "EST_ACTIVE"
    elif notam.item_c and notam.item_c < now:
        is_active = False
        lifecycle_status = "EXPIRED"
    elif notam.item_c and (notam.item_c - now).total_seconds() < 48 * 3600:
        lifecycle_status = "EXPIRING_SOON"
    else:
        lifecycle_status = "ACTIVE"

    # Deliveries
    if deliveries_by_notam is not None:
        raw_delivs = deliveries_by_notam.get(notam.id, [])
    else:
        raw_delivs = list(
            await session.scalars(
                select(PublicationDelivery).where(PublicationDelivery.notam_id == notam.id)
            )
        )
    deliv_reads = [PublicationDeliveryRead.model_validate(d) for d in raw_delivs]

    req = request
    if req is None and notam.request_id:
        req = await session.get(NotamRequest, notam.request_id)

    prep = None
    if notam.prepared_by_id:
        prep = await session.get(User, notam.prepared_by_id)

    appr = None
    if notam.approved_by_id:
        appr = await session.get(User, notam.approved_by_id)

    return NotamRead(
        id=notam.id,
        request_id=notam.request_id,
        identifier=notam.identifier,
        series=notam.series,
        kind=notam.kind,
        serial_number=notam.serial_number,
        year=notam.year,
        replaces_notam_id=notam.replaces_notam_id,
        replaces_identifier=replaces_ident,
        replaced_by_identifier=replaced_by_ident,
        lifecycle_status=lifecycle_status,
        is_active=is_active,
        fir=notam.fir,
        q_code=notam.q_code,
        traffic=notam.traffic,
        purpose=notam.purpose,
        scope=notam.scope,
        lower_limit=notam.lower_limit,
        upper_limit=notam.upper_limit,
        coordinates_radius=notam.coordinates_radius,
        item_a=notam.item_a,
        item_b=notam.item_b,
        item_c=notam.item_c,
        item_c_qualifier=notam.item_c_qualifier,
        item_d=notam.item_d,
        item_e=notam.item_e,
        item_f=notam.item_f,
        item_g=notam.item_g,
        aip_supplement_reference=notam.aip_supplement_reference,
        formatted_message=notam.formatted_message,
        aixm_payload=notam.aixm_payload,
        aixm_xml=notam.aixm_xml,
        validation_result=notam.validation_result,
        ruleset_version=notam.ruleset_version,
        prepared_by_id=notam.prepared_by_id,
        prepared_by_name=prep.full_name if prep else None,
        prepared_by_role=prep.role.value if prep else None,
        approved_by_id=notam.approved_by_id,
        approved_by_name=appr.full_name if appr else None,
        approved_by_role=appr.role.value if appr else None,
        approved_at=notam.approved_at,
        published_at=notam.published_at,
        request_number=req.request_number if req else None,
        request_source=req.source.value if req and req.source else None,
        received_at=req.received_at if req else None,
        originator_name=req.originator_name if req else None,
        originator_email=req.originator_email if req else None,
        originator_reference=req.originator_reference if req else None,
        deliveries=deliv_reads,
    )


@router.get(
    "/requests/{request_id}/notam", response_model=NotamRead | None, tags=["notams"]
)
async def get_request_notam(
    request_id: uuid.UUID, session: Session, _: CurrentUser
) -> NotamRead | None:
    """The prepared NOTAM for a request, once one exists."""
    request = await session.scalar(
        select(NotamRequest)
        .options(selectinload(NotamRequest.notam))
        .where(NotamRequest.id == request_id)
    )
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")
    if request.notam is None:
        return None
    return await _build_notam_read(request.notam, session, request=request)



@router.get("/notams", response_model=list[NotamRead], tags=["notams"])
async def list_notams(
    session: Session,
    _: CurrentUser,
    series: NotamSeries | None = None,
    location: str | None = None,
    status: str | None = None,
    search: str | None = None,
) -> list[NotamRead]:
    """Lists published NOTAMs with full operational, audit, and lifecycle tracking."""
    statement = (
        select(Notam)
        .options(
            selectinload(Notam.request),
            selectinload(Notam.prepared_by),
            selectinload(Notam.approved_by),
        )
        .where(Notam.published_at.is_not(None))
        .order_by(Notam.published_at.desc())
    )
    if series is not None:
        statement = statement.where(Notam.series == series)
    if location:
        statement = statement.where(Notam.item_a == location.upper().strip())

    notams = list(await session.scalars(statement))
    if not notams:
        return []

    # Pre-fetch all deliveries
    notam_ids = [n.id for n in notams]
    deliveries = list(
        await session.scalars(
            select(PublicationDelivery).where(PublicationDelivery.notam_id.in_(notam_ids))
        )
    )
    deliveries_by_notam: dict[uuid.UUID, list[PublicationDelivery]] = {}
    for d in deliveries:
        deliveries_by_notam.setdefault(d.notam_id, []).append(d)

    # Build maps for replacements
    all_notams_by_id = {n.id: n for n in notams}
    replacing_map: dict[uuid.UUID, Notam] = {}
    for n in notams:
        if n.replaces_notam_id and n.kind in {NotamKind.REPLACE, NotamKind.CANCEL}:
            replacing_map[n.replaces_notam_id] = n

    results: list[NotamRead] = []
    for n in notams:
        item = await _build_notam_read(
            n,
            session,
            replacing_map=replacing_map,
            all_notams_by_id=all_notams_by_id,
            deliveries_by_notam=deliveries_by_notam,
        )
        # Optional filter by lifecycle status
        if status:
            st = status.upper().strip()
            if st == "ACTIVE" and not item.is_active:
                continue
            if st == "EXPIRING" and item.lifecycle_status not in {"EXPIRING_SOON", "EST_EXPIRING_SOON"}:
                continue
            if st == "EST" and "EST" not in item.lifecycle_status:
                continue
            if st == "PERM" and item.lifecycle_status != "PERM":
                continue
            if st == "REPLACED_CANCELLED" and item.lifecycle_status not in {"REPLACED", "CANCELLED", "CANCELLATION_NOTICE"}:
                continue
        # Optional search filter
        if search:
            q = search.casefold().strip()
            searchable = f"{item.identifier} {item.q_code} {item.item_a} {item.item_e} {item.originator_name or ''} {item.originator_reference or ''}".casefold()
            if q not in searchable:
                continue
        results.append(item)

    return results




@router.post("/requests/{request_id}/acknowledge", response_model=RequestRead, tags=["requests"])
async def acknowledge_request(
    request_id: uuid.UUID,
    session: Session,
    user: Annotated[
        User, Depends(require_roles(Role.AIS_OFFICER, Role.AIS_SPECIALIST, Role.NOF_MANAGER))
    ],
) -> NotamRequest:
    request = await session.get(NotamRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")
    request.acknowledgement_sent_at = datetime.now(UTC)
    await audit(session, "notam_request", request.id, "receipt_acknowledged", user.id)
    await session.commit()
    await session.refresh(request)
    return request


@router.post("/requests/{request_id}/attachments", status_code=201, tags=["requests"])
async def upload_attachment(
    request_id: uuid.UUID,
    session: Session,
    user: CurrentUser,
    file: UploadFile = File(...),
) -> dict[str, object]:
    request = await session.get(NotamRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")
    content = await file.read()
    try:
        stored = await storage.put(request.id, file.filename or "attachment", content)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    attachment = Attachment(
        request_id=request.id,
        filename=file.filename or "attachment",
        media_type=file.content_type or "application/octet-stream",
        size_bytes=stored.size,
        object_key=stored.key,
        sha256=stored.sha256,
        uploaded_by_id=user.id,
    )
    session.add(attachment)
    await audit(
        session,
        "notam_request",
        request.id,
        "evidence_attached",
        user.id,
        payload={"sha256": stored.sha256, "filename": attachment.filename},
    )
    await session.flush()
    if settings.extraction_enabled:
        await run_extraction(session, storage, request.id, attachment.id)
    await session.commit()
    return {"id": attachment.id, "filename": attachment.filename, "sha256": stored.sha256}


@router.get(
    "/requests/{request_id}/attachments",
    response_model=list[AttachmentRead],
    tags=["requests"],
)
async def list_attachments(
    request_id: uuid.UUID, session: Session, _: CurrentUser
) -> list[Attachment]:
    request = await session.get(NotamRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")
    result = await session.scalars(
        select(Attachment)
        .where(Attachment.request_id == request_id)
        .order_by(Attachment.created_at)
    )
    return list(result)


@router.get("/attachments/{attachment_id}/content", tags=["requests"])
async def download_attachment(
    attachment_id: uuid.UUID, session: Session, _: CurrentUser
) -> Response:
    attachment = await session.get(Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    try:
        content = await storage.get(attachment.object_key)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Evidence object missing from storage"
        ) from exc
    return Response(
        content=content,
        media_type=attachment.media_type,
        headers={"Content-Disposition": f'inline; filename="{attachment.filename}"'},
    )


@router.get(
    "/requests/{request_id}/extraction",
    response_model=ExtractionRunRead | None,
    tags=["extraction"],
)
async def latest_extraction(
    request_id: uuid.UUID, session: Session, _: CurrentUser
) -> ExtractionRun | None:
    request = await session.get(NotamRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")
    run: ExtractionRun | None = await session.scalar(
        select(ExtractionRun)
        .join(Attachment, ExtractionRun.attachment_id == Attachment.id)
        .options(selectinload(ExtractionRun.fields))
        .where(Attachment.request_id == request_id)
        .order_by(ExtractionRun.created_at.desc())
        .limit(1)
    )
    return run


@router.post(
    "/requests/{request_id}/extraction/rerun",
    response_model=ExtractionRunRead,
    tags=["extraction"],
)
async def rerun_extraction(
    request_id: uuid.UUID,
    session: Session,
    user: Annotated[
        User, Depends(require_roles(Role.AIS_OFFICER, Role.AIS_SPECIALIST, Role.NOF_MANAGER))
    ],
) -> ExtractionRun:
    if not settings.extraction_enabled:
        raise HTTPException(status_code=409, detail="Document extraction is not enabled")
    request = await session.get(NotamRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")
    latest_attachment = await session.scalar(
        select(Attachment)
        .where(Attachment.request_id == request_id)
        .order_by(Attachment.created_at.desc())
        .limit(1)
    )
    if latest_attachment is None:
        raise HTTPException(status_code=404, detail="No attachment to extract from")
    run = await run_extraction(session, storage, request_id, latest_attachment.id)
    await audit(
        session,
        "notam_request",
        request_id,
        "extraction_rerun",
        user.id,
        payload={"run_id": str(run.id), "attachment_id": str(latest_attachment.id)},
    )
    await session.commit()
    reloaded = await session.scalar(
        select(ExtractionRun)
        .options(selectinload(ExtractionRun.fields))
        .where(ExtractionRun.id == run.id)
    )
    assert reloaded is not None
    return reloaded


@router.post(
    "/extraction/preview",
    response_model=ExtractionPreviewResult,
    tags=["extraction"],
)
async def preview_extraction(
    user: Annotated[
        User, Depends(require_roles(Role.AIS_OFFICER, Role.AIS_SPECIALIST, Role.NOF_MANAGER))
    ],
    file: UploadFile = File(...),
) -> ExtractionPreviewResult:
    """Stateless read of a photo/scan before a request exists -- lets the
    intake form pre-fill itself from a hard-copy GCAA-AIS-NTM-FR01 the
    moment it's photographed, instead of only extracting for reference
    after the officer has already retyped everything. Nothing is persisted
    here (no Attachment/ExtractionRun row); the real, audited extraction
    still runs again on submit via the normal upload_attachment path."""
    if not settings.extraction_enabled:
        raise HTTPException(status_code=409, detail="Document extraction is not enabled")
    content = await file.read()
    media_type = file.content_type or "application/octet-stream"
    engine = build_engine(settings.ocr_engine)
    try:
        result = run_pipeline(content, media_type, engine)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    d = result.as_dict()
    return ExtractionPreviewResult(
        fields=d["fields"],  # type: ignore[arg-type]
        page_count=d["page_count"],  # type: ignore[arg-type]
        q_code_suggestions=d["q_code_suggestions"],  # type: ignore[arg-type]
        raw_text=d["raw_text"],  # type: ignore[arg-type]
    )


@router.post(
    "/extraction/fields/{field_id}/accept",
    response_model=ExtractedFieldRead,
    tags=["extraction"],
)
async def accept_extracted_field(
    field_id: uuid.UUID,
    payload: FieldAcceptRequest,
    session: Session,
    user: Annotated[
        User, Depends(require_roles(Role.AIS_OFFICER, Role.AIS_SPECIALIST, Role.NOF_MANAGER))
    ],
) -> ExtractedField:
    field = await session.get(ExtractedField, field_id)
    if field is None:
        raise HTTPException(status_code=404, detail="Extracted field not found")
    if payload.value is not None:
        field.normalized_value = payload.value
    field.accepted_by_id = user.id
    field.accepted_at = datetime.now(UTC)
    await audit(
        session,
        "extracted_field",
        field.id,
        "extraction_field_accepted",
        user.id,
        payload={"field_name": field.field_name, "value": field.normalized_value},
    )
    await session.commit()
    await session.refresh(field)
    return field


@router.post("/requests/{request_id}/draft", response_model=NotamRead, tags=["notams"])
async def save_draft(
    request_id: uuid.UUID,
    payload: NotamDraftCreate,
    session: Session,
    user: Annotated[
        User, Depends(require_roles(Role.AIS_OFFICER, Role.AIS_SPECIALIST, Role.NOF_MANAGER))
    ],
) -> Notam:
    request = await session.scalar(
        select(NotamRequest)
        .options(selectinload(NotamRequest.notam))
        .where(NotamRequest.id == request_id)
    )
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")
    notam = await create_draft(session, request, payload, user)
    await session.commit()
    await session.refresh(notam)
    return notam


@router.post("/requests/{request_id}/submit", response_model=RequestRead, tags=["workflow"])
async def submit_for_review(
    request_id: uuid.UUID,
    session: Session,
    user: Annotated[
        User, Depends(require_roles(Role.AIS_OFFICER, Role.AIS_SPECIALIST, Role.NOF_MANAGER))
    ],
) -> NotamRequest:
    request = await session.scalar(
        select(NotamRequest)
        .options(selectinload(NotamRequest.notam))
        .where(NotamRequest.id == request_id)
    )
    if request is None or request.notam is None:
        raise HTTPException(status_code=404, detail="Prepared NOTAM not found")
    if not request.notam.validation_result.get("valid"):
        raise HTTPException(status_code=422, detail="NOTAM has unresolved validation errors")
    await transition_request(session, request, WorkflowStatus.REVIEW, user, "submitted_for_review")
    await session.commit()
    await session.refresh(request)
    return request


@router.post(
    "/requests/{request_id}/request-changes", response_model=RequestRead, tags=["workflow"]
)
async def request_changes(
    request_id: uuid.UUID,
    payload: ReviewAction,
    session: Session,
    user: Annotated[User, Depends(require_roles(Role.AIS_SPECIALIST, Role.NOF_MANAGER))],
) -> NotamRequest:
    request = await session.get(NotamRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")
    await transition_request(
        session,
        request,
        WorkflowStatus.CHANGES_REQUESTED,
        user,
        "changes_requested",
        {"comment": payload.comment or ""},
    )
    await session.commit()
    await session.refresh(request)
    return request


@router.post("/requests/{request_id}/approve", response_model=NotamRead, tags=["workflow"])
async def approve(
    request_id: uuid.UUID,
    payload: ReviewAction,
    session: Session,
    user: Annotated[User, Depends(require_roles(Role.AIS_SPECIALIST, Role.NOF_MANAGER))],
) -> Notam:
    request = await session.scalar(
        select(NotamRequest)
        .options(selectinload(NotamRequest.notam))
        .where(NotamRequest.id == request_id)
    )
    if request is None or request.notam is None:
        raise HTTPException(status_code=404, detail="Prepared NOTAM not found")
    if request.notam.prepared_by_id == user.id:
        raise HTTPException(status_code=409, detail="Four-eyes control prohibits self-approval")
    await transition_request(
        session,
        request,
        WorkflowStatus.APPROVED,
        user,
        "draft_approved",
        {"comment": payload.comment or ""},
    )
    request.notam.approved_by_id = user.id
    request.notam.approved_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(request.notam)
    return request.notam


@router.post("/requests/{request_id}/publish", response_model=RequestRead, tags=["publication"])
async def publish(
    request_id: uuid.UUID,
    session: Session,
    user: Annotated[
        User, Depends(require_roles(Role.AIS_OFFICER, Role.AIS_SPECIALIST, Role.NOF_MANAGER))
    ],
) -> NotamRequest:
    request = await session.scalar(
        select(NotamRequest)
        .options(selectinload(NotamRequest.notam))
        .where(NotamRequest.id == request_id)
    )
    if request is None or request.notam is None:
        raise HTTPException(status_code=404, detail="Approved NOTAM not found")
    await transition_request(
        session, request, WorkflowStatus.PUBLISHING, user, "publication_started"
    )
    deliveries = [
        PublicationDelivery(notam_id=request.notam.id, channel=channel, destination=destination)
        for channel, destination in CHANNELS
    ]
    session.add_all(deliveries)
    await session.flush()

    for delivery in deliveries:
        simulated = settings.mode_for_channel(delivery.channel) == "simulated_sync"
        await dispatch_delivery(session, delivery, request.notam, simulated=simulated)

    failed = [d for d in deliveries if d.status == "failed"]
    if failed and len(failed) < len(deliveries):
        # Mixed outcome -- some channels failed, not all. Audited separately
        # from the total-failure/all-success cases _reconcile_publishing_status
        # below handles, since "partial" is a distinct, actionable state
        # worth its own trail (the request stays PUBLISHING either way).
        await audit(
            session,
            "notam_request",
            request.id,
            "publication_partial",
            user.id,
            payload={"failed_channels": [d.channel for d in failed]},
        )
    await _reconcile_publishing_status(session, request.notam, user)
    await session.commit()
    await session.refresh(request)
    return request


@router.get(
    "/notams/{notam_id}/deliveries",
    response_model=list[PublicationDeliveryRead],
    tags=["publication"],
)
async def list_deliveries(notam_id: uuid.UUID, session: Session, _: CurrentUser) -> list[PublicationDelivery]:
    notam = await session.get(Notam, notam_id)
    if notam is None:
        raise HTTPException(status_code=404, detail="NOTAM not found")
    result = await session.scalars(
        select(PublicationDelivery)
        .where(PublicationDelivery.notam_id == notam_id)
        .order_by(PublicationDelivery.attempted_at)
    )
    return list(result)


@router.post(
    "/deliveries/{delivery_id}/retry",
    response_model=PublicationDeliveryRead,
    tags=["publication"],
)
async def retry_delivery(
    delivery_id: uuid.UUID,
    session: Session,
    user: Annotated[
        User, Depends(require_roles(Role.AIS_OFFICER, Role.AIS_SPECIALIST, Role.NOF_MANAGER))
    ],
) -> PublicationDelivery:
    delivery = await session.get(PublicationDelivery, delivery_id)
    if delivery is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    notam = await session.get(Notam, delivery.notam_id)
    if notam is None:
        raise HTTPException(status_code=404, detail="NOTAM not found")
    simulated = settings.mode_for_channel(delivery.channel) == "simulated_sync"
    await dispatch_delivery(session, delivery, notam, simulated=simulated)
    await audit(
        session,
        "publication_delivery",
        delivery.id,
        "delivery_retried",
        user.id,
        payload={"channel": delivery.channel, "status": delivery.status},
    )

    await _reconcile_publishing_status(session, notam, user)
    await session.commit()
    await session.refresh(delivery)
    return delivery


@router.post(
    "/deliveries/{delivery_id}/acknowledge",
    response_model=PublicationDeliveryRead,
    tags=["publication"],
)
async def acknowledge_delivery(
    delivery_id: uuid.UUID,
    session: Session,
    user: Annotated[
        User, Depends(require_roles(Role.AIS_OFFICER, Role.AIS_SPECIALIST, Role.NOF_MANAGER))
    ],
) -> PublicationDelivery:
    """Manually marks a specific channel delivery as acknowledged after manual transmission."""
    delivery = await session.get(PublicationDelivery, delivery_id)
    if delivery is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    notam = await session.get(Notam, delivery.notam_id)
    if notam is None:
        raise HTTPException(status_code=404, detail="NOTAM not found")

    now = datetime.now(UTC)
    delivery.status = "acknowledged"
    delivery.acknowledged_at = now
    delivery.response_payload = {
        **delivery.response_payload,
        "manual_acknowledgement": True,
        "acknowledged_by": user.full_name,
    }
    await audit(
        session,
        "publication_delivery",
        delivery.id,
        "delivery_manually_acknowledged",
        user.id,
        payload={"channel": delivery.channel, "status": "acknowledged"},
    )
    await _reconcile_publishing_status(session, notam, user)
    await session.commit()
    await session.refresh(delivery)
    return delivery


@router.post(
    "/requests/{request_id}/mark-published",
    response_model=RequestRead,
    tags=["publication"],
)
async def mark_request_published(
    request_id: uuid.UUID,
    session: Session,
    user: Annotated[
        User, Depends(require_roles(Role.AIS_OFFICER, Role.AIS_SPECIALIST, Role.NOF_MANAGER))
    ],
) -> NotamRequest:
    """Allows an AIS Officer, Specialist, or Manager to mark a NOTAM as Published
    when it was manually transmitted (e.g. entered directly into AFTN terminal
    or web portal after automatic delivery failure)."""
    request = await session.scalar(
        select(NotamRequest)
        .options(selectinload(NotamRequest.notam))
        .where(NotamRequest.id == request_id)
    )
    if request is None or request.notam is None:
        raise HTTPException(status_code=404, detail="Prepared NOTAM not found")
    if request.status not in {
        WorkflowStatus.PUBLISHING,
        WorkflowStatus.APPROVED,
        WorkflowStatus.PUBLISHED,
    }:
        raise HTTPException(
            status_code=409,
            detail="Only approved or publishing NOTAMs can be marked as published",
        )

    now = datetime.now(UTC)
    request.notam.published_at = now
    deliveries = list(
        await session.scalars(
            select(PublicationDelivery).where(PublicationDelivery.notam_id == request.notam.id)
        )
    )
    for delivery in deliveries:
        if delivery.status != "acknowledged":
            delivery.status = "acknowledged"
            delivery.acknowledged_at = now
            delivery.response_payload = {
                **delivery.response_payload,
                "manual_acknowledgement": True,
                "acknowledged_by": user.full_name,
            }

    if request.status == WorkflowStatus.APPROVED:
        await transition_request(
            session, request, WorkflowStatus.PUBLISHING, user, "publication_started"
        )
    if request.status == WorkflowStatus.PUBLISHING:
        await transition_request(
            session,
            request,
            WorkflowStatus.PUBLISHED,
            user,
            "publication_manual_completed",
            payload={"manual_override": True, "actor": user.email},
        )

    await session.commit()
    await session.refresh(request)
    return request


async def _reconcile_publishing_status(
    session: AsyncSession, notam: Notam, actor: User
) -> None:
    """Shared by /deliveries/{id}/retry and /aftn/outbox/{id}/ack -- after
    any single delivery's status changes, re-check the whole set the same
    way /publish itself does: only a *total* failure reverts to APPROVED
    (nothing to retry against, start over), only *all* acknowledged reaches
    PUBLISHED, and a still-mixed outcome (e.g. one channel retried and
    failed again, others fine) is left exactly where it is -- PUBLISHING,
    with the delivery table still visible and actionable. A one-line
    `any(failed)` check here previously reverted the whole request on a
    single still-failing retry, undoing the same fix made in /publish."""
    request = await session.scalar(
        select(NotamRequest)
        .options(selectinload(NotamRequest.notam))
        .where(NotamRequest.id == notam.request_id)
    )
    if request is None or request.status != WorkflowStatus.PUBLISHING:
        return
    siblings = list(
        await session.scalars(
            select(PublicationDelivery).where(PublicationDelivery.notam_id == notam.id)
        )
    )
    failed = [s for s in siblings if s.status == "failed"]
    if failed and len(failed) == len(siblings):
        await transition_request(
            session, request, WorkflowStatus.APPROVED, actor, "publication_failed",
            payload={"failed_channels": [s.channel for s in failed]},
        )
    elif all(s.status == "acknowledged" for s in siblings):
        notam.published_at = datetime.now(UTC)
        await transition_request(
            session, request, WorkflowStatus.PUBLISHED, actor, "publication_completed"
        )


async def _get_aftn_bridge_actor(session: AsyncSession) -> User:
    """No person operates app/aftn_bridge.py -- it authenticates with the
    service key, not a login -- but transition_request()/audit() still need
    a User to attribute the resulting state changes to, same reasoning as
    _get_portal_user for anonymous public submissions."""
    actor = await session.scalar(select(User).where(User.email == "aftn-bridge@notamsys.app"))
    if actor is None:
        actor = User(
            email="aftn-bridge@notamsys.app",
            full_name="AFTN Bridge Service",
            role=Role.ORIGINATOR,
            password_hash=hash_password(uuid.uuid4().hex + uuid.uuid4().hex),
            organization="GCAA AIS",
        )
        session.add(actor)
        await session.flush()
    return actor


@router.get(
    "/aftn/outbox",
    response_model=list[AftnOutboxItem],
    tags=["aftn-bridge"],
    dependencies=[Depends(require_service_key)],
)
async def aftn_outbox(session: Session) -> list[PublicationDelivery]:
    """Polled by app/aftn_bridge.py on ATSEP's on-prem Comsoft box -- see
    docs/AFTN_BRIDGE.md. Lists AFTN envelopes built and queued (PullQueueAftnAdapter
    marked them "sent") but not yet picked up (no external_reference yet)."""
    result = await session.scalars(
        select(PublicationDelivery)
        .where(
            PublicationDelivery.channel == "AFTN",
            PublicationDelivery.status == "sent",
            PublicationDelivery.external_reference.is_(None),
        )
        .order_by(PublicationDelivery.attempted_at)
    )
    return list(result)


@router.post(
    "/aftn/outbox/{delivery_id}/ack",
    response_model=PublicationDeliveryRead,
    tags=["aftn-bridge"],
    dependencies=[Depends(require_service_key)],
)
async def aftn_ack(
    delivery_id: uuid.UUID, payload: AftnAckRequest, session: Session
) -> PublicationDelivery:
    """Called by app/aftn_bridge.py once it has written the envelope to the
    directory Comsoft's terminal actually watches. `external_reference` is
    whatever filename or id the bridge script reports. Still "sent" ->
    "acknowledged" here, not a confirmation Comsoft transmitted it -- that
    remains outside what this process can ever observe."""
    delivery = await session.get(PublicationDelivery, delivery_id)
    if delivery is None or delivery.channel != "AFTN":
        raise HTTPException(status_code=404, detail="AFTN delivery not found")
    delivery.status = "acknowledged"
    delivery.acknowledged_at = datetime.now(UTC)
    delivery.external_reference = payload.external_reference
    notam = await session.get(Notam, delivery.notam_id)
    if notam is not None:
        actor = await _get_aftn_bridge_actor(session)
        await audit(
            session,
            "publication_delivery",
            delivery.id,
            "aftn_bridge_acknowledged",
            actor.id,
            payload={"external_reference": payload.external_reference},
        )
        await _reconcile_publishing_status(session, notam, actor)
    await session.commit()
    await session.refresh(delivery)
    return delivery


@router.get("/reference/datasets", response_model=AipDatasetRead | None, tags=["reference"])
async def active_aip_dataset(session: Session, _: CurrentUser) -> object:
    return await default_provider().dataset_metadata(session)


@router.get("/reference/firs", response_model=list[FirRead], tags=["reference"])
async def list_firs(session: Session, _: CurrentUser) -> list[Fir]:
    return await default_provider().list_firs(session)


@router.get("/reference/aerodromes", response_model=list[AerodromeRead], tags=["reference"])
async def list_aerodromes(
    session: Session, _: CurrentUser, q: str | None = None
) -> list[Aerodrome]:
    return await default_provider().list_aerodromes(session, q)


@router.get(
    "/reference/aerodromes/{icao_code}", response_model=AerodromeRead, tags=["reference"]
)
async def get_aerodrome(icao_code: str, session: Session, _: CurrentUser) -> Aerodrome:
    aerodrome = await default_provider().get_aerodrome(session, icao_code)
    if aerodrome is None:
        raise HTTPException(status_code=404, detail="Aerodrome not found in the active dataset")
    return aerodrome


@router.get("/audit-events", tags=["quality"])
async def list_audit_events(
    session: Session,
    _: CurrentUser,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    correlation_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, object]]:
    statement = (
        select(AuditEvent)
        .options(selectinload(AuditEvent.actor))
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    )
    if entity_type:
        statement = statement.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        statement = statement.where(AuditEvent.entity_id == entity_id)
    if correlation_id:
        statement = statement.where(AuditEvent.correlation_id == correlation_id)
    events = await session.scalars(statement)
    return [
        {
            "id": event.id,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "action": event.action,
            "actor_name": event.actor.full_name if event.actor else "system",
            "actor_role": event.actor.role.value if event.actor else None,
            "from_state": event.from_state,
            "to_state": event.to_state,
            "payload": event.payload,
            "correlation_id": event.correlation_id,
            "created_at": event.created_at,
        }
        for event in events
    ]


@router.post("/rules/validate", tags=["rules"])
async def validate_rule(payload: ValidationRequest, _: CurrentUser) -> dict[str, object]:
    if payload.q_code:
        subject, condition = payload.q_code[1:3], payload.q_code[3:5]
    else:
        # ValidationRequest.check_subject_source guarantees both are set here.
        assert payload.subject is not None
        assert payload.condition is not None
        subject, condition = payload.subject, payload.condition
    return validate_selection(
        subject,
        condition,
        payload.traffic,
        payload.purpose,
        payload.scope,
        payload.kind,
    )


@router.get("/rules/catalog", tags=["rules"])
async def rules_catalog(
    _: CurrentUser,
    search: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[dict[str, Any]]:
    rows = [{**asdict(rule), "q_code": rule.q_code} for rule in get_catalog().rules]
    if search:
        term = search.casefold()
        rows = [
            row
            for row in rows
            if term in row["subject"].casefold()
            or term in row["condition"].casefold()
            or term in row["q_code"].casefold()
        ]
    if status_filter:
        rows = [row for row in rows if row["verification_status"] == status_filter]
    return rows


@router.get("/rules/qcode/{q_code}", tags=["rules"])
async def rule_by_qcode(q_code: str, _: CurrentUser) -> dict[str, object]:
    rule = get_catalog().find_by_qcode(q_code.upper())
    if rule is None:
        raise HTTPException(status_code=404, detail="No selection-criteria rule for that Q-code")
    return {**asdict(rule), "q_code": rule.q_code}


@router.post("/rules/qcode-suggestions", tags=["rules"])
async def qcode_suggestions(payload: QCodeSuggestionRequest, _: CurrentUser) -> list[dict[str, object]]:
    """Ranked Q-code candidates for whatever narrative text is currently in
    Item E, using the Option A three-tier hybrid pipeline:

    1. Deterministic two-sided keyword scoring against all 1,250 Doc 8126
       selection criteria rules (subject keywords + condition keywords).
    2. RapidFuzz Levenshtein OCR typo-correction with ICAO Doc 8400 /
       EUROCONTROL OPADD Ed 4.1 abbreviation normalizer applied to the
       input before scoring, recovering OCR errors (0→O, 1→I/L, 5→S, 8→B)
       and expanding standard aviation abbreviations.
    3. Local sentence-transformers cosine similarity (all-MiniLM-L6-v2)
       used to re-rank the top candidates by semantic meaning against the
       canonical Doc 8126 rule descriptions -- no GPU, no external API.

    Confidence is always capped at 90% to prevent false certainty.
    Never returns a single silent answer: the officer picks one or
    ignores all -- same contract as suggest_q_codes() itself."""
    return suggest_q_codes(payload.narrative, location_indicator=payload.location_indicator)


@router.post("/rules/qcode-corrections", response_model=QCodeCorrectionRead, tags=["rules"])
async def record_qcode_correction(
    payload: QCodeCorrectionCreate,
    session: Session,
    user: CurrentUser,
) -> QCodeCorrection:
    """Records an officer's correction/selection feedback when choosing a Q-code.
    Used for continuous improvement of keyword and semantic matching models.
    """
    correction = QCodeCorrection(
        request_id=payload.request_id,
        officer_id=user.id,
        location_indicator=payload.location_indicator,
        narrative=payload.narrative,
        suggested_q_code=payload.suggested_q_code,
        suggested_confidence=payload.suggested_confidence,
        chosen_q_code=payload.chosen_q_code.upper(),
        suggestion_was_in_top5=payload.suggestion_was_in_top5,
    )
    session.add(correction)
    await session.commit()
    await session.refresh(correction)
    return correction


@router.get("/rules/versions", response_model=list[RuleVersionRead], tags=["rules"])
async def list_rule_versions(session: Session, _: CurrentUser) -> list[RuleVersion]:
    result = await session.scalars(select(RuleVersion).order_by(RuleVersion.approved_at.desc()))
    return list(result)


@router.post(
    "/rules/versions/{version_id}/activate", response_model=RuleVersionRead, tags=["rules"]
)
async def activate_rule_version(
    version_id: uuid.UUID,
    session: Session,
    user: Annotated[User, Depends(require_roles(Role.NOF_MANAGER))],
) -> RuleVersion:
    version = await session.get(RuleVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Rule version not found")
    if canonical_checksum(version.rules) != version.checksum:
        raise HTTPException(
            status_code=409,
            detail="Rule version checksum mismatch; refusing to activate unverified data",
        )
    await session.execute(update(RuleVersion).where(RuleVersion.id != version.id).values(active=False))
    version.active = True
    reload_catalog(version.rules["rules"])
    await audit(
        session,
        "rule_version",
        version.id,
        "rule_version_activated",
        user.id,
        payload={"version": version.version, "checksum": version.checksum},
    )
    await session.commit()
    await session.refresh(version)
    return version


@router.get("/system/status", tags=["system"])
async def system_status(_: CurrentUser) -> dict[str, object]:
    """Exposes the non-secret operational off-switches from core/config.py
    so the UI can state honestly what's live vs. simulated/stubbed instead
    of hardcoding claims like "HEALTHY" that nothing actually checks. See
    docs/ARCHITECTURE.md's operational boundary."""
    from app.services.extraction.semantic import get_semantic_matcher

    return {
        "environment": settings.environment,
        "ocr_engine": settings.ocr_engine,
        "extraction_enabled": settings.extraction_enabled,
        "publication_mode": settings.publication_mode,
        "channel_modes": {
            "AFTN": settings.mode_for_channel("AFTN"),
            "GCAA_WEB": settings.mode_for_channel("GCAA_WEB"),
            "EMAIL": settings.mode_for_channel("EMAIL"),
        },
        "aip_provider": settings.aip_provider,
        "storage_backend": settings.storage_backend,
        "public_intake_enabled": settings.public_intake_enabled,
        "semantic_model_status": get_semantic_matcher().model_status,
    }



@router.get("/dashboard/summary", response_model=DashboardSummary, tags=["dashboard"])
async def dashboard_summary(session: Session, _: CurrentUser) -> DashboardSummary:
    queue_states = [
        WorkflowStatus.RECEIVED,
        WorkflowStatus.TRIAGE,
        WorkflowStatus.DRAFT,
        WorkflowStatus.CHANGES_REQUESTED,
    ]
    queue = await session.scalar(
        select(func.count()).select_from(NotamRequest).where(NotamRequest.status.in_(queue_states))
    )
    review = await session.scalar(
        select(func.count())
        .select_from(NotamRequest)
        .where(NotamRequest.status == WorkflowStatus.REVIEW)
    )
    start = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    published = await session.scalar(
        select(func.count()).select_from(Notam).where(Notam.published_at >= start)
    )
    estimated_due = await session.scalar(
        select(func.count())
        .select_from(Notam)
        .where(Notam.item_c_qualifier == "EST", Notam.published_at.is_not(None))
    )
    # Real first-pass quality: of requests that reached a specialist decision
    # (approved or further), what share never had a changes-requested cycle.
    # Vacuously 100% with zero decided requests -- no defects because no
    # data yet, not a claim about actual performance.
    decided_states = [WorkflowStatus.APPROVED, WorkflowStatus.PUBLISHING, WorkflowStatus.PUBLISHED]
    decided_ids = list(
        await session.scalars(select(NotamRequest.id).where(NotamRequest.status.in_(decided_states)))
    )
    first_pass_quality = 100.0
    if decided_ids:
        revised_ids = await session.scalars(
            select(AuditEvent.entity_id)
            .where(
                AuditEvent.entity_type == "notam_request",
                AuditEvent.action == "changes_requested",
                AuditEvent.entity_id.in_(decided_ids),
            )
            .distinct()
        )
        revised_count = len(set(revised_ids))
        first_pass_quality = round(100 * (len(decided_ids) - revised_count) / len(decided_ids), 1)
    return DashboardSummary(
        requests_in_queue=queue or 0,
        awaiting_specialist=review or 0,
        published_today=published or 0,
        estimated_due=estimated_due or 0,
        first_pass_quality=first_pass_quality,
    )


@router.get("/admin/users", response_model=list[UserRead], tags=["admin"])
async def list_users(
    session: Session, _: Annotated[User, Depends(require_roles(Role.SYSTEM_ADMIN))]
) -> list[User]:
    result = await session.scalars(select(User).order_by(User.created_at))
    return list(result)


@router.post("/admin/users", response_model=UserRead, status_code=201, tags=["admin"])
async def create_user(
    payload: UserCreate,
    session: Session,
    admin: Annotated[User, Depends(require_roles(Role.SYSTEM_ADMIN))],
) -> User:
    existing = await session.scalar(select(User).where(User.email == payload.email.lower()))
    if existing is not None:
        raise HTTPException(status_code=409, detail="A user with that email already exists")
    new_user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        role=payload.role,
        organization=payload.organization,
        password_hash=hash_password(payload.password),
    )
    session.add(new_user)
    await session.flush()
    await audit(
        session,
        "user",
        new_user.id,
        "user_created",
        admin.id,
        payload={"email": new_user.email, "role": new_user.role.value},
    )
    await session.commit()
    await session.refresh(new_user)
    return new_user


@router.patch("/admin/users/{user_id}", response_model=UserRead, tags=["admin"])
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    session: Session,
    admin: Annotated[User, Depends(require_roles(Role.SYSTEM_ADMIN))],
) -> User:
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id and payload.is_active is False:
        raise HTTPException(status_code=409, detail="You cannot deactivate your own account")
    changes: dict[str, object] = {}
    if payload.role is not None and payload.role != target.role:
        changes["role"] = {"from": target.role.value, "to": payload.role.value}
        target.role = payload.role
    if payload.is_active is not None and payload.is_active != target.is_active:
        changes["is_active"] = {"from": target.is_active, "to": payload.is_active}
        target.is_active = payload.is_active
    if changes:
        await audit(session, "user", target.id, "user_updated", admin.id, payload=changes)
    await session.commit()
    await session.refresh(target)
    return target


@router.get("/users/presence", response_model=list[UserPresenceRead], tags=["users"])
async def get_users_presence(session: Session, _: CurrentUser) -> list[dict[str, object]]:
    """Returns presence status and last seen timestamp of all active personnel."""
    users = (
        await session.scalars(
            select(User).where(User.is_active.is_(True)).order_by(User.full_name.asc())
        )
    ).all()
    now = datetime.now(UTC)
    results: list[dict[str, object]] = []
    for u in users:
        is_online = False
        status_label = "Offline"
        if u.last_seen_at:
            last_seen = u.last_seen_at
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=UTC)
            diff_secs = (now - last_seen).total_seconds()
            if diff_secs <= 300:  # within 5 minutes
                is_online = True
                status_label = "Online"
            elif diff_secs <= 1800:  # within 30 minutes
                status_label = "Away"
        results.append(
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role,
                "organization": u.organization,
                "is_active": u.is_active,
                "last_seen_at": u.last_seen_at,
                "is_online": is_online,
                "status_label": status_label,
            }
        )
    return results


@router.post("/users/heartbeat", tags=["users"])
async def user_heartbeat(session: Session, user: CurrentUser) -> dict[str, str]:
    """Heartbeat signal to keep user online status fresh."""
    user.last_seen_at = datetime.now(UTC)
    await session.commit()
    return {"status": "ok"}


ALLOWED_LOGO_TYPES = {"image/png", "image/jpeg", "image/webp", "image/svg+xml"}
LOGO_OBJECT_KEY = "branding/logo"


async def _get_org_settings(session: AsyncSession) -> OrgSettings:
    org = await session.scalar(select(OrgSettings).limit(1))
    if org is None:
        org = OrgSettings()
        session.add(org)
        await session.flush()
    return org


def _branding_read(org: OrgSettings) -> BrandingRead:
    # Deliberately a path relative to this API, not a frontend-facing URL --
    # the browser never talks to this backend directly (see apps/web's BFF
    # architecture), so the frontend rewrites this into its own
    # /api/branding/logo proxy path before it ever reaches an <img> tag.
    logo_url = (
        f"/branding/logo?v={int(org.updated_at.timestamp())}"
        if org.logo_object_key
        else None
    )
    return BrandingRead(
        org_name=org.org_name,
        org_subtitle=org.org_subtitle,
        description=org.description,
        logo_url=logo_url,
    )


@router.get("/branding", response_model=BrandingRead, tags=["system"])
async def get_branding(session: Session) -> BrandingRead:
    """Unauthenticated by design -- renders on /login and the public
    /submit page before any session exists."""
    org = await _get_org_settings(session)
    await session.commit()
    return _branding_read(org)


@router.get("/branding/logo", tags=["system"])
async def get_branding_logo(session: Session) -> Response:
    org = await _get_org_settings(session)
    await session.commit()
    if not org.logo_object_key:
        raise HTTPException(status_code=404, detail="No logo uploaded")
    try:
        content = await storage.get(org.logo_object_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Logo object missing from storage") from exc
    return Response(content=content, media_type=org.logo_media_type or "image/png")


@router.patch("/admin/branding", response_model=BrandingRead, tags=["admin"])
async def update_branding(
    payload: BrandingUpdate,
    session: Session,
    admin: Annotated[User, Depends(require_roles(Role.SYSTEM_ADMIN))],
) -> BrandingRead:
    org = await _get_org_settings(session)
    changes: dict[str, object] = {}
    if payload.org_name is not None and payload.org_name != org.org_name:
        changes["org_name"] = {"from": org.org_name, "to": payload.org_name}
        org.org_name = payload.org_name
    if payload.org_subtitle is not None and payload.org_subtitle != org.org_subtitle:
        changes["org_subtitle"] = {"from": org.org_subtitle, "to": payload.org_subtitle}
        org.org_subtitle = payload.org_subtitle
    if payload.description is not None and payload.description != org.description:
        changes["description"] = True
        org.description = payload.description
    if changes:
        org.updated_by_id = admin.id
        await audit(session, "org_settings", org.id, "branding_updated", admin.id, payload=changes)
    await session.commit()
    await session.refresh(org)
    return _branding_read(org)


@router.post("/admin/branding/logo", response_model=BrandingRead, status_code=201, tags=["admin"])
async def upload_branding_logo(
    session: Session,
    admin: Annotated[User, Depends(require_roles(Role.SYSTEM_ADMIN))],
    file: UploadFile = File(...),
) -> BrandingRead:
    if file.content_type not in ALLOWED_LOGO_TYPES:
        raise HTTPException(
            status_code=415, detail="Logo must be PNG, JPEG, WEBP or SVG"
        )
    content = await file.read()
    try:
        stored = await storage.put_named(LOGO_OBJECT_KEY, content)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    org = await _get_org_settings(session)
    org.logo_object_key = stored.key
    org.logo_media_type = file.content_type
    org.updated_by_id = admin.id
    await audit(
        session,
        "org_settings",
        org.id,
        "branding_logo_updated",
        admin.id,
        payload={"sha256": stored.sha256, "media_type": file.content_type},
    )
    await session.commit()
    await session.refresh(org)
    return _branding_read(org)


@router.delete("/admin/branding/logo", response_model=BrandingRead, tags=["admin"])
async def remove_branding_logo(
    session: Session,
    admin: Annotated[User, Depends(require_roles(Role.SYSTEM_ADMIN))],
) -> BrandingRead:
    """Clears the logo reference, reverting the UI to the text-initial mark.
    Doesn't delete the stored object itself -- consistent with evidence
    storage elsewhere in this app never deleting on a mere reference
    change, and cheap since put_named() overwrites in place anyway."""
    org = await _get_org_settings(session)
    if org.logo_object_key:
        org.logo_object_key = None
        org.logo_media_type = None
        org.updated_by_id = admin.id
        await audit(session, "org_settings", org.id, "branding_logo_removed", admin.id)
    await session.commit()
    await session.refresh(org)
    return _branding_read(org)
