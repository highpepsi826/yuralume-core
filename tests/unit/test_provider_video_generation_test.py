"""Isolated admin video previews never publish posts or mutate settings."""
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kokoro_link.api.dependencies import get_container, require_admin
from kokoro_link.api.routes import admin_providers
from kokoro_link.application.services.provider_connection_service import (
    ProviderConnectionError,
    ProviderConnectionService,
)
from kokoro_link.infrastructure.provider_settings import adapter_builders
from kokoro_link.infrastructure.repositories.in_memory_provider_connections import (
    InMemoryProviderConnectionRepository,
)
from kokoro_link.infrastructure.security.provider_secret_cipher import ProviderSecretCipher


CONFIG = {
    "base_url": "https://video.example.test/v1", "video_model": "test-model",
    "video_protocol": "openai_videos",
}
PROVIDER = "custom_openai_compatible"
VIDEO = b"\x00\x00\x00\x18ftypmp42test-video"


@pytest.fixture
def service():
    return ProviderConnectionService(
        repository=InMemoryProviderConnectionRepository(),
        cipher=ProviderSecretCipher("unit-test-video-preview-key"),
    )


@pytest.mark.asyncio
async def test_saved_secret_and_draft_override_generate_without_writes(service, monkeypatch):
    saved = await service.create_connection(
        provider=PROVIDER, label="Video", enabled=True, capabilities=["video"],
        config=CONFIG, secret={"api_key": "stored-preview-credential"},
    )
    before = await service.list_connections()
    adapter = AsyncMock()
    adapter.generate.return_value = VIDEO
    builds = []

    def build(row, secret):
        builds.append((row, secret))
        return adapter

    monkeypatch.setattr(adapter_builders, "build_video_provider", build)
    for draft_secret in ({}, {"api_key": ""}, {"api_key": "draft-preview-credential"}):
        assert await service.generate_test_video(
            provider=PROVIDER, config={**CONFIG, "video_model": "draft-model"},
            secret=draft_secret, prompt=" Paper boat on water ", connection_id=saved.id,
        ) == VIDEO
    assert [secret["api_key"] for _, secret in builds] == [
        "stored-preview-credential", "stored-preview-credential", "draft-preview-credential",
    ]
    assert builds[0][0].config["video_model"] == "draft-model"
    kwargs = adapter.generate.call_args.kwargs
    assert kwargs["positive"] == "Paper boat on water"
    assert kwargs["length_frames"] == 81
    assert kwargs["use_runtime_state"] is False
    assert kwargs["character"].appearance == ""
    assert await service.list_connections() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["mismatch", "unsupported", "missing-key", "empty-prompt"])
async def test_invalid_draft_never_calls_adapter(service, monkeypatch, case):
    builder = AsyncMock()
    monkeypatch.setattr(adapter_builders, "build_video_provider", builder)
    kwargs = dict(provider=PROVIDER, config=CONFIG, secret={"api_key": "preview-credential"}, prompt="Boat")
    if case == "mismatch":
        row = await service.create_connection(
            provider="openai", label="OpenAI", capabilities=["llm"], enabled=True,
            config={"default_model": "gpt-test"}, secret={"api_key": "stored-credential"},
        )
        kwargs["connection_id"] = row.id
    elif case == "unsupported":
        kwargs["provider"] = "tavily"
    elif case == "missing-key":
        kwargs["secret"] = {}
    else:
        kwargs["prompt"] = "   "
    with pytest.raises(ProviderConnectionError):
        await service.generate_test_video(**kwargs)
    builder.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["empty", "exception", "timeout", "unsupported-adapter"])
async def test_generation_failures_are_safe(service, monkeypatch, failure):
    adapter = AsyncMock()
    adapter.generate.return_value = b""
    if failure == "exception":
        adapter.generate.side_effect = RuntimeError("upstream echoed arbitrary-preview-credential")
    elif failure == "timeout":
        adapter.generate.side_effect = TimeoutError()
    monkeypatch.setattr(
        adapter_builders, "build_video_provider",
        lambda *_: None if failure == "unsupported-adapter" else adapter,
    )
    with pytest.raises(ProviderConnectionError) as caught:
        await service.generate_test_video(
            provider=PROVIDER, config=CONFIG,
            secret={"api_key": "arbitrary-preview-credential"}, prompt="Boat",
        )
    assert "arbitrary-preview-credential" not in str(caught.value)
    if failure == "exception":
        assert "redacted" in str(caught.value)
    elif failure == "timeout":
        assert "timed out" in str(caught.value)
    elif failure == "empty":
        assert "no video" in str(caught.value)
    else:
        assert "not supported" in str(caught.value)


def route_client(service, monkeypatch):
    from types import SimpleNamespace
    app = FastAPI()
    app.include_router(admin_providers.router, prefix="/api/v1")
    app.dependency_overrides[get_container] = lambda: SimpleNamespace(provider_connection_service=service)
    app.dependency_overrides[require_admin] = lambda: object()
    monkeypatch.setattr(admin_providers, "is_cloud_mode", lambda _: False)
    return app, TestClient(app)


def test_route_returns_private_mp4_and_validation_errors(service, monkeypatch):
    adapter = AsyncMock()
    adapter.generate.return_value = VIDEO
    monkeypatch.setattr(adapter_builders, "build_video_provider", lambda *_: adapter)
    _, client = route_client(service, monkeypatch)
    body = dict(provider=PROVIDER, config=CONFIG, secret={"api_key": "preview-credential"}, prompt="Boat")
    response = client.post("/api/v1/admin/providers/generate-test-video", json=body)
    assert response.status_code == 200
    assert response.content == VIDEO
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["cache-control"] == "no-store"
    assert client.post("/api/v1/admin/providers/generate-test-video", json={**body, "prompt": ""}).status_code == 422
    assert client.post("/api/v1/admin/providers/generate-test-video", json={**body, "secret": {}}).status_code == 400


def test_route_enforces_admin_and_cloud_lock(service, monkeypatch):
    from fastapi import HTTPException
    app, client = route_client(service, monkeypatch)
    body = dict(provider=PROVIDER, config=CONFIG, secret={}, prompt="Boat")
    monkeypatch.setattr(admin_providers, "is_cloud_mode", lambda _: True)
    assert client.post("/api/v1/admin/providers/generate-test-video", json=body).status_code == 403
    monkeypatch.setattr(admin_providers, "is_cloud_mode", lambda _: False)

    def denied():
        raise HTTPException(status_code=403, detail="admin required")

    app.dependency_overrides[require_admin] = denied
    assert client.post("/api/v1/admin/providers/generate-test-video", json=body).status_code == 403
