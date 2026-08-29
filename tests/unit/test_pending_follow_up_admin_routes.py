"""Route-contract tests for admin scheduled-promise CRUD."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from kokoro_link.api.routes.pending_follow_ups import (
    PendingFollowUpAdminResponse,
    PendingFollowUpCreateRequest,
    PendingFollowUpResponse,
    PendingFollowUpUpdateRequest,
    create_admin_scheduled_promise,
    delete_admin_scheduled_promise,
    list_admin_for_character,
    update_admin_scheduled_promise,
)
from kokoro_link.application.services.pending_follow_up_admin_service import (
    PendingFollowUpStateError,
)
from kokoro_link.domain.entities.pending_follow_up import PendingFollowUp


SCHEDULED = datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc)


def _row() -> PendingFollowUp:
    return PendingFollowUp.new_promise(
        character_id="char-1",
        conversation_id="conv-1",
        promise_intent="提醒玩家帶卡",
        scheduled_for=SCHEDULED,
        source_message_content="記得提醒我帶卡",
        commitment_key="meeting-card",
        now=datetime(2026, 8, 30, 9, 0, tzinfo=timezone.utc),
    )


class StubAdminService:
    def __init__(self, row: PendingFollowUp) -> None:
        self.row = row
        self.deleted: list[str] = []

    async def list_for_character(self, character_id: str):  # noqa: ANN202
        assert character_id == self.row.character_id
        return [self.row]

    async def create_scheduled_promise(self, **kwargs):  # noqa: ANN003, ANN202
        assert kwargs["character_id"] == self.row.character_id
        return self.row

    async def update_scheduled_promise(
        self, follow_up_id: str, **kwargs,  # noqa: ANN003
    ) -> PendingFollowUp:
        assert follow_up_id == self.row.id
        assert kwargs["promise_intent"] == "更新後"
        return self.row

    async def delete_scheduled_promise(self, follow_up_id: str) -> bool:
        self.deleted.append(follow_up_id)
        return True


def _container(service: object) -> SimpleNamespace:
    return SimpleNamespace(pending_follow_up_admin_service=service)


def test_player_response_shape_stays_read_only_compatible() -> None:
    row = _row()
    player = PendingFollowUpResponse.from_domain(row).model_dump()
    admin = PendingFollowUpAdminResponse.from_domain(row).model_dump()

    assert "kind" not in player
    assert "promise_intent" not in player
    assert "commitment_key" not in player
    assert admin["kind"] == "scheduled_promise"
    assert admin["promise_intent"] == "提醒玩家帶卡"
    assert admin["commitment_key"] == "meeting-card"


@pytest.mark.asyncio
async def test_admin_list_create_update_delete_contracts() -> None:
    row = _row()
    service = StubAdminService(row)
    container = _container(service)

    listed = await list_admin_for_character(
        "char-1", container=container, _admin=object(),
    )
    assert [item.id for item in listed] == [row.id]

    created = await create_admin_scheduled_promise(
        PendingFollowUpCreateRequest(
            character_id="char-1",
            scheduled_for=SCHEDULED,
            promise_intent="提醒玩家帶卡",
        ),
        container=container,
        _admin=object(),
    )
    assert created.id == row.id

    updated = await update_admin_scheduled_promise(
        row.id,
        PendingFollowUpUpdateRequest(promise_intent="更新後"),
        container=container,
        _admin=object(),
    )
    assert updated.id == row.id

    response = await delete_admin_scheduled_promise(
        row.id,
        container=container,
        _admin=object(),
    )
    assert response.status_code == 204
    assert service.deleted == [row.id]


@pytest.mark.asyncio
async def test_admin_route_maps_state_conflict_to_http_409() -> None:
    class RefusingService(StubAdminService):
        async def update_scheduled_promise(
            self, follow_up_id: str, **kwargs,  # noqa: ANN003
        ) -> PendingFollowUp:
            raise PendingFollowUpStateError("only queued rows can be changed")

    row = _row()
    with pytest.raises(HTTPException) as captured:
        await update_admin_scheduled_promise(
            row.id,
            PendingFollowUpUpdateRequest(promise_intent="更新後"),
            container=_container(RefusingService(row)),
            _admin=object(),
        )

    assert captured.value.status_code == 409
