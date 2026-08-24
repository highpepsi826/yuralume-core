from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from kokoro_link.infrastructure.persistence.models import OutboundMessageDeliveryRow
from kokoro_link.infrastructure.persistence.sa_outbound_deliveries import (
    SAOutboundDeliveryRepository,
)


@pytest.mark.asyncio
async def test_create_pending_does_not_read_expired_orm_attributes() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(OutboundMessageDeliveryRow.__table__.create)
    try:
        factory = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=True,
        )
        repository = SAOutboundDeliveryRepository(factory)
        saved = await repository.create_pending(
            delivery_id="delivery-1",
            platform="telegram",
            account_id="account-1",
            chat_ref="chat-1",
            payload_json="{}",
            now=datetime(2026, 8, 25, tzinfo=timezone.utc),
        )
        assert saved.id == "delivery-1"
        assert saved.attempt_count == 0
    finally:
        await engine.dispose()
