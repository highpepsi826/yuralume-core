"""Offline compatibility and explicit request controls for custom video APIs."""

import json
from dataclasses import asdict

import httpx
import pytest

from kokoro_link.bootstrap.video_profiles import load_video_profiles
from kokoro_link.contracts.provider_settings import ProviderConnection
from kokoro_link.contracts.video_provider import VideoGenerationError
from kokoro_link.infrastructure.provider_settings.adapter_builders import build_video_profile
from kokoro_link.infrastructure.provider_settings.catalog import catalog_by_id
from kokoro_link.infrastructure.video.openai_compatible_provider import OpenAICompatibleVideoProvider
from kokoro_link.infrastructure.video.profile_registry import VideoProfileRegistry


def _provider(protocol="openai_videos", **controls):
    return OpenAICompatibleVideoProvider(
        base_url="https://video.example.test/v1", api_key="test-key",
        model="test-model", protocol=protocol, **controls,
    )


@pytest.mark.parametrize("protocol,size_key,duration_key,seconds", [
    ("openai_videos", "size", "seconds", "8"),
    ("generations_polling", "resolution", "duration", 5),
])
@pytest.mark.parametrize("blank", [None, "", "  "])
def test_missing_and_blank_controls_preserve_legacy(protocol, size_key, duration_key, seconds, blank):
    provider = _provider(protocol, video_size=blank, video_duration_seconds=blank)
    payload = provider._request_payload(prompt="scene", aspect="portrait", length_frames=81)
    assert payload[size_key] == ("720x1280" if protocol == "openai_videos" else "720p")
    assert payload[duration_key] == seconds


@pytest.mark.parametrize("protocol,size_key,duration_key,seconds", [
    ("openai_videos", "size", "seconds", "6"),
    ("generations_polling", "resolution", "duration", 6),
])
def test_explicit_controls_preserve_protocol_types(protocol, size_key, duration_key, seconds):
    provider = _provider(protocol, video_size=" custom-documented-size ", video_duration_seconds="6")
    payload = provider._request_payload(prompt="scene", aspect="landscape", length_frames=81)
    assert payload[size_key] == "custom-documented-size"
    assert payload[duration_key] == seconds
    assert type(payload[duration_key]) is type(seconds)


@pytest.mark.parametrize("protocol,size_key,duration_key", [
    ("openai_videos", "size", "seconds"),
    ("generations_polling", "resolution", "duration"),
])
def test_provider_defaults_omit_fields_and_report_safe_settings(protocol, size_key, duration_key):
    provider = _provider(protocol, video_size="provider_default", video_duration_seconds="provider_default")
    payload = provider._request_payload(prompt="scene", aspect="portrait", length_frames=81)
    assert size_key not in payload
    assert duration_key not in payload
    settings = provider.generation_settings()
    assert settings[size_key] == settings[duration_key] == "provider_default"
    assert settings["model"] == "test-model"
    assert "prompt" not in settings
    assert "test-key" not in json.dumps(settings)


@pytest.mark.parametrize("size,duration,expected", [
    ("provider_default", "6", {"seconds": "6"}),
    ("1280x720", "provider_default", {"size": "1280x720"}),
])
def test_size_and_duration_omission_are_independent(size, duration, expected):
    payload = _provider(video_size=size, video_duration_seconds=duration)._request_payload(
        prompt="scene", aspect="portrait", length_frames=81,
    )
    assert {key: value for key, value in payload.items() if key in {"size", "seconds"}} == expected


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "1.5", "-2", "secret-value", {}, []])
def test_invalid_duration_rejected_with_actionable_safe_message(value):
    with pytest.raises(ValueError, match="video_duration_seconds must be a positive integer or provider_default") as error:
        _provider(video_duration_seconds=value)
    assert "secret-value" not in str(error.value)


@pytest.mark.parametrize("duration", ["provider_default", "6", 6, ""])
def test_controls_roundtrip_builder_json_loader_registry(duration):
    row = ProviderConnection(
        id="video-row", provider="custom_openai_compatible", label="Custom video",
        enabled=True, capabilities=("video",), config={
            "base_url": "https://video.example.test/v1", "video_model": "test-model",
            "video_protocol": "generations_polling", "video_size": "provider_default",
            "video_duration_seconds": duration,
        },
    )
    profile = build_video_profile(row, {"api_key": "test-key"})
    loaded = load_video_profiles(raw_config=json.dumps([asdict(profile)]))
    assert loaded == [profile]
    provider = VideoProfileRegistry(loaded).resolve(profile.id)
    settings = provider.generation_settings()
    assert settings["resolution"] == "provider_default"
    assert settings["duration"] == (6 if duration in (6, "6") else duration or 5)


def test_controls_catalog_is_custom_only_and_text_fields():
    for provider_id, entry in catalog_by_id().items():
        fields = {field.key: field for field in entry.config_fields}
        for key in ("video_size", "video_duration_seconds"):
            assert (key in fields) == (provider_id == "custom_openai_compatible")
            if key in fields:
                assert fields[key].kind == "text"
                assert "provider_default" in fields[key].hint


@pytest.mark.asyncio
async def test_rejected_submission_is_never_retried(monkeypatch):
    requests = []
    monkeypatch.setattr(
        "kokoro_link.infrastructure.video.openai_compatible_provider._build_prompt",
        lambda **kwargs: "scene",
    )
    def handler(request):
        requests.append(request)
        assert "size" not in json.loads(request.content)
        return httpx.Response(400, json={"error": "unsupported parameter"})
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(
        **kwargs, transport=httpx.MockTransport(handler),
    ))
    with pytest.raises(VideoGenerationError, match="400"):
        await _provider(video_size="provider_default").generate(
            character=None, positive="scene",
        )
    assert len(requests) == 1


@pytest.fixture
def connection_service():
    from kokoro_link.application.services.provider_connection_service import ProviderConnectionService
    from kokoro_link.infrastructure.repositories.in_memory_provider_connections import InMemoryProviderConnectionRepository
    from kokoro_link.infrastructure.security.provider_secret_cipher import ProviderSecretCipher

    repository = InMemoryProviderConnectionRepository()
    return ProviderConnectionService(
        repository=repository,
        cipher=ProviderSecretCipher("test-only-encryption-key"),
    ), repository


@pytest.mark.asyncio
async def test_create_connection_rejects_invalid_duration_before_writing(connection_service):
    from kokoro_link.application.services.provider_connection_service import ProviderConnectionError

    service, repository = connection_service
    with pytest.raises(ProviderConnectionError, match="video_duration_seconds.*positive integer"):
        await service.create_connection(
            provider="custom_openai_compatible", label="Custom video", enabled=True,
            capabilities=["video"], secret={"api_key": "test-key"}, config={
                "base_url": "https://video.example.test/v1", "video_model": "test-model",
                "video_protocol": "openai_videos", "video_duration_seconds": 0,
            },
        )
    assert await repository.list_all() == []


@pytest.mark.asyncio
async def test_create_connection_persists_provider_default_controls(connection_service):
    service, repository = connection_service
    created = await service.create_connection(
        provider="custom_openai_compatible", label="Custom video", enabled=True,
        capabilities=["video"], secret={"api_key": "test-key"}, config={
            "base_url": "https://video.example.test/v1", "video_model": "test-model",
            "video_protocol": "openai_videos", "video_size": "provider_default",
            "video_duration_seconds": "provider_default",
        },
    )
    fetched = await service.get_connection(created.id)
    assert fetched.config["video_size"] == "provider_default"
    assert fetched.config["video_duration_seconds"] == "provider_default"
    assert len(await repository.list_all()) == 1
