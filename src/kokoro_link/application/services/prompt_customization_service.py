"""Prompt Studio template overrides, scoped by player/admin authority."""

from __future__ import annotations

import logging
import asyncio
from collections.abc import Mapping
from typing import Final

from kokoro_link.application.services.scoped_preferences import (
    user_preference_key,
    set_user_preference,
)
from kokoro_link.contracts.repositories import PreferencesRepositoryPort
from kokoro_link.infrastructure.prompts.registry import (
    prompt_template_catalog,
    template_default,
    validate_template_override,
)
from kokoro_link.infrastructure.prompts.loader import set_admin_template_overrides

_LOGGER = logging.getLogger(__name__)

PLAYER_PROMPT_CUSTOMIZATION_KEY: Final = "player_prompt_template_overrides"
ADMIN_PROMPT_CUSTOMIZATION_KEY: Final = "admin_prompt_template_overrides"


def normalise_prompt_customizations(value: object) -> dict[str, str]:
    """Validate an override map of registered logical template names."""
    if not isinstance(value, Mapping):
        raise ValueError("prompt template overrides must be an object")
    catalog = prompt_template_catalog()
    unknown = set(value) - set(catalog)
    if unknown:
        raise ValueError(f"unknown prompt templates: {', '.join(sorted(unknown))}")
    cleaned: dict[str, str] = {}
    for name, raw in value.items():
        text = validate_template_override(name, raw)
        if text:
            cleaned[name] = text
    return cleaned


class PromptCustomizationService:
    def __init__(self, preferences: PreferencesRepositoryPort) -> None:
        self._preferences = preferences

    async def get_player(self, *, user_id: str) -> dict[str, str]:
        return await self._read(PLAYER_PROMPT_CUSTOMIZATION_KEY, user_id=user_id)

    async def set_player(self, *, user_id: str, values: object) -> dict[str, str]:
        catalog = prompt_template_catalog()
        if isinstance(values, Mapping) and any(
            name in catalog and not catalog[name].player_editable for name in values
        ):
            raise ValueError("prompt template is not available")
        cleaned = normalise_prompt_customizations(values)
        await set_user_preference(
            self._preferences, PLAYER_PROMPT_CUSTOMIZATION_KEY, cleaned,
            user_id=user_id,
        )
        return cleaned

    async def get_admin(self) -> dict[str, str]:
        return await self._read(ADMIN_PROMPT_CUSTOMIZATION_KEY, user_id=None)

    async def set_admin(self, *, values: object) -> dict[str, str]:
        cleaned = normalise_prompt_customizations(values)
        await self._preferences.set(ADMIN_PROMPT_CUSTOMIZATION_KEY, cleaned)
        set_admin_template_overrides(cleaned)
        return cleaned

    async def list_templates(self, *, user_id: str, admin: bool) -> list[dict]:
        overrides = await (self.get_admin() if admin else self.get_player(user_id=user_id))
        return [
            {
                "name": item.name, "title": item.title, "category": item.category,
                "player_editable": item.player_editable, "important": item.important,
                "impact": item.impact, "variables": item.variables,
                "overridden": item.name in overrides,
            }
            for item in prompt_template_catalog().values()
            if admin or item.player_editable
        ]

    async def get_template(self, *, name: str, user_id: str, admin: bool) -> dict:
        item = prompt_template_catalog().get(name)
        if item is None or (not admin and not item.player_editable):
            raise ValueError("prompt template is not available")
        overrides = await (self.get_admin() if admin else self.get_player(user_id=user_id))
        default = template_default(name)
        if not admin:
            default = (await self.get_admin()).get(name, default)
        return {
            "name": name, "title": item.title, "category": item.category,
            "player_editable": item.player_editable,
            "important": item.important, "impact": item.impact,
            "variables": item.variables, "default_content": default,
            "content": overrides.get(name, default), "overridden": name in overrides,
        }

    async def set_template(
        self, *, name: str, content: object, user_id: str, admin: bool,
    ) -> dict:
        item = prompt_template_catalog().get(name)
        if item is None or (not admin and not item.player_editable):
            raise ValueError("prompt template is not available")
        cleaned = validate_template_override(name, content)
        key = ADMIN_PROMPT_CUSTOMIZATION_KEY if admin else PLAYER_PROMPT_CUSTOMIZATION_KEY
        current = await (self.get_admin() if admin else self.get_player(user_id=user_id))
        if cleaned:
            current[name] = cleaned
        else:
            current.pop(name, None)
        if admin:
            await self._preferences.set(key, current)
            set_admin_template_overrides(current)
        else:
            await set_user_preference(self._preferences, key, current, user_id=user_id)
        return await self.get_template(name=name, user_id=user_id, admin=admin)

    async def effective_overrides(
        self, *, user_id: str | None = None,
    ) -> dict[str, str]:
        """Admin defaults plus a player's permitted template overrides."""
        admin = await self.get_admin()
        if not user_id:
            return admin
        player = await self.get_player(user_id=user_id)
        catalog = prompt_template_catalog()
        return {
            **admin,
            **{
                name: value for name, value in player.items()
                if catalog[name].player_editable
            },
        }

    async def _read(self, key: str, *, user_id: str | None) -> dict[str, str]:
        raw = await self._preferences.get(
            user_preference_key(user_id, key) if user_id else key,
        )
        if raw is None:
            return {}
        try:
            return normalise_prompt_customizations(raw)
        except ValueError:
            _LOGGER.warning("ignoring invalid stored prompt customization key=%s", key)
            return {}


class AdminPromptTemplateRefresher:
    """Load global admin templates in every API/coordinator/worker/connector process."""

    def __init__(self, service: PromptCustomizationService, interval: float = 10) -> None:
        self._service = service
        self._interval = interval
        self._task: asyncio.Task | None = None

    async def refresh(self) -> None:
        try:
            set_admin_template_overrides(await self._service.get_admin())
        except Exception:
            _LOGGER.warning("admin prompt refresh failed; retaining last snapshot", exc_info=True)

    async def start(self) -> None:
        await self.refresh()
        self._task = asyncio.create_task(self._run(), name="admin-prompt-template-refresh")

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self.refresh()

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
