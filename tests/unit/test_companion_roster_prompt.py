"""The character's private NPC circle must reach the chat prompt.

``Character.companions`` (the shopkeeper, the cat, the roommate) used to
be read only by the schedule planner and the story-scene writers, so a
chat turn had never heard of them and asked the player "who is that?"
when the player named one.

These tests pin the rendering and the two properties that matter: an
empty roster produces no block at all, and a populated one names every
companion with the fields that were configured.
"""

from dataclasses import replace

from kokoro_link.domain.entities.character import Character
from kokoro_link.domain.value_objects.character_state import CharacterState
from kokoro_link.domain.value_objects.companion import CharacterCompanion
from kokoro_link.infrastructure.prompt.sections.identity import (
    _COMPANION_HEADER,
    _COMPANION_MAX_CHARS,
    _render_companion_roster_block,
)


def _character(**overrides) -> Character:
    state = CharacterState(
        emotion="calm", affection=50, fatigue=10, trust=50, energy=70,
    )
    return replace(
        Character.create(
            name="測試角色",
            summary="測試用",
            personality=[],
            interests=[],
            speaking_style="",
            boundaries=[],
            state=state,
        ),
        **overrides,
    )


def _dango() -> CharacterCompanion:
    return CharacterCompanion.create(
        name="糰子",
        role="舊日式甜品店的店貓",
        brief_profile="一隻親人的橘白貓",
        personality_sketch=("黏人", "愛玩"),
        relationship_snippet="總愛蹭他的腳",
    )


def test_no_companions_renders_nothing() -> None:
    assert _render_companion_roster_block(_character()) == []


def test_companion_is_named_in_the_block() -> None:
    block = _render_companion_roster_block(
        _character(companions=(_dango(),)),
    )

    assert _COMPANION_HEADER in block
    text = "\n".join(block)
    assert "糰子" in text
    assert "舊日式甜品店的店貓" in text
    assert "一隻親人的橘白貓" in text
    assert "黏人" in text and "愛玩" in text
    assert "總愛蹭他的腳" in text


def test_bare_companion_renders_name_only() -> None:
    """A companion with nothing but a name still has to be known."""
    block = _render_companion_roster_block(
        _character(companions=(CharacterCompanion.create(name="阿明"),)),
    )

    assert any("阿明" in line for line in block)


def test_block_stays_within_the_character_budget() -> None:
    many = tuple(
        CharacterCompanion.create(
            name="同伴%d" % index,
            role="角色",
            brief_profile="描述" * 20,
        )
        for index in range(12)
    )
    block = _render_companion_roster_block(_character(companions=many))

    assert sum(len(line) for line in block) <= _COMPANION_MAX_CHARS
    # The cap drops whole trailing entries rather than truncating one.
    assert block[-1].startswith("- ")
    assert "…" not in block[-1]
