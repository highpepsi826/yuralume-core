"""Durable ledger for outbound channel messages.

The assistant turn is persisted before a channel call is made.  This ledger
stores the exact channel payload (without credentials), allowing a transport
timeout to be retried without invoking the LLM or appending another turn.
Telegram has no idempotency key, so a timeout can still produce a duplicate if
the platform accepted the request before the connection was lost.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from kokoro_link.contracts.clock import ensure_utc
from kokoro_link.contracts.messaging import (
    OutboundAttachment,
    OutboundMessage,
)
from kokoro_link.domain.value_objects.platform import Platform


class OutboundDeliveryState(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class OutboundDelivery:
    id: str
    platform: str
    account_id: str
    chat_ref: str
    batch_id: str | None
    sequence_no: int
    payload_json: str
    state: OutboundDeliveryState
    attempt_count: int
    next_attempt_at: datetime
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    delivered_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class OutboundDeliveryDraft:
    """One immutable row to insert before a channel network call."""

    id: str
    platform: str
    account_id: str
    chat_ref: str
    payload_json: str
    now: datetime
    batch_id: str | None = None
    sequence_no: int = 0


class OutboundDeliveryRepositoryPort(Protocol):
    async def create_pending_batch(
        self, drafts: Sequence[OutboundDeliveryDraft],
    ) -> list[OutboundDelivery]: ...

    async def create_pending(
        self,
        *,
        delivery_id: str,
        platform: str,
        account_id: str,
        chat_ref: str,
        payload_json: str,
        now: datetime,
    ) -> OutboundDelivery: ...

    async def claim(
        self,
        delivery_id: str,
        *,
        owner_id: str,
        now: datetime,
        lease_seconds: float,
    ) -> bool: ...

    async def mark_delivered(
        self, delivery_id: str, *, owner_id: str, now: datetime,
    ) -> bool: ...

    async def mark_retryable(
        self,
        delivery_id: str,
        *,
        owner_id: str,
        error: str,
        next_attempt_at: datetime,
        now: datetime,
    ) -> bool: ...

    async def mark_terminal(
        self,
        delivery_id: str,
        *,
        owner_id: str,
        reason: str,
        now: datetime,
    ) -> bool: ...

    async def list_pending_due(
        self, *, now: datetime, limit: int = 100,
    ) -> list[OutboundDelivery]: ...


def serialize_outbound_message(message: OutboundMessage) -> str:
    """Serialize only the replayable payload; never serialize credentials."""
    payload = {
        "platform": message.platform.value,
        "chat_ref": message.chat_ref,
        "text": message.text,
        "attachments": [
            {
                "kind": attachment.kind,
                "url": attachment.url,
                "mime_type": attachment.mime_type,
                "caption": attachment.caption,
            }
            for attachment in message.attachments
        ],
        "locale": message.locale,
        "reply_context": dict(message.reply_context),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def deserialize_outbound_message(
    payload_json: str, *, credentials: dict[str, str],
) -> OutboundMessage:
    """Rehydrate a stored payload with freshly loaded account credentials."""
    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise ValueError("outbound payload must be a JSON object")
    platform = Platform(str(payload["platform"]))
    chat_ref = payload["chat_ref"]
    text = payload.get("text", "")
    if not isinstance(chat_ref, str) or not isinstance(text, str):
        raise ValueError("outbound payload has invalid chat_ref/text")
    raw_attachments = payload.get("attachments", [])
    if not isinstance(raw_attachments, list):
        raise ValueError("outbound payload attachments must be a list")
    attachments: list[OutboundAttachment] = []
    for raw in raw_attachments:
        if not isinstance(raw, dict):
            raise ValueError("outbound attachment must be an object")
        url = raw.get("url")
        kind = raw.get("kind")
        if not isinstance(url, str) or not isinstance(kind, str):
            raise ValueError("outbound attachment has invalid kind/url")
        attachments.append(
            OutboundAttachment(
                kind=kind,
                url=url,
                mime_type=str(raw.get("mime_type") or "application/octet-stream"),
                caption=(
                    raw["caption"]
                    if isinstance(raw.get("caption"), str) else None
                ),
            ),
        )
    raw_context = payload.get("reply_context", {})
    if not isinstance(raw_context, dict):
        raw_context = {}
    return OutboundMessage(
        platform=platform,
        chat_ref=chat_ref,
        text=text,
        credentials=dict(credentials),
        attachments=tuple(attachments),
        locale=str(payload.get("locale") or "zh-TW"),
        reply_context={
            str(key): str(value)
            for key, value in raw_context.items()
            if isinstance(key, str) and isinstance(value, str)
        },
    )


def delivery_from_values(**values: object) -> OutboundDelivery:
    """Build a DTO from ORM/in-memory values with normalized timestamps."""
    return OutboundDelivery(
        id=str(values["id"]),
        platform=str(values["platform"]),
        account_id=str(values["account_id"]),
        chat_ref=str(values["chat_ref"]),
        batch_id=(
            str(values["batch_id"])
            if values.get("batch_id") is not None else None
        ),
        sequence_no=int(values.get("sequence_no", 0)),
        payload_json=str(values["payload_json"]),
        state=OutboundDeliveryState(str(values["state"])),
        attempt_count=int(values.get("attempt_count", 0)),
        next_attempt_at=ensure_utc(values["next_attempt_at"]),  # type: ignore[arg-type]
        last_error=(
            str(values["last_error"])
            if values.get("last_error") is not None else None
        ),
        created_at=ensure_utc(values["created_at"]),  # type: ignore[arg-type]
        updated_at=ensure_utc(values["updated_at"]),  # type: ignore[arg-type]
        delivered_at=(
            ensure_utc(values["delivered_at"])  # type: ignore[arg-type]
            if values.get("delivered_at") is not None else None
        ),
    )
