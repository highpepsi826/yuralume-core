"""LLM adapter for bounded current-intent reconciliation."""

from __future__ import annotations

import logging
import re
from datetime import datetime

from kokoro_link.application.services.model_resolver import ModelResolver
from kokoro_link.contracts.active_llm import ActiveLLMProviderPort
from kokoro_link.contracts.current_intent_reviewer import (
    CurrentIntentReview,
    CurrentIntentReviewerPort,
)
from kokoro_link.contracts.llm import ChatModelPort
from kokoro_link.domain.entities.character import Character
from kokoro_link.infrastructure.prompt.operator_language import (
    render_operator_language_hint,
)
from kokoro_link.infrastructure.prompts import get_default_loader


_LOGGER = logging.getLogger(__name__)
_MAX_INTENT_CHARS = 120
_MAX_REASON_CHARS = 160
_ACTION_RE = re.compile(r"^(?:判定|action)\s*[:：]\s*(.*)$", re.IGNORECASE)
_INTENT_RE = re.compile(r"^(?:新意圖|replacement)\s*[:：]\s*(.*)$", re.IGNORECASE)
_REASON_RE = re.compile(r"^(?:原因|reason)\s*[:：]\s*(.*)$", re.IGNORECASE)


class LLMCurrentIntentReviewer(CurrentIntentReviewerPort):
    """Review only stale intent text; never produces a send decision or task."""

    def __init__(
        self,
        model: ChatModelPort | None = None,
        *,
        provider: ActiveLLMProviderPort | None = None,
        feature_key: str | None = None,
    ) -> None:
        self._resolver = ModelResolver(
            provider=provider, model=model, feature_key=feature_key,
        )

    async def review(
        self,
        *,
        character: Character,
        current_intent: str,
        intent_age_minutes: float | None,
        now: datetime,
        schedule_summary: str,
        operator_primary_language: str = "zh-TW",
    ) -> CurrentIntentReview | None:
        if await self._resolver.is_fake(character=character):
            return CurrentIntentReview(action="keep", reason="fake provider")
        prompt = _build_prompt(
            character=character,
            current_intent=current_intent,
            intent_age_minutes=intent_age_minutes,
            now=now,
            schedule_summary=schedule_summary,
            operator_primary_language=operator_primary_language,
        )
        try:
            raw = await self._resolver.generate(prompt, character=character)
        except Exception:
            _LOGGER.exception(
                "current-intent review LLM call failed character=%s",
                character.id,
            )
            return None
        return _parse(raw)


class NullCurrentIntentReviewer(CurrentIntentReviewerPort):
    async def review(
        self,
        *,
        character: Character,
        current_intent: str,
        intent_age_minutes: float | None,
        now: datetime,
        schedule_summary: str,
        operator_primary_language: str = "zh-TW",
    ) -> CurrentIntentReview | None:
        return None


def _build_prompt(
    *,
    character: Character,
    current_intent: str,
    intent_age_minutes: float | None,
    now: datetime,
    schedule_summary: str,
    operator_primary_language: str,
) -> str:
    age = "未知（舊資料）" if intent_age_minutes is None else f"{intent_age_minutes:.0f} 分鐘"
    persona_lines = [f"- 名稱：{character.name}"]
    if character.summary:
        persona_lines.append(f"- 簡介：{character.summary[:160]}")
    if character.personality:
        persona_lines.append("- 性格：" + "、".join(character.personality[:6]))
    persona_lines.append(
        f"- 狀態：{character.state.emotion}；精力 {character.state.energy}/100",
    )
    return get_default_loader().render(
        "state/current_intent_reconcile",
        language_hint=render_operator_language_hint(operator_primary_language),
        persona_block="\n".join(persona_lines),
        current_intent=current_intent[:_MAX_INTENT_CHARS],
        intent_age=age,
        now=now.isoformat(),
        schedule_summary=schedule_summary or "（沒有可用行程）",
        max_intent_chars=_MAX_INTENT_CHARS,
        max_reason_chars=_MAX_REASON_CHARS,
    )


def _parse(raw: str) -> CurrentIntentReview | None:
    action = ""
    replacement = ""
    reason = ""
    for line in (raw or "").strip().splitlines():
        text = line.strip().strip("` ")
        if not text:
            continue
        match = _ACTION_RE.match(text)
        if match:
            action = match.group(1).strip().lower()
            continue
        match = _INTENT_RE.match(text)
        if match:
            replacement = match.group(1).strip().strip('「」"\'')
            continue
        match = _REASON_RE.match(text)
        if match:
            reason = match.group(1).strip().strip('「」"\'')
    aliases = {
        "keep": "keep", "保留": "keep",
        "replace": "replace", "更新": "replace",
        "clear": "clear", "清除": "clear",
    }
    action = aliases.get(action, "")
    if not action:
        return None
    if action == "replace":
        replacement = replacement[:_MAX_INTENT_CHARS].strip()
        if not replacement:
            return None
    return CurrentIntentReview(
        action=action,
        replacement=replacement,
        reason=reason[:_MAX_REASON_CHARS].strip(),
    )
