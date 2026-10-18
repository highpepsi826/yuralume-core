from __future__ import annotations

import pytest
import asyncio

from kokoro_link.application.services.prompt_customization_service import (
    PromptCustomizationService,
    normalise_prompt_customizations,
    AdminPromptTemplateRefresher,
)
from kokoro_link.infrastructure.prompts.loader import get_default_loader, set_admin_template_overrides


@pytest.fixture(autouse=True)
def clear_admin_snapshot():
    set_admin_template_overrides({})
    yield
    set_admin_template_overrides({})
from kokoro_link.infrastructure.repositories.in_memory_preferences import (
    InMemoryPreferencesRepository,
)


@pytest.mark.asyncio
async def test_player_and_admin_blocks_are_bounded_and_ordered() -> None:
    service = PromptCustomizationService(InMemoryPreferencesRepository())
    name = "chat/instructions_footer_style"
    default = (await service.get_template(name=name, user_id="owner", admin=False))["default_content"]
    admin_value = default + "\nUse concise language."
    player_value = default + "\nUse playful language."
    await service.set_template(name=name, content=admin_value, user_id="admin", admin=True)
    await service.set_template(name=name, content=player_value, user_id="owner", admin=False)

    effective = await service.effective_overrides(user_id="owner")

    assert effective[name] == player_value.strip() + "\n"
    assert (await service.effective_overrides(user_id="other"))[name] == admin_value.strip() + "\n"


def test_rejects_unknown_surface_and_control_characters() -> None:
    with pytest.raises(ValueError, match="unknown"):
        normalise_prompt_customizations({"system": "override"})
    with pytest.raises(ValueError, match="control"):
        normalise_prompt_customizations({"chat/instructions_footer_style": "hello\x00there"})


@pytest.mark.asyncio
async def test_player_cannot_access_admin_only_template() -> None:
    service = PromptCustomizationService(InMemoryPreferencesRepository())

    with pytest.raises(ValueError, match="not available"):
        await service.get_template(
            name="proactive/intention_judge", user_id="owner", admin=False,
        )

    templates = await service.list_templates(user_id="owner", admin=False)
    assert templates
    assert all(item["player_editable"] for item in templates)


@pytest.mark.asyncio
async def test_template_override_rejects_changed_placeholders() -> None:
    service = PromptCustomizationService(InMemoryPreferencesRepository())
    name = "feed/composer_style"
    default = (await service.get_template(name=name, user_id="owner", admin=False))["default_content"]

    with pytest.raises(ValueError, match="variables"):
        await service.set_template(
            name=name,
            content=default + "${unexpected}\n",
            user_id="owner",
            admin=False,
        )


@pytest.mark.asyncio
async def test_admin_background_snapshot_refresh_and_player_reset() -> None:
    repo = InMemoryPreferencesRepository()
    writer = PromptCustomizationService(repo)
    reader = PromptCustomizationService(repo)
    name = "chat/instructions_footer_style"
    await writer.set_template(name=name, content="admin style", user_id="admin", admin=True)
    await writer.set_template(name=name, content="player style", user_id="owner", admin=False)
    reset = await writer.set_template(name=name, content="", user_id="owner", admin=False)
    assert reset["content"] == "admin style\n"
    assert not reset["overridden"]
    set_admin_template_overrides({})
    refresher = AdminPromptTemplateRefresher(reader, interval=0.01)
    await refresher.start()
    try:
        assert get_default_loader().render(name) == "admin style"
        await repo.set("admin_prompt_template_overrides", {name: "refreshed style\n"})
        for _ in range(20):
            if get_default_loader().render(name) == "refreshed style":
                break
            await asyncio.sleep(0.01)
        assert get_default_loader().render(name) == "refreshed style"
    finally:
        await refresher.stop()


@pytest.mark.asyncio
async def test_player_bulk_set_cannot_write_core_template() -> None:
    service = PromptCustomizationService(InMemoryPreferencesRepository())
    with pytest.raises(ValueError, match="not available"):
        await service.set_player(user_id="owner", values={"proactive/intention_judge": "override"})


@pytest.mark.asyncio
async def test_template_override_rejects_invalid_template_syntax() -> None:
    service = PromptCustomizationService(InMemoryPreferencesRepository())
    name = "chat/instructions_footer_style"
    default = (await service.get_template(name=name, user_id="owner", admin=False))["default_content"]

    with pytest.raises(ValueError, match="invalid prompt template syntax"):
        await service.set_template(
            name=name,
            content=default + "\n$\n",
            user_id="owner",
            admin=False,
        )
