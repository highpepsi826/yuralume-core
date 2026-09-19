"""ChatService adapter for the durable foreground command executor."""

from __future__ import annotations

import json
import hashlib
from typing import Any

from kokoro_link.application.dto.chat import SendChatMessageRequest
from kokoro_link.application.services.chat_service import (
    ChatCharacterContractEndedError,
    ChatCharacterRestoringError,
    ChatRuntimeLimitExceeded,
    ChatService,
    ChatSubscriptionFrozen,
)
from kokoro_link.application.services.chat_turn_lease import ConversationBusyError
from kokoro_link.application.services.durable_chat_turn import (
    DurableChatTurnAdapter,
    DurableChatTurnFenced,
    rebuild_assistant_message,
)
from kokoro_link.application.services.post_turn_runner import (
    PostTurnEnqueueOutcome,
)
from kokoro_link.contracts.durable_chat_effects import ChatTurnEffectState
from kokoro_link.contracts.durable_chat_effects import DurableChatEffectLedgerPort
from kokoro_link.contracts.durable_chat_commands import ChatTurnCommand, ChatTurnPhase
from kokoro_link.contracts.durable_chat_execution import (
    DurableChatExecutionOutcome,
    DurableChatHeartbeat,
    DurableChatFailedError,
    DurableChatRecoveryRequiredError,
    DurableChatRetryableError,
)


class ChatServiceDurableCommandHandler:
    """Rebuild one accepted payload and run the existing non-streaming turn.

    The adapter does not own receipt transitions.  It only gives the executor
    the same service entry point used by non-durable callers and keeps the
    command ID attached to ChatService's turn-record/billing identity seam.
    """

    def __init__(
        self,
        chat_service: ChatService,
        *,
        repository=None,
        conversation_repository=None,
        lease_seconds: int = 180,
        effects: DurableChatEffectLedgerPort | None = None,
    ) -> None:
        self._chat_service = chat_service
        self._repository = repository
        self._conversation_repository = conversation_repository
        self._lease_seconds = lease_seconds
        self._effects = effects

    async def __call__(
        self,
        command: ChatTurnCommand,
        *,
        heartbeat: DurableChatHeartbeat,
    ) -> DurableChatExecutionOutcome:
        payload = self._payload(command)
        first_heartbeat = await heartbeat(ChatTurnPhase.PREPARING)
        if not first_heartbeat:
            raise DurableChatRecoveryRequiredError(
                "worker_lease_lost",
                "Worker lease was lost before chat execution started",
            )
        try:
            if command.state.value == "committed":
                await self._recover_committed_effect(command)
                return DurableChatExecutionOutcome(
                    result_message_id=command.result_message_id,
                    generated_already_persisted=True,
                    committed_already_persisted=True,
                )
            if command.state.value == "generated":
                if (
                    self._repository is None
                    or self._conversation_repository is None
                    or command.generated_snapshot_json is None
                ):
                    raise DurableChatRecoveryRequiredError(
                        "generated_snapshot_missing",
                        "Generated turn snapshot is unavailable for recovery",
                    )
                adapter = DurableChatTurnAdapter(
                    repository=self._repository,
                    conversations=self._conversation_repository,
                    command=command,
                    lease_seconds=self._lease_seconds,
                    effects=self._effects,
                )
                conversation = await self._conversation_repository.get(
                    command.conversation_id,
                )
                if conversation is None:
                    raise DurableChatRecoveryRequiredError(
                        "conversation_missing",
                        "Conversation is unavailable for generated recovery",
                    )
                await adapter.commit_assistant_turn(
                    conversation,
                    rebuild_assistant_message(command.generated_snapshot_json),
                )
                return DurableChatExecutionOutcome(
                    result_message_id=adapter.result_message_id,
                    generated_already_persisted=True,
                    committed_already_persisted=True,
                )
            if self._repository is None or self._conversation_repository is None:
                if not await heartbeat(ChatTurnPhase.WAITING_MODEL):
                    raise DurableChatRecoveryRequiredError(
                        "worker_lease_lost",
                        "Worker lease was lost before the model call",
                    )
                reply = await self._chat_service.send_message(
                    payload,
                    current_user_id=command.owner_id,
                )
                if not await heartbeat(ChatTurnPhase.COMMITTING):
                    raise DurableChatRecoveryRequiredError(
                        "worker_lease_lost_after_chat",
                        "Worker lease was lost after chat execution; reconcile the turn",
                    )
                snapshot_json = json.dumps(
                    reply.model_dump(mode="json"),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                return DurableChatExecutionOutcome(
                    generated_snapshot_json=snapshot_json,
                    generated_snapshot_hash=hashlib.sha256(
                        snapshot_json.encode("utf-8"),
                    ).hexdigest(),
                )
            adapter = DurableChatTurnAdapter(
                repository=self._repository,
                conversations=self._conversation_repository,
                command=command,
                lease_seconds=self._lease_seconds,
                effects=self._effects,
            )
            if not await heartbeat(ChatTurnPhase.WAITING_MODEL):
                raise DurableChatRecoveryRequiredError(
                    "worker_lease_lost",
                    "Worker lease was lost before the model call",
                )
            reply = await self._chat_service.send_message(
                payload,
                current_user_id=command.owner_id,
                external_turn=adapter,
            )
        except DurableChatTurnFenced as exc:
            raise DurableChatRecoveryRequiredError(
                "worker_lease_lost",
                "Worker lease was lost while committing the chat turn",
            ) from exc
        except ConversationBusyError as exc:
            raise DurableChatRetryableError(
                "conversation_busy",
                "Conversation is still busy; the worker will retry",
                retry_after_seconds=2,
            ) from exc
        except (
            ChatSubscriptionFrozen,
            ChatCharacterRestoringError,
            ChatCharacterContractEndedError,
            ChatRuntimeLimitExceeded,
        ) as exc:
            raise DurableChatFailedError(
                _known_failure_code(exc),
                _known_failure_message(exc),
            ) from exc
        if not await heartbeat(ChatTurnPhase.COMMITTING):
            raise DurableChatRecoveryRequiredError(
                "worker_lease_lost_after_chat",
                "Worker lease was lost after chat execution; reconcile the turn",
            )
        return DurableChatExecutionOutcome(
            result_message_id=adapter.result_message_id,
            generated_already_persisted=True,
            committed_already_persisted=True,
        )

    async def _recover_committed_effect(self, command: ChatTurnCommand) -> None:
        """Repair a crash gap after the assistant row was committed."""
        if self._effects is None:
            return
        if command.assistant_message_position is None:
            raise DurableChatRecoveryRequiredError(
                "assistant_anchor_missing",
                "Committed turn is missing its assistant message anchor",
            )
        effect = await self._effects.get(
            turn_id=command.turn_id, effect_kind="post_turn",
        )
        if effect is not None:
            if effect.state in {
                ChatTurnEffectState.COMPLETED,
                ChatTurnEffectState.ENQUEUED,
                ChatTurnEffectState.RUNNING,
                ChatTurnEffectState.FAILED,
                ChatTurnEffectState.RECOVERY_REQUIRED,
            }:
                return
            # ``pending`` is the crash window around queue enqueue. The
            # stable queue key is safe to submit again: an already committed
            # job converges to ``ALREADY_ACTIVE`` and an uncommitted job is
            # inserted once. The post-turn body itself is never replayed here.
        try:
            raw = json.loads(command.payload_json)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DurableChatRecoveryRequiredError(
                "invalid_command_payload",
                "The committed turn payload could not be reconstructed",
            ) from exc
        has_user_message = not (
            bool(raw.get("stage_nudge"))
            and not str(raw.get("message", "")).strip()
        )
        content_mode = raw.get("content_mode")
        if not isinstance(content_mode, str) or not content_mode:
            content_mode = "normal"
        conversation = await self._conversation_repository.get(
            command.conversation_id,
        ) if self._conversation_repository is not None else None
        if conversation is not None:
            position = command.assistant_message_position
            if 0 <= position < len(conversation.messages):
                content_mode = conversation.messages[position].content_mode.value
        payload = {
            "turn_record_id": command.turn_id,
            "conversation_id": command.conversation_id,
            "character_id": command.character_id,
            "assistant_index": command.assistant_message_position or 0,
            "persona_enabled": bool(raw.get("operator_persona_enabled", True)),
            "content_mode": content_mode,
            "has_user_message": has_user_message,
            "private_memory_ids": [],
        }
        payload_json = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        await self._effects.ensure(
            turn_id=command.turn_id,
            effect_kind="post_turn",
            idempotency_key=f"{command.turn_id}:post_turn",
            payload_json=payload_json,
        )
        enqueue = getattr(
            self._chat_service, "enqueue_post_turn_for_record", None,
        )
        if not callable(enqueue):
            await self._mark_effect_recovery_required(
                command.turn_id,
                "A durable post-turn enqueuer is unavailable during recovery",
            )
            return
        try:
            outcome = await enqueue(
                turn_record_id=command.turn_id,
                conversation_id=command.conversation_id,
                character_id=command.character_id,
                assistant_index=command.assistant_message_position or 0,
                persona_enabled=payload["persona_enabled"],
                content_mode=content_mode,
                has_user_message=has_user_message,
                private_memory_ids=(),
                operator_id=command.owner_id,
            )
        except Exception as exc:  # noqa: BLE001 - unknown enqueue commit
            await self._mark_effect_recovery_required(
                command.turn_id,
                "Recovered post-turn enqueue failed with an unknown outcome: "
                f"{type(exc).__name__}",
            )
            return
        if outcome in {
            PostTurnEnqueueOutcome.INSERTED,
            PostTurnEnqueueOutcome.ALREADY_ACTIVE,
        }:
            await self._effects.mark_enqueued(
                turn_id=command.turn_id,
                effect_kind="post_turn",
            )
            return
        await self._mark_effect_recovery_required(
            command.turn_id,
            "Recovered post-turn intent has no confirmed durable queue owner "
            f"({outcome.value})",
        )

    async def _mark_effect_recovery_required(
        self, turn_id: str, error: str,
    ) -> None:
        assert self._effects is not None
        await self._effects.mark_failed(
            turn_id=turn_id,
            effect_kind="post_turn",
            error=error,
            recovery_required=True,
        )

    @staticmethod
    def _payload(command: ChatTurnCommand) -> SendChatMessageRequest:
        try:
            raw: Any = json.loads(command.payload_json)
            payload = SendChatMessageRequest.model_validate(raw)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DurableChatFailedError(
                "invalid_command_payload",
                "The accepted chat payload could not be reconstructed",
            ) from exc
        return payload.model_copy(update={"durable_turn_id": command.turn_id})


def _known_failure_code(error: BaseException) -> str:
    if isinstance(error, ChatSubscriptionFrozen):
        return "subscription_frozen"
    if isinstance(error, ChatCharacterRestoringError):
        return "character_restoring"
    if isinstance(error, ChatCharacterContractEndedError):
        return "character_contract_ended"
    if isinstance(error, ChatRuntimeLimitExceeded):
        return "runtime_limit_exceeded"
    return "chat_rejected"


def _known_failure_message(error: BaseException) -> str:
    if isinstance(error, ChatSubscriptionFrozen):
        return "Chat is unavailable while the subscription is frozen"
    if isinstance(error, ChatCharacterRestoringError):
        return "Chat is unavailable while the character is being restored"
    if isinstance(error, ChatCharacterContractEndedError):
        return "Chat is unavailable because the character contract ended"
    if isinstance(error, ChatRuntimeLimitExceeded):
        return "Chat runtime limit reached"
    return "Chat request was rejected before model execution"


__all__ = ["ChatServiceDurableCommandHandler"]
