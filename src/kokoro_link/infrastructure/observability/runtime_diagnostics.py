"""Non-blocking, body-free runtime evidence with request-local correlation."""
from __future__ import annotations

import asyncio
import contextvars
import functools
import time
from contextlib import contextmanager
from uuid import uuid4

_CONTEXT: contextvars.ContextVar[dict] = contextvars.ContextVar("diagnostic_context", default={})


def current_context() -> dict:
    """A copy of structural identities only; callers cannot mutate another task."""
    return dict(_CONTEXT.get())


def _operation_context(parent, fields):
    context = {**parent, **{k: v for k, v in fields.items() if v is not None}}
    context.setdefault("request_id", str(uuid4()))
    context.setdefault("trace_id", context["request_id"])
    if parent.get("operation_id"):
        context["parent_operation_id"] = parent["operation_id"]
    context["operation_id"] = str(uuid4())
    return context


@contextmanager
def diagnostic_scope(*, captured=None, **fields):
    """Restore captured identities while keeping a live descendant's operation."""
    parent = _CONTEXT.get()
    if captured is not None:
        # A model may outlive its resolver task; bind it to the originating work.
        parent = {**captured, **(parent if parent.get("trace_id") == captured.get("trace_id") else {})}
    token = _CONTEXT.set(_operation_context(parent, fields))
    try:
        yield current_context()
    finally:
        _CONTEXT.reset(token)


class DiagnosticRequestMiddleware:
    """Pure ASGI observation including stream closure, without inspecting bodies."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        token = _CONTEXT.set(_operation_context({}, {}))
        started = time.perf_counter()
        status = None
        completed = False
        async def tracked_send(message):
            nonlocal status, completed
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                completed = True
        try:
            await self.app(scope, receive, tracked_send)
        except BaseException as exc:
            event("http.failed", error_type=type(exc).__name__, status="failed")
            raise
        finally:
            # No raw URL, query, headers, client address or request/response body.
            if scope.get("method") != "GET" or (status or 0) >= 400 or not completed:
                route = getattr(scope.get("route"), "path", "unmatched")
                event("http.completed", route=route, http_status=status,
                      status="completed" if completed else "detached",
                      elapsed_ms=int((time.perf_counter() - started) * 1000))
            _CONTEXT.reset(token)


def bind(**fields) -> None:
    """Enrich the current operation after durable identities become available."""
    _CONTEXT.set({**_CONTEXT.get(), **{k: v for k, v in fields.items() if v is not None}})


def event(name: str, **metadata) -> None:
    """Diagnostics must never alter the business operation they observe."""
    try:
        from .persistent_diagnostics import emit_event
        fields = {**_CONTEXT.get(), **metadata}
        emit_event(name, **fields)
    except Exception:
        pass


def observed(phase: str):
    """Observe a coroutine phase, never its input/output bodies or exception text.

    A streaming setup coroutine is only setup, not stream completion. Streaming
    provider iterators must be observed separately for their actual lifetime.
    """
    def decorate(fn):
        @functools.wraps(fn)
        async def wrapped(*args, **kwargs):
            old = _CONTEXT.get()
            fields = dict(old)
            candidate = kwargs.get("job", kwargs.get("payload", kwargs.get("character", kwargs.get("character_id"))))
            if candidate is None and len(args) > 1:
                candidate = args[1]
            for key in ("character_id", "conversation_id"):
                value = getattr(candidate, key, None)
                if value:
                    fields[key] = str(value)
            durable_id = getattr(candidate, "durable_turn_id", None)
            if durable_id:
                fields["turn_id"] = str(durable_id)
            if phase.startswith(("feed", "background")) and getattr(candidate, "id", None):
                fields["character_id"] = str(candidate.id)
            if phase.startswith("background") and isinstance(candidate, str):
                fields["character_id"] = candidate
            if phase == "background.job" and getattr(candidate, "id", None):
                fields = {"job_id": str(candidate.id), "request_id": "job:" + str(candidate.id),
                          "trace_id": "job:" + str(candidate.id)}
                if getattr(candidate, "character_id", None) and getattr(candidate, "kind", None) != "encounter_tick":
                    fields["character_id"] = str(candidate.character_id)
            fields = _operation_context(old if phase != "background.job" else {}, fields)
            token = _CONTEXT.set(fields)
            started = time.perf_counter()
            event("phase.started", phase=phase)
            try:
                result = await fn(*args, **kwargs)
                event("phase.completed", phase=phase, status="succeeded",
                      elapsed_ms=int((time.perf_counter() - started) * 1000))
                return result
            except asyncio.CancelledError:
                event("phase.cancelled", phase=phase, status="cancelled",
                      elapsed_ms=int((time.perf_counter() - started) * 1000))
                raise
            except Exception as exc:
                event("phase.failed", phase=phase, status="failed", error_type=type(exc).__name__,
                      elapsed_ms=int((time.perf_counter() - started) * 1000))
                raise
            finally:
                completed_context = _CONTEXT.get()
                _CONTEXT.reset(token)
                same_character = not old.get("character_id") or old.get("character_id") == completed_context.get("character_id")
                enrich_parent = phase in {"chat.prelude", "chat.request", "chat.stream_setup"}
                if enrich_parent and old and same_character and completed_context.get("request_id") == old.get("request_id"):
                    bind(**{k: v for k, v in completed_context.items()
                            if k in {"character_id", "conversation_id", "turn_id"} and not old.get(k)})
        return wrapped
    return decorate


def response_shape(response) -> dict:
    """Extract structural facts only. Never export headers or provider body text."""
    facts = {"http_status": response.status_code}
    try:
        data = response.json()
        if not isinstance(data, dict):
            return {**facts, "reason": "non_object_json"}
        choices = data.get("choices")
        choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        message = choice.get("message") or {}
        if not isinstance(message, dict):
            message = {}
        content = message.get("content")
        facts.update(has_text=isinstance(content, str) and bool(content.strip()),
                     text_chars=len(content) if isinstance(content, str) else 0,
                     has_tool_calls=bool(message.get("tool_calls")),
                     has_reasoning=bool(message.get("reasoning_content") or message.get("reasoning")))
        # These fields are provider controlled; accept only known structural values.
        finish = choice.get("finish_reason")
        if finish in {"stop", "length", "tool_calls", "content_filter", "function_call"}:
            facts["finish_reason"] = finish
        output = data.get("output")
        if isinstance(output, list):
            texts = [c.get("text") for item in output[:100] if isinstance(item, dict)
                     for c in (item.get("content") or [])[:100] if isinstance(c, dict)
                     and c.get("type") == "output_text" and isinstance(c.get("text"), str)]
            facts.update(has_text=any(x.strip() for x in texts), text_chars=sum(map(len, texts)),
                         has_reasoning=any(isinstance(x, dict) and x.get("type") == "reasoning" for x in output))
    except Exception:
        facts["reason"] = "unreadable_json"
    return facts


def observed_stream(phase: str):
    """Carry correlation across deferred stream consumption and cancellation."""
    def decorate(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            context = _operation_context(_CONTEXT.get(), {})
            async def iterate():
                started = time.perf_counter()
                event_fields = {**context, "phase": phase}
                def report(name, **fields):
                    token = _CONTEXT.set(context)
                    try:
                        event(name, **fields)
                    finally:
                        _CONTEXT.reset(token)
                report("phase.started", **event_fields)
                first = True
                iterator = fn(*args, **kwargs).__aiter__()
                try:
                    while True:
                        token = _CONTEXT.set(context)
                        try:
                            chunk = await iterator.__anext__()
                        except StopAsyncIteration:
                            break
                        finally:
                            _CONTEXT.reset(token)
                        if first:
                            report("phase.first_chunk", **event_fields,
                                  elapsed_ms=int((time.perf_counter() - started) * 1000))
                            first = False
                        yield chunk
                    report("phase.completed", **event_fields, status="succeeded",
                          elapsed_ms=int((time.perf_counter() - started) * 1000))
                except (asyncio.CancelledError, GeneratorExit):
                    report("phase.cancelled", **event_fields, status="cancelled")
                    raise
                except Exception as exc:
                    report("phase.failed", **event_fields, status="failed", error_type=type(exc).__name__,
                          elapsed_ms=int((time.perf_counter() - started) * 1000))
                    raise
                finally:
                    token = _CONTEXT.set(context)
                    try:
                        await iterator.aclose()
                    finally:
                        _CONTEXT.reset(token)
            return iterate()
        return wrapped
    return decorate
