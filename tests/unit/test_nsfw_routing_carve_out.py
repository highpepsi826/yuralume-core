"""NSFW routing carve-out — structural features stay on the normal route.

Design: ``NSFW_ROUTING_CARVE_OUT_REFERENCE.md``.

T4 (safety) is the keystone: a carved-out feature that resolves to a
frontier provider while ``content_mode`` is NSFW must be scored
``frontier`` so explicit text is sanitised. The other tests guard the
regression (empty allowlist), the cross-branch consistency, and the
fail-closed default for unknown features.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest

from kokoro_link.application.services.active_llm_provider import (
    ROUTING_SOURCE_ACTIVE_MODEL,
    ROUTING_SOURCE_NSFW_MODE,
    PreferenceBackedActiveLLMProvider,
)
from kokoro_link.application.services.nsfw_mode import (
    NSFW_MODE_TARGET_PREFERENCE_KEY,
    NsfwModeService,
    NsfwModeTarget,
    _target_from_raw,
    _target_to_raw,
)
from kokoro_link.contracts.llm import ChatModelPort, ReasoningOverrides
from kokoro_link.domain.entities.character import Character
from kokoro_link.domain.entities.conversation import MessageContentMode
from kokoro_link.domain.value_objects.character_state import CharacterState
from kokoro_link.domain.value_objects.content_flow import (
    CONTENT_TOLERANCE_FRONTIER,
    content_tolerance_for_route,
)
from kokoro_link.infrastructure.llm.registry import InMemoryChatModelRegistry
from kokoro_link.infrastructure.repositories.in_memory_preferences import (
    InMemoryPreferencesRepository,
)

STRUCTURAL = "schedule_plan"
CHAT = "chat"


class _RecordingModel(ChatModelPort):
    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id
        self.supports_vision = False
        self.bound_overrides: ReasoningOverrides | None = None
        self.calls: list[tuple[str, str | None]] = []

    async def generate(
        self, prompt: str, *,
        image_urls: Sequence[str] = (), model: str | None = None,
    ) -> str:
        self.calls.append((prompt, model))
        return "{}"

    async def generate_stream(
        self, prompt: str, *,
        image_urls: Sequence[str] = (), model: str | None = None,
    ) -> AsyncIterator[str]:
        await self.generate(prompt)
        reply = "{}"

        async def _iter() -> AsyncIterator[str]:
            yield reply
        return _iter()

    async def list_models(self) -> list[str]:
        return [self.provider_id]

    def with_reasoning_overrides(self, overrides: ReasoningOverrides) -> Any:
        clone = _RecordingModel(self.provider_id)
        clone.bound_overrides = overrides
        return clone

    def with_supports_vision(self, enabled: bool) -> Any:
        clone = _RecordingModel(self.provider_id)
        clone.supports_vision = enabled
        return clone


def _character(user_id: str = "alice") -> Character:
    return Character.create(
        name="Yuki", summary="", user_id=user_id,
        personality=[], interests=[], speaking_style="", boundaries=[],
        state=CharacterState(
            emotion="neutral", affection=50, fatigue=0, trust=50, energy=100,
        ),
    )


def _wire() -> tuple[
    PreferenceBackedActiveLLMProvider,
    NsfwModeService,
    InMemoryPreferencesRepository,
    _RecordingModel,
    _RecordingModel,
]:
    registry = InMemoryChatModelRegistry(default_provider_id="lmstudio")
    lmstudio = _RecordingModel("lmstudio")
    anthropic = _RecordingModel("anthropic")
    registry.register(lmstudio)
    registry.register(anthropic)
    prefs = InMemoryPreferencesRepository()
    nsfw = NsfwModeService(preferences=prefs, ttl_seconds=600)
    provider = PreferenceBackedActiveLLMProvider(
        registry=registry,
        preferences=prefs,
        default_provider_id="lmstudio",
        nsfw_mode_service=nsfw,
    )
    return provider, nsfw, prefs, lmstudio, anthropic


async def _configure(
    nsfw: NsfwModeService,
    prefs: InMemoryPreferencesRepository,
    *,
    structural_features: tuple[str, ...],
    enable: bool = True,
) -> None:
    """NSFW target = community ``lmstudio``; the normal route
    (``active_model``) = frontier ``anthropic``."""
    target = NsfwModeTarget(
        llm_provider_id="lmstudio",
        llm_model_id="community-nsfw",
        image_profile_id=None,
        structural_features=structural_features,
    )
    await prefs.set(NSFW_MODE_TARGET_PREFERENCE_KEY, _target_to_raw(target))
    await prefs.set(
        "active_model", {"provider_id": "anthropic", "model_id": "claude-x"},
    )
    if enable:
        await nsfw.enable(user_id="alice")


# ---- T4: safety -----------------------------------------------------


@pytest.mark.asyncio
async def test_t4_carved_out_feature_on_frontier_is_scored_frontier() -> None:
    provider, nsfw, prefs, lmstudio, anthropic = _wire()
    await _configure(nsfw, prefs, structural_features=(STRUCTURAL,))
    character = _character()

    source = await provider.resolve_routing_source(
        STRUCTURAL, character=character,
    )
    model = await provider.resolve(STRUCTURAL, character=character)

    # Pre-condition: the carve-out really moved the call off the target.
    assert source == ROUTING_SOURCE_ACTIVE_MODEL
    assert model is anthropic
    assert lmstudio.calls == []

    # Safety: NSFW content mode + frontier provider → frontier tolerance,
    # so explicit messages get sanitised instead of leaking through.
    assert content_tolerance_for_route(
        getattr(model, "provider_id", ""),
        routed_to_nsfw_target=source == ROUTING_SOURCE_NSFW_MODE,
    ) == CONTENT_TOLERANCE_FRONTIER


# ---- T1: empty allowlist is a byte-for-byte regression ---------------


@pytest.mark.asyncio
@pytest.mark.parametrize("feature_key", [CHAT, STRUCTURAL, "some_future_feature"])
async def test_t1_empty_allowlist_routes_every_feature_to_target(
    feature_key: str,
) -> None:
    provider, nsfw, prefs, lmstudio, anthropic = _wire()
    await _configure(nsfw, prefs, structural_features=())
    character = _character()

    assert await provider.resolve(feature_key, character=character) is lmstudio
    assert await provider.resolve_model_id(
        feature_key, character=character,
    ) == "community-nsfw"
    assert await provider.resolve_routing_source(
        feature_key, character=character,
    ) == ROUTING_SOURCE_NSFW_MODE
    assert anthropic.calls == []


# ---- T2: allowlisted feature routes normally, chat does not ----------


@pytest.mark.asyncio
async def test_t2_allowlisted_feature_uses_normal_route_chat_does_not() -> None:
    provider, nsfw, prefs, lmstudio, anthropic = _wire()
    await _configure(nsfw, prefs, structural_features=(STRUCTURAL,))
    character = _character()

    assert await provider.resolve(
        STRUCTURAL, character=character,
    ) is anthropic
    assert await provider.resolve_model_id(
        STRUCTURAL, character=character,
    ) == "claude-x"
    assert await provider.resolve_routing_source(
        STRUCTURAL, character=character,
    ) == ROUTING_SOURCE_ACTIVE_MODEL

    assert await provider.resolve(CHAT, character=character) is lmstudio
    assert await provider.resolve_model_id(
        CHAT, character=character,
    ) == "community-nsfw"
    assert await provider.resolve_routing_source(
        CHAT, character=character,
    ) == ROUTING_SOURCE_NSFW_MODE


# ---- T3: model and reasoning come from the same provider -------------


@pytest.mark.asyncio
async def test_t3_carved_out_feature_model_and_reasoning_match() -> None:
    provider, nsfw, prefs, lmstudio, anthropic = _wire()
    await _configure(nsfw, prefs, structural_features=(STRUCTURAL,))
    # Pin reasoning on the normal route only.
    await prefs.set(
        "active_model",
        {
            "provider_id": "anthropic",
            "model_id": "claude-x",
            "reasoning": {"reasoning_effort": "high"},
        },
    )
    character = _character()

    model = await provider.resolve(STRUCTURAL, character=character)
    assert model.provider_id == "anthropic"
    assert model.bound_overrides is not None
    assert model.bound_overrides.reasoning_effort == "high"

    # Chat keeps the target and must NOT inherit the normal posture.
    chat_model = await provider.resolve(CHAT, character=character)
    assert chat_model.provider_id == "lmstudio"
    assert chat_model.bound_overrides is None


@pytest.mark.asyncio
async def test_t3_chat_model_and_reasoning_match_on_target() -> None:
    provider, nsfw, prefs, lmstudio, anthropic = _wire()
    await _configure(nsfw, prefs, structural_features=(STRUCTURAL,))
    await prefs.set(
        "active_model",
        {
            "provider_id": "anthropic",
            "model_id": "claude-x",
            "reasoning": {"reasoning_effort": "high"},
        },
    )
    character = _character()

    chat_model = await provider.resolve(CHAT, character=character)
    chat_reasoning = await provider._maybe_bind_reasoning(
        chat_model, CHAT, character=character, content_tolerance=None,
    )
    assert chat_reasoning.provider_id == "lmstudio"
    assert chat_reasoning.bound_overrides is None


# ---- T5: unknown feature stays on the target (fail-closed) -----------


@pytest.mark.asyncio
async def test_t5_unknown_feature_stays_on_nsfw_target() -> None:
    provider, nsfw, prefs, lmstudio, anthropic = _wire()
    await _configure(nsfw, prefs, structural_features=(STRUCTURAL,))
    character = _character()

    assert await provider.resolve(
        "brand_new_feature", character=character,
    ) is lmstudio
    assert await provider.resolve_routing_source(
        "brand_new_feature", character=character,
    ) == ROUTING_SOURCE_NSFW_MODE


@pytest.mark.asyncio
async def test_t5_no_feature_key_never_carves_out() -> None:
    provider, nsfw, prefs, lmstudio, anthropic = _wire()
    await _configure(nsfw, prefs, structural_features=(STRUCTURAL,))

    assert await provider.resolve(character=_character()) is lmstudio
    assert anthropic.calls == []


# ---- T7: legacy target without the key -------------------------------


def test_t7_legacy_target_without_structural_features_is_empty_tuple() -> None:
    target = _target_from_raw({
        "llm": {"provider_id": "lmstudio", "model_id": "community-nsfw"},
        "image_profile_id": "anime_nsfw",
    })
    assert target is not None
    assert target.structural_features == ()


def test_t7_round_trip_preserves_structural_features() -> None:
    target = NsfwModeTarget(
        llm_provider_id="lmstudio",
        llm_model_id="community-nsfw",
        image_profile_id=None,
        structural_features=(STRUCTURAL, CHAT),
    )
    raw = _target_to_raw(target)
    assert raw["structural_features"] == [STRUCTURAL, CHAT]
    assert _target_from_raw(raw) == target


def test_t7_empty_structural_features_is_not_serialized() -> None:
    target = NsfwModeTarget(
        llm_provider_id="lmstudio",
        llm_model_id="community-nsfw",
        image_profile_id=None,
    )
    assert "structural_features" not in _target_to_raw(target)


@pytest.mark.asyncio
async def test_t7_legacy_target_routes_everything_to_target() -> None:
    provider, nsfw, prefs, lmstudio, anthropic = _wire()
    # Written the pre-feature way: no structural_features array.
    await prefs.set(
        NSFW_MODE_TARGET_PREFERENCE_KEY,
        {
            "llm": {"provider_id": "lmstudio", "model_id": "community-nsfw"},
            "image_profile_id": None,
        },
    )
    await prefs.set(
        "active_model", {"provider_id": "anthropic", "model_id": "claude-x"},
    )
    await nsfw.enable(user_id="alice")
    character = _character()

    assert await provider.resolve(STRUCTURAL, character=character) is lmstudio
    assert await provider.resolve_routing_source(
        STRUCTURAL, character=character,
    ) == ROUTING_SOURCE_NSFW_MODE


def test_malformed_structural_features_degrades_to_empty() -> None:
    target = _target_from_raw({
        "llm": {"provider_id": "lmstudio", "model_id": "community-nsfw"},
        "structural_features": "not-a-list",
    })
    assert target is not None
    assert target.structural_features == ()


# ---- tolerance helper ------------------------------------------------


def test_content_tolerance_for_route_is_fail_closed() -> None:
    assert content_tolerance_for_route(
        "anthropic", routed_to_nsfw_target=False,
    ) == CONTENT_TOLERANCE_FRONTIER
    assert content_tolerance_for_route(
        "Anthropic ", routed_to_nsfw_target=False,
    ) == CONTENT_TOLERANCE_FRONTIER
    # Unknown / local providers stay community.
    assert content_tolerance_for_route(
        "lmstudio", routed_to_nsfw_target=False,
    ) == "community"
    assert content_tolerance_for_route(
        None, routed_to_nsfw_target=False,
    ) == "community"
    # Anything that actually went to the NSFW target is community, even
    # a frontier target the operator picked explicitly.
    assert content_tolerance_for_route(
        "anthropic", routed_to_nsfw_target=True,
    ) == "community"


def test_content_mode_override_still_forces_community() -> None:
    """The existing helper keeps its NSFW-mode short-circuit."""
    from kokoro_link.domain.value_objects.content_flow import (
        content_tolerance_for_llm_provider,
    )

    assert content_tolerance_for_llm_provider(
        "anthropic",
        current_content_mode=MessageContentMode.NSFW,
    ) == "community"


# ---- adversarial / edge cases ---------------------------------------


def test_structural_features_normalizes_blank_and_duplicates() -> None:
    target = _target_from_raw({
        "llm": {"provider_id": "lmstudio", "model_id": "community-nsfw"},
        "structural_features": [" schedule_plan ", "", "  ", "schedule_plan",
                                "arc_plan", 7, None],
    })
    assert target is not None
    assert target.structural_features == ("schedule_plan", "arc_plan")


@pytest.mark.asyncio
async def test_listed_feature_with_reasoning_tolerance_hint_stays_routed() -> None:
    """A Rule-B community hint on a carved-out feature re-reads the
    *configured* (possibly inactive) target and returns ``nsfw_content``.
    That is upstream behaviour, unchanged: T4 still scores it frontier
    because the routing source is not ``nsfw_mode``."""
    provider, nsfw, prefs, lmstudio, anthropic = _wire()
    await _configure(nsfw, prefs, structural_features=(STRUCTURAL,))
    character = _character()

    source = await provider.resolve_routing_source(
        STRUCTURAL, character=character,
        content_tolerance="community",
    )
    assert source == "nsfw_content"
    assert content_tolerance_for_route(
        "lmstudio", routed_to_nsfw_target=source == ROUTING_SOURCE_NSFW_MODE,
    ) == "community"


@pytest.mark.asyncio
async def test_unknown_but_listed_feature_is_carved_out_and_cleared_persists() -> None:
    """A key the backend does not know is honoured verbatim (hence
    fail-closed lives at classification time, not here), and survives a
    write/read round trip."""
    provider, nsfw, prefs, lmstudio, anthropic = _wire()
    await _configure(nsfw, prefs, structural_features=("future_feature",))
    character = _character()

    assert await provider.resolve(
        "future_feature", character=character,
    ) is anthropic
    assert (await nsfw.get_global_target()).structural_features == (
        "future_feature",
    )


@pytest.mark.asyncio
async def test_typo_in_allowlist_fails_closed() -> None:
    provider, nsfw, prefs, lmstudio, anthropic = _wire()
    # A key normalised at write time reads back trimmed, so list
    # membership rather than whitespace decides the carve-out.
    await _configure(
        nsfw, prefs, structural_features=("schedule_plan ", "scheduel_plan"),
    )
    character = _character()
    assert (await nsfw.get_global_target()).structural_features == (
        "schedule_plan", "scheduel_plan",
    )
    # The typo is its own key: the real feature is still carved out, and
    # the typo'd key matches nothing, so chat stays on the target.
    assert await provider.resolve(
        "schedule_plan", character=character,
    ) is anthropic
    assert await provider.resolve(
        CHAT, character=character,
    ) is lmstudio


def test_chat_turn_tolerance_is_frontier_when_carved_out() -> None:
    """T4 at the chat-service layer: an NSFW turn that did NOT go to the
    target scores by the provider it reached."""
    from kokoro_link.application.services.chat_service import (
        _content_tolerance_for_model,
        _routed_to_nsfw_target,
    )

    target = NsfwModeTarget(
        llm_provider_id="lmstudio",
        llm_model_id="community-nsfw",
        image_profile_id=None,
    )

    class _M:
        provider_id = "anthropic"

    model = _M()
    assert _routed_to_nsfw_target(
        model, "claude-x", MessageContentMode.NSFW, target,
    ) is False
    assert _content_tolerance_for_model(
        model,
        content_mode=MessageContentMode.NSFW,
        routed_to_nsfw_target=False,
    ) == CONTENT_TOLERANCE_FRONTIER

    # On the target: community, even if the target itself is frontier.
    class _F:
        provider_id = "anthropic"

    assert _routed_to_nsfw_target(
        _F(), "community-nsfw", MessageContentMode.NSFW, target,
    ) is False
    frontier_target = NsfwModeTarget(
        llm_provider_id="anthropic",
        llm_model_id="claude-x",
        image_profile_id=None,
    )
    assert _routed_to_nsfw_target(
        _F(), "claude-x", MessageContentMode.NSFW, frontier_target,
    ) is True
    assert _content_tolerance_for_model(
        _F(),
        content_mode=MessageContentMode.NSFW,
        routed_to_nsfw_target=True,
    ) == "community"


def test_chat_turn_without_known_target_never_widens_tolerance() -> None:
    from kokoro_link.application.services.chat_service import (
        _routed_to_nsfw_target,
    )

    class _M:
        provider_id = "anthropic"

    assert _routed_to_nsfw_target(
        _M(), "claude-x", MessageContentMode.NSFW, None,
    ) is True


def test_normal_turn_never_counts_as_on_target() -> None:
    from kokoro_link.application.services.chat_service import (
        _routed_to_nsfw_target,
    )

    class _M:
        provider_id = "anthropic"

    assert _routed_to_nsfw_target(
        _M(), None, MessageContentMode.NORMAL, object(),
    ) is False
