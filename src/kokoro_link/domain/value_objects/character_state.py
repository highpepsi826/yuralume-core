from dataclasses import dataclass, replace
from datetime import datetime


def _clamp(value: int) -> int:
    return max(0, min(100, value))


_UNSET = object()


CURRENT_INTENT_STATUS_UNKNOWN = "unknown"
CURRENT_INTENT_STATUS_FRESH = "fresh"
CURRENT_INTENT_STATUS_VALID = "valid"
CURRENT_INTENT_STATUS_NEEDS_REVIEW = "needs_review"
CURRENT_INTENT_STATUS_REVIEWING = "reviewing"
CURRENT_INTENT_STATUS_EXPIRED = "expired"
CURRENT_INTENT_STATUS_CLEARED = "cleared"
CURRENT_INTENT_STATUS_UPDATED = "updated"
CURRENT_INTENT_STATUS_NEEDS_SCHEDULE = "needs_schedule"
CURRENT_INTENT_STATUS_CANDIDATE = "candidate"


@dataclass(frozen=True, slots=True)
class CharacterState:
    emotion: str
    affection: int
    fatigue: int
    trust: int
    energy: int
    last_active_at: datetime | None = None
    current_intent: str | None = None
    """Short-term goal for the current conversation (1-sentence, revised each turn)."""
    current_intent_updated_at: datetime | None = None
    """When the current intent text was last written. ``None`` denotes legacy/unknown."""
    current_intent_checked_at: datetime | None = None
    """Most recent deterministic reconciliation pass for the current intent."""
    current_intent_reviewed_at: datetime | None = None
    """Most recent LLM fallback attempt; also serves as its per-intent cooldown stamp."""
    current_intent_status: str = CURRENT_INTENT_STATUS_UNKNOWN
    """Small lifecycle value shown to the owner; never drives outgoing delivery."""
    current_intent_source: str = ""
    """Writer of the current intent text, e.g. ``post_turn`` or ``idle_drift``."""
    current_intent_candidate_at: datetime | None = None
    """Internal time to re-evaluate an unscheduled, concrete intent."""
    current_intent_candidate_key: str = ""
    """Stable fingerprint for the one internal candidate tied to this intent."""

    def adjust(
        self,
        *,
        emotion: str | None = None,
        affection_delta: int = 0,
        fatigue_delta: int = 0,
        trust_delta: int = 0,
        energy_delta: int = 0,
        current_intent: str | None | object = _UNSET,
    ) -> "CharacterState":
        next_intent = self.current_intent if current_intent is _UNSET else current_intent
        intent_changed = (
            current_intent is not _UNSET
            and next_intent != self.current_intent
        )
        return replace(
            self,
            emotion=self.emotion if emotion is None else emotion,
            affection=_clamp(self.affection + affection_delta),
            fatigue=_clamp(self.fatigue + fatigue_delta),
            trust=_clamp(self.trust + trust_delta),
            energy=_clamp(self.energy + energy_delta),
            current_intent=next_intent,
            current_intent_updated_at=(
                None if intent_changed else self.current_intent_updated_at
            ),
            current_intent_checked_at=(
                None if intent_changed else self.current_intent_checked_at
            ),
            current_intent_reviewed_at=(
                None if intent_changed else self.current_intent_reviewed_at
            ),
            current_intent_status=(
                CURRENT_INTENT_STATUS_UNKNOWN
                if intent_changed else self.current_intent_status
            ),
            current_intent_source=("" if intent_changed else self.current_intent_source),
            current_intent_candidate_at=(
                None if intent_changed else self.current_intent_candidate_at
            ),
            current_intent_candidate_key=(
                "" if intent_changed else self.current_intent_candidate_key
            ),
        )

    def with_current_intent(
        self,
        intent: str | None,
        *,
        updated_at: datetime,
        source: str,
        status: str = CURRENT_INTENT_STATUS_FRESH,
    ) -> "CharacterState":
        """Write a new intent with lifecycle metadata from its actual writer."""
        cleaned = (intent or "").strip() or None
        return replace(
            self,
            current_intent=cleaned,
            current_intent_updated_at=updated_at,
            current_intent_checked_at=None,
            current_intent_reviewed_at=None,
            current_intent_status=(status or CURRENT_INTENT_STATUS_UNKNOWN).strip(),
            current_intent_source=(source or "").strip(),
            current_intent_candidate_at=None,
            current_intent_candidate_key="",
        )

    def with_current_intent_check(
        self,
        *,
        checked_at: datetime,
        status: str,
        reviewed_at: datetime | None | object = _UNSET,
    ) -> "CharacterState":
        """Record a deterministic or LLM reconciliation without changing text."""
        return replace(
            self,
            current_intent_checked_at=checked_at,
            current_intent_reviewed_at=(
                self.current_intent_reviewed_at
                if reviewed_at is _UNSET else reviewed_at
            ),
            current_intent_status=(status or CURRENT_INTENT_STATUS_UNKNOWN).strip(),
        )

    def with_active_now(self, now: datetime) -> "CharacterState":
        """Return a copy with ``last_active_at`` set to *now*."""
        return replace(self, last_active_at=now)
