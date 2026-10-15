"""Regression tests for bounded source projections, not business-data mutations."""
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from kokoro_link.infrastructure.observability.diagnostic_export_sources import (
    MAX_ROWS, read_additional_sources,
)
from kokoro_link.infrastructure.persistence.models import GenerationUsageEventRow


def test_turn_auxiliary_metadata_preserves_routes_and_errors_without_prose():
    from kokoro_link.infrastructure.observability.diagnostic_sources import safe_turn_refs
    refs = safe_turn_refs({"material_digest": {"provider_id": "deepseek", "precomputed": True,
                           "bullet_text": "private prompt"},
                          "novelty_gate": {"model_id": "model-a", "error": "private error body",
                           "feedback": "private generated text", "latency_ms": 500},
                          "secret_body": "private secret"})
    assert refs["material_digest"] == {"provider_id": "deepseek", "precomputed": True}
    assert refs["novelty_gate"] == {"model_id": "model-a", "has_error": True, "latency_ms": 500}
    assert "private" not in repr(refs)


@pytest.mark.asyncio
async def test_usage_projection_is_bounded_private_and_includes_cross_window_completion():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(GenerationUsageEventRow.__table__.create)
    start = datetime.now(timezone.utc) - timedelta(hours=1)
    end = start + timedelta(hours=1)
    async with factory() as session, session.begin():
        for index in range(MAX_ROWS + 1):
            session.add(GenerationUsageEventRow(id=f"usage-{index}", character_id="c1", capability="llm",
                created_at=start + timedelta(seconds=index), status="failed", error_code="response_shape",
                error_message="private message", metadata_json='{"api_key":"secret","prompt":"private"}'))
        session.add(GenerationUsageEventRow(id="other-character", character_id="c2", capability="llm", created_at=start))
    sources, coverage = await read_additional_sources(factory, "c1", start, end)
    assert len(sources["generation_events"]) == MAX_ROWS
    assert coverage["generation_events"]["truncated"] is True
    assert coverage["commands"]["status"] == "unavailable"  # missing tables remain isolated
    assert all("metadata_json" not in row and "error_message" not in row for row in sources["generation_events"])
    assert all(row["id"] != "other-character" for row in sources["generation_events"])
    async with factory() as session, session.begin():
        session.add(GenerationUsageEventRow(id="cross-window", character_id="cross", capability="image",
            created_at=start - timedelta(hours=2), completed_at=start + timedelta(minutes=3)))
        session.add(GenerationUsageEventRow(id="after-window", character_id="cross", capability="image",
            created_at=start - timedelta(hours=2), completed_at=end + timedelta(hours=2)))
    sources, coverage = await read_additional_sources(factory, "cross", start, end)
    assert [row["id"] for row in sources["generation_events"]] == ["cross-window"]
    assert sources["generation_events"][0]["window_inclusion"] == "cross_window_activity"
    await engine.dispose()


@pytest.mark.asyncio
async def test_routing_snapshot_safe_provider_profiles_and_read_only_nsfw():
    from kokoro_link.infrastructure.observability.diagnostic_export_sources import routing_snapshot
    from kokoro_link.infrastructure.persistence.models import ProviderConnectionRow
    from kokoro_link.infrastructure.repositories.in_memory_preferences import InMemoryPreferencesRepository
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(ProviderConnectionRow.__table__.create)
    now = datetime.now(timezone.utc)
    async with factory() as session, session.begin():
        session.add(ProviderConnectionRow(id="provider-1", provider="openai", enabled=False,
            config_json=json.dumps({"model": "model-1", "base_url": "https://private?token=secret", "headers": {"auth": "private"}}),
            encrypted_secret_json="encrypted-private", secret_fingerprint="private-fingerprint", created_at=now, updated_at=now))
    class Characters:
        _session_factory = factory
        async def get(self, _): return SimpleNamespace(user_id="owner-1", feature_models=(), feature_image_profiles=())
    class Nsfw:
        async def configured_target(self, *, user_id):
            assert user_id == "owner-1"
            return SimpleNamespace(llm_provider_id="nsfw-provider", llm_model_id="nsfw-model", image_profile_id=None)
        async def get_status(self, **_): raise AssertionError("export must never call mutating get_status")
    container = SimpleNamespace(character_repository=Characters(), conversation_repository=SimpleNamespace(_session_factory=factory), preferences_repository=InMemoryPreferencesRepository(),
        nsfw_mode_service=Nsfw(), model_registry=SimpleNamespace(list_ids=lambda: ["provider-1"]),
        image_profile_registry=SimpleNamespace(profile_ids=["image-1"], profiles=[SimpleNamespace(
            id="image-1", kind="openai", openai=SimpleNamespace(model="image-model", quality="high", api_key="private-image-key"))]))
    snapshot, coverage = await routing_snapshot(container, "c1")
    assert snapshot["provider_connections"] == [{"id": "provider-1", "provider": "openai", "enabled": False,
        "config_truncated": False, "routing_config": {"model": "model-1"}}]
    assert snapshot["image_profiles"][0]["model"] == "image-model"
    assert snapshot["nsfw_mode"]["active"] == "unknown"
    assert snapshot["nsfw_mode"]["target"]["llm_provider_id"] == "nsfw-provider"
    assert "private" not in json.dumps(snapshot)
    assert coverage["scope"] == "current_snapshot_not_history"
    await engine.dispose()
