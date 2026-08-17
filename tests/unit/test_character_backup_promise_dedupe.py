"""Backup restore coverage for scheduled-promise dedupe identities."""

from __future__ import annotations

from datetime import datetime, timezone

from kokoro_link.application.dto.character_backup import (
    BACKUP_TABLE_RULES_BY_NAME,
)
from kokoro_link.application.services.character_backup_restore_pipeline import (
    CharacterRestorePipeline,
    RestoreContext,
)
from kokoro_link.domain.entities.pending_follow_up import (
    scheduled_promise_delivery_slot_key,
    scheduled_promise_dedupe_key,
)
from kokoro_link.infrastructure.storage.in_memory import InMemoryObjectStorage


NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


def _context() -> RestoreContext:
    return RestoreContext(
        new_character_id="new-character",
        old_character_id="old-character",
        importer_id="operator",
        id_map={},
        old_operator_ids=set(),
        url_map={},
        transfers={},
    )


def _promise(*, row_id: str, dedupe_key: str) -> dict:
    return {
        "id": row_id,
        "character_id": "old-character",
        "conversation_id": "conversation-1",
        "status": "queued",
        "scheduled_for": NOW,
        "queued_at": NOW,
        "updated_at": NOW,
        "kind": "scheduled_promise",
        "promise_intent": "回家後傳照片給你。",
        "dedupe_key": dedupe_key,
    }


def test_restore_rekeys_open_promises_for_the_new_character() -> None:
    pipeline = CharacterRestorePipeline(
        object_storage=InMemoryObjectStorage(), cloud_mode=False,
    )
    context = _context()
    rule = BACKUP_TABLE_RULES_BY_NAME["pending_follow_ups"]
    source_key = scheduled_promise_dedupe_key(
        character_id="old-character",
        promise_intent="回家後傳照片給你。",
        scheduled_for=NOW,
    )

    first, _ = pipeline._prepare_row(  # noqa: SLF001
        rule, _promise(row_id="promise-1", dedupe_key=source_key), {}, context,
    )
    duplicate, _ = pipeline._prepare_row(  # noqa: SLF001
        rule, _promise(row_id="promise-2", dedupe_key=source_key), {}, context,
    )

    expected = scheduled_promise_dedupe_key(
        character_id="new-character",
        promise_intent="回家後傳照片給你。",
        scheduled_for=NOW,
    )
    expected_delivery_slot = scheduled_promise_delivery_slot_key(
        character_id="new-character",
        scheduled_for=NOW,
    )
    assert first["character_id"] == "new-character"
    assert first["dedupe_key"] == expected
    assert first["dedupe_key"] != source_key
    assert first["delivery_slot_key"] == expected_delivery_slot
    # The old exact key remains useful audit data. Only the new delivery-slot
    # key is constrained, so a legacy duplicate lands without violating the
    # target database's partial unique index.
    assert duplicate["dedupe_key"] == expected
    assert duplicate["delivery_slot_key"] == ""
