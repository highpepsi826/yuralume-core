"""Fenced conversation adapter for durable foreground chat commands.

The adapter is deliberately small.  ChatService still owns prompt assembly,
model/tool execution and post-turn work; this object owns the two conversation
append boundaries and mirrors their durable row references onto the command
receipt.  Every append uses the stable command id as its idempotency key.
"""

from __future__ import annotations

import hashlib

from kokoro_link.application.services.external_chat.turn_support import (
    generated_snapshot_to_json,
    rebuild_assistant_from_generated,
)
from kokoro_link.contracts.durable_chat_commands import (
    ChatTurnCommand,
    DurableChatCommandRepositoryPort,
)
from kokoro_link.contracts.durable_chat_effects import DurableChatEffectLedgerPort
from kokoro_link.contracts.external_chat_execution import (
    AttachmentSnapshot,
    CommittedTurnRef,
    ExternalChatTurnExecutionPort,
    GeneratedTurnSnapshot,
    PersistedTurnRef,
    PostTurnAnchors,
)
from kokoro_link.contracts.repositories import ConversationRepositoryPort
from kokoro_link.domain.entities.conversation import Conversation, Message


class DurableChatTurnFenced(RuntimeError):
    """The command lease no longer permits a conversation write."""


class DurableChatTurnAdapter(ExternalChatTurnExecutionPort):
    """Bind ChatService's external-turn seam to one durable command claim."""

    def __init__(
        self,
        *,
        repository: DurableChatCommandRepositoryPort,
        conversations: ConversationRepositoryPort,
        command: ChatTurnCommand,
        lease_seconds: int,
        effects: DurableChatEffectLedgerPort | None = None,
    ) -> None:
        self._repository = repository
        self._conversations = conversations
        self._command = command
        self._lease_seconds = lease_seconds
        self._effects = effects
        self._user_id = command.user_message_id
        self._user_position = command.user_message_position
        self._assistant_id = command.assistant_message_id
        self._assistant_position = command.assistant_message_position

    @property
    def result_message_id(self) -> int | None:
        return self._assistant_id or self._command.result_message_id

    async def persist_user_turn(
        self, conversation: Conversation, message: Message,
    ) -> PersistedTurnRef:
        if self._user_id is not None:
            return PersistedTurnRef(
                row_id=self._user_id,
                position=self._user_position or 0,
            )
        result = await self._conversations.append_messages(
            conversation.id,
            expected_next_position=len(conversation.messages),
            messages=[message],
            idempotency_key=f"{self._command.turn_id}:user",
        )
        if not result.ok or not result.row_ids:
            raise DurableChatTurnFenced("user append conflict")
        row_id, position = result.row_ids[0], result.positions[0]
        recorded = await self._repository.record_user_turn(
            turn_id=self._command.turn_id,
            worker_id=self._command.lease_owner or "",
            lease_generation=self._command.lease_generation,
            user_message_id=row_id,
            user_message_position=position,
        )
        if not recorded:
            raise DurableChatTurnFenced("user receipt write fenced")
        self._user_id = row_id
        self._user_position = position
        return PersistedTurnRef(row_id=row_id, position=position)

    async def checkpoint_generated(
        self, generated: GeneratedTurnSnapshot,
    ) -> None:
        snapshot_json = generated_snapshot_to_json(generated)
        saved = await self._repository.mark_generated(
            turn_id=self._command.turn_id,
            worker_id=self._command.lease_owner or "",
            lease_generation=self._command.lease_generation,
            snapshot_json=snapshot_json,
            snapshot_hash=hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest(),
        )
        if not saved:
            raise DurableChatTurnFenced("generated checkpoint fenced")

    async def commit_assistant_turn(
        self, conversation: Conversation, assistant_message: Message,
    ) -> CommittedTurnRef:
        if self._assistant_id is None:
            expected = (
                self._user_position + 1
                if self._user_position is not None
                else len(conversation.messages)
            )
            result = await self._conversations.append_messages(
                conversation.id,
                expected_next_position=expected,
                messages=[assistant_message],
                idempotency_key=f"{self._command.turn_id}:assistant",
            )
            if not result.ok or not result.row_ids:
                raise DurableChatTurnFenced("assistant append conflict")
            self._assistant_id = result.row_ids[0]
            self._assistant_position = result.positions[0]
        recorded = await self._repository.record_assistant_turn(
            turn_id=self._command.turn_id,
            worker_id=self._command.lease_owner or "",
            lease_generation=self._command.lease_generation,
            assistant_message_id=self._assistant_id,
            assistant_message_position=self._assistant_position or 0,
        )
        if not recorded:
            raise DurableChatTurnFenced("assistant receipt write fenced")
        committed = await self._repository.mark_committed(
            turn_id=self._command.turn_id,
            worker_id=self._command.lease_owner or "",
            lease_generation=self._command.lease_generation,
            result_message_id=self._assistant_id,
        )
        if not committed:
            raise DurableChatTurnFenced("committed receipt write fenced")
        return CommittedTurnRef(
            row_id=self._assistant_id,
            position=self._assistant_position or 0,
        )

    async def commit_deferred_reply(
        self,
        conversation: Conversation,
        user_message: Message,
        assistant_message: Message,
    ) -> CommittedTurnRef:
        if self._user_id is None:
            await self.persist_user_turn(conversation, user_message)
        await self.checkpoint_generated(
            GeneratedTurnSnapshot(
                turn_id=self._command.turn_id,
                assistant_text=assistant_message.content,
                attachments=tuple(
                    AttachmentSnapshot(
                        kind=item.kind,
                        url=item.url,
                        mime_type=item.mime_type,
                        caption=item.caption,
                    )
                    for item in assistant_message.attachments
                ),
                assistant_kind=assistant_message.kind.value,
                content_mode=assistant_message.content_mode.value,
            ),
        )
        return await self.commit_assistant_turn(conversation, assistant_message)

    def stable_turn_id(self) -> str:
        return self._command.turn_id

    def post_turn_anchors(self) -> PostTurnAnchors:
        return PostTurnAnchors(
            user_message_row_id=self._user_id or 0,
            assistant_message_row_id=self._assistant_id or 0,
            assistant_position=self._assistant_position or 0,
        )

    async def heartbeat(self) -> None:
        alive = await self._repository.heartbeat(
            turn_id=self._command.turn_id,
            worker_id=self._command.lease_owner or "",
            lease_generation=self._command.lease_generation,
            lease_seconds=self._lease_seconds,
            phase=self._command.phase,
        )
        if not alive:
            raise DurableChatTurnFenced("lease heartbeat fenced")

    async def record_effect_intent(
        self, *, effect_kind: str, payload_json: str, completed: bool,
        enqueued: bool = False, recovery_required: bool = False,
        error: str | None = None,
    ) -> None:
        if self._effects is None:
            return
        await self._effects.ensure(
            turn_id=self._command.turn_id,
            effect_kind=effect_kind,
            idempotency_key=f"{self._command.turn_id}:{effect_kind}",
            payload_json=payload_json,
        )
        if recovery_required:
            changed = await self._effects.mark_failed(
                turn_id=self._command.turn_id,
                effect_kind=effect_kind,
                error=error or "effect outcome requires reconciliation",
                recovery_required=True,
            )
        elif completed:
            changed = await self._effects.mark_completed(
                turn_id=self._command.turn_id,
                effect_kind=effect_kind,
            )
        elif enqueued:
            changed = await self._effects.mark_enqueued(
                turn_id=self._command.turn_id,
                effect_kind=effect_kind,
            )
        else:
            # ``PENDING`` is the intentional state between registering an
            # effect and learning that its queue enqueue committed.
            return
        if not changed:
            existing = await self._effects.get(
                turn_id=self._command.turn_id,
                effect_kind=effect_kind,
            )
            expected_states = {
                "completed" if completed else (
                    "recovery_required" if recovery_required else "enqueued"
                ),
            }
            if existing is None or existing.state.value not in expected_states:
                raise DurableChatTurnFenced("effect intent write fenced")

    def heartbeat_interval_seconds(self) -> float:
        return max(1.0, self._lease_seconds / 3.0)


def rebuild_assistant_message(snapshot_json: str) -> Message:
    """Public recovery helper kept beside the durable adapter."""

    return rebuild_assistant_from_generated(snapshot_json)


__all__ = [
    "DurableChatTurnAdapter",
    "DurableChatTurnFenced",
    "rebuild_assistant_message",
]
