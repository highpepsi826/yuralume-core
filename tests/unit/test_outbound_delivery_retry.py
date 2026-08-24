from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from kokoro_link.application.services.outbound_delivery_retry_worker import (
    OutboundDeliveryRetryWorker,
)
from kokoro_link.contracts.messaging import OutboundMessage
from kokoro_link.contracts.outbound_deliveries import (
    OutboundDeliveryDraft,
    OutboundDeliveryState,
    serialize_outbound_message,
)
from kokoro_link.domain.entities.messaging_account import MessagingAccount
from kokoro_link.domain.value_objects.delivery_mode import DeliveryMode
from kokoro_link.domain.value_objects.platform import Platform
from kokoro_link.infrastructure.repositories.in_memory_outbound_deliveries import (
    InMemoryOutboundDeliveryRepository,
)
from tests.unit._messaging_harness import (
    build_messaging_harness,
    create_character,
    create_telegram_account,
    make_inbound,
)


_NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_transport_failure_is_pending_and_chat_turn_runs_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = build_messaging_harness()
    ledger = InMemoryOutboundDeliveryRepository()
    # The production container wires this port; inject it into the existing
    # messaging harness so this test keeps the normal ChatService setup.
    harness.dispatcher._outbound_deliveries = ledger  # noqa: SLF001
    character = await create_character(harness)
    account = await create_telegram_account(harness, character_id=character.id)

    llm_calls = 0
    original_send_message = harness.chat_service.send_message

    async def counted_send_message(request):  # noqa: ANN001
        nonlocal llm_calls
        llm_calls += 1
        return await original_send_message(request)

    monkeypatch.setattr(harness.chat_service, "send_message", counted_send_message)
    adapter_calls = 0

    async def fail_transport(_message: OutboundMessage) -> None:
        nonlocal adapter_calls
        adapter_calls += 1
        raise RuntimeError("telegram timeout")

    monkeypatch.setattr(harness.telegram_adapter, "send", fail_transport)

    await harness.dispatcher.handle_inbound(
        make_inbound(
            platform=Platform.TELEGRAM,
            account_id=account.id,
            chat_ref="tg-42",
            text="你好",
        ),
    )

    due = await ledger.list_pending_due(now=_NOW + timedelta(minutes=1))
    assert len(due) == 1
    assert due[0].state is OutboundDeliveryState.PENDING
    assert "TG-TOKEN" not in due[0].payload_json
    assert llm_calls == 1
    assert adapter_calls == 1


@pytest.mark.asyncio
async def test_retry_reuses_payload_and_latest_credentials() -> None:
    ledger = InMemoryOutboundDeliveryRepository()
    account_harness = build_messaging_harness()
    account_repo = account_harness.account_repository
    account = MessagingAccount.create(
        character_id="character-1",
        platform=Platform.TELEGRAM,
        credentials={"bot_token": "OLD-TOKEN"},
        delivery_mode=DeliveryMode.WEBHOOK,
    )
    await account_repo.save(account)
    payload = serialize_outbound_message(
        OutboundMessage(
            platform=Platform.TELEGRAM,
            chat_ref="tg-42",
            text="原本的回覆",
            credentials={"bot_token": "OLD-TOKEN"},
        ),
    )
    await ledger.create_pending(
        delivery_id="delivery-1",
        platform="telegram",
        account_id=account.id,
        chat_ref="tg-42",
        payload_json=payload,
        now=_NOW,
    )
    await account_repo.save(account.with_credentials({"bot_token": "NEW-TOKEN"}))

    class _Adapter:
        platform = Platform.TELEGRAM

        def __init__(self) -> None:
            self.messages: list[OutboundMessage] = []

        async def send(self, message: OutboundMessage) -> None:
            self.messages.append(message)

    adapter = _Adapter()
    worker = OutboundDeliveryRetryWorker(
        ledger=ledger,
        account_repository=account_repo,
        adapters={Platform.TELEGRAM: adapter},
        max_attempts=2,
    )

    await worker.tick(now=_NOW + timedelta(seconds=6))

    assert len(adapter.messages) == 1
    assert adapter.messages[0].text == "原本的回覆"
    assert adapter.messages[0].credentials == {"bot_token": "NEW-TOKEN"}
    stored = (await ledger.list_pending_due(now=_NOW + timedelta(minutes=1)))
    assert stored == []


@pytest.mark.asyncio
async def test_segment_failure_retries_only_unfinished_bubbles() -> None:
    ledger = InMemoryOutboundDeliveryRepository()
    now = _NOW
    await ledger.create_pending_batch(())
    await ledger.create_pending(
        delivery_id="delivery-1",
        platform="telegram",
        account_id="account-1",
        chat_ref="tg-42",
        payload_json=serialize_outbound_message(
            OutboundMessage(
                platform=Platform.TELEGRAM,
                chat_ref="tg-42",
                text="第二段",
                credentials={},
            ),
        ),
        now=now,
    )

    class _AccountRepository:
        async def get(self, account_id: str):  # noqa: ANN001
            assert account_id == "account-1"
            return SimpleNamespace(
                id=account_id,
                platform=Platform.TELEGRAM,
                enabled=True,
                credentials={"bot_token": "CURRENT"},
            )

    class _Adapter:
        platform = Platform.TELEGRAM

        def __init__(self) -> None:
            self.messages: list[OutboundMessage] = []

        async def send(self, message: OutboundMessage) -> None:
            self.messages.append(message)

    adapter = _Adapter()
    worker = OutboundDeliveryRetryWorker(
        ledger=ledger,
        account_repository=_AccountRepository(),  # type: ignore[arg-type]
        adapters={Platform.TELEGRAM: adapter},
    )

    await worker.tick(now=now + timedelta(seconds=6))

    assert [message.text for message in adapter.messages] == ["第二段"]
    stored = await ledger.list_pending_due(now=now + timedelta(minutes=1))
    assert stored == []


@pytest.mark.asyncio
async def test_segment_batch_keeps_later_bubbles_blocked() -> None:
    ledger = InMemoryOutboundDeliveryRepository()
    await ledger.create_pending_batch((
        OutboundDeliveryDraft(
            id="delivery-1",
            platform="telegram",
            account_id="account-1",
            chat_ref="tg-42",
            payload_json=serialize_outbound_message(
                OutboundMessage(
                    platform=Platform.TELEGRAM,
                    chat_ref="tg-42",
                    text="第一段",
                    credentials={},
                ),
            ),
            now=_NOW,
            batch_id="batch-1",
            sequence_no=0,
        ),
        OutboundDeliveryDraft(
            id="delivery-2",
            platform="telegram",
            account_id="account-1",
            chat_ref="tg-42",
            payload_json=serialize_outbound_message(
                OutboundMessage(
                    platform=Platform.TELEGRAM,
                    chat_ref="tg-42",
                    text="第二段",
                    credentials={},
                ),
            ),
            now=_NOW,
            batch_id="batch-1",
            sequence_no=1,
        ),
    ))

    due = await ledger.list_pending_due(now=_NOW)
    assert [item.id for item in due] == ["delivery-1"]
    assert await ledger.claim(
        "delivery-1", owner_id="worker", now=_NOW, lease_seconds=60,
    )
    assert not await ledger.claim(
        "delivery-2", owner_id="worker", now=_NOW, lease_seconds=60,
    )
    assert await ledger.mark_retryable(
        "delivery-1", owner_id="worker", error="timeout",
        next_attempt_at=_NOW, now=_NOW,
    )
    assert [item.id for item in await ledger.list_pending_due(now=_NOW)] == [
        "delivery-1",
    ]
    assert await ledger.claim(
        "delivery-1", owner_id="worker", now=_NOW, lease_seconds=60,
    )
    assert await ledger.mark_delivered(
        "delivery-1", owner_id="worker", now=_NOW,
    )
    assert [item.id for item in await ledger.list_pending_due(now=_NOW)] == [
        "delivery-2",
    ]


@pytest.mark.asyncio
async def test_attempt_ceiling_is_claimed_then_marked_terminal() -> None:
    ledger = InMemoryOutboundDeliveryRepository()
    await ledger.create_pending(
        delivery_id="delivery-1",
        platform="telegram",
        account_id="account-1",
        chat_ref="tg-42",
        payload_json="{}",
        now=_NOW,
    )
    assert await ledger.claim(
        "delivery-1", owner_id="seed", now=_NOW, lease_seconds=1,
    )
    assert await ledger.mark_retryable(
        "delivery-1",
        owner_id="seed",
        error="failed",
        next_attempt_at=_NOW,
        now=_NOW,
    )

    class _AccountRepository:
        async def get(self, _account_id: str):  # noqa: ANN001
            raise AssertionError("terminal rows must not load credentials")

    worker = OutboundDeliveryRetryWorker(
        ledger=ledger,
        account_repository=_AccountRepository(),  # type: ignore[arg-type]
        adapters={},
        max_attempts=1,
    )
    await worker.tick(now=_NOW)

    assert await ledger.list_pending_due(now=_NOW) == []
