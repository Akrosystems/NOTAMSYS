import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent, Notam, NotamKind, NotamRequest, Role, User, WorkflowStatus
from app.schemas import NotamDraftCreate
from app.services import qline
from app.services.aip.provider import default_provider
from app.services.aixm.builder import build_event_xml
from app.services.formatter import build_aixm_event, format_notam
from app.services.rules import RULESET_VERSION, validate_selection

TRANSITIONS: dict[WorkflowStatus, set[WorkflowStatus]] = {
    WorkflowStatus.RECEIVED: {WorkflowStatus.TRIAGE, WorkflowStatus.REJECTED},
    WorkflowStatus.TRIAGE: {WorkflowStatus.DRAFT, WorkflowStatus.REJECTED},
    WorkflowStatus.DRAFT: {WorkflowStatus.REVIEW, WorkflowStatus.CANCELLED},
    WorkflowStatus.REVIEW: {
        WorkflowStatus.CHANGES_REQUESTED,
        WorkflowStatus.APPROVED,
        WorkflowStatus.REJECTED,
    },
    WorkflowStatus.CHANGES_REQUESTED: {WorkflowStatus.DRAFT},
    WorkflowStatus.APPROVED: {WorkflowStatus.PUBLISHING},
    WorkflowStatus.PUBLISHING: {WorkflowStatus.PUBLISHED, WorkflowStatus.APPROVED},
    WorkflowStatus.PUBLISHED: {WorkflowStatus.CANCELLED},
    WorkflowStatus.REJECTED: set(),
    WorkflowStatus.CANCELLED: set(),
}


async def audit(
    session: AsyncSession,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    actor_id: uuid.UUID,
    from_state: WorkflowStatus | None = None,
    to_state: WorkflowStatus | None = None,
    payload: dict[str, object] | None = None,
) -> None:
    session.add(
        AuditEvent(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_id=actor_id,
            from_state=from_state.value if from_state else None,
            to_state=to_state.value if to_state else None,
            payload=payload or {},
        )
    )


async def transition_request(
    session: AsyncSession,
    request: NotamRequest,
    target: WorkflowStatus,
    actor: User,
    action: str,
    payload: dict[str, object] | None = None,
) -> None:
    if target not in TRANSITIONS[request.status]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invalid workflow transition: {request.status.value} -> {target.value}",
        )
    previous = request.status
    request.status = target
    await audit(session, "notam_request", request.id, action, actor.id, previous, target, payload)


async def next_serial(session: AsyncSession, series: str, year: int) -> int:
    current = await session.scalar(
        select(func.max(Notam.serial_number)).where(Notam.series == series, Notam.year == year)
    )
    return int(current or 0) + 1


async def create_draft(
    session: AsyncSession,
    request: NotamRequest,
    draft: NotamDraftCreate,
    actor: User,
) -> Notam:
    if actor.role not in {Role.AIS_OFFICER, Role.AIS_SPECIALIST, Role.NOF_MANAGER}:
        raise HTTPException(status_code=403, detail="Only AIS operations staff can prepare NOTAM")
    if request.status == WorkflowStatus.RECEIVED:
        await transition_request(session, request, WorkflowStatus.TRIAGE, actor, "triage_started")
    if request.status == WorkflowStatus.TRIAGE:
        await transition_request(session, request, WorkflowStatus.DRAFT, actor, "draft_started")
    if request.status == WorkflowStatus.CHANGES_REQUESTED:
        await transition_request(
            session, request, WorkflowStatus.DRAFT, actor, "draft_revision_started"
        )
    if request.status not in {WorkflowStatus.DRAFT, WorkflowStatus.CHANGES_REQUESTED}:
        raise HTTPException(status_code=409, detail="Request is not available for preparation")

    subject, condition = draft.q_code[1:3], draft.q_code[3:5]
    validation = validate_selection(
        subject, condition, draft.traffic, draft.purpose, draft.scope, draft.kind
    )
    warnings = list(validation["warnings"])
    if len(draft.item_a) == 4 and draft.item_a.isalpha():
        try:
            aerodromes = await default_provider().list_aerodromes(session)
        except NotImplementedError:
            aerodromes = []
        known_codes = {aerodrome.icao_code for aerodrome in aerodromes}
        if known_codes and draft.item_a.upper() not in known_codes:
            warnings.append(
                f"Item A location indicator {draft.item_a.upper()} was not found in the "
                "active AIP reference dataset -- confirm it is correct before approval"
            )
    validation["warnings"] = warnings

    errors = list(validation["errors"])
    errors.extend(qline.validate_purpose(draft.purpose))
    errors.extend(qline.validate_item_d(draft.item_d))
    replaced_identifier: str | None = None
    if draft.kind in {NotamKind.REPLACE, NotamKind.CANCEL}:
        if not draft.replaces_notam_id:
            errors.append("NOTAMR and NOTAMC must reference exactly one active NOTAM")
        else:
            replaced_notam = await session.get(Notam, draft.replaces_notam_id)
            if replaced_notam is None:
                errors.append("Referenced NOTAM for NOTAMR/NOTAMC was not found")
            else:
                replaced_identifier = replaced_notam.identifier
    if draft.kind == NotamKind.NEW and draft.replaces_notam_id:
        errors.append("NOTAMN must not reference another NOTAM")
    if draft.item_c and draft.item_c <= draft.item_b:
        errors.append("Item C must be later than Item B")
    if draft.item_c_qualifier == "EST" and not draft.item_c:
        errors.append("EST requires a date-time in Item C")
    if errors:
        raise HTTPException(
            status_code=422, detail={"message": "Draft failed validation", "errors": errors}
        )

    now = datetime.now(UTC)
    serial = await next_serial(session, draft.series.value, now.year)
    formatted = format_notam(draft, serial, now.year, replaced_identifier=replaced_identifier)
    identifier = f"{draft.series.value}{serial:04d}/{now.year % 100:02d}"
    aixm_xml = build_event_xml(draft, identifier)
    notam = request.notam
    if notam is None:
        notam = Notam(
            request_id=request.id,
            series=draft.series,
            kind=draft.kind,
            serial_number=serial,
            year=now.year,
            prepared_by_id=actor.id,
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
            replaces_notam_id=draft.replaces_notam_id,
            formatted_message=formatted,
            validation_result=validation,
            ruleset_version=RULESET_VERSION,
            aixm_payload=build_aixm_event(draft, identifier),
            aixm_xml=aixm_xml,
        )
        session.add(notam)
    else:
        for field, value in draft.model_dump().items():
            if hasattr(notam, field):
                setattr(notam, field, value)
        notam.formatted_message = formatted
        notam.validation_result = validation
        notam.aixm_payload = build_aixm_event(draft, identifier)
        notam.aixm_xml = aixm_xml
        notam.prepared_by_id = actor.id
    await session.flush()
    await audit(
        session,
        "notam",
        notam.id,
        "draft_saved",
        actor.id,
        payload={"identifier": identifier, "ruleset": RULESET_VERSION},
    )
    return notam
