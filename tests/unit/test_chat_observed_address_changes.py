"""ChatService routes post-turn-observed address changes through the
address-change governance with source=observed (S1 fix), instead of
letting them become a direction-flipped free-text memory."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from kokoro_link.application.services.chat_service import ChatService
from kokoro_link.contracts.post_turn import AddressChangeSignal


class _FakeNamesService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def update_names(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(**kwargs)


def _service(names) -> ChatService:
    # Test the routing method in isolation — it only reads
    # self._relationship_names_service.
    svc = object.__new__(ChatService)
    svc._relationship_names_service = names
    return svc


def _run(svc, *, changes, operator=SimpleNamespace(id="op1"),
         character=SimpleNamespace(id="c1", name="周景澄"),
         persona_enabled: bool = True):
    return asyncio.run(
        svc._apply_observed_address_changes(
            character=character,
            operator=operator,
            changes=changes,
            persona_enabled=persona_enabled,
        )
    )


def test_player_direction_maps_to_user_address_name() -> None:
    names = _FakeNamesService()
    _run(_service(names), changes=[
        AddressChangeSignal(direction="player", new_value="森森"),
    ])
    assert names.calls == [{
        "character_id": "c1",
        "operator_id": "op1",
        "source": "observed",
        "user_address_name": "森森",
    }]


def test_character_direction_maps_to_character_address_name() -> None:
    names = _FakeNamesService()
    _run(_service(names), changes=[
        AddressChangeSignal(direction="character", new_value="小美"),
    ])
    assert names.calls == [{
        "character_id": "c1",
        "operator_id": "op1",
        "source": "observed",
        "character_address_name": "小美",
    }]


def test_unknown_direction_and_empty_value_skipped() -> None:
    names = _FakeNamesService()
    _run(_service(names), changes=[
        AddressChangeSignal(direction="both", new_value="x"),
        AddressChangeSignal(direction="player", new_value=""),
    ])
    assert names.calls == []


def test_noop_when_service_or_operator_missing() -> None:
    # No service wired.
    _run(_service(None), changes=[
        AddressChangeSignal(direction="player", new_value="森森"),
    ])
    # No operator resolved.
    names = _FakeNamesService()
    _run(_service(names), changes=[
        AddressChangeSignal(direction="player", new_value="森森"),
    ], operator=None)
    assert names.calls == []


def test_player_direction_naming_character_itself_is_skipped() -> None:
    # The player calling the character by the character's own name (「周景澄」)
    # is a mis-read: the model proposed using the character's name as how the
    # character should address the *player*. Must not reach update_names.
    names = _FakeNamesService()
    _run(_service(names), changes=[
        AddressChangeSignal(direction="player", new_value="周景澄"),
    ])
    assert names.calls == []


def test_player_direction_character_name_match_is_case_and_space_insensitive() -> None:
    # Normalise whitespace/case before equality (English names): a
    # player-direction value equal to the character name after trimming and
    # case-folding is dropped.
    names = _FakeNamesService()
    _run(
        _service(names),
        changes=[AddressChangeSignal(direction="player", new_value=" Alex ")],
        character=SimpleNamespace(id="c1", name="alex"),
    )
    assert names.calls == []


def test_player_direction_non_matching_name_still_applies() -> None:
    # A genuine player-direction rename that is NOT the character's name must
    # still route to update_names — the guard must not over-block.
    names = _FakeNamesService()
    _run(_service(names), changes=[
        AddressChangeSignal(direction="player", new_value="森森"),
    ])
    assert names.calls == [{
        "character_id": "c1",
        "operator_id": "op1",
        "source": "observed",
        "user_address_name": "森森",
    }]


def test_character_direction_equal_to_character_name_still_applies() -> None:
    # The character-direction check is only for the player direction. A
    # character-direction value equal to the character's name is legitimate
    # (the player addressing the character by name) and must pass through.
    names = _FakeNamesService()
    _run(_service(names), changes=[
        AddressChangeSignal(direction="character", new_value="周景澄"),
    ])
    assert names.calls == [{
        "character_id": "c1",
        "operator_id": "op1",
        "source": "observed",
        "character_address_name": "周景澄",
    }]


def test_persona_suppressed_turn_writes_no_address_change() -> None:
    """The 2026-10-19 asymmetry: reads were gated, writes were not.

    A turn that ran with ``persona_enabled=False`` had the operator persona,
    the player persona note and the resolved address withheld from its
    prompt. It must not then commit a durable rename — that is how a blind
    Telegram turn wrote 「女朋友」 and never corrected it.
    """
    names = _FakeNamesService()
    _run(
        _service(names),
        changes=[AddressChangeSignal(direction="player", new_value="女朋友")],
        persona_enabled=False,
    )
    assert names.calls == []


def test_persona_suppressed_gate_covers_both_directions() -> None:
    # Gating only the player direction would still let a persona-less turn
    # rename how the operator addresses the character.
    names = _FakeNamesService()
    _run(_service(names), changes=[
        AddressChangeSignal(direction="player", new_value="森森"),
        AddressChangeSignal(direction="character", new_value="小雪"),
    ], persona_enabled=False)
    assert names.calls == []


def test_persona_enabled_default_keeps_the_existing_behaviour() -> None:
    # The flag defaults to True so every pre-existing caller keeps writing;
    # the gate only fires when a caller explicitly says the turn was blind.
    names = _FakeNamesService()
    _run(_service(names), changes=[
        AddressChangeSignal(direction="player", new_value="森森"),
    ])
    assert [call["user_address_name"] for call in names.calls] == ["森森"]
