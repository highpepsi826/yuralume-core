"""Adapter-owned probe hook tests (httpx.MockTransport-driven).

The 2026-07-16 unification moved probe request shapes INTO the runtime
adapters (``probe_chat`` / ``probe_embedding`` / ``probe_tts`` /
``probe_image_generation``). These tests pin the core property the
architecture exists for: the probe inherits the adapter's own
signal-driven retry/memo machinery, so a quirk fixed in the adapter can
never again be missed by the probe (the max_tokens incident).
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

import httpx

from kokoro_link.infrastructure.embedder.lm_studio import LMStudioEmbedder
from kokoro_link.infrastructure.image.xai_provider import XAIImageProvider
from kokoro_link.infrastructure.llm.anthropic import AnthropicChatModel
from kokoro_link.infrastructure.llm.openai_compatible import (
    OpenAICompatibleChatModel,
)
from kokoro_link.infrastructure.tts.external_api import (
    ExternalTTSAdapter,
    OpenAITTSAdapter,
)


def _chat_model(**overrides: Any) -> OpenAICompatibleChatModel:
    kwargs: dict[str, Any] = {
        "provider_id": "openai",
        "base_url": "https://api.example.test/v1",
        "api_key": "sk-unit",
        "model": "gpt-x",
    }
    kwargs.update(overrides)
    return OpenAICompatibleChatModel(**kwargs)


# ---------------------------------------------------------------------------
# probe_chat — retry inheritance via the adapter's own machinery
# ---------------------------------------------------------------------------


def test_probe_chat_inherits_max_completion_tokens_rename() -> None:
    """The rename happens inside probe_chat via the adapter's
    ``_adapted_payload_for_rejection`` (not probe-local code) and the
    lesson is memoized on the instance for later runtime calls."""
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "gpt-x"}]})
        body = json.loads(request.content)
        bodies.append(body)
        if "max_tokens" in body:
            return httpx.Response(400, json={"error": {
                "message": "Unsupported parameter: 'max_tokens'. "
                "Use 'max_completion_tokens' instead.",
            }})
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "ok"}}],
        })

    model = _chat_model(max_tokens=64)
    checks = asyncio.run(
        model.probe_chat(transport=httpx.MockTransport(handler)),
    )

    assert [(c.action, c.ok) for c in checks] == [
        ("listed_models", True),
        ("chat_completion", True),
    ]
    assert "max_completion_tokens" in checks[1].detail
    assert [("max_tokens" in b, "max_completion_tokens" in b) for b in bodies] == [
        (True, False),
        (False, True),
    ]
    # The lesson lives on the adapter instance — runtime generate()
    # would now skip the failed round.
    assert model._max_tokens_param == "max_completion_tokens"


def test_probe_chat_inherits_system_role_merge_retry() -> None:
    """A retry the old probe-local payload could never exercise (it sent
    no system message at all): the Gemma-2-class system-role rejection
    is healed by the adapter's merge memo, inside the probe."""
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "gpt-x"}]})
        body = json.loads(request.content)
        bodies.append(body)
        roles = [m.get("role") for m in body["messages"]]
        if "system" in roles:
            return httpx.Response(400, text="System role not supported")
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "ok"}}],
        })

    model = _chat_model()
    checks = asyncio.run(
        model.probe_chat(transport=httpx.MockTransport(handler)),
    )

    assert checks[1].ok is True
    assert len(bodies) == 2
    assert [m.get("role") for m in bodies[1]["messages"]] == ["user"]
    # System prompt merged into the user turn, memoized on the instance.
    assert bodies[1]["messages"][0]["content"].startswith(
        "You are a roleplay character backend.",
    )
    # Model-scoped memo (keyed by the resolved model the probe sent).
    assert model._quirks_for("gpt-x").merge_system_into_user is True


def test_probe_chat_carries_configured_reasoning_knobs() -> None:
    """The probe payload is built by ``_build_payload``, so the opt-in
    knobs the runtime would send (disable_reasoning etc.) ride along —
    a knob-induced upstream rejection fails the Test button instead of
    the first real chat."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": []})
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "ok"}}],
        })

    model = _chat_model(
        max_tokens=64,
        disable_reasoning=True,
        reasoning_effort="high",
    )
    checks = asyncio.run(
        model.probe_chat(transport=httpx.MockTransport(handler)),
    )

    assert checks[1].ok is True
    assert seen["chat_template_kwargs"] == {"enable_thinking": False}
    assert seen["reasoning_effort"] == "high"
    assert seen["max_tokens"] == 1  # probe cap via max_tokens_override


def test_probe_chat_omits_token_limit_when_not_configured() -> None:
    """The Test button must preserve an intentionally unset limit.

    Some strict relays reject either token-limit field.  When the operator
    leaves Max tokens blank, both probe and runtime need to send no limit.
    """
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": []})
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "ok"}}],
        })

    model = _chat_model()
    checks = asyncio.run(
        model.probe_chat(transport=httpx.MockTransport(handler)),
    )

    assert checks[1].ok is True
    assert len(bodies) == 1
    assert "max_tokens" not in bodies[0]
    assert "max_completion_tokens" not in bodies[0]


def test_responses_probe_uses_responses_request_shape() -> None:
    paths: list[str] = []
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "gpt-x"}]})
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": "ok"}],
            }],
        })

    checks = asyncio.run(
        _chat_model(llm_protocol="responses", max_tokens=64).probe_chat(
            transport=httpx.MockTransport(handler),
        ),
    )

    assert [check.ok for check in checks] == [True, True]
    assert paths == ["/v1/models", "/v1/responses"]
    assert bodies == [{
        "model": "gpt-x",
        "instructions": "You are a roleplay character backend.",
        "input": "ping",
        "max_output_tokens": 1,
    }]
    assert "Responses request" in checks[1].detail


def test_chat_structured_profile_probe_stays_on_chat_completions() -> None:
    """A dual-mode card tests its foreground chat endpoint, not Responses."""
    paths: list[str] = []
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "gpt-x"}]})
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "ok"}}],
        })

    checks = asyncio.run(
        _chat_model(
            llm_protocol="chat_completions",
            responses_request_profile="structured_streaming",
        ).probe_chat(transport=httpx.MockTransport(handler)),
    )

    assert [check.ok for check in checks] == [True, True]
    assert paths == ["/v1/models", "/v1/chat/completions"]
    assert "max_tokens" not in bodies[0]
    assert "max_completion_tokens" not in bodies[0]


def test_structured_streaming_responses_probe_reads_sse_text() -> None:
    paths: list[str] = []
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "gpt-x"}]})
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                'data: {"type":"response.output_text.delta","delta":"ok"}\n\n'
                "data: [DONE]\n\n"
            ).encode("utf-8"),
        )

    checks = asyncio.run(
        _chat_model(
            llm_protocol="responses",
            responses_request_profile="structured_streaming",
            max_tokens=64,
            disable_streaming=True,
        ).probe_chat(transport=httpx.MockTransport(handler)),
    )

    assert [check.ok for check in checks] == [True, True]
    assert paths == ["/v1/models", "/v1/responses"]
    assert bodies == [{
        "model": "gpt-x",
        "input": [{
            "role": "user",
            "content": [{
                "type": "input_text",
                "text": "You are a roleplay character backend.\n\nping",
            }],
        }],
        "stream": True,
    }]
    assert "structured streaming Responses" in checks[1].detail


# ---------------------------------------------------------------------------
# Anthropic probe_chat — URL parity with the runtime adapter
# ---------------------------------------------------------------------------


def test_anthropic_probe_and_runtime_share_url_rule() -> None:
    """A pasted base_url ending in /v1 resolves to /v1/messages for BOTH
    the probe hook and runtime generate() — the probe can no longer
    green-light a config the runtime would 404 on."""
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        body = json.loads(request.content)
        assert "thinking" not in body  # probe cap can't satisfy budget<max
        return httpx.Response(
            200, json={"content": [{"type": "text", "text": "pong"}]},
        )

    model = AnthropicChatModel(
        api_key="sk-ant-unit",
        base_url="https://api.anthropic.com/v1",  # pasted /v1 suffix
        thinking_budget_tokens=2048,
    )
    checks = asyncio.run(
        model.probe_chat(transport=httpx.MockTransport(handler)),
    )

    assert [(c.action, c.ok) for c in checks] == [("chat_completion", True)]
    assert paths == ["/v1/messages"]  # not /v1/v1/messages
    # Runtime resolves the identical URL from the identical config.
    assert model._api_url("messages") == "https://api.anthropic.com/v1/messages"


def test_anthropic_probe_caps_max_tokens_to_one() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200, json={"content": [{"type": "text", "text": "pong"}]},
        )

    model = AnthropicChatModel(api_key="sk-ant-unit", max_tokens=4096)
    checks = asyncio.run(
        model.probe_chat(transport=httpx.MockTransport(handler)),
    )

    assert checks[0].ok is True
    assert seen["max_tokens"] == 1
    assert seen["system"]  # runtime shape: top-level system prompt rides along


# ---------------------------------------------------------------------------
# embedder / tts hooks
# ---------------------------------------------------------------------------


def test_probe_embedding_flags_dimension_mismatch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"embedding": [0.0] * 1536}]})

    embedder = LMStudioEmbedder(
        base_url="http://127.0.0.1:1234/v1",
        model="text-embedding-3-small",
        dimension=1024,
    )
    checks = asyncio.run(
        embedder.probe_embedding(transport=httpx.MockTransport(handler)),
    )

    assert [(c.action, c.ok) for c in checks] == [("embedded", False)]
    assert "1536" in checks[0].detail
    assert "1024" in checks[0].detail
    assert "Request dimensions" in checks[0].detail


def test_probe_embedding_sends_runtime_payload() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"data": [{"embedding": [0.0] * 1024}]})

    embedder = LMStudioEmbedder(
        base_url="http://127.0.0.1:1234/v1",
        model="text-embedding-3-small",
        dimension=1024,
        request_dimensions=True,
    )
    checks = asyncio.run(
        embedder.probe_embedding(transport=httpx.MockTransport(handler)),
    )

    assert checks[0].ok is True
    assert seen == {
        "model": "text-embedding-3-small",
        "input": ["ping"],
        "dimensions": 1024,
    }


def test_openai_tts_probe_synthesizes_with_runtime_payload() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/audio/speech"
        seen.update(json.loads(request.content))
        return httpx.Response(200, content=b"RIFF0000WAVE")

    adapter = OpenAITTSAdapter(api_key="sk-unit")
    checks = asyncio.run(
        adapter.probe_tts(transport=httpx.MockTransport(handler)),
    )

    assert [(c.action, c.ok) for c in checks] == [("synthesized_speech", True)]
    assert "12 bytes" in checks[0].detail
    assert seen == {
        "model": "gpt-4o-mini-tts",
        "voice": "marin",
        "input": "Hi",
        "response_format": "wav",
    }


def test_custom_tts_probe_lists_voices_only() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        assert request.url.path == "/v1/voices"
        return httpx.Response(200, json={"voices": [{"id": "v1"}]})

    adapter = ExternalTTSAdapter(base_url="https://tts.example.test/v1")
    checks = asyncio.run(
        adapter.probe_tts(transport=httpx.MockTransport(handler)),
    )

    assert [(c.action, c.ok) for c in checks] == [("listed_voices", True)]
    assert checks[0].detail == "1 voices"
    assert methods == ["GET"]  # never a billed synthesis


# ---------------------------------------------------------------------------
# image hook — signal-driven memo shared with the runtime path
# ---------------------------------------------------------------------------


def test_xai_probe_learns_aspect_ratio_drop_on_instance() -> None:
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if "aspect_ratio" in body:
            return httpx.Response(400, json={
                "code": "400",
                "error": "Argument not supported: aspect_ratio",
            })
        return httpx.Response(200, json={
            "data": [{"b64_json": base64.b64encode(b"png").decode()}],
        })

    provider = XAIImageProvider(api_key="xai-unit", model="grok-2-image-1212")
    checks = asyncio.run(
        provider.probe_image_generation(
            prompt="a tiny plain blue circle",
            transport=httpx.MockTransport(handler),
        ),
    )

    assert [(c.action, c.ok) for c in checks] == [("generated_image", True)]
    assert len(bodies) == 2
    assert "aspect_ratio" not in bodies[1]
    # The memo is the ADAPTER's own — runtime generate() on this
    # instance would skip the failed round too.
    assert provider._send_aspect_ratio is False
