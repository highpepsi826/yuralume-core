"""Real metering/recorder integration with fake providers and no network or DB."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from kokoro_link.application.services.character_tick_executor import CharacterTickExecutor
from kokoro_link.application.services.execution_mode_runner import ExecutionModeRunner
from kokoro_link.infrastructure.observability import persistent_diagnostics, runtime_diagnostics as diagnostics
from kokoro_link.infrastructure.usage.llm_metering import MeteredActiveLLMProvider
from kokoro_link.infrastructure.usage.recorder import BackgroundUsageEventRecorder

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


class _Model:
    provider_id = "fake"
    supports_vision = False
    last_request_id = "fake-upstream"

    @diagnostics.observed("provider.generate")
    async def generate(self, prompt, **kwargs):
        await asyncio.sleep(0)
        return "generated"

    @diagnostics.observed_stream("provider.stream")
    async def generate_stream(self, prompt, **kwargs):
        await asyncio.sleep(0)
        yield "first"
        await asyncio.sleep(0)
        yield "second"


class _Provider:
    @diagnostics.observed("feature.resolve")
    async def resolve(self, feature_key=None, **kwargs):
        await asyncio.sleep(0)
        return _Model()


@pytest.fixture
def harness(monkeypatch):
    events, rows = [], []
    monkeypatch.setenv("KOKORO_ENABLE_USAGE_LEDGER", "true")
    monkeypatch.setattr(persistent_diagnostics, "emit_event", lambda name, **fields: events.append({"name": name, **fields}))
    recorder = BackgroundUsageEventRecorder(SimpleNamespace(add=AsyncMock(side_effect=lambda event: rows.append(event))))
    provider = MeteredActiveLLMProvider(inner=_Provider(), recorder=lambda: recorder)
    token = diagnostics._CONTEXT.set({})
    yield SimpleNamespace(events=events, rows=rows, recorder=recorder, provider=provider)
    diagnostics._CONTEXT.reset(token)


def _started(harness, phase):
    return [event for event in harness.events if event["name"] == "phase.started" and event.get("phase") == phase]


def _assert_usage_matches_generation(harness, phase):
    starts = {event["operation_id"]: event for event in _started(harness, phase)}
    assert len(starts) == len(harness.rows)
    for row in harness.rows:
        generation = starts[row.request_id]
        assert row.metadata["operation_id"] == generation["operation_id"]
        assert row.metadata["trace_id"] == generation["trace_id"]
        assert row.character_id == generation["character_id"]
        assert row.upstream_request_id == "fake-upstream"


async def test_feature_resolution_generation_and_persisted_usage_share_trace(harness):
    with diagnostics.diagnostic_scope(character_id="a", conversation_id="conversation-a", turn_id="turn-a"):
        model = await harness.provider.resolve("schedule", character=SimpleNamespace(id="a", user_id="operator"))
        assert await model.generate("input") == "generated"
    await harness.recorder.flush()
    _assert_usage_matches_generation(harness, "generation.feature")
    trace = harness.rows[0].metadata["trace_id"]
    assert {event["trace_id"] for event in _started(harness, "feature.resolve") + _started(harness, "provider.generate")} == {trace}
    assert harness.rows[0].conversation_id == "conversation-a"
    assert harness.rows[0].turn_record_id == "turn-a"
    assert diagnostics.current_context() == {}


async def test_deferred_parallel_streams_keep_their_origin_after_resolver_scope_exits(harness):
    async def prepare(cid):
        with diagnostics.diagnostic_scope(character_id=cid):
            model = await harness.provider.resolve("schedule", character=SimpleNamespace(id=cid, user_id="operator"))
            return model.generate_stream("input")

    streams = await asyncio.gather(prepare("a"), prepare("b"))
    with diagnostics.diagnostic_scope(character_id="unrelated", trace_id="unrelated"):
        previous = diagnostics.current_context()

        async def consume(stream):
            result = []
            async for chunk in stream:
                assert diagnostics.current_context() == previous
                result.append(chunk)
            return result

        assert await asyncio.gather(*(consume(stream) for stream in streams)) == [["first", "second"], ["first", "second"]]
        assert diagnostics.current_context() == previous
    await harness.recorder.flush()
    _assert_usage_matches_generation(harness, "generation.feature_stream")
    assert {row.character_id for row in harness.rows} == {"a", "b"}
    assert len({row.metadata["trace_id"] for row in harness.rows}) == 2
    for row in harness.rows:
        origin = next(event for event in _started(harness, "feature.resolve") if event["character_id"] == row.character_id)
        assert row.metadata["trace_id"] == origin["trace_id"]
    assert diagnostics.current_context() == {}


async def test_real_job_retry_keeps_trace_through_provider_and_usage(harness):
    class Schedule:
        async def ensure_window(self, character):
            model = await harness.provider.resolve("schedule", character=character)
            await model.generate("input")

    runner = ExecutionModeRunner(
        queue=SimpleNamespace(),
        character_repository=SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(id="a", user_id="operator"))),
        character_tick_executor=CharacterTickExecutor(dispatcher=SimpleNamespace(), schedule_service=Schedule()),
        social_tick_executor=SimpleNamespace(), gate_service=SimpleNamespace(), cursor=SimpleNamespace(),
    )
    job = SimpleNamespace(id="durable-metered", kind="character_warmup", character_id="a", payload={}, attempt_count=1, due_at=NOW)
    for attempt in (1, 2):
        job.attempt_count = attempt
        result = await runner.execute(job, would_run=True, skip_reason=None, now=NOW, worker_id="worker", lease_seconds=120)
        assert result.action == "complete"
    await harness.recorder.flush()
    _assert_usage_matches_generation(harness, "generation.feature")
    assert len(harness.rows) == 2
    assert {row.metadata["trace_id"] for row in harness.rows} == {"job:durable-metered"}
    assert {row.metadata["job_id"] for row in harness.rows} == {"durable-metered"}
    assert len({row.request_id for row in harness.rows}) == 2
    assert len({event["operation_id"] for event in _started(harness, "background.job")}) == 2
    assert diagnostics.current_context() == {}


async def test_stream_early_close_records_origin_and_restores_consumer(harness):
    with diagnostics.diagnostic_scope(character_id="a"):
        model = await harness.provider.resolve("schedule", character=SimpleNamespace(id="a", user_id="operator"))
        stream = model.generate_stream("input")
    assert await anext(stream) == "first"
    assert diagnostics.current_context() == {}
    await stream.aclose()
    await harness.recorder.flush()
    assert len(harness.rows) == 1
    _assert_usage_matches_generation(harness, "generation.feature_stream")
    assert harness.rows[0].character_id == "a"
    assert harness.rows[0].status == "failed"
    assert harness.rows[0].error_code == "GeneratorExit"
    assert diagnostics.current_context() == {}


@pytest.mark.parametrize("streaming", [False, True])
async def test_cancellation_is_failed_usage_and_restores_all_context(harness, monkeypatch, streaming):
    reached = asyncio.Event()

    class BlockingModel(_Model):
        @diagnostics.observed("provider.generate")
        async def generate(self, prompt, **kwargs):
            reached.set()
            await asyncio.Future()

        @diagnostics.observed_stream("provider.stream")
        async def generate_stream(self, prompt, **kwargs):
            yield "first"
            reached.set()
            await asyncio.Future()

    monkeypatch.setattr(harness.provider.inner, "resolve", AsyncMock(return_value=BlockingModel()))
    with diagnostics.diagnostic_scope(character_id="a"):
        model = await harness.provider.resolve("schedule", character=SimpleNamespace(id="a", user_id="operator"))

    async def consume():
        if streaming:
            async for _chunk in model.generate_stream("input"):
                pass
        else:
            await model.generate("input")

    with diagnostics.diagnostic_scope(character_id="unrelated"):
        previous = diagnostics.current_context()
        task = asyncio.create_task(consume())
        await reached.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert diagnostics.current_context() == previous
    await harness.recorder.flush()
    assert len(harness.rows) == 1
    row = harness.rows[0]
    assert row.status == "failed"
    assert row.error_code == "CancelledError"
    assert row.character_id == "a"
    assert row.metadata["trace_id"] != previous["trace_id"]
    assert diagnostics.current_context() == {}


async def test_observed_child_character_does_not_replace_parent_identity(harness):
    class OtherCharacterWork:
        @diagnostics.observed("background.character_warmup")
        async def run(self, character):
            diagnostics.bind(conversation_id="conversation-b", turn_id="turn-b")

    with diagnostics.diagnostic_scope(character_id="a", conversation_id="conversation-a", turn_id="turn-a"):
        previous = diagnostics.current_context()
        await OtherCharacterWork().run(SimpleNamespace(id="b"))
        assert diagnostics.current_context() == previous
    assert diagnostics.current_context() == {}


async def test_global_deferred_stream_events_do_not_adopt_consumer_character_or_job(harness):
    model = await harness.provider.resolve("global-maintenance")
    stream = model.generate_stream("input")
    with diagnostics.diagnostic_scope(character_id="unrelated", job_id="unrelated-job", turn_id="unrelated-turn"):
        previous = diagnostics.current_context()
        assert [chunk async for chunk in stream] == ["first", "second"]
        assert diagnostics.current_context() == previous
    await harness.recorder.flush()
    phases = [event for event in harness.events if event.get("phase") in {"generation.feature_stream", "provider.stream"}]
    assert phases
    for event in phases:
        assert "character_id" not in event
        assert "job_id" not in event
        assert "turn_id" not in event
    assert len(harness.rows) == 1
    assert harness.rows[0].character_id is None
    assert "job_id" not in harness.rows[0].metadata
    assert diagnostics.current_context() == {}
