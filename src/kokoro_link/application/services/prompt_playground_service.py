"""Read-only Prompt Studio comparison runs.

This service deliberately bypasses :class:`ChatService`: a playground run is
not a chat turn and must never create conversation, schedule or post-turn work.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from kokoro_link.application.services.feature_keys import FEATURE_CHAT
from kokoro_link.domain.entities.conversation import Conversation
from kokoro_link.domain.entities.operator_profile import OperatorProfile
from kokoro_link.domain.value_objects.content_flow import content_tolerance_for_llm_provider
from kokoro_link.domain.value_objects.goal_status import GoalStatus
from kokoro_link.domain.value_objects.timezone import timezone_for_id, to_timezone
from kokoro_link.infrastructure.memory.ranker import rank
from kokoro_link.infrastructure.prompts.registry import prompt_template_catalog, template_default
from kokoro_link.infrastructure.prompts.loader import request_template_overrides
from kokoro_link.application.services.dialogue_window_loader import load_unified_recent_messages
from kokoro_link.infrastructure.observability.runtime_diagnostics import diagnostic_scope

if TYPE_CHECKING:  # pragma: no cover
    from kokoro_link.application.services.prompt_customization_service import PromptCustomizationService
    from kokoro_link.application.services.schedule_service import ScheduleService
    from kokoro_link.contracts.active_llm import ActiveLLMProviderPort
    from kokoro_link.contracts.goal_repository import GoalRepositoryPort
    from kokoro_link.contracts.memory import MemoryRepositoryPort
    from kokoro_link.contracts.repositories import CharacterRepositoryPort, ConversationRepositoryPort
    from kokoro_link.contracts.story_arc import StoryArcRepositoryPort
    from kokoro_link.infrastructure.prompt.default import DefaultPromptContextBuilder


_MAX_MESSAGE_CHARS = 2000
_MAX_REPLY_CHARS = 1200
_RECENT_MESSAGES = 12


class PromptPlaygroundAccessError(ValueError):
    pass


class PromptPlaygroundBusyError(RuntimeError):
    pass


class PromptPlaygroundGenerationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PromptPlaygroundRun:
    published_reply: str
    draft_reply: str | None
    model_id: str | None
    prompt_hash: str
    snapshot_summary: dict[str, int | bool]
    has_draft: bool
    draft_prompt_hash: str | None = None
    provider_id: str = ""
    elapsed_ms: int = 0


class PromptPlaygroundService:
    def __init__(
        self,
        *,
        character_repository: "CharacterRepositoryPort | None",
        conversation_repository: "ConversationRepositoryPort | None",
        memory_repository: "MemoryRepositoryPort | None",
        goal_repository: "GoalRepositoryPort | None",
        story_arc_repository: "StoryArcRepositoryPort | None",
        schedule_service: "ScheduleService | None",
        operator_profile_repository,
        prompt_context_builder: "DefaultPromptContextBuilder",
        prompt_customization_service: "PromptCustomizationService",
        active_llm_provider: "ActiveLLMProviderPort",
        player_persona_note_repository=None,
        relationship_seed_repository=None,
        story_event_repository=None,
        story_scene_session_repository=None,
        world_event_repository=None,
        address_preference_repository=None,
        operator_persona_repository=None,
        operator_persona_renderer=None,
    ) -> None:
        self._character_repository = character_repository
        self._conversation_repository = conversation_repository
        self._memory_repository = memory_repository
        self._goal_repository = goal_repository
        self._story_arc_repository = story_arc_repository
        self._schedule_service = schedule_service
        self._operator_profiles = operator_profile_repository
        self._prompt_context_builder = prompt_context_builder
        self._prompt_customization_service = prompt_customization_service
        self._active_llm_provider = active_llm_provider
        self._player_persona_notes = player_persona_note_repository
        self._relationship_seeds = relationship_seed_repository
        self._story_events = story_event_repository
        self._story_scenes = story_scene_session_repository
        self._world_events = world_event_repository
        self._address_preferences = address_preference_repository
        self._personas = operator_persona_repository
        self._persona_renderer = operator_persona_renderer
        self._locks: dict[str, asyncio.Lock] = {}
        self._attempts: dict[str, deque[float]] = {}

    async def list_characters(self, *, user_id: str, admin: bool):
        if self._character_repository is None:
            return []
        if admin:
            return await self._character_repository.list()
        return await self._character_repository.list_for_user(user_id)

    async def run(
        self, *, character_id: str, user_id: str, admin: bool,
        message: str, include_current_progress: bool,
        draft_scope: str = "player",
    ) -> PromptPlaygroundRun:
        text = (message or "").strip()
        if not text or len(message) > _MAX_MESSAGE_CHARS:
            raise ValueError(f"message must be 1-{_MAX_MESSAGE_CHARS} characters")
        character = await self._load_character(character_id, user_id=user_id, admin=admin)
        if draft_scope not in {"player", "admin"} or (draft_scope == "admin" and not admin):
            raise PromptPlaygroundAccessError("Draft scope is not available")
        admin_drafts = draft_scope == "admin"
        lock = self._locks.setdefault(user_id, asyncio.Lock())
        if lock.locked():
            raise PromptPlaygroundBusyError("a playground run is already in progress")
        async with lock:
            self._check_rate(user_id)
            started = time.monotonic()
            snapshot = await self._snapshot(
                character=character, user_id=user_id,
                include_current_progress=include_current_progress,
            )
            stored_effective = await self._prompt_customization_service.effective_overrides(
                user_id=None if admin_drafts else user_id,
            )
            catalog = prompt_template_catalog()
            # Fully materialise the template base now. The process-global admin
            # refresher must not change the second prompt while the model runs.
            effective = {name: template_default(name) for name in catalog}
            effective.update(stored_effective)
            drafts = await self._prompt_customization_service.get_drafts(
                user_id=user_id, admin=admin_drafts,
            )
            drafts = {name: value for name, value in drafts.items() if admin_drafts or catalog[name].player_editable}
            model = await self._active_llm_provider.resolve(FEATURE_CHAT, character=character)
            model_id = await self._active_llm_provider.resolve_model_id(
                FEATURE_CHAT, character=character,
            )
            tolerance = content_tolerance_for_llm_provider(getattr(model, 'provider_id', ''))
            published_prompt = self._render(snapshot, text, effective, tolerance)
            draft_prompt = self._render(snapshot, text, {**effective, **drafts}, tolerance) if drafts else None
            published_reply = await self._generate(model, published_prompt, model_id)
            draft_reply = None
            if draft_prompt is not None:
                draft_reply = await self._generate(model, draft_prompt, model_id)
            return PromptPlaygroundRun(
                published_reply=published_reply,
                draft_reply=draft_reply,
                model_id=model_id,
                prompt_hash=hashlib.sha256(published_prompt.encode("utf-8")).hexdigest()[:12],
                snapshot_summary=snapshot.summary,
                has_draft=bool(drafts),
                draft_prompt_hash=(hashlib.sha256(draft_prompt.encode('utf-8')).hexdigest()[:12] if draft_prompt is not None else None),
                provider_id=str(getattr(model, 'provider_id', '')),
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )

    def _check_rate(self, user_id: str) -> None:
        now = time.monotonic()
        attempts = self._attempts.setdefault(user_id, deque())
        while attempts and attempts[0] <= now - 3600:
            attempts.popleft()
        if len(attempts) >= 30 or sum(value > now - 60 for value in attempts) >= 6:
            raise PromptPlaygroundBusyError("playground rate limit exceeded")
        attempts.append(now)

    @staticmethod
    async def _generate(model, prompt: str, model_id: str | None) -> str:
        try:
            async with asyncio.timeout(120):
                with diagnostic_scope(source_surface="prompt_playground"):
                    return _clip(await model.generate(prompt, model=model_id))
        except Exception:
            # Provider exception strings may contain credentials/request bodies.
            raise PromptPlaygroundGenerationError("playground model generation failed") from None

    async def _load_character(self, character_id: str, *, user_id: str, admin: bool):
        character = (
            await self._character_repository.get(character_id)
            if self._character_repository is not None else None
        )
        if character is None or (not admin and character.user_id != user_id):
            raise PromptPlaygroundAccessError("Character not found")
        return character

    async def _snapshot(self, *, character, user_id: str, include_current_progress: bool):  # noqa: ANN001
        # A cross-character administrator previews the selected owner's world,
        # not the administrator's personal identity or progress.
        owner_id = character.user_id
        operator = await self._operator_profiles.get(owner_id) if self._operator_profiles else None
        if operator is None:
            operator = OperatorProfile(id=owner_id, display_name='使用者')
        now = datetime.now(timezone.utc)
        local_tz = timezone_for_id(getattr(operator, "timezone_id", None))
        recent, memories, goals, arc = [], [], [], None
        if include_current_progress:
            recent, memories, goals, arc = await asyncio.gather(
                self._recent(character.id), self._memories(character.id), self._goals(character.id), self._arc(character.id),
            )
        schedule = await self._schedule_service.get_schedule(
            character.id, date_=to_timezone(now, local_tz).date(),
        ) if include_current_progress and self._schedule_service else None
        current = just_finished = None
        upcoming = completed = invites = ()
        if schedule is not None and self._schedule_service is not None:
            current, upcoming_list, just_finished = self._schedule_service.resolve_current(schedule, now=now)
            upcoming = tuple(upcoming_list)
            completed = tuple(self._schedule_service.resolve_completed_today(schedule, now=now, local_tz=local_tz))
            invites = tuple(self._schedule_service.resolve_pending_invites(schedule, now=now))
        conversation = Conversation.start(character_id=character.id)
        extra = {}
        persona = None
        if include_current_progress and self._personas is not None:
            persona = await self._personas.get(character.id, owner_id)
        preference = None
        if include_current_progress and self._address_preferences is not None:
            preference = await self._address_preferences.get(character_id=character.id, operator_id=owner_id)
            extra['address_preference'] = preference
        if self._player_persona_notes is not None:
            note = await self._player_persona_notes.get(character_id=character.id, operator_id=owner_id)
            extra['player_persona_note'] = note.note if note else None
        if self._relationship_seeds is not None:
            from kokoro_link.infrastructure.prompt.initial_relationship import render_initial_relationship_seed_lines
            from kokoro_link.domain.services.address_resolver import resolve_player_address, resolve_character_address
            seed = await self._relationship_seeds.get(character.id, owner_id)
            extra['initial_relationship_lines'] = render_initial_relationship_seed_lines(seed)
            extra['resolved_player_address'] = resolve_player_address(seed=seed, persona=persona, profile=operator)
            extra['resolved_character_address'] = resolve_character_address(seed=seed, preference=preference, character=character)
        if include_current_progress:
            if self._schedule_service is not None:
                upcoming_days = await self._schedule_service.load_upcoming_schedules(character.id, start_after=to_timezone(now, local_tz).date())
                extra['upcoming_day_schedules'] = upcoming_days
                invites = tuple(self._schedule_service.resolve_pending_invites_from_schedules(([schedule] if schedule else []) + upcoming_days, now=now))
            if self._story_events is not None:
                extra['story_events'] = await self._story_events.list_recent(character.id, limit=5)
            if self._story_scenes is not None:
                extra['story_scene'] = await self._story_scenes.get_open_for_character(character.id)
            if self._world_events is not None and character.world_awareness_enabled:
                from kokoro_link.application.services.chat_assist_service import _world_event_lines
                events = await self._world_events.query_recent(limit=4, topic_tags=list(character.world_topics) or None, max_age_days=7)
                categories = {c.strip().lower() for c in character.subscribed_categories if c.strip()}
                events = [e for e in events if not categories or (e.category or 'news').lower() in categories]
                extra['world_event_context'] = tuple(_world_event_lines(events))
        return deepcopy(_Snapshot(
            character=character, operator=operator, now=now, today=to_timezone(now, local_tz).date(),
            conversation=conversation, recent=recent, memories=memories, goals=goals, arc=arc,
            current=current, upcoming=upcoming, just_finished=just_finished, completed=completed, invites=invites,
            summary={"recent_message_count": len(recent), "memory_count": len(memories), "has_current_activity": current is not None, "has_story_arc": arc is not None}, extra=extra, persona=persona,
        ))

    async def _recent(self, character_id: str):
        if self._conversation_repository is None:
            return []
        return await load_unified_recent_messages(self._conversation_repository, character_id=character_id, limit=_RECENT_MESSAGES)

    async def _memories(self, character_id: str):
        if self._memory_repository is None:
            return []
        pool = await self._memory_repository.query(character_id, limit=80, world_scope=None)
        return rank(pool, top_k=8)

    async def _goals(self, character_id: str):
        if self._goal_repository is None:
            return []
        return await self._goal_repository.list_for_character(character_id, statuses=(GoalStatus.ACTIVE,))

    async def _arc(self, character_id: str):
        if self._story_arc_repository is None:
            return None
        return await self._story_arc_repository.get_active_for_character(character_id)

    def _render(self, snapshot: "_Snapshot", message: str, overrides: dict[str, str], tolerance: str) -> str:
        extra = dict(snapshot.extra)
        if snapshot.persona is not None and self._persona_renderer is not None:
            with request_template_overrides(overrides):
                extra['operator_persona_lines'] = self._persona_renderer(snapshot.persona)
        return self._prompt_context_builder.build(
            character=snapshot.character, conversation=snapshot.conversation,
            recent_messages=snapshot.recent, memories=snapshot.memories,
            pending_state=snapshot.character.state, latest_user_message=message,
            active_goals=snapshot.goals, current_activity=snapshot.current,
            upcoming_activities=list(snapshot.upcoming), just_finished_activity=snapshot.just_finished,
            completed_today_activities=list(snapshot.completed), pending_invite_activities=list(snapshot.invites),
            now=snapshot.now, character_tool_names=(), story_arc=snapshot.arc,
            upcoming_arc_beats=(snapshot.arc.forward_beats(after=snapshot.today, limit=3, include_today=True) if snapshot.arc else []),
            today_local=snapshot.today, operator=snapshot.operator,
            template_overrides=overrides, content_tolerance=tolerance,
            **extra,
        )


@dataclass(frozen=True, slots=True)
class _Snapshot:
    character: object
    operator: object | None
    now: datetime
    today: object
    conversation: Conversation
    recent: list
    memories: list
    goals: list
    arc: object | None
    current: object | None
    upcoming: tuple
    just_finished: object | None
    completed: tuple
    invites: tuple
    summary: dict[str, int | bool]
    extra: dict
    persona: object | None


def _clip(value: str) -> str:
    text = (value or "").strip()
    return text if len(text) <= _MAX_REPLY_CHARS else text[:_MAX_REPLY_CHARS].rstrip() + "…"
