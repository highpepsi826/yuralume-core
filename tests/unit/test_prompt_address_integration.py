"""The prompt builder consumes resolved addresses (Step 6 wiring)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from kokoro_link.application.services.operator_persona_service import (
    OperatorPersonaService,
)
from kokoro_link.domain.entities.character_operator_relationship_seed import (
    CharacterOperatorRelationshipSeed,
)
from kokoro_link.domain.entities.operator_persona import OperatorPersona
from kokoro_link.domain.entities.operator_profile import (
    DEFAULT_OPERATOR_DISPLAY_NAME,
    OperatorProfile,
)
from kokoro_link.domain.value_objects.profile_field import EvidenceRef, ProfileField
from kokoro_link.domain.value_objects.resolved_address import (
    AddressProvenance,
    ResolvedAddress,
)
from kokoro_link.infrastructure.prompt.default import (
    _render_operator_block,
    _render_register_block,
)
from kokoro_link.infrastructure.prompt.initial_relationship import (
    render_initial_relationship_seed_lines,
)


def test_operator_block_uses_resolved_primary_over_display_name() -> None:
    operator = OperatorProfile(id="op1", display_name="alex_4821")
    resolved = ResolvedAddress(
        primary="阿力",
        aliases=("alex_4821",),
        provenance=AddressProvenance.EXPLICIT_SEED,
    )
    lines = _render_operator_block(operator, resolved)
    text = "\n".join(lines)
    assert "稱呼：阿力" in text          # resolved per-char name wins
    assert "稱呼：alex_4821" not in text  # raw platform label demoted
    assert "別稱：alex_4821" in text     # old/platform label kept as alias


def test_operator_block_without_resolver_keeps_legacy_behaviour() -> None:
    operator = OperatorProfile(id="op1", display_name="Alex")
    lines = _render_operator_block(operator)  # no resolved → legacy path
    assert "- 稱呼：Alex" in "\n".join(lines)


def test_operator_block_fallback_renders_nothing() -> None:
    # Placeholder operator + a fallback resolution (no seed/persona/real
    # name anywhere) → the block stays quiet so the legacy 「使用者」
    # wording elsewhere still reads naturally.
    operator = OperatorProfile.default()
    fallback = ResolvedAddress(primary="對方", provenance=AddressProvenance.FALLBACK)
    assert _render_operator_block(operator, fallback) == []


def test_operator_block_renders_a_configured_pronoun() -> None:
    operator = OperatorProfile(id="op1", display_name="桃桃", pronouns="她")
    text = "\n".join(_render_operator_block(operator))
    assert "- 代名詞：她" in text


def test_operator_block_renders_pronoun_with_a_resolved_address() -> None:
    # The resolved-address branch is a separate render path from the
    # display-name one; a pronoun that only reached the second would go
    # missing on every character with a seed name.
    operator = OperatorProfile(id="op1", display_name="桃桃", pronouns="她")
    resolved = ResolvedAddress(
        primary="阿力",
        aliases=("桃桃",),
        provenance=AddressProvenance.EXPLICIT_SEED,
    )
    text = "\n".join(_render_operator_block(operator, resolved))
    assert "- 稱呼：阿力" in text
    assert "- 代名詞：她" in text


def test_pronoun_without_a_display_name_renders_no_block() -> None:
    """Pins the documented dependency rather than the desired behaviour.

    ``_render_operator_block`` returns ``[]`` for a profile without a saved
    name so the legacy 「使用者」 wording stays consistent everywhere else.
    That means a pronoun on its own reaches no prompt — which is exactly
    why the settings UI tells the player to save a name first.
    """
    operator = OperatorProfile(
        id="op1",
        display_name=DEFAULT_OPERATOR_DISPLAY_NAME,
        pronouns="她",
    )
    assert operator.has_real_name() is False
    assert _render_operator_block(operator) == []


def test_learned_gender_and_configured_pronoun_do_not_contradict() -> None:
    """Case 4 of the design's test list: the two channels coexist.

    Layer-1 learned gender renders inside 對方資料 (the persona block);
    the configured pronoun renders as 代名詞 inside 對方身份. They are
    different facts from different sources, so both have to survive in one
    prompt without either block claiming the other's line.
    """
    persona_service = OperatorPersonaService(
        repository=SimpleNamespace(),
        strength_calculator=SimpleNamespace(),
        settings=SimpleNamespace(
            recent_activity_frequent_min_7d=5,
            recent_activity_inactive_max_7d=14,
        ),
    )
    persona = OperatorPersona(
        character_id="c1",
        operator_id="op1",
        layer1_identity={"gender": ProfileField(
            character_id="c1",
            field_key="gender",
            layer=1,
            value="女性",
            confidence=0.8,
            evidence_refs=(EvidenceRef(
                turn_id="turn-1",
                conversation_id="conv-1",
                quote="我是女生",
                extracted_at=datetime.now(timezone.utc),
            ),),
            last_updated=datetime.now(timezone.utc),
            update_count=1,
            source="extraction",
        )},
    )
    rendered_persona = persona_service.render_for_prompt(persona)
    operator = OperatorProfile(id="op1", display_name="桃桃", pronouns="她")
    identity = _render_operator_block(operator)

    assert any("性別：女性" in line for line in rendered_persona)
    assert any("代名詞：她" in line for line in identity)
    # The pronoun line belongs to the identity block only; duplicating it
    # in the persona block would let the two drift apart after one edit.
    assert not any("代名詞" in line for line in rendered_persona)


def test_initial_relationship_can_drop_address_lines() -> None:
    seed = CharacterOperatorRelationshipSeed(
        character_id="c1",
        operator_id="op1",
        relationship_label="朋友",
        user_address_name="阿力",
        character_address_name="美緒",
    )
    with_address = render_initial_relationship_seed_lines(seed)
    without_address = render_initial_relationship_seed_lines(
        seed, include_address=False,
    )
    assert any("稱呼使用者：阿力" in line for line in with_address)
    assert any("使用者怎麼稱呼你：美緒" in line for line in with_address)
    assert not any("稱呼使用者" in line for line in without_address)
    assert not any("使用者怎麼稱呼你" in line for line in without_address)
    # the relationship context itself is still rendered
    assert any("關係：朋友" in line for line in without_address)


def test_register_block_surfaces_seed_salutation_without_observation() -> None:
    resolved = ResolvedAddress(
        primary="美緒姐", provenance=AddressProvenance.EXPLICIT_SEED,
    )
    lines = _render_register_block(
        character=SimpleNamespace(name="美緒", operator_pace_preference=None),
        address_preference=None,  # nothing observed yet
        resolved_character_address=resolved,
    )
    assert any("對方稱呼你：美緒姐" in line for line in lines)


def test_register_block_ignores_character_name_fallback() -> None:
    # A pure character-name fallback must NOT inject an assumed salutation.
    resolved = ResolvedAddress(
        primary="美緒", provenance=AddressProvenance.CHARACTER_NAME,
    )
    lines = _render_register_block(
        character=SimpleNamespace(name="美緒", operator_pace_preference=None),
        address_preference=None,
        resolved_character_address=resolved,
    )
    assert not any("對方稱呼你" in line for line in lines)
