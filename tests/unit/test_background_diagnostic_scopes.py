"""Background entry points correlate real nested work without external services."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from kokoro_link.application.services.character_tick_executor import CharacterTickExecutor
from kokoro_link.application.services.execution_mode_runner import ExecutionModeRunner
from kokoro_link.application.services.proactive_dispatcher import ProactiveDispatcher
from kokoro_link.contracts.background_jobs import ClaimedJob
from kokoro_link.domain.value_objects.proactive_trigger import ProactiveTrigger
from kokoro_link.infrastructure.observability import persistent_diagnostics, runtime_diagnostics as diagnostics

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


async def test_global_parent_does_not_adopt_nested_character(events):
    @diagnostics.observed('background.character_tick')
    async def child(character):
        diagnostics.event('child.work')

    with diagnostics.diagnostic_scope(job_id='global-job') as before:
        await child(character=SimpleNamespace(id='character-a'))
        assert diagnostics.current_context() == before
        diagnostics.event('global.work')
    row = next(row for row in events if row['name'] == 'global.work')
    assert 'character_id' not in row
    assert next(row for row in events if row['name'] == 'child.work')['character_id'] == 'character-a'


@pytest.fixture
def events(monkeypatch):
    recorded = []
    monkeypatch.setattr(persistent_diagnostics, "emit_event", lambda name, **fields: recorded.append({"name": name, **fields}))
    token = diagnostics._CONTEXT.set({})
    yield recorded
    diagnostics._CONTEXT.reset(token)


class _Schedule:
    @diagnostics.observed("feature.resolve")
    async def ensure_window(self, character):
        await asyncio.sleep(0)
        # Child tasks must inherit the character and job context.
        await asyncio.create_task(self._provider())

    @diagnostics.observed("provider.execute")
    async def _provider(self):
        await asyncio.sleep(0)


def _executor():
    return CharacterTickExecutor(dispatcher=SimpleNamespace(), schedule_service=_Schedule())


async def test_direct_maintenance_and_warmup_keep_parallel_characters_isolated(events):
    executor = _executor()
    await asyncio.gather(
        executor.run_warmup(SimpleNamespace(id="a"), now=NOW),
        executor.step_schedule_maintenance(character=SimpleNamespace(id="b")),
    )
    providers = [event for event in events if event.get("phase") == "provider.execute" and event["name"] == "phase.started"]
    assert {event["character_id"] for event in providers} == {"a", "b"}
    assert len({event["trace_id"] for event in providers}) == 2
    for provider in providers:
        feature = next(event for event in events if event.get("phase") == "feature.resolve" and event["name"] == "phase.started" and event["character_id"] == provider["character_id"])
        assert provider["trace_id"] == feature["trace_id"]
        assert provider["parent_operation_id"] == feature["operation_id"]
        assert provider["operation_id"] != feature["operation_id"]
    assert diagnostics._CONTEXT.get() == {}


def _job():
    return ClaimedJob(
        id="durable-1", kind="character_warmup", attempt_count=1, max_attempts=5,
        fencing_epoch=0, idempotency_key="warmup:a", priority=3, due_at=NOW,
        payload_version=1, payload={}, lease_owner="worker",
        lease_until=NOW + timedelta(seconds=120), character_id="a",
    )


async def test_durable_job_retry_keeps_trace_and_new_operation(events):
    runner = ExecutionModeRunner(
        queue=SimpleNamespace(), character_repository=SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(id="a"))),
        character_tick_executor=_executor(), social_tick_executor=SimpleNamespace(),
        gate_service=SimpleNamespace(), cursor=SimpleNamespace(),
    )
    diagnostics.bind(request_id="unrelated-request", trace_id="unrelated-trace", character_id="other")
    previous = dict(diagnostics._CONTEXT.get())
    for attempt in (1, 2):
        result = await runner.execute(
            replace(_job(), attempt_count=attempt), would_run=True, skip_reason=None,
            now=NOW, worker_id="worker", lease_seconds=120,
        )
        assert result.action == "complete"
        assert diagnostics._CONTEXT.get() == previous
    roots = [event for event in events if event.get("phase") == "background.job" and event["name"] == "phase.started"]
    assert len(roots) == 2
    assert {event["trace_id"] for event in roots} == {"job:durable-1"}
    assert len({event["operation_id"] for event in roots}) == 2
    providers = [event for event in events if event.get("phase") == "provider.execute"]
    assert providers
    assert all(event["job_id"] == "durable-1" and event["character_id"] == "a" and event["trace_id"] == "job:durable-1" for event in providers)


async def test_direct_proactive_evaluation_scopes_character_id(events):
    dispatcher = ProactiveDispatcher.__new__(ProactiveDispatcher)
    dispatcher._evaluation_lease = None
    dispatcher._resolve_now = lambda now: now

    @diagnostics.observed("feature.resolve")
    async def evaluate(**kwargs):
        diagnostics.event("test.provider")
        return "unchanged-result"

    dispatcher._evaluate_unlocked = evaluate
    assert await dispatcher.evaluate(character_id="a", trigger=ProactiveTrigger.TICK, now=NOW) == "unchanged-result"
    nested = next(event for event in events if event["name"] == "test.provider")
    root = next(event for event in events if event.get("phase") == "background.proactive_evaluate" and event["name"] == "phase.started")
    assert nested["character_id"] == "a"
    assert nested["trace_id"] == root["trace_id"]
    assert nested["parent_operation_id"] == root["operation_id"]
    assert diagnostics._CONTEXT.get() == {}
