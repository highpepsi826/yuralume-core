"""Character preview uses feed rendering without creating permanent media."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kokoro_link.api.dependencies import get_container, get_current_user_id
from kokoro_link.api.routes.album import router
from kokoro_link.application.services.feature_keys import FEATURE_VIDEO_FEED
from kokoro_link.application.services.feed_composer_service import FeedComposerService
from kokoro_link.contracts.video_provider import VideoGenerationError
from kokoro_link.domain.entities.character import Character
from kokoro_link.domain.value_objects.character_state import CharacterState


@pytest.fixture
def character():
    return replace(Character.create(
        name="Rin", summary="A quiet reader", personality=[], interests=[],
        speaking_style="", boundaries=[],
        state=CharacterState(emotion="happy", affection=70, fatigue=12,
                             trust=60, energy=88, current_intent="reading a book"),
    ), id="rin", user_id="owner", appearance="Silver hair, green eyes")


def _rig(*, enabled=True, available=True, blob=b"fake-mp4"):
    provider = SimpleNamespace(
        generate=AsyncMock(return_value=blob),
        generation_settings=Mock(return_value={"size": "provider_default"}),
    )
    resolver = SimpleNamespace(
        resolve=AsyncMock(return_value=provider if available else None),
        resolve_profile_id=AsyncMock(return_value="character-pinned"),
    )
    style = SimpleNamespace(styled_prompt=AsyncMock(return_value="styled scene"))
    repository, storage, composer, candidates = (Mock() for _ in range(4))
    runtime = SimpleNamespace(resolve_for_operator=AsyncMock(
        return_value=SimpleNamespace(video_generation_enabled=enabled)))
    service = FeedComposerService(
        repository=repository, candidates=candidates, composer=composer,
        video_provider=resolver, object_storage=storage,
        visual_style_service=style, account_runtime_profile_resolver=runtime,
    )
    return SimpleNamespace(**locals())


@pytest.mark.asyncio
async def test_preview_resolves_character_feed_target_and_preserves_render_arguments(character):
    rig = _rig()
    assert await rig.service.generate_character_video_preview(character, "  scene  ") == b"fake-mp4"
    rig.resolver.resolve.assert_awaited_once_with(FEATURE_VIDEO_FEED, character=character)
    rig.runtime.resolve_for_operator.assert_awaited_once_with("owner")
    rig.style.styled_prompt.assert_awaited_once_with("scene", character=character)
    rig.provider.generate.assert_awaited_once_with(
        character=character, positive="styled scene", aspect="portrait", use_runtime_state=True,
    )
    # The provider receives the full live entity, including visual identity and intent.
    passed = rig.provider.generate.call_args.kwargs["character"]
    assert passed.appearance == "Silver hair, green eyes"
    assert passed.state.emotion == "happy"
    assert passed.state.current_intent == "reading a book"
    # No frame override: this preserves the feed adapter's own default length.
    assert "length_frames" not in rig.provider.generate.call_args.kwargs
    for boundary in (rig.repository, rig.storage, rig.composer, rig.candidates):
        assert boundary.mock_calls == []


@pytest.mark.asyncio
async def test_settings_are_free_and_use_same_target(character):
    rig = _rig()
    settings = await rig.service.character_video_preview_settings(character)
    assert settings["profile_id"] == "character-pinned"
    assert settings["aspect"] == "portrait"
    assert "reading a book" in settings["prompt"]
    rig.resolver.resolve.assert_awaited_once_with(FEATURE_VIDEO_FEED, character=character)
    rig.resolver.resolve_profile_id.assert_awaited_once_with(FEATURE_VIDEO_FEED, character=character)
    rig.provider.generation_settings.assert_called_once_with(aspect="portrait", length_frames=81)
    rig.provider.generate.assert_not_awaited()
    assert rig.storage.mock_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["disabled", "missing", "unwired", "empty", "blank", "long"])
async def test_preview_refuses_unusable_requests(character, case):
    rig = _rig(enabled=case != "disabled", available=case != "missing",
               blob=b"" if case == "empty" else b"video")
    if case == "unwired":
        rig.service._video_provider = None
    prompt = " " if case == "blank" else "x" * 2001 if case == "long" else "scene"
    with pytest.raises(VideoGenerationError):
        await rig.service.generate_character_video_preview(character, prompt)
    if case != "empty":
        rig.provider.generate.assert_not_awaited()
    assert rig.storage.mock_calls == []
    assert rig.repository.mock_calls == []


@pytest.mark.asyncio
async def test_provider_timeout_propagates_without_retry_or_storage(character):
    rig = _rig()
    rig.provider.generate.side_effect = TimeoutError("upstream timed out")
    with pytest.raises(TimeoutError):
        await rig.service.generate_character_video_preview(character, "scene")
    assert rig.provider.generate.await_count == 1
    assert rig.storage.mock_calls == []


def _client(character, *, owned=True, cloud=False):
    app = FastAPI()
    app.include_router(router)
    service = SimpleNamespace(
        generate_character_video_preview=AsyncMock(return_value=b"fake-mp4"),
        character_video_preview_settings=AsyncMock(return_value={"profile_id": "pinned"}),
    )
    character_service = SimpleNamespace(get_character_entity=AsyncMock(
        return_value=character if owned else None))
    container = SimpleNamespace(
        feed_composer_service=service, character_service=character_service,
        app_settings=SimpleNamespace(cloud=SimpleNamespace(active=cloud)),
    )
    app.dependency_overrides[get_container] = lambda: container
    app.dependency_overrides[get_current_user_id] = lambda: "owner"
    return TestClient(app), service, character_service


@pytest.mark.parametrize("method", ["get", "post"])
def test_routes_require_owned_character_before_generation(character, method):
    client, service, character_service = _client(character, owned=False)
    response = getattr(client, method)("/characters/rin/album/video-preview", **(
        {"json": {"prompt": "scene"}} if method == "post" else {}))
    assert response.status_code == 404
    character_service.get_character_entity.assert_awaited_once_with("rin", user_id="owner")
    service.generate_character_video_preview.assert_not_awaited()
    service.character_video_preview_settings.assert_not_awaited()


@pytest.mark.parametrize("method", ["get", "post"])
def test_cloud_preview_is_blocked(character, method):
    client, service, _ = _client(character, cloud=True)
    response = getattr(client, method)("/characters/rin/album/video-preview", **(
        {"json": {"prompt": "scene"}} if method == "post" else {}))
    assert response.status_code == 403
    service.generate_character_video_preview.assert_not_awaited()
    service.character_video_preview_settings.assert_not_awaited()


def test_route_returns_temporary_mp4_for_actual_owned_entity(character):
    client, service, _ = _client(character)
    response = client.post("/characters/rin/album/video-preview", json={"prompt": "scene"})
    assert response.status_code == 200
    assert response.content == b"fake-mp4"
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["cache-control"] == "no-store"
    assert "character-preview.mp4" in response.headers["content-disposition"]
    service.generate_character_video_preview.assert_awaited_once_with(character, "scene")


@pytest.mark.parametrize("error,expected", [
    (VideoGenerationError("Authorization Bearer secret-credential upstream body"), 400),
    (TimeoutError("secret-credential upstream timeout"), 504),
])
def test_route_errors_hide_upstream_credentials(character, error, expected):
    client, service, _ = _client(character)
    service.generate_character_video_preview.side_effect = error
    response = client.post("/characters/rin/album/video-preview", json={"prompt": "scene"})
    assert response.status_code == expected
    assert "secret-credential" not in response.text
    assert "Authorization" not in response.text


def test_route_settings_and_prompt_validation(character):
    client, service, _ = _client(character)
    assert client.get("/characters/rin/album/video-preview").json() == {"profile_id": "pinned"}
    service.character_video_preview_settings.assert_awaited_once_with(character)
    for prompt in ("", "x" * 2001):
        assert client.post("/characters/rin/album/video-preview", json={"prompt": prompt}).status_code == 422
    service.generate_character_video_preview.assert_not_awaited()
