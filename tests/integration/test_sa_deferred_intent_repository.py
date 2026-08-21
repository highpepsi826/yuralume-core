from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import sessionmaker

from kokoro_link.domain.entities.character import Character
from kokoro_link.domain.entities.deferred_intent import (
    REVISIT_GRACE_MINUTES,
    DeferredIntent,
)
from kokoro_link.domain.entities.operator_profile import DEFAULT_OPERATOR_ID
from kokoro_link.domain.value_objects.character_state import CharacterState
from kokoro_link.infrastructure.persistence.sa_character_repository import (
    SACharacterRepository,
)
from kokoro_link.infrastructure.persistence.sa_deferred_intent_repository import (
    SADeferredIntentRepository,
)


async def _create_character(session_factory: sessionmaker) -> str:
    character = Character.create(
        name="Mio",
        summary="",
        personality=[],
        interests=[],
        speaking_style="",
        boundaries=[],
        state=CharacterState(
            emotion="neutral",
            affection=50,
            fatigue=0,
            trust=50,
            energy=100,
        ),
    )
    await SACharacterRepository(session_factory).save(character)
    return character.id


@pytest.mark.asyncio
async def test_semantically_identical_active_intent_is_replaced_in_place(
    session_factory: sessionmaker,
) -> None:
    character_id = await _create_character(session_factory)
    repository = SADeferredIntentRepository(session_factory)
    created_at = datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc)
    first = DeferredIntent.new(
        character_id=character_id,
        operator_id=DEFAULT_OPERATOR_ID,
        trigger="tick",
        inner_motive="想在約定時間提醒使用者",
        conversation_purpose="提醒 喝水",
        expected_reply="知道了",
        now=created_at,
    )
    stored = await repository.upsert_active_semantically_identical(
        first,
        now=created_at,
    )

    replacement = DeferredIntent.new(
        character_id=character_id,
        operator_id=DEFAULT_OPERATOR_ID,
        trigger="manual",
        inner_motive="更新後的提醒動機",
        conversation_purpose="  提醒   喝水  ",
        expected_reply="謝謝提醒",
        revisit_at=created_at + timedelta(days=2),
        now=created_at + timedelta(minutes=10),
    )
    updated = await repository.upsert_active_semantically_identical(
        replacement,
        now=created_at + timedelta(minutes=10),
    )

    active = await repository.list_active_for(
        character_id,
        DEFAULT_OPERATOR_ID,
        now=created_at + timedelta(minutes=10),
    )
    assert len(active) == 1
    assert updated.id == stored.id == first.id
    assert updated.created_at == stored.created_at
    assert updated.inner_motive == "更新後的提醒動機"
    assert updated.expected_reply == "謝謝提醒"
    assert updated.revisit_at == replacement.revisit_at
    assert updated.expires_at == replacement.revisit_at + timedelta(
        minutes=REVISIT_GRACE_MINUTES,
    )
    assert active[0] == updated
