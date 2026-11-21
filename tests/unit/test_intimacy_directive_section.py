"""``intimacy_directive``: NSFW mode's writing-direction block.

Three things are pinned here:

* the gate — NORMAL renders nothing, NSFW renders the directive;
* the content — the block actually says what the design approved;
* the slot — ``intimacy_directive`` sorts immediately after
  ``turn_register``, i.e. in the per-turn frame layer below the
  cacheable prefix, never inside it.
"""

from __future__ import annotations

from datetime import timezone

from kokoro_link.application.services.nsfw_mode import (
    CONTENT_MODE_NORMAL,
    CONTENT_MODE_NSFW,
)
from kokoro_link.domain.entities.character import Character
from kokoro_link.domain.entities.conversation import Conversation
from kokoro_link.domain.value_objects.character_state import CharacterState
from kokoro_link.domain.value_objects.content_flow import (
    CONTENT_TOLERANCE_FRONTIER,
)
from kokoro_link.domain.value_objects.presence_frame import PresenceFrame
from kokoro_link.infrastructure.prompt.default import DefaultPromptContextBuilder
from kokoro_link.infrastructure.prompt.sections import intimacy
from kokoro_link.infrastructure.prompt.sections.context import (
    DialogueContext,
    IdentityContext,
    PromptSectionContext,
    RailsContext,
    ScheduleContext,
    StateContext,
    StoryContext,
    TimeContext,
    ToolsContext,
    VisionContext,
)
from kokoro_link.infrastructure.prompt.sections.order import SECTION_ORDER
from kokoro_link.infrastructure.prompt.sections.registry import default_registry

DIRECTIVE_HEADER = "親密場景取向"
# The approved draft's own instruction: "請內化，不要複述本段" — if this
# line ever drops out, the block starts leaking as spoken text.
INTERNALISE = "不要複述本段"


def _character(*, boundaries: list[str] | None = None) -> Character:
    return Character.create(
        name="Airi",
        summary="溫柔的角色",
        personality=["gentle"],
        interests=["music"],
        speaking_style="soft",
        boundaries=boundaries or [],
        state=CharacterState(
            emotion="neutral", affection=50, fatigue=0, trust=50, energy=100,
        ),
    )


def _rails(*, content_mode: str) -> RailsContext:
    return RailsContext(
        experiment_overlay={},
        content_tolerance=CONTENT_TOLERANCE_FRONTIER,
        body_state_enabled=True,
        subjective_time_enabled=True,
        address_preference_enabled=True,
        content_mode=content_mode,
    )


def _context(*, content_mode: str, character: Character | None = None) -> PromptSectionContext:
    character = character or _character()
    conversation = Conversation.start(character_id=character.id)
    return PromptSectionContext(
        time=TimeContext(
            now=None, today_local=None, idle_minutes=None,
            local_tz=timezone.utc,
        ),
        identity=IdentityContext(
            character=character,
            operator=None,
            operator_persona_lines=(),
            player_persona_note=None,
            peer_roster_lines=(),
            initial_relationship_lines=(),
            address_change_lines=(),
            address_preference=None,
            resolved_player_address=None,
            resolved_character_address=None,
        ),
        state=StateContext(
            pending_state=character.state,
            memories=(),
            active_goals=(),
            emotion_events=(),
            self_reflections=(),
        ),
        schedule=ScheduleContext(
            current_activity=None,
            upcoming_activities=(),
            just_finished_activity=None,
            completed_today_activities=(),
            pending_invite_activities=(),
            upcoming_day_schedules=(),
            calendar_context="",
            weather_context="",
            world_event_context=(),
            world_event_recall=(),
        ),
        story=StoryContext(
            story_events=(), story_arc=None, upcoming_arc_beats=(),
            story_scene=None,
        ),
        dialogue=DialogueContext(
            conversation=conversation,
            recent_messages=(),
            latest_user_message="過來。",
            older_dialogue_summary=None,
            recent_proactive_messages=(),
            recent_feed_posts=(),
            self_repetition_hint=None,
            phrase_habit_lines=(),
            turn_register_profile=None,
            reply_diversity_evidence=None,
            persona_curiosity_plan=None,
            material_digest=None,
            retry_directive=None,
            presence_frame=PresenceFrame.web_stage(),
            stage_nudge=False,
        ),
        tools=ToolsContext(
            available_tools=(), tool_outcomes=(), forced_tool_name=None,
        ),
        vision=VisionContext(markers={}, image_recognition_context=""),
        rails=_rails(content_mode=content_mode),
    )


def _build(*, content_mode: str) -> str:
    character = _character()
    return DefaultPromptContextBuilder().build(
        character=character,
        conversation=Conversation.start(character_id=character.id),
        recent_messages=[],
        memories=[],
        pending_state=character.state,
        latest_user_message="過來。",
        content_mode=content_mode,
    )


# --- the gate --------------------------------------------------------


def test_normal_mode_renders_nothing() -> None:
    assert intimacy._intimacy_directive(_context(content_mode=CONTENT_MODE_NORMAL)) == []


def test_nsfw_mode_renders_the_directive() -> None:
    lines = intimacy._intimacy_directive(_context(content_mode=CONTENT_MODE_NSFW))
    assert lines
    text = "\n".join(lines)
    assert DIRECTIVE_HEADER in text
    assert INTERNALISE in text


def test_nsfw_mode_forbids_self_censorship() -> None:
    text = "\n".join(
        intimacy._intimacy_directive(_context(content_mode=CONTENT_MODE_NSFW)),
    )
    assert "不要自我審查" in text


def test_unsets_or_other_values_stay_silent() -> None:
    # Any value other than the explicit NSFW constant must behave as NORMAL:
    # the gate is an equality check on the write-time fact, never "not normal".
    assert intimacy._intimacy_directive(_context(content_mode="")) == []
    assert intimacy._intimacy_directive(_context(content_mode="NSFW")) == []


def test_header_is_followed_by_a_blank_separator_line() -> None:
    lines = intimacy._intimacy_directive(_context(content_mode=CONTENT_MODE_NSFW))
    assert lines[0] == f"{DIRECTIVE_HEADER}（本輪適用，請內化，不要複述本段）："
    assert lines[1] == ""


# --- through the real builder ---------------------------------------


def test_normal_prompt_omits_the_directive_and_nsfw_prompt_has_it() -> None:
    assert DIRECTIVE_HEADER not in _build(content_mode=CONTENT_MODE_NORMAL)
    assert DIRECTIVE_HEADER in _build(content_mode=CONTENT_MODE_NSFW)


def test_default_content_mode_is_normal() -> None:
    """Callers that never pass ``content_mode`` must get NORMAL output.
    Pinned because 20+ call sites rely on the default."""
    character = _character()
    conversation = Conversation.start(character_id=character.id)
    common = {
        "character": character,
        "conversation": conversation,
        "recent_messages": [],
        "memories": [],
        "pending_state": character.state,
        "latest_user_message": "過來。",
    }
    omitted = DefaultPromptContextBuilder().build(**common)
    explicit = DefaultPromptContextBuilder().build(
        **common, content_mode=CONTENT_MODE_NORMAL,
    )
    assert omitted == explicit


# --- the slot --------------------------------------------------------


def test_directive_sits_immediately_after_turn_register() -> None:
    index = SECTION_ORDER.index("intimacy_directive")
    assert SECTION_ORDER[index - 1] == "turn_register"
    assert SECTION_ORDER[index + 1] == "character_state"


def test_directive_is_registered() -> None:
    assert "intimacy_directive" in default_registry()


def test_directive_renders_between_turn_register_and_character_state() -> None:
    prompt = _build(content_mode=CONTENT_MODE_NSFW)
    i_register = prompt.index("本輪語域基底")
    i_directive = prompt.index(DIRECTIVE_HEADER)
    i_state = prompt.index("角色當前狀態")
    assert i_register < i_directive < i_state
