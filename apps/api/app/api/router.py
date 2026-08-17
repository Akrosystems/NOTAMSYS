import uuid
from dataclasses import asdict
from datetime import UTC, datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_session
from app.core.security import create_token, hash_password, verify_password
from app.dependencies import get_current_user, require_roles
from app.models import (
    Aerodrome,
    Attachment,
    AuditEvent,
    ExtractedField,
    ExtractionRun,
    Fir,
    Notam,
    NotamRequest,
    OrgSettings,
    PublicationDelivery,
    RequestSource,
    Role,
    RuleVersion,
    User,
    WorkflowStatus,
)
from app.schemas import (
    AerodromeRead,
    AipDatasetRead,
    AttachmentRead,
    BrandingRead,
    BrandingUpdate,
    DashboardSummary,
    ExtractedFieldRead,
    ExtractionRunRead,
    FieldAcceptRequest,
    FirRead,
    LoginRequest,
    NotamDraftCreate,
    NotamRead,
    NotamRequestCreate,
    PublicationDeliveryRead,
    RequestRead,
    ReviewAction,
    RuleVersionRead,
    TokenPair,
    UserCreate,
    UserRead,
    UserUpdate,
    ValidationRequest,
)
from app.services.aip.provider import default_provider
from app.services.extraction.orchestrator import run_extraction
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
        "originator_email": str(payload.originator_email) if payload.originator_email else None,
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


@router.get(
    "/requests/{request_id}/notam", response_model=NotamRead | None, tags=["notams"]
)
async def get_request_notam(
    request_id: uuid.UUID, session: Session, _: CurrentUser
) -> Notam | None:
    """The prepared NOTAM for a request, once one exists. saveDraft (POST
    .../draft) both creates and updates the draft but only works while the
    request is in DRAFT/CHANGES_REQUESTED -- this is the read path for every
    later stage (review, approved, publishing, published) where the UI needs
    to show what was prepared without being able to re-trigger drafting."""
    request = await session.scalar(
        select(NotamRequest)
        .options(selectinload(NotamRequest.notam))
        .where(NotamRequest.id == request_id)
    )
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return request.notam


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

    simulated = settings.publication_mode == "simulated_sync"
    for delivery in deliveries:
        await dispatch_delivery(session, delivery, request.notam, simulated=simulated)

    if any(delivery.status == "failed" for delivery in deliveries):
        await transition_request(
            session,
            request,
            WorkflowStatus.APPROVED,
            user,
            "publication_failed",
            payload={
                "failed_channels": [d.channel for d in deliveries if d.status == "failed"]
            },
        )
    elif all(delivery.status == "acknowledged" for delivery in deliveries):
        request.notam.published_at = datetime.now(UTC)
        await transition_request(
            session, request, WorkflowStatus.PUBLISHED, user, "publication_completed"
        )
    # Otherwise one or more channels are "sent" (dispatched, awaiting
    # acknowledgement) with none failed -- the request stays PUBLISHING
    # until a retry (see /deliveries/{id}/retry) resolves them.
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
    user: Annotated[User, Depends(require_roles(Role.NOF_MANAGER))],
) -> PublicationDelivery:
    delivery = await session.get(PublicationDelivery, delivery_id)
    if delivery is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    notam = await session.get(Notam, delivery.notam_id)
    if notam is None:
        raise HTTPException(status_code=404, detail="NOTAM not found")
    simulated = settings.publication_mode == "simulated_sync"
    await dispatch_delivery(session, delivery, notam, simulated=simulated)
    await audit(
        session,
        "publication_delivery",
        delivery.id,
        "delivery_retried",
        user.id,
        payload={"channel": delivery.channel, "status": delivery.status},
    )

    request = await session.scalar(
        select(NotamRequest)
        .options(selectinload(NotamRequest.notam))
        .where(NotamRequest.id == notam.request_id)
    )
    if request is not None and request.status == WorkflowStatus.PUBLISHING:
        siblings = list(
            await session.scalars(
                select(PublicationDelivery).where(PublicationDelivery.notam_id == notam.id)
            )
        )
        if any(sibling.status == "failed" for sibling in siblings):
            await transition_request(
                session, request, WorkflowStatus.APPROVED, user, "publication_failed"
            )
        elif all(sibling.status == "acknowledged" for sibling in siblings):
            notam.published_at = datetime.now(UTC)
            await transition_request(
                session, request, WorkflowStatus.PUBLISHED, user, "publication_completed"
            )
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
) -> list[dict[str, object]]:
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
    return {
        "environment": settings.environment,
        "ocr_engine": settings.ocr_engine,
        "extraction_enabled": settings.extraction_enabled,
        "publication_mode": settings.publication_mode,
        "aip_provider": settings.aip_provider,
        "storage_backend": settings.storage_backend,
        "public_intake_enabled": settings.public_intake_enabled,
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
        requests_in_queue=int(queue or 0),
        awaiting_specialist=int(review or 0),
        published_today=int(published or 0),
        estimated_due=int(estimated_due or 0),
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
