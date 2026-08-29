"""Narrow admin operations for queued scheduled promises.

This service deliberately owns only the queue row.  It does not attempt to
reconcile schedules, story arcs, goals, memories, or chat prose; those surfaces
have their own writers and remain outside this operational escape hatch.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from kokoro_link.contracts.clock import ClockPort, ensure_utc
from kokoro_link.contracts.pending_follow_up import (
    PendingFollowUpRepositoryPort,
)
from kokoro_link.contracts.repositories import (
    CharacterRepositoryPort,
    ConversationRepositoryPort,
)
from kokoro_link.domain.entities.pending_follow_up import (
    PendingFollowUp,
    PendingFollowUpKind,
    PendingFollowUpStatus,
    scheduled_promise_delivery_slot_key,
)

_LOGGER = logging.getLogger(__name__)
_MAX_INTENT_LENGTH = 500


class PendingFollowUpAdminError(ValueError):
    """Base error for an invalid admin queue operation."""


class PendingFollowUpNotFoundError(PendingFollowUpAdminError):
    """The requested character, conversation, or row does not exist."""


class PendingFollowUpStateError(PendingFollowUpAdminError):
    """The row exists but is not editable/deletable in its current state."""


class PendingFollowUpConflictError(PendingFollowUpAdminError):
    """The requested delivery slot is already occupied."""


class PendingFollowUpValidationError(PendingFollowUpAdminError):
    """The request does not satisfy the queue's input invariants."""


class PendingFollowUpAdminService:
    """Application boundary for manual scheduled-promise queue maintenance."""

    def __init__(
        self,
        *,
        repository: PendingFollowUpRepositoryPort,
        character_repository: CharacterRepositoryPort,
        conversation_repository: ConversationRepositoryPort,
        clock: ClockPort | None = None,
        release_enqueuer: Any | None = None,
        release_withdrawer: Any | None = None,
    ) -> None:
        self._repository = repository
        self._characters = character_repository
        self._conversations = conversation_repository
        self._clock = clock
        self._release_enqueuer = release_enqueuer
        self._release_withdrawer = release_withdrawer

    async def list_for_character(
        self, character_id: str,
    ) -> list[PendingFollowUp]:
        """Return all open rows for the admin panel.

        Busy-defer rows remain visible for diagnosis, but only scheduled
        promises are actionable in the UI.
        """
        character_id = self._clean_id(character_id, "character_id")
        await self._require_character(character_id)
        return await self._repository.list_open_for_character(character_id)

    async def create_scheduled_promise(
        self,
        *,
        character_id: str,
        scheduled_for: datetime,
        promise_intent: str,
        conversation_id: str | None = None,
    ) -> PendingFollowUp:
        """Create one operator-authored future scheduled promise."""
        character_id = self._clean_id(character_id, "character_id")
        await self._require_character(character_id)
        now = self._now()
        scheduled = self._future_time(scheduled_for, now)
        intent = self._intent(promise_intent)
        conversation = await self._resolve_conversation(
            character_id,
            conversation_id,
        )
        row = PendingFollowUp.new_promise(
            character_id=character_id,
            conversation_id=conversation.id,
            promise_intent=intent,
            scheduled_for=scheduled,
            # There is no source chat turn for a manual row.  The entity uses
            # the intent as a compact audit message when source text is blank.
            source_message_content="",
            turn_record_id=None,
            commitment_key=None,
            now=now,
        )
        await self._assert_slot_available(row.delivery_slot_key)
        inserted = await self._repository.add_admin_scheduled_promise(row)
        if not inserted:
            raise PendingFollowUpConflictError(
                "delivery slot is already occupied by another scheduled promise",
            )
        await self._enqueue(row, now=now)
        return row

    async def update_scheduled_promise(
        self,
        follow_up_id: str,
        *,
        scheduled_for: datetime | None = None,
        promise_intent: str | None = None,
    ) -> PendingFollowUp:
        """Edit a queued promise's future time and/or intent."""
        follow_up_id = self._clean_id(follow_up_id, "follow_up_id")
        row = await self._require_row(follow_up_id)
        self._ensure_editable(row)
        if scheduled_for is None and promise_intent is None:
            raise PendingFollowUpValidationError(
                "provide scheduled_for and/or promise_intent",
            )
        now = self._now()
        target_time = self._future_time(
            row.scheduled_for if scheduled_for is None else scheduled_for,
            now,
        )
        target_intent = (
            None if promise_intent is None else self._intent(promise_intent)
        )
        candidate = row.with_admin_edit(
            scheduled_for=target_time,
            promise_intent=target_intent,
            now=now,
        )
        await self._assert_slot_available(
            candidate.delivery_slot_key,
            exclude_id=row.id,
        )
        saved = await self._repository.save_admin_edit(
            candidate,
            expected_updated_at=row.updated_at,
        )
        if not saved:
            raise PendingFollowUpConflictError(
                "pending follow-up changed while it was being edited",
            )
        # The old idempotency key contains the old timestamp.  Withdraw first,
        # then mint the new timestamp's key; both operations are fail-soft in
        # the existing release helpers.
        await self._withdraw(row, now=now)
        await self._enqueue(candidate, now=now)
        return candidate

    async def delete_scheduled_promise(self, follow_up_id: str) -> bool:
        """Delete one queued scheduled promise and retire its release jobs."""
        follow_up_id = self._clean_id(follow_up_id, "follow_up_id")
        row = await self._require_row(follow_up_id)
        self._ensure_editable(row)
        deleted = await self._repository.delete_admin_queued_scheduled_promise(
            row.id,
            expected_updated_at=row.updated_at,
        )
        if not deleted:
            current = await self._repository.get(row.id)
            if current is None:
                raise PendingFollowUpNotFoundError("pending follow-up not found")
            raise PendingFollowUpStateError(
                "pending follow-up is no longer a queued scheduled promise",
            )
        await self._withdraw(row, now=self._now())
        return True

    async def _require_character(self, character_id: str) -> object:
        character = await self._characters.get(character_id)
        if character is None:
            raise PendingFollowUpNotFoundError("character not found")
        return character

    async def _resolve_conversation(
        self,
        character_id: str,
        conversation_id: str | None,
    ) -> object:
        if conversation_id is not None and conversation_id.strip():
            conversation = await self._conversations.get(conversation_id.strip())
            if conversation is None:
                raise PendingFollowUpNotFoundError("conversation not found")
            if conversation.character_id != character_id:
                raise PendingFollowUpValidationError(
                    "conversation does not belong to character",
                )
            return conversation

        # Admin-created callbacks may intentionally target Telegram/LINE's
        # latest thread, so ignore the repository's web-only default here.
        try:
            conversation = await self._conversations.latest_for_character(
                character_id,
                source=None,
            )
        except TypeError:
            # Small test doubles and older adapters may not expose ``source``.
            conversation = await self._conversations.latest_for_character(
                character_id,
            )
        if conversation is None:
            raise PendingFollowUpNotFoundError(
                "an existing conversation is required",
            )
        if conversation.character_id != character_id:
            raise PendingFollowUpValidationError(
                "conversation does not belong to character",
            )
        return conversation

    async def _require_row(self, follow_up_id: str) -> PendingFollowUp:
        row = await self._repository.get(follow_up_id)
        if row is None:
            raise PendingFollowUpNotFoundError("pending follow-up not found")
        return row

    async def _assert_slot_available(
        self,
        slot_key: str,
        *,
        exclude_id: str | None = None,
    ) -> None:
        """Provide a useful conflict before the atomic repository guard.

        This read is advisory only; the repository's conditional insert/update
        remains the race-safe authority when two admins submit concurrently.
        """
        rows = await self._repository.list_open_scheduled_promises()
        for row in rows:
            if row.id == exclude_id:
                continue
            existing_key = row.delivery_slot_key or scheduled_promise_delivery_slot_key(
                character_id=row.character_id,
                scheduled_for=row.scheduled_for,
            )
            if existing_key == slot_key:
                raise PendingFollowUpConflictError(
                    "delivery slot is already occupied by another scheduled promise",
                )

    @staticmethod
    def _ensure_editable(row: PendingFollowUp) -> None:
        if row.kind != PendingFollowUpKind.SCHEDULED_PROMISE:
            raise PendingFollowUpStateError(
                "only scheduled promises can be changed here",
            )
        if row.status != PendingFollowUpStatus.QUEUED:
            raise PendingFollowUpStateError(
                "only queued scheduled promises can be changed here",
            )

    async def _enqueue(self, row: PendingFollowUp, *, now: datetime) -> None:
        if self._release_enqueuer is None:
            return
        try:
            await self._release_enqueuer.enqueue(row, now=now)
        except Exception:
            # Queue availability is optional.  The persisted row remains the
            # source of truth and the distributed reconciler can recover it.
            _LOGGER.exception(
                "admin pending-follow-up release enqueue failed id=%s",
                row.id,
            )

    async def _withdraw(self, row: PendingFollowUp, *, now: datetime) -> None:
        if self._release_withdrawer is None:
            return
        try:
            await self._release_withdrawer.withdraw(row, now=now)
        except Exception:
            # The helper itself is fail-soft; this guard also protects custom
            # queue adapters supplied by tests or deployments.
            _LOGGER.exception(
                "admin pending-follow-up release withdraw failed id=%s",
                row.id,
            )

    def _now(self) -> datetime:
        value = self._clock.now() if self._clock is not None else datetime.now(timezone.utc)
        return ensure_utc(value)

    @staticmethod
    def _clean_id(value: str, field_name: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise PendingFollowUpValidationError(
                f"{field_name} must be non-empty",
            )
        return cleaned

    @staticmethod
    def _intent(value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise PendingFollowUpValidationError(
                "promise_intent must be non-empty",
            )
        if len(cleaned) > _MAX_INTENT_LENGTH:
            raise PendingFollowUpValidationError(
                f"promise_intent must be at most {_MAX_INTENT_LENGTH} characters",
            )
        return cleaned

    @staticmethod
    def _future_time(value: datetime, now: datetime) -> datetime:
        if not isinstance(value, datetime):
            raise PendingFollowUpValidationError(
                "scheduled_for must be a datetime",
            )
        if value.tzinfo is None or value.utcoffset() is None:
            raise PendingFollowUpValidationError(
                "scheduled_for must include a timezone",
            )
        normalized = ensure_utc(value)
        if normalized <= now:
            raise PendingFollowUpValidationError(
                "scheduled_for must be in the future",
            )
        return normalized


__all__ = [
    "PendingFollowUpAdminError",
    "PendingFollowUpAdminService",
    "PendingFollowUpConflictError",
    "PendingFollowUpNotFoundError",
    "PendingFollowUpStateError",
    "PendingFollowUpValidationError",
]
