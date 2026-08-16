"""Bounded LLM fallback for stale character current intents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from kokoro_link.domain.entities.character import Character


@dataclass(frozen=True, slots=True)
class CurrentIntentReview:
    """A reviewer verdict that can only keep, replace, or clear text."""

    action: str
    replacement: str = ""
    reason: str = ""

    @property
    def normalized_action(self) -> str:
        return self.action.strip().lower()


class CurrentIntentReviewerPort(Protocol):
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
        """Review one stale/ambiguous intent without sending any message.

        ``None`` means unavailable or unusable output. Callers must leave the
        prior text intact in that case and retry only after their cooldown.
        """
