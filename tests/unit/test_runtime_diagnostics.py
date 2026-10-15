from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from kokoro_link.infrastructure.observability import persistent_diagnostics, runtime_diagnostics as diagnostics


@pytest.fixture
def events(monkeypatch):
    rows = []
    monkeypatch.setattr(persistent_diagnostics, "emit_event", lambda name, **fields: rows.append({"name": name, **fields}))
    return rows


@pytest.mark.asyncio
async def test_nested_phases_share_request_and_character_without_leaking_to_next_request(events):
    class Service:
        @diagnostics.observed("chat.request")
        async def run(self, payload):
            return await self.child(payload)

        @diagnostics.observed("chat.route")
        async def child(self, payload):
            diagnostics.event("routing.llm", provider_id="provider-a")
            return "private assistant body"

    service = Service()
    first = SimpleNamespace(character_id="character-a", conversation_id="conversation-a")
    assert await service.run(first) == "private assistant body"
    first_rows = list(events)
    assert len({row["request_id"] for row in first_rows}) == 1
    assert all(row["character_id"] == "character-a" for row in first_rows)
    assert all(row["conversation_id"] == "conversation-a" for row in first_rows)
    assert "private assistant body" not in repr(first_rows)
    events.clear()
    await service.run(SimpleNamespace(character_id="character-b"))
    assert events[0]["request_id"] != first_rows[0]["request_id"]
    assert all("conversation_id" not in row for row in events)
    diagnostics.event("outside")
    assert events[-1] == {"name": "outside"}


@pytest.mark.asyncio
async def test_cancellation_is_reraised_recorded_and_context_is_reset(events):
    class Service:
        @diagnostics.observed("chat.request")
        async def run(self, payload):
            raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await Service().run(SimpleNamespace(character_id="character-a"))
    assert [row["name"] for row in events] == ["phase.started", "phase.cancelled"]
    assert events[-1]["status"] == "cancelled"
    diagnostics.event("outside")
    assert events[-1] == {"name": "outside"}


@pytest.mark.asyncio
async def test_concurrent_requests_keep_separate_correlations(events):
    both_started = asyncio.Event()
    arrived = 0

    class Service:
        @diagnostics.observed("chat.request")
        async def run(self, payload):
            nonlocal arrived
            arrived += 1
            if arrived == 2:
                both_started.set()
            await both_started.wait()
            diagnostics.event("request.resumed")

    await asyncio.gather(*(Service().run(SimpleNamespace(character_id=key)) for key in ("a", "b")))
    request_ids = {}
    for row in events:
        request_ids.setdefault(row["character_id"], set()).add(row["request_id"])
    assert all(len(ids) == 1 for ids in request_ids.values())
    assert request_ids["a"].isdisjoint(request_ids["b"])


@pytest.mark.asyncio
async def test_diagnostic_sink_failure_preserves_business_result_and_original_exception(monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError("diagnostic backend unavailable")

    monkeypatch.setattr(persistent_diagnostics, "emit_event", unavailable)

    @diagnostics.observed("provider.completion")
    async def run(fail=False):
        if fail:
            raise ValueError("private provider detail")
        return "business result"

    assert await run() == "business result"
    with pytest.raises(ValueError, match="private provider detail"):
        await run(fail=True)


@pytest.mark.asyncio
async def test_deferred_stream_preserves_nested_correlation_without_leaking_to_consumer(events):
    class Service:
        @diagnostics.observed("chat.stream_setup")
        async def setup(self, payload):
            return self.stream()

        @diagnostics.observed_stream("provider.stream")
        async def stream(self):
            diagnostics.event("provider.before_chunk")
            yield "private first token"
            diagnostics.event("provider.after_chunk")

    stream = await Service().setup(SimpleNamespace(character_id="character-a", conversation_id="conversation-a"))
    setup_request = events[0]["request_id"]
    assert await anext(stream) == "private first token"
    diagnostics.event("consumer")
    assert events[-1] == {"name": "consumer"}
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    nested = [row for row in events if row["name"].startswith("provider.")]
    assert len(nested) == 2
    assert all(row.get("request_id") == setup_request for row in nested)
    assert all(row.get("character_id") == "character-a" for row in nested)
    assert "private first token" not in repr(events)


@pytest.mark.asyncio
async def test_stream_close_records_cancellation_instead_of_success(events):
    @diagnostics.observed_stream("provider.stream")
    async def stream():
        yield "first"
        yield "second"

    iterator = stream()
    await anext(iterator)
    await iterator.aclose()
    assert events[-1]["name"] == "phase.cancelled"
    assert not any(row["name"] == "phase.completed" for row in events)


def test_response_shape_exports_only_structural_facts():
    class Response:
        status_code = 200

        def json(self):
            return {"choices": [{"finish_reason": "stop", "message": {
                "content": "private body", "reasoning_content": "private thought",
                "tool_calls": [{"function": {"arguments": "private arguments"}}],
            }}], "api_key": "private credential"}

    assert diagnostics.response_shape(Response()) == {
        "http_status": 200, "has_text": True, "text_chars": 12,
        "has_reasoning": True, "has_tool_calls": True, "finish_reason": "stop",
    }


def test_response_shape_bounds_responses_output_and_handles_invalid_json():
    class Response:
        status_code = 200

        def json(self):
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": "abc"}]}] * 101}

    shape = diagnostics.response_shape(Response())
    assert shape["text_chars"] == 300
    assert shape["has_text"] is True

    class Invalid(Response):
        def json(self):
            raise ValueError("private parser message")

    assert diagnostics.response_shape(Invalid()) == {"http_status": 200, "reason": "unreadable_json"}


def test_response_shape_does_not_export_provider_controlled_finish_reason():
    class Response:
        status_code = 200

        def json(self):
            return {"choices": [{"finish_reason": "private diagnostic injected by provider",
                                 "message": {"content": "  "}}]}

    shape = diagnostics.response_shape(Response())
    assert "finish_reason" not in shape
    assert shape["has_text"] is False
    assert "private diagnostic" not in repr(shape)


@pytest.mark.asyncio
async def test_http_observation_tracks_stream_completion_without_urls_or_bodies(events):
    async def app(scope, receive, send):
        diagnostics.bind(character_id="char-1", conversation_id="new-conversation")
        diagnostics.event("routing.llm", provider_id="provider-a")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"private response", "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    messages = []
    async def send(message):
        messages.append(message)
    scope = {"type": "http", "method": "POST", "path": "/private-token",
             "query_string": b"token=private-secret", "headers": [(b"authorization", b"private-secret")],
             "route": SimpleNamespace(path="/api/v1/chat")}
    await diagnostics.DiagnosticRequestMiddleware(app)(scope, None, send)
    row = next(x for x in events if x["name"] == "http.completed")
    assert row["status"] == "completed" and row["http_status"] == 200
    assert row["conversation_id"] == "new-conversation"
    assert len({x["request_id"] for x in events}) == 1
    assert "private" not in repr(events)
    assert diagnostics._CONTEXT.get() == {}


@pytest.mark.asyncio
async def test_resolved_conversation_propagates_from_child_phase(events):
    @diagnostics.observed("chat.prelude")
    async def child(payload):
        diagnostics.bind(conversation_id="resolved-c", turn_id="durable-turn")

    @diagnostics.observed("chat.request")
    async def parent(payload):
        await child(payload)
        diagnostics.event("provider.started")

    await parent(SimpleNamespace(character_id="c1", conversation_id=None))
    row = next(x for x in events if x["name"] == "provider.started")
    assert row["conversation_id"] == "resolved-c" and row["turn_id"] == "durable-turn"
    assert diagnostics._CONTEXT.get() == {}
