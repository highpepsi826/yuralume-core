from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kokoro_link.api.dependencies import get_container, get_current_user
from kokoro_link.api.routes.prompt_playground import router
from kokoro_link.application.services.prompt_playground_service import (
    PromptPlaygroundAccessError, PromptPlaygroundBusyError,
    PromptPlaygroundGenerationError, PromptPlaygroundRun,
)
from kokoro_link.domain.entities.operator_profile import OperatorProfile


@pytest.fixture
def api():
    service = SimpleNamespace(
        preview=AsyncMock(return_value={'template_usage': {'published': [], 'draft': []}, 'draft_templates': []}),
        run=AsyncMock(return_value=PromptPlaygroundRun('reply', None, 'model', 'hash', {}, False)),
        list_characters=AsyncMock(return_value=[SimpleNamespace(id='c', name='Character')]),
    )
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    app.dependency_overrides[get_container] = lambda: SimpleNamespace(prompt_playground_service=service)
    app.dependency_overrides[get_current_user] = lambda: OperatorProfile(id='alice', display_name='Alice')
    return app, TestClient(app), service


def test_run_uses_authenticated_identity_and_private_draft_scope(api):
    _, client, service = api
    result = client.post('/api/v1/characters/c/prompt-playground/runs', json={'message': 'test'})
    assert result.status_code == 200
    assert result.json()['draft_reply'] is None
    service.run.assert_awaited_once_with(character_id='c', user_id='alice', admin=False, message='test', include_current_progress=True, draft_scope='player')


@pytest.mark.parametrize('body', [{'message': 'x' * 2001}, {'message': ''}, {'message': 'x', 'user_id': 'other'}, {'message': 'x', 'admin_draft_overrides': {'x': 'y'}}, {'message': 'x', 'draft_scope': 'unknown'}])
def test_rejects_unbounded_or_injected_payloads(api, body):
    _, client, service = api
    assert client.post('/api/v1/characters/c/prompt-playground/runs', json=body).status_code == 422
    service.run.assert_not_awaited()


@pytest.mark.parametrize(('error', 'expected'), [(PromptPlaygroundAccessError('Character not found'), 404), (PromptPlaygroundBusyError('busy'), 429), (PromptPlaygroundGenerationError('SECRET'), 502)])
def test_bounded_errors(api, error, expected):
    _, client, service = api
    service.run.side_effect = error
    result = client.post('/api/v1/characters/c/prompt-playground/runs', json={'message': 'test'})
    assert result.status_code == expected
    assert 'SECRET' not in result.text


def test_character_listing_passes_authority_and_returns_only_names(api):
    app, client, service = api
    assert client.get('/api/v1/prompt-playground/characters').json() == {'characters': [{'id': 'c', 'name': 'Character'}]}
    service.list_characters.assert_awaited_with(user_id='alice', admin=False)
    app.dependency_overrides[get_current_user] = lambda: OperatorProfile(id='root', display_name='Root', is_admin=True)
    client.get('/api/v1/prompt-playground/characters')
    service.list_characters.assert_awaited_with(user_id='root', admin=True)


def test_container_wires_isolated_playground():
    from kokoro_link.bootstrap.container import build_container
    from kokoro_link.bootstrap.settings import AppSettings
    container = build_container(AppSettings())
    assert container.prompt_playground_service is not None
    assert container.prompt_playground_service._character_repository is container.character_repository
    assert not hasattr(container.prompt_playground_service, '_chat_service')


@pytest.mark.asyncio
async def test_real_container_fake_model_run_does_not_write_game_data():
    from kokoro_link.bootstrap.container import build_container
    from kokoro_link.bootstrap.settings import AppSettings
    from kokoro_link.domain.entities.character import Character
    from kokoro_link.domain.value_objects.character_state import CharacterState
    from kokoro_link.domain.entities.conversation import Conversation, Message, MessageRole
    container = build_container(AppSettings())
    character = Character.create(name='Test', summary='Test card', personality=[], interests=[], speaking_style='calm', boundaries=[], state=CharacterState(emotion='calm', energy=80, affection=50, fatigue=0, trust=50))
    await container.character_repository.save(character)
    conversation = Conversation.start(character_id=character.id).append(Message(role=MessageRole.USER, content='Previous test message'))
    await container.conversation_repository.save(conversation)
    await container.prompt_customization_service.set_draft(name='chat/instructions_footer_style', content='Use short sentences.', user_id='default', admin=False)
    writes = []
    for repository, methods in ((container.character_repository, ('save', 'touch_last_active')), (container.conversation_repository, ('save', 'append_messages')), (container.memory_repository, ('add', 'add_many', 'touch')), (container.preferences_repository, ('set', 'delete'))):
        for method in methods:
            mock = AsyncMock(side_effect=AssertionError('Playground must not write'))
            setattr(repository, method, mock)
            writes.append(mock)
    result = await container.prompt_playground_service.run(character_id=character.id, user_id='default', admin=False, message='今天有點累', include_current_progress=True)
    assert result.published_reply and result.draft_reply
    assert result.snapshot_summary['recent_message_count'] == 1
    for method in writes:
        method.assert_not_awaited()


def test_preview_uses_identity_and_never_calls_generation(api):
    _, client, service = api
    response = client.get('/api/v1/characters/c/prompt-playground/preview?draft_scope=player&include_current_progress=false')
    assert response.status_code == 200
    service.preview.assert_awaited_once_with(character_id='c', user_id='alice', admin=False,
        include_current_progress=False, draft_scope='player')
    service.run.assert_not_awaited()
    assert client.get('/api/v1/characters/c/prompt-playground/preview?draft_scope=unknown').status_code == 422
