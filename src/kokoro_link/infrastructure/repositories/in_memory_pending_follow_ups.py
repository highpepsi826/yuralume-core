"""In-memory ``PendingFollowUpRepositoryPort`` adapter.

Used by unit tests and the fake-provider dev path. Asyncio single-
threaded — no locking needed.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from kokoro_link.contracts.pending_follow_up import (
    PendingFollowUpRepositoryPort,
)
from kokoro_link.domain.entities.pending_follow_up import (
    PendingFollowUp,
    PendingFollowUpKind,
    PendingFollowUpStatus,
)


_OPEN_STATUSES: frozenset[str] = frozenset({
    PendingFollowUpStatus.QUEUED.value,
    PendingFollowUpStatus.RESOLVING.value,
})


def _aware(value: datetime) -> datetime:
    """Naive timestamps only reach here from a store that dropped the
    offset; UTC is what every writer meant."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class InMemoryPendingFollowUpRepository(PendingFollowUpRepositoryPort):
    def __init__(self) -> None:
        self._rows: dict[str, PendingFollowUp] = {}

    async def add(self, follow_up: PendingFollowUp) -> PendingFollowUp:
        if (
            follow_up.kind == PendingFollowUpKind.SCHEDULED_PROMISE
            and follow_up.delivery_slot_key
        ):
            matches = [
                row for row in self._rows.values()
                if row.kind == PendingFollowUpKind.SCHEDULED_PROMISE
                and row.delivery_slot_key == follow_up.delivery_slot_key
                and row.status.value in _OPEN_STATUSES
            ]
            if matches:
                matches.sort(key=lambda row: (row.queued_at, row.id))
                canonical = matches[0].merged_scheduled_promise_context(follow_up)
                self._rows[canonical.id] = canonical
                return canonical
        self._rows[follow_up.id] = follow_up
        return follow_up

    async def add_admin_scheduled_promise(
        self, follow_up: PendingFollowUp,
    ) -> bool:
        if follow_up.kind != PendingFollowUpKind.SCHEDULED_PROMISE:
            raise ValueError("admin insert requires a scheduled promise")
        if any(
            row.kind == PendingFollowUpKind.SCHEDULED_PROMISE
            and row.delivery_slot_key == follow_up.delivery_slot_key
            and row.status.value in _OPEN_STATUSES
            for row in self._rows.values()
        ):
            return False
        self._rows[follow_up.id] = follow_up
        return True

    async def save(self, follow_up: PendingFollowUp) -> None:
        self._rows[follow_up.id] = follow_up

    async def save_admin_edit(
        self,
        follow_up: PendingFollowUp,
        *,
        expected_updated_at: datetime,
    ) -> bool:
        current = self._rows.get(follow_up.id)
        if current is None:
            return False
        if current.kind != PendingFollowUpKind.SCHEDULED_PROMISE:
            return False
        if current.status != PendingFollowUpStatus.QUEUED:
            return False
        if _aware(current.updated_at) != _aware(expected_updated_at):
            return False
        if any(
            row.id != follow_up.id
            and row.kind == PendingFollowUpKind.SCHEDULED_PROMISE
            and row.delivery_slot_key == follow_up.delivery_slot_key
            and row.status.value in _OPEN_STATUSES
            for row in self._rows.values()
        ):
            return False
        self._rows[follow_up.id] = follow_up
        return True

    async def get(self, follow_up_id: str) -> PendingFollowUp | None:
        return self._rows.get(follow_up_id)

    async def coalesce_promise_intent(
        self,
        follow_up_id: str,
        *,
        expected_intent: str,
        new_intent: str,
        now: datetime,
    ) -> bool:
        """The SQL adapter's conditional UPDATE, predicate for predicate.

        Single-threaded asyncio, so the swap cannot be interleaved here —
        but the *predicates* still have to be evaluated, because they are
        what the tests covering the racing-audit case assert against, and
        a stub that always said ``True`` would let that race pass in
        tests and lose a claim in production."""
        row = self._rows.get(follow_up_id)
        if row is None:
            return False
        if row.status != PendingFollowUpStatus.QUEUED:
            return False
        if _aware(row.scheduled_for) <= _aware(now):
            return False
        if row.promise_intent != expected_intent:
            return False
        self._rows[follow_up_id] = replace(
            row, promise_intent=new_intent, updated_at=now,
        )
        return True

    async def find_open_for_conversation(
        self, conversation_id: str,
    ) -> PendingFollowUp | None:
        candidates = [
            row for row in self._rows.values()
            if row.conversation_id == conversation_id
            and row.status.value in _OPEN_STATUSES
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda row: row.queued_at, reverse=True)
        return candidates[0]

    async def list_open_for_conversation(
        self, conversation_id: str,
    ) -> list[PendingFollowUp]:
        rows = [
            row for row in self._rows.values()
            if row.conversation_id == conversation_id
            and row.status.value in _OPEN_STATUSES
        ]
        rows.sort(key=lambda row: row.queued_at)
        return rows

    async def list_due(
        self,
        *,
        now: datetime,
        limit: int = 50,
    ) -> list[PendingFollowUp]:
        eligible = [
            row for row in self._rows.values()
            if row.status == PendingFollowUpStatus.QUEUED
            and row.scheduled_for <= now
        ]
        eligible.sort(key=lambda row: row.scheduled_for)
        return eligible[: max(0, limit)]

    async def list_stale_resolving(
        self,
        *,
        now: datetime,
        older_than_seconds: float,
        limit: int = 50,
    ) -> list[PendingFollowUp]:
        cutoff = now - timedelta(seconds=max(0.0, older_than_seconds))
        eligible = [
            row for row in self._rows.values()
            if row.status == PendingFollowUpStatus.RESOLVING
            and row.updated_at < cutoff
        ]
        eligible.sort(key=lambda row: row.updated_at)
        return eligible[: max(0, limit)]

    async def list_open_for_character(
        self, character_id: str,
    ) -> list[PendingFollowUp]:
        return [
            row for row in self._rows.values()
            if row.character_id == character_id
            and row.status.value in _OPEN_STATUSES
        ]

    async def list_open_scheduled_promises(self) -> list[PendingFollowUp]:
        rows = [
            row for row in self._rows.values()
            if row.kind == PendingFollowUpKind.SCHEDULED_PROMISE
            and row.status.value in _OPEN_STATUSES
        ]
        rows.sort(key=lambda row: (row.scheduled_for, row.queued_at, row.id))
        return rows

    async def list_created_since(
        self, conversation_id: str, since: datetime,
    ) -> list[PendingFollowUp]:
        floor = _aware(since)
        rows = [
            row for row in self._rows.values()
            if row.conversation_id == conversation_id
            and _aware(row.queued_at) >= floor
        ]
        rows.sort(key=lambda row: row.queued_at)
        return rows

    async def list_created_by_turn(
        self, conversation_id: str, turn_record_id: str,
    ) -> list[PendingFollowUp]:
        rows = [
            row for row in self._rows.values()
            if row.conversation_id == conversation_id
            and row.turn_record_id == turn_record_id
        ]
        rows.sort(key=lambda row: row.queued_at)
        return rows

    async def delete(self, follow_up_id: str) -> bool:
        return self._rows.pop(follow_up_id, None) is not None

    async def delete_admin_queued_scheduled_promise(
        self,
        follow_up_id: str,
        *,
        expected_updated_at: datetime | None = None,
    ) -> bool:
        current = self._rows.get(follow_up_id)
        if (
            current is None
            or current.kind != PendingFollowUpKind.SCHEDULED_PROMISE
            or current.status != PendingFollowUpStatus.QUEUED
            or (
                expected_updated_at is not None
                and _aware(current.updated_at) != _aware(expected_updated_at)
            )
        ):
            return False
        self._rows.pop(follow_up_id, None)
        return True

    async def delete_for_conversation(self, conversation_id: str) -> int:
        ids = [
            row.id for row in self._rows.values()
            if row.conversation_id == conversation_id
        ]
        for rid in ids:
            self._rows.pop(rid, None)
        return len(ids)

    async def delete_for_character(self, character_id: str) -> int:
        ids = [
            row.id for row in self._rows.values()
            if row.character_id == character_id
        ]
        for rid in ids:
            self._rows.pop(rid, None)
        return len(ids)
