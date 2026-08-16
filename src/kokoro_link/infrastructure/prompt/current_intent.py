"""Prompt-ready facts for a character's private short-term intent.

``current_intent`` is useful continuity context, but it is not a shared
appointment and must never turn into an implicit delivery instruction.  Both
proactive LLM layers use the same rendering so the intention judge and message
decider receive the same bounded fact.
"""

from __future__ import annotations

from datetime import datetime, tzinfo

from kokoro_link.contracts.clock import ensure_utc
from kokoro_link.domain.value_objects.character_state import CharacterState
from kokoro_link.domain.value_objects.timezone import to_timezone


def render_current_intent_fact_lines(
    state: CharacterState,
    *,
    now: datetime,
    local_tz: tzinfo,
) -> list[str]:
    """Render a private-intent fact without turning it into a send command."""
    intent = (state.current_intent or "").strip()
    if not intent:
        return []

    lines = [
        "當下意圖（角色私下的短期念頭，不是雙方已確認的約定；"
        "它本身不會要求你發訊息）：",
        f"- {intent[:300]}",
    ]
    candidate_at = state.current_intent_candidate_at
    if candidate_at is None:
        return lines

    candidate_utc = ensure_utc(candidate_at)
    local_candidate = to_timezone(candidate_utc, local_tz)
    timestamp = local_candidate.strftime("%m/%d %H:%M")
    now_utc = ensure_utc(now)
    if candidate_utc <= now_utc:
        lines.append(
            f"- 內部檢查時間已到（{timestamp}）：這只是可以重新衡量的候選動機。"
            "是否發訊仍須依人格、當下情境與所有正常 gate 判斷；可以選擇不發。"
        )
    else:
        lines.append(
            f"- 內部檢查時間：{timestamp}。在那之前不可把它說成共同約定、"
            "提醒或已答應要做的事，也不可為此提早發訊。"
        )
    return lines
