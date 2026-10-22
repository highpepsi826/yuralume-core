"""Gender as a learned layer-1 fact, and the address-change evidence guard.

Covers GENDER_AND_ADDRESS_SEPARATION_IMPLEMENTATION_REFERENCE.md tests 1-10.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from kokoro_link.application.services.operator_persona_projection_service import (
    _safe_projection_facts,
)
from kokoro_link.application.services.operator_persona_service import (
    OperatorPersonaService,
)
from kokoro_link.bootstrap.settings import PersonaSettings
from kokoro_link.domain.entities.operator_persona import OperatorPersona
from kokoro_link.domain.value_objects.profile_field import (
    CandidateField,
    EvidenceRef,
    ProfileField,
)
from kokoro_link.infrastructure.persona import llm_consolidator, llm_extractor
from kokoro_link.infrastructure.post_turn.llm_processor import (
    _parse_address_changes,
    _parse_response as post_turn_parse_response,
)
from unittest.mock import AsyncMock

_PLAYER_MSG = "我是女的！是女朋友！你又打錯了！"


def _extract(candidates: list[dict], user_message: str):
    return llm_extractor._parse_response(
        json.dumps({"candidates": candidates}, ensure_ascii=False),
        character_id="char-A",
        conversation_id="conv-1",
        user_message_id="msg-1",
        user_message=user_message,
        recent_user_messages=(),
    )


def _gender_entry(**overrides) -> dict:
    entry = {
        "layer": 1,
        "field_key": "gender",
        "value": "女性",
        "quote": "我是女的",
        "self_confidence": 0.9,
        "subject": "operator_self",
    }
    entry.update(overrides)
    return entry


# 1
def test_gender_operator_self_is_accepted() -> None:
    out = _extract([_gender_entry()], "我是女的")
    assert [(c.layer, c.field_key, c.proposed_value) for c in out] == [
        (1, "gender", "女性"),
    ]


# 2
def test_gender_about_other_person_is_rejected() -> None:
    out = _extract(
        [_gender_entry(subject="other_person", quote="我朋友是女的")],
        "我朋友是女的",
    )
    assert out == []


# 3
def test_gender_missing_subject_is_rejected() -> None:
    entry = _gender_entry()
    del entry["subject"]
    assert _extract([entry], "我是女的") == []


def _evidence() -> EvidenceRef:
    return EvidenceRef(
        turn_id="msg-1",
        conversation_id="conv-1",
        quote="我是女的",
        extracted_at=datetime.now(timezone.utc),
    )


def _gender_candidate(cid: str) -> CandidateField:
    return CandidateField(
        candidate_id=cid,
        field_key="gender",
        layer=1,
        proposed_value="女性",
        evidence_ref=_evidence(),
        raw_extractor_confidence=0.8,
        character_id="char-A",
    )


# 4
def test_consolidator_accepts_gender_promote_and_merge() -> None:
    a = _gender_candidate("a")
    b = _gender_candidate("b")
    result = llm_consolidator._parse_response(
        json.dumps({"actions": [
            {
                "type": "promote", "candidate_id": "a",
                "field_key": "gender", "layer": 1,
                "value": "女性", "new_confidence": 0.8,
            },
            {
                "type": "merge", "candidate_ids": ["a", "b"],
                "field_key": "gender", "layer": 1,
                "value": "女性", "new_confidence": 0.85,
            },
        ]}, ensure_ascii=False),
        candidate_by_id={"a": a, "b": b},
        valid_field_ids=set(),
        confirmed_by_id={},
    )
    assert len(result.promotions) == 1
    assert len(result.merges) == 1


def _gender_field(confidence: float = 0.8) -> ProfileField:
    return ProfileField(
        field_key="gender",
        layer=1,
        value="女性",
        confidence=confidence,
        evidence_refs=(_evidence(),),
        last_updated=datetime.now(timezone.utc),
        update_count=2,
        source="extraction",
        character_id="char-A",
        field_id="fld-gender",
    )


# 5
def test_gender_renders_in_prompt_layer1_line() -> None:
    svc = OperatorPersonaService(
        repository=AsyncMock(),
        strength_calculator=AsyncMock(),
        settings=PersonaSettings(),
    )
    persona = OperatorPersona(
        character_id="char-A",
        operator_id="default",
        layer1_identity={"gender": _gender_field(0.75)},
    )
    body = "\n".join(svc.render_for_prompt(persona))
    assert "性別：女性" in body


# 6
def test_gender_appears_in_projection_facts() -> None:
    persona = OperatorPersona(
        character_id="char-A",
        operator_id="default",
        layer1_identity={"gender": _gender_field(0.8)},
    )
    facts = _safe_projection_facts(persona)
    assert [(f.field_key, f.value) for f in facts] == [("gender", "女性")]


# 7
def test_address_change_with_non_substring_source_text_is_dropped() -> None:
    out = _parse_address_changes(
        [{
            "direction": "player", "new_value": "森森",
            "subject": "operator_self", "source_text": "今天開始叫我森森",
        }],
        user_message="晚安",
    )
    assert out == []


# 8
def test_address_change_with_empty_source_text_is_dropped() -> None:
    out = _parse_address_changes(
        [{
            "direction": "player", "new_value": "森森",
            "subject": "operator_self", "source_text": "",
        }],
        user_message="今天開始叫我森森",
    )
    assert out == []


def test_address_change_with_verbatim_source_text_is_kept() -> None:
    out = _parse_address_changes(
        [{
            "direction": "player", "new_value": "森森",
            "subject": "operator_self", "source_text": "叫我森森",
        }],
        user_message="今天開始叫我森森",
    )
    assert len(out) == 1


# 9
def test_2026_10_19_correction_drops_empty_and_invented_renames() -> None:
    """The model, following the routing rule, emits no address change; a
    paraphrased / invented quote of the same turn is also dropped."""
    empty = post_turn_parse_response(
        '{"memories": [], "address_changes": []}',
        character_id="c1", conversation_id="conv1",
        user_message=_PLAYER_MSG,
    )
    assert empty.address_changes == []

    invented = post_turn_parse_response(
        json.dumps({"memories": [], "address_changes": [{
            "direction": "player", "new_value": "女朋友",
            "subject": "operator_self",
            "source_text": "以後請叫我女朋友",
        }]}, ensure_ascii=False),
        character_id="c1", conversation_id="conv1",
        user_message=_PLAYER_MSG,
    )
    assert invented.address_changes == []


def test_verbatim_quote_of_correction_still_passes_guard() -> None:
    """Documents the residual risk accepted under B-lite (design 2c): the
    evidence guard cannot reject a genuine verbatim quote, so a model that
    ignores routing rule (f) and quotes 「是女朋友」 still yields a rename.
    Part 1 (learned gender) is what makes that state recoverable. If this
    test starts failing, the guard has grown stricter and the design doc's
    B-lite section must be revisited."""
    verbatim = post_turn_parse_response(
        json.dumps({"memories": [], "address_changes": [{
            "direction": "player", "new_value": "女朋友",
            "subject": "operator_self",
            "source_text": "是女朋友",
        }]}, ensure_ascii=False),
        character_id="c1", conversation_id="conv1",
        user_message=_PLAYER_MSG,
    )
    assert len(verbatim.address_changes) == 1


# 10
def test_layer1_whitelists_do_not_drift() -> None:
    assert set(llm_extractor._LAYER_FIELD_KEYS[1]) == set(
        llm_consolidator._LAYER_FIELD_KEYS[1],
    )
    assert "gender" in llm_consolidator._LAYER_FIELD_KEYS[1]
    assert "gender" not in llm_extractor._IDENTITY_FIELD_KEYS
