"""Pending-follow-up introspection and narrow admin queue operations.

Lets operators see whether the mechanism is firing — list open rows
per character, see the queued user messages, and (optionally) force a
dispatcher tick now to validate the release path without waiting up to
5 minutes for the next scheduler sweep.

The player-facing character endpoint stays read-only.  Admin CRUD is limited
to queued ``scheduled_promise`` rows; the application service enforces the
state and delivery-slot rules.
"""

from datetime import datetime, timezone
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from kokoro_link.api.dependencies import (
    ensure_owned_character_id,
    get_container,
    require_admin,
)
from kokoro_link.bootstrap.container import ServiceContainer
from kokoro_link.application.services.pending_follow_up_admin_service import (
    PendingFollowUpAdminError,
    PendingFollowUpConflictError,
    PendingFollowUpNotFoundError,
    PendingFollowUpAdminService,
    PendingFollowUpStateError,
)
from kokoro_link.domain.entities.pending_follow_up import (
    PendingFollowUp,
    ScheduledPromiseDuplicateGroup,
    group_open_scheduled_promise_duplicates,
)

router = APIRouter(tags=["pending-follow-ups"])


class PendingFollowUpMessageResponse(BaseModel):
    content: str
    queued_at: datetime


class PendingFollowUpResponse(BaseModel):
    id: str
    character_id: str
    conversation_id: str
    status: str
    brief_reply: str
    defer_reason: str
    scheduled_for: datetime
    queued_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    last_error: str | None = None
    messages: list[PendingFollowUpMessageResponse]

    @classmethod
    def from_domain(cls, row: PendingFollowUp) -> "PendingFollowUpResponse":
        return cls(
            id=row.id,
            character_id=row.character_id,
            conversation_id=row.conversation_id,
            status=row.status.value,
            brief_reply=row.brief_reply,
            defer_reason=row.defer_reason,
            scheduled_for=row.scheduled_for,
            queued_at=row.queued_at,
            updated_at=row.updated_at,
            resolved_at=row.resolved_at,
            last_error=row.last_error,
            messages=[
                PendingFollowUpMessageResponse(
                    content=m.content, queued_at=m.queued_at,
                )
                for m in row.messages
            ],
        )


class PendingFollowUpAdminResponse(PendingFollowUpResponse):
    """Admin-only details; the player response remains backward-compatible."""

    kind: str
    promise_intent: str
    commitment_key: str | None = None

    @classmethod
    def from_domain(cls, row: PendingFollowUp) -> "PendingFollowUpAdminResponse":
        return cls(
            id=row.id,
            character_id=row.character_id,
            conversation_id=row.conversation_id,
            status=row.status.value,
            brief_reply=row.brief_reply,
            defer_reason=row.defer_reason,
            scheduled_for=row.scheduled_for,
            queued_at=row.queued_at,
            updated_at=row.updated_at,
            resolved_at=row.resolved_at,
            last_error=row.last_error,
            messages=[
                PendingFollowUpMessageResponse(
                    content=m.content, queued_at=m.queued_at,
                )
                for m in row.messages
            ],
            kind=row.kind.value,
            promise_intent=row.promise_intent,
            commitment_key=row.commitment_key,
        )


class PendingFollowUpCreateRequest(BaseModel):
    character_id: str = Field(min_length=1, max_length=36)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=36)
    scheduled_for: datetime
    promise_intent: str = Field(min_length=1, max_length=500)


class PendingFollowUpUpdateRequest(BaseModel):
    scheduled_for: datetime | None = None
    promise_intent: str | None = Field(default=None, min_length=1, max_length=500)


class ScheduledPromiseDuplicateRowResponse(BaseModel):
    id: str
    conversation_id: str
    status: str
    queued_at: datetime


class ScheduledPromiseDuplicateGroupResponse(BaseModel):
    """Read-only report item; no queued message body is returned."""

    fingerprint: str
    character_id: str
    promise_intent: str
    scheduled_for: datetime
    canonical_id: str
    duplicate_ids: list[str]
    rows: list[ScheduledPromiseDuplicateRowResponse]

    @classmethod
    def from_domain(
        cls, group: ScheduledPromiseDuplicateGroup,
    ) -> "ScheduledPromiseDuplicateGroupResponse":
        return cls(
            fingerprint=group.dedupe_key,
            character_id=group.character_id,
            promise_intent=group.promise_intent,
            scheduled_for=group.scheduled_for,
            canonical_id=group.canonical.id,
            duplicate_ids=[row.id for row in group.rows[1:]],
            rows=[
                ScheduledPromiseDuplicateRowResponse(
                    id=row.id,
                    conversation_id=row.conversation_id,
                    status=row.status.value,
                    queued_at=row.queued_at,
                )
                for row in group.rows
            ],
        )


@router.get(
    "/admin/pending-follow-ups",
    response_model=list[PendingFollowUpAdminResponse],
)
async def list_due_pending_follow_ups(
    container: ServiceContainer = Depends(get_container),
    _admin: object = Depends(require_admin),
) -> list[PendingFollowUpAdminResponse]:
    """List queued rows whose scheduled_for has passed.

    Same query the dispatcher uses on every tick — useful to confirm
    "are there even any rows to release right now?" without waiting
    for the next tick.
    """
    repo = container.pending_follow_up_repository
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="pending-follow-up repository not wired",
        )
    rows = await repo.list_due(now=datetime.now(tz=timezone.utc))
    return [PendingFollowUpAdminResponse.from_domain(r) for r in rows]


def _admin_service(container: ServiceContainer) -> PendingFollowUpAdminService:
    service = getattr(container, "pending_follow_up_admin_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="pending-follow-up admin service not wired",
        )
    return service


def _raise_admin_error(error: PendingFollowUpAdminError) -> NoReturn:
    if isinstance(error, PendingFollowUpNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, (PendingFollowUpConflictError, PendingFollowUpStateError)):
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=code, detail=str(error)) from error


@router.get(
    "/admin/pending-follow-ups/characters/{character_id}",
    response_model=list[PendingFollowUpAdminResponse],
)
async def list_admin_for_character(
    character_id: str,
    container: ServiceContainer = Depends(get_container),
    _admin: object = Depends(require_admin),
) -> list[PendingFollowUpAdminResponse]:
    try:
        rows = await _admin_service(container).list_for_character(character_id)
    except PendingFollowUpAdminError as exc:
        _raise_admin_error(exc)
    return [PendingFollowUpAdminResponse.from_domain(row) for row in rows]


@router.post(
    "/admin/pending-follow-ups",
    response_model=PendingFollowUpAdminResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_admin_scheduled_promise(
    payload: PendingFollowUpCreateRequest,
    container: ServiceContainer = Depends(get_container),
    _admin: object = Depends(require_admin),
) -> PendingFollowUpAdminResponse:
    try:
        row = await _admin_service(container).create_scheduled_promise(
            character_id=payload.character_id,
            conversation_id=payload.conversation_id,
            scheduled_for=payload.scheduled_for,
            promise_intent=payload.promise_intent,
        )
    except PendingFollowUpAdminError as exc:
        _raise_admin_error(exc)
    return PendingFollowUpAdminResponse.from_domain(row)


@router.patch(
    "/admin/pending-follow-ups/{follow_up_id}",
    response_model=PendingFollowUpAdminResponse,
)
async def update_admin_scheduled_promise(
    follow_up_id: str,
    payload: PendingFollowUpUpdateRequest,
    container: ServiceContainer = Depends(get_container),
    _admin: object = Depends(require_admin),
) -> PendingFollowUpAdminResponse:
    # Pydantic distinguishes an omitted field from an explicit null.  Null is
    # rejected here so a typo cannot silently turn into a no-op edit.
    if "scheduled_for" in payload.model_fields_set and payload.scheduled_for is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="scheduled_for cannot be null",
        )
    if "promise_intent" in payload.model_fields_set and payload.promise_intent is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="promise_intent cannot be null",
        )
    try:
        row = await _admin_service(container).update_scheduled_promise(
            follow_up_id,
            scheduled_for=payload.scheduled_for,
            promise_intent=payload.promise_intent,
        )
    except PendingFollowUpAdminError as exc:
        _raise_admin_error(exc)
    return PendingFollowUpAdminResponse.from_domain(row)


@router.delete(
    "/admin/pending-follow-ups/{follow_up_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_admin_scheduled_promise(
    follow_up_id: str,
    container: ServiceContainer = Depends(get_container),
    _admin: object = Depends(require_admin),
) -> Response:
    try:
        await _admin_service(container).delete_scheduled_promise(follow_up_id)
    except PendingFollowUpAdminError as exc:
        _raise_admin_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/admin/pending-follow-ups/scheduled-promise-duplicates",
    response_model=list[ScheduledPromiseDuplicateGroupResponse],
)
async def report_open_scheduled_promise_duplicates(
    container: ServiceContainer = Depends(get_container),
    _admin: object = Depends(require_admin),
) -> list[ScheduledPromiseDuplicateGroupResponse]:
    """Report existing open duplicate promises without touching any row.

    New rows are protected by the partial unique index. This endpoint exists
    solely for a human review of older blank-key rows before any separately
    approved cleanup is attempted.
    """
    repo = container.pending_follow_up_repository
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="pending-follow-up repository not wired",
        )
    groups = group_open_scheduled_promise_duplicates(
        await repo.list_open_scheduled_promises(),
    )
    return [ScheduledPromiseDuplicateGroupResponse.from_domain(group) for group in groups]


@router.get(
    "/characters/{character_id}/pending-follow-ups",
    response_model=list[PendingFollowUpResponse],
)
async def list_open_for_character(
    character_id: str,
    container: ServiceContainer = Depends(get_container),
    _owned_character_id: str = Depends(ensure_owned_character_id),
) -> list[PendingFollowUpResponse]:
    """List every open (queued or resolving) row for the character.

    Includes rows whose ``scheduled_for`` is still in the future —
    useful right after sending a test message to confirm a row was
    queued by ``ChatService``.
    """
    repo = container.pending_follow_up_repository
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="pending-follow-up repository not wired",
        )
    rows = await repo.list_open_for_character(character_id)
    return [PendingFollowUpResponse.from_domain(r) for r in rows]


class TickResponse(BaseModel):
    resolved: int


@router.post(
    "/admin/pending-follow-ups/tick",
    response_model=TickResponse,
)
async def trigger_tick(
    container: ServiceContainer = Depends(get_container),
    _admin: object = Depends(require_admin),
) -> TickResponse:
    """Run one dispatcher pass right now.

    Skips the 5-minute scheduler wait so a manual end-to-end test
    (defer → wait 30s → release) doesn't take 5 minutes. The dispatcher
    still applies its double-gate (scheduled_for + current busy_score),
    so calling this on a row whose scheduled_for is still in the future
    is a no-op.
    """
    dispatcher = container.pending_follow_up_dispatcher
    if dispatcher is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="pending-follow-up dispatcher not wired",
        )
    resolved = await dispatcher.tick()
    return TickResponse(resolved=resolved)
