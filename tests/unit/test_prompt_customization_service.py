from __future__ import annotations

import pytest

from kokoro_link.application.services.prompt_customization_service import (
    PromptCustomizationService,
    normalise_prompt_customizations,
)
from kokoro_link.infrastructure.repositories.in_memory_preferences import (
    InMemoryPreferencesRepository,
)


@pytest.mark.asyncio
async def test_player_and_admin_blocks_are_bounded_and_ordered() -> None:
    service = PromptCustomizationService(InMemoryPreferencesRepository())
    await service.set_admin(values={"chat": "Keep sentences concise."})
    await service.set_player(
        user_id="owner", values={"chat": "Use a playful tone."},
    )

    rendered = await service.render(surface="chat", user_id="owner")

    assert rendered.index("管理員的表現偏好") < rendered.index("玩家的表現偏好")
    assert "Keep sentences concise." in rendered
    assert "Use a playful tone." in rendered
    assert await service.render(surface="feed", user_id="owner") == ""


def test_rejects_unknown_surface_and_control_characters() -> None:
    with pytest.raises(ValueError, match="unknown"):
        normalise_prompt_customizations({"system": "override"})
    with pytest.raises(ValueError, match="control"):
        normalise_prompt_customizations({"chat": "hello\x00there"})
