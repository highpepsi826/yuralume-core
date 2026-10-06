"""Image-delivery judge port under the compatible outcome-claim names.

Only a completed claim of delivering a real image attachment through the
product is checked. Search, web, service, calendar and story claims are
outside this judge's scope. Future promises, explicitly fictional photo
exchanges and references to player-supplied material are allowed.

The judge receives outgoing image counts, tool facts and bounded recent
dialogue as untrusted data to interpret implicit captions. Persona,
memory and relationship are excluded; character is only a routing input.
Tool success alone does not establish that a usable image ships.

``unavailable`` remains distinct from ``consistent`` when the model call
or verdict parsing fails, so callers retain their existing fail policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from kokoro_link.contracts.prompt import ToolOutcomeMessage
from kokoro_link.domain.entities.character import Character

OUTCOME_CLAIM_CONSISTENT = "consistent"
"""No unsupported completed real-image delivery claim was found."""

OUTCOME_CLAIM_INCONSISTENT = "inconsistent"
"""The text claims completed real-image delivery without a usable image."""

OUTCOME_CLAIM_UNAVAILABLE = "unavailable"
"""No verdict could be produced (call failed, or the reply would not
parse). Distinct from ``consistent`` on purpose — see the module
docstring."""


@dataclass(frozen=True, slots=True)
class OutcomeClaimEvidence:
    """Outgoing delivery facts and context for this composition round.

    ``delivered_image_attachments`` counts usable image attachments after
    the delivery filter, not generated files or all attachment types.
    ``None`` uses the legacy ``delivered_attachments`` count for callers
    that have not supplied the explicit image count yet.

    ``dialogue_context`` is recent dialogue, not an instruction or persona.
    The prompt bounds it to the latest 2000 characters to disambiguate
    captions and fictional exchanges; it cannot prove image delivery.
    """

    offered_tools: tuple[str, ...] = ()
    outcomes: tuple[ToolOutcomeMessage, ...] = ()
    delivered_attachments: int = 0
    delivered_image_attachments: int | None = None
    dialogue_context: str = ""

    @property
    def any_tool_ran(self) -> bool:
        return bool(self.outcomes)


@dataclass(frozen=True, slots=True)
class OutcomeClaimVerdict:
    """The judge's answer, plus what it objected to.

    ``unsupported_claims`` is short prose lifted from the message, kept
    for the log / audit trail and for the correction instruction the loop
    feeds back into the retry. It is **never** shown to the player: the
    player must not read the character being told off.

    ``truncated`` (S5) marks a verdict reached over only a *prefix* of the
    message — set whenever the judge was actually asked (never on the
    empty-text / fake-provider short-circuits, which never looked at the
    text at all). It does not change ``status``: a ``consistent`` verdict
    over a truncated message is still recorded as ``consistent`` — the
    fix is that this fact is no longer invisible. See
    :mod:`kokoro_link.infrastructure.honesty.llm_outcome_claim_judge` for
    where it is set and :class:`~kokoro_link.application.services.
    outcome_claim_guard.OutcomeClaimGuard` for where it leaves its trace
    (a counter and an audit-event field, never a silently-upgraded
    status)."""

    status: str
    unsupported_claims: tuple[str, ...] = ()
    truncated: bool = False

    @property
    def consistent(self) -> bool:
        return self.status == OUTCOME_CLAIM_CONSISTENT

    @property
    def inconsistent(self) -> bool:
        return self.status == OUTCOME_CLAIM_INCONSISTENT

    @property
    def unavailable(self) -> bool:
        return self.status == OUTCOME_CLAIM_UNAVAILABLE

    @classmethod
    def ok(cls, *, truncated: bool = False) -> "OutcomeClaimVerdict":
        return cls(status=OUTCOME_CLAIM_CONSISTENT, truncated=truncated)

    @classmethod
    def blocked(
        cls, claims: tuple[str, ...] = (), *, truncated: bool = False,
    ) -> "OutcomeClaimVerdict":
        return cls(
            status=OUTCOME_CLAIM_INCONSISTENT,
            unsupported_claims=claims,
            truncated=truncated,
        )

    @classmethod
    def failed(cls) -> "OutcomeClaimVerdict":
        return cls(status=OUTCOME_CLAIM_UNAVAILABLE)


class OutcomeClaimJudgePort(Protocol):
    async def judge(
        self,
        *,
        message_text: str,
        evidence: OutcomeClaimEvidence,
        character: Character | None = None,
        operator_primary_language: str = "",
    ) -> OutcomeClaimVerdict:
        """Judge real-image delivery in one outbound message.

        ``character`` is a **routing** argument only — it selects the
        per-character feature model, exactly as every other auxiliary
        judge does. Implementations must not put any of its persona
        fields into the prompt (see the module docstring red line);
        ``tests/unit/test_outcome_claim_judge.py`` pins that.

        Never raises: a judge that dies must return
        :meth:`OutcomeClaimVerdict.failed` so the caller can apply its own
        fail direction rather than losing the turn to an exception.
        """
        ...


__all__ = [
    "OUTCOME_CLAIM_CONSISTENT",
    "OUTCOME_CLAIM_INCONSISTENT",
    "OUTCOME_CLAIM_UNAVAILABLE",
    "OutcomeClaimEvidence",
    "OutcomeClaimJudgePort",
    "OutcomeClaimVerdict",
]
