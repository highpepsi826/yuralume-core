"""The post-turn write gate: a blind turn must not rename the player.

The 2026-10-19 mis-address had one shape. The Telegram account's allowlist
was empty, so ``persona_safe_for_account`` returned False, so
``operator_persona_enabled=False`` reached the chat turn — and the prompt
correctly withheld the operator persona, the player persona note and the
resolved address. The post-turn body, however, loaded the operator
unconditionally and ran ``_apply_observed_address_changes`` anyway, so a
turn that never knew who was speaking committed a durable rename to
「女朋友」 and left it in ``operator_address_change_log``.

This module pins the two halves of the repair, end to end through the real
``ChatService`` (not the helper in isolation — ``test_chat_observed_address
_changes`` covers the helper):

* ``operator_persona_enabled=False`` writes no seed change and no log row,
  even when the extractor emits a confident ``player``-direction signal;
* the default (``True``) keeps the pre-fix behaviour byte for byte, so the
  gate cannot quietly turn into "never rename".
"""

from __future__ import annotations

import pytest

from kokoro_link.application.dto.chat import SendChatMessageRequest
from kokoro_link.contracts.post_turn import AddressChangeSignal
from kokoro_link.domain.value_objects.address_change_event import (
    DIRECTION_CHARACTER,
    DIRECTION_PLAYER,
)
from tests.unit.test_turn_undo_address_and_scene import _Harness


def _blind_rename(h: _Harness) -> None:
    """The exact signals the extractor produced on 10/19.

    Both directions, because gating only ``player`` would still let a
    persona-less turn rename how the operator addresses the character.
    """
    h.post_turn.address_changes = [
        AddressChangeSignal(
            direction=DIRECTION_PLAYER, new_value="女朋友",
            subject="operator_self", source_text="叫我女朋友",
        ),
        AddressChangeSignal(direction=DIRECTION_CHARACTER, new_value="寶貝"),
    ]


@pytest.mark.asyncio
async def test_persona_suppressed_turn_commits_no_rename() -> None:
    h = _Harness()
    character_id, operator_id = await h.new_character()
    await h.seed_names(character_id, operator_id, user_address_name="桃桃")
    _blind_rename(h)

    await h.chat.send_message(SendChatMessageRequest(
        character_id=character_id,
        message="叫我女朋友",
        operator_persona_enabled=False,
    ))

    assert await h.names_now(character_id, operator_id) == ("桃桃", "")
    assert await h.log_for(character_id, operator_id) == []


@pytest.mark.asyncio
async def test_persona_suppressed_turn_writes_no_seed_at_all() -> None:
    """The seed check has to be on the pair, not on the row's existence.

    A run that reached ``update_names`` would *create* the seed row even
    when the values ended up empty, which is a write nobody asked for on
    a channel the owner may not even be using.
    """
    h = _Harness()
    character_id, operator_id = await h.new_character()
    await h.seed_names(character_id, operator_id)
    _blind_rename(h)

    await h.chat.send_message(SendChatMessageRequest(
        character_id=character_id,
        message="叫我女朋友",
        operator_persona_enabled=False,
    ))

    seed = await h.seeds.get(character_id, operator_id)
    assert seed is not None
    assert seed.user_address_name == ""
    assert seed.character_address_name == ""


@pytest.mark.asyncio
async def test_persona_enabled_turn_still_renames() -> None:
    """The negative twin — the pre-fix behaviour, unchanged.

    Without this the gate would pass just as well if the address path had
    been broken outright.
    """
    h = _Harness()
    character_id, operator_id = await h.new_character()
    await h.seed_names(character_id, operator_id, user_address_name="桃桃")
    _blind_rename(h)

    await h.chat.send_message(SendChatMessageRequest(
        character_id=character_id,
        message="叫我女朋友",
    ))

    assert await h.names_now(character_id, operator_id) == ("女朋友", "寶貝")
    entries = await h.log_for(character_id, operator_id)
    # ``list_for_pair`` is newest-first, and both rows share one instant,
    # so the order between them is not part of the contract.
    assert sorted(e.new_value for e in entries) == sorted(["女朋友", "寶貝"])
