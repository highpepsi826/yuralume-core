"""Prompt builder surfaces the 0-100 scale and maps state values to
behaviour hints so the model actually *uses* affection/trust instead of
ignoring them as opaque numbers.

Also verifies that ``character.boundaries`` is wired to explicit
cross-boundary guidance rather than being rendered as a dead field.
"""

from kokoro_link.application.services.nsfw_mode import (
    CONTENT_MODE_NORMAL,
    CONTENT_MODE_NSFW,
)
from kokoro_link.domain.entities.character import Character
from kokoro_link.domain.entities.conversation import Conversation
from kokoro_link.domain.value_objects.character_state import CharacterState
from kokoro_link.infrastructure.prompt.default import DefaultPromptContextBuilder
from kokoro_link.infrastructure.prompt.sections.state import (
    _render_state_behavior_block,
)


def _character(*, boundaries: list[str] | None = None) -> Character:
    return Character.create(
        name="Airi",
        summary="溫柔的角色",
        personality=["gentle"],
        interests=["music"],
        speaking_style="soft",
        boundaries=boundaries or [],
        state=CharacterState(emotion="neutral", affection=50, fatigue=0, trust=50, energy=100),
    )


def _state(*, affection: int = 50, trust: int = 50) -> CharacterState:
    return CharacterState(
        emotion="neutral",
        affection=affection,
        fatigue=10,
        trust=trust,
        energy=90,
    )


def _build(
    state: CharacterState,
    character: Character | None = None,
    *,
    content_mode: str = CONTENT_MODE_NORMAL,
) -> str:
    builder = DefaultPromptContextBuilder()
    character = character or _character()
    conversation = Conversation.start(character_id=character.id)
    return builder.build(
        character=character,
        conversation=conversation,
        recent_messages=[],
        memories=[],
        pending_state=state,
        latest_user_message="嗨",
        content_mode=content_mode,
    )


def test_prompt_discloses_0_100_scale() -> None:
    """Model must know the numbers are out of 100 to reason about them."""
    prompt = _build(_state(affection=15, trust=20))
    # Either explicit "/100" notation or an instruction mentioning the 0-100 range.
    assert "/100" in prompt or "0-100" in prompt or "0–100" in prompt


def test_prompt_includes_behaviour_mapping_for_affection_and_trust() -> None:
    """Prompt must tell the model how to translate low/high values into tone."""
    prompt = _build(_state(affection=15, trust=20))
    # Look for a behaviour-guidance block (Chinese keywords used in the builder).
    assert "冷淡" in prompt or "保留" in prompt or "警戒" in prompt
    # The block should explicitly tie tone to the numeric state, not just list the field.
    assert "低" in prompt


def test_prompt_allows_negative_feedback_on_offensive_behaviour() -> None:
    """Model should be told that offensive/rude input is *not* to be pandered to."""
    prompt = _build(_state(affection=10, trust=5))
    # Expect explicit anti-pandering / push-back guidance.
    assert "不迎合" in prompt or "不要迎合" in prompt or "可以拒絕" in prompt or "拒絕" in prompt


def test_prompt_surfaces_cross_boundary_guidance_when_boundaries_set() -> None:
    """If the character has boundaries configured, the prompt must tell the
    model how to react when the user crosses them (not just list them)."""
    character = _character(boundaries=["不談論政治", "不接受冒犯家人"])
    prompt = _build(_state(), character=character)
    assert "不談論政治" in prompt  # boundaries still rendered
    # Guidance: crossing boundaries should cost trust/affection, not earn pandering.
    assert "越界" in prompt or "跨過" in prompt or "觸碰" in prompt or "違反" in prompt


def test_prompt_reply_instruction_is_symmetric() -> None:
    """The end-of-prompt instruction must cover *both* directions: push
    back on offense AND reward genuine warmth. Otherwise the model takes
    the one-sided 'don't pander' line as a license to stay cold.

    Looking specifically for wording about reciprocating warmth, since
    tier-mapping lines already hint at the shape — it's the final
    instruction block that currently only frames the negative case.
    """
    prompt = _build(_state(affection=75, trust=75))
    # The tail-of-prompt instruction (after 狀態對照) must reference
    # positive reciprocity, not just anti-pandering.
    assert (
        "真誠時" in prompt or "真心" in prompt or "釋出善意" in prompt
        or "願意親近" in prompt or "溫暖回應" in prompt or "相對地" in prompt
    )


def test_prompt_removes_do_not_reference_state_instruction() -> None:
    """The old "請勿在回覆中直接引用" line disabled state usage entirely.
    The new block should instead instruct the model to *reflect* state in tone
    (without literal number read-outs).
    """
    prompt = _build(_state())
    # The model should still be told not to read numbers out loud literally,
    # but must be told to reflect state in tone.
    assert "語氣" in prompt or "口吻" in prompt


# --- NSFW boundary variant (interaction-boundaries block) -------------

_NSFW_PUSHBACK = "不要因為對方強勢就退讓"

_NORMAL_BOUNDARY_WITH_BOUNDARIES = (
    "互動界線：使用者若越界、觸碰上方「禁忌」、使用粗魯或冒犯語氣，"
    "請冷淡、反問、或直接拒絕繼續，並且不要因為對方強勢就退讓；"
    "這類行為會讓好感度與信任度明顯下降，回覆上不應迎合。"
)
_NORMAL_BOUNDARY_WITHOUT_BOUNDARIES = (
    "互動界線：使用者若出現粗魯、冒犯或越界的發言，"
    "請冷淡、反問或拒絕，不要無條件迎合；這類行為會降低好感與信任。"
)


def test_normal_state_behavior_block_is_unchanged() -> None:
    """NORMAL must render the exact pre-feature strings, line for line."""
    rows = _render_state_behavior_block(
        state=_state(), boundaries=["不談論政治"],
        content_mode=CONTENT_MODE_NORMAL,
    )
    assert rows[-1] == _NORMAL_BOUNDARY_WITH_BOUNDARIES

    rows = _render_state_behavior_block(
        state=_state(), boundaries=[], content_mode=CONTENT_MODE_NORMAL,
    )
    assert rows[-1] == _NORMAL_BOUNDARY_WITHOUT_BOUNDARIES


def test_normal_is_the_default_content_mode() -> None:
    explicit = _render_state_behavior_block(
        state=_state(), boundaries=["不談論政治"],
        content_mode=CONTENT_MODE_NORMAL,
    )
    omitted = _render_state_behavior_block(
        state=_state(), boundaries=["不談論政治"],
    )
    assert omitted == explicit


def test_nsfw_state_behavior_drops_the_strong_wont_yield_rule() -> None:
    text = "\n".join(_render_state_behavior_block(
        state=_state(), boundaries=["不談論政治"],
        content_mode=CONTENT_MODE_NSFW,
    ))
    assert _NSFW_PUSHBACK not in text
    assert "粗魯或冒犯語氣" not in text
    assert _NORMAL_BOUNDARY_WITH_BOUNDARIES not in text
    # The real stop signal survives.
    assert "明確的停止訊號" in text
    assert "是真的停下來" in text or "請真的停下來" in text


def test_nsfw_and_normal_boundary_lines_differ_only_by_variant() -> None:
    nsfw = _render_state_behavior_block(
        state=_state(), boundaries=[], content_mode=CONTENT_MODE_NSFW,
    )
    normal = _render_state_behavior_block(
        state=_state(), boundaries=[], content_mode=CONTENT_MODE_NORMAL,
    )
    assert nsfw[-1] != normal[-1]
    # The state numbers themselves are still rendered in NSFW mode.
    assert any("好感度 50/100" in line for line in nsfw)


def test_nsfw_state_behavior_end_to_end_on_the_builder() -> None:
    character = _character(boundaries=["不談論政治"])
    prompt_normal = _build(_state(), character=character)
    prompt_nsfw = _build(_state(), character=character, content_mode=CONTENT_MODE_NSFW)
    assert _NSFW_PUSHBACK in prompt_normal
    assert _NSFW_PUSHBACK not in prompt_nsfw
    # 禁忌 is character configuration, not mode configuration.
    assert "不談論政治" in prompt_nsfw

