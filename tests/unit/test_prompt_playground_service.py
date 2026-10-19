from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
import asyncio

import pytest

from kokoro_link.application.services.prompt_playground_service import (
    PromptPlaygroundService, PromptPlaygroundAccessError,
    PromptPlaygroundBusyError, PromptPlaygroundGenerationError,
)
from kokoro_link.application.services.prompt_customization_service import PromptCustomizationService
from kokoro_link.domain.entities.character import Character
from kokoro_link.domain.entities.conversation import Message, MessageRole
from kokoro_link.domain.entities.operator_profile import OperatorProfile
from kokoro_link.domain.value_objects.character_state import CharacterState
from kokoro_link.infrastructure.prompt.default import DefaultPromptContextBuilder
from kokoro_link.infrastructure.prompts.loader import set_admin_template_overrides
from kokoro_link.infrastructure.repositories.in_memory_preferences import InMemoryPreferencesRepository


STYLE = 'chat/instructions_footer_style'


@pytest.fixture
def playground():
    set_admin_template_overrides({})
    character = Character.create(name='Test character', summary='Snapshot identity', personality=['calm'], interests=[], speaking_style='gentle', boundaries=[], user_id='alice', state=CharacterState(emotion='calm', affection=50, fatigue=0, trust=50, energy=80))
    repo = SimpleNamespace(get=AsyncMock(return_value=character), list=AsyncMock(return_value=[character]), list_for_user=AsyncMock(return_value=[character]), save=AsyncMock())
    conversations = SimpleNamespace(recent_messages_for_character=AsyncMock(return_value=[Message(role=MessageRole.USER, content='Earlier shared memory')]), save=AsyncMock(), append_messages=AsyncMock())
    memories = SimpleNamespace(query=AsyncMock(return_value=[]), touch=AsyncMock(), add=AsyncMock())
    goals = SimpleNamespace(list_for_character=AsyncMock(return_value=[]), save=AsyncMock())
    arcs = SimpleNamespace(get_active_for_character=AsyncMock(return_value=None), save=AsyncMock())
    schedule = SimpleNamespace(get_schedule=AsyncMock(return_value=None), ensure_schedule=AsyncMock(), load_upcoming_schedules=AsyncMock(return_value=[]), resolve_pending_invites_from_schedules=lambda *args, **kwargs: [])
    operators = SimpleNamespace(get=AsyncMock(return_value=OperatorProfile(id='alice', display_name='Alice')))
    customizations = PromptCustomizationService(InMemoryPreferencesRepository())
    model = SimpleNamespace(generate=AsyncMock(return_value='Test reply'), provider_id='fake')
    provider = SimpleNamespace(resolve=AsyncMock(return_value=model), resolve_model_id=AsyncMock(return_value='model-id'))
    builder = DefaultPromptContextBuilder()
    service = PromptPlaygroundService(character_repository=repo, conversation_repository=conversations, memory_repository=memories, goal_repository=goals, story_arc_repository=arcs, schedule_service=schedule, operator_profile_repository=operators, prompt_context_builder=builder, prompt_customization_service=customizations, active_llm_provider=provider)
    yield SimpleNamespace(service=service, character=character, repo=repo, conversations=conversations, memories=memories, goals=goals, arcs=arcs, schedule=schedule, operators=operators, prompts=customizations, model=model, provider=provider, builder=builder)
    set_admin_template_overrides({})


async def run(p, **kwargs):
    return await p.service.run(character_id=p.character.id, user_id=kwargs.pop('user_id', 'alice'), admin=kwargs.pop('admin', False), message='New test message', include_current_progress=kwargs.pop('include_current_progress', True), **kwargs)


@pytest.mark.asyncio
async def test_effective_only_one_call_and_no_game_writes(playground):
    p = playground
    result = await run(p)
    assert result.published_reply == 'Test reply'
    assert result.draft_reply is None
    assert not result.has_draft
    assert p.model.generate.await_count == 1
    assert result.snapshot_summary['recent_message_count'] == 1
    for method in (p.repo.save, p.conversations.save, p.conversations.append_messages, p.memories.touch, p.memories.add, p.goals.save, p.arcs.save, p.schedule.ensure_schedule):
        method.assert_not_awaited()
    prompt = p.model.generate.call_args.args[0]
    assert 'Earlier shared memory' in prompt
    assert 'New test message' in prompt
    assert 'Snapshot identity' in prompt


@pytest.mark.asyncio
async def test_draft_pair_uses_same_snapshot_even_when_data_changes(playground):
    p = playground
    await p.prompts.set_draft(name=STYLE, content='DRAFT_MARKER', user_id='alice', admin=False)
    async def generate(prompt, *, model):
        p.repo.get.return_value = replace(p.character, summary='NEW LIVE DATA')
        p.conversations.recent_messages_for_character.return_value = []
        set_admin_template_overrides({STYLE: 'GLOBAL_CHANGED'})
        return 'reply'
    p.model.generate.side_effect = generate
    result = await run(p)
    first, second = [call.args[0] for call in p.model.generate.call_args_list]
    assert 'DRAFT_MARKER' not in first and 'DRAFT_MARKER' in second
    assert all('Earlier shared memory' in x and 'Snapshot identity' in x and 'NEW LIVE DATA' not in x and 'GLOBAL_CHANGED' not in x for x in (first, second))
    p.repo.get.assert_awaited_once()
    p.conversations.recent_messages_for_character.assert_awaited_once()
    assert result.has_draft and result.draft_reply == 'reply'
    assert p.provider.resolve.await_count == p.provider.resolve_model_id.await_count == 1


@pytest.mark.asyncio
async def test_ownership_and_admin_draft_scope(playground):
    p = playground
    with pytest.raises(PromptPlaygroundAccessError):
        await run(p, user_id='bob')
    with pytest.raises(PromptPlaygroundAccessError):
        await run(p, draft_scope='admin')
    await p.prompts.set_draft(name=STYLE, content='OTHER_PRIVATE_DRAFT', user_id='bob', admin=False)
    await p.prompts.set_draft(name=STYLE, content='ADMIN_PRIVATE_DRAFT', user_id='root', admin=True)
    result = await run(p, user_id='root', admin=True, draft_scope='admin')
    assert result.has_draft
    assert 'ADMIN_PRIVATE_DRAFT' in p.model.generate.call_args.args[0]
    assert 'OTHER_PRIVATE_DRAFT' not in p.model.generate.call_args.args[0]
    p.operators.get.assert_awaited_with('alice')


@pytest.mark.asyncio
async def test_progress_off_skips_progress_reads(playground):
    p = playground
    result = await run(p, include_current_progress=False)
    assert result.snapshot_summary == {'recent_message_count': 0, 'memory_count': 0, 'has_current_activity': False, 'has_story_arc': False}
    for method in (p.conversations.recent_messages_for_character, p.memories.query, p.goals.list_for_character, p.arcs.get_active_for_character, p.schedule.get_schedule):
        method.assert_not_awaited()


@pytest.mark.asyncio
async def test_parallel_run_is_refused_and_failure_releases_lock(playground):
    p = playground
    entered, release = asyncio.Event(), asyncio.Event()
    async def generate(*args, **kwargs):
        entered.set()
        await release.wait()
        raise Exception('secret provider response')
    p.model.generate.side_effect = generate
    pending = asyncio.create_task(run(p))
    await entered.wait()
    with pytest.raises(PromptPlaygroundBusyError):
        await run(p)
    release.set()
    with pytest.raises(PromptPlaygroundGenerationError, match='^playground model generation failed$'):
        await pending
    p.model.generate.side_effect = None
    assert (await run(p)).published_reply == 'Test reply'


@pytest.mark.asyncio
async def test_per_user_rate_and_input_limits(playground):
    p = playground
    for _ in range(6):
        await run(p)
    with pytest.raises(PromptPlaygroundBusyError, match='rate limit'):
        await run(p)
    for value in ('', ' ' * 2001, 'x' * 2001):
        with pytest.raises(ValueError):
            await p.service.run(character_id=p.character.id, user_id='alice', admin=False, message=value, include_current_progress=True)


@pytest.mark.asyncio
async def test_chat_route_does_not_create_automatic_usage_rows(playground):
    from kokoro_link.infrastructure.usage.llm_metering import MeteredActiveLLMProvider
    p = playground
    recorder = SimpleNamespace(record=AsyncMock())
    p.service._active_llm_provider = MeteredActiveLLMProvider(inner=p.provider, recorder=lambda: recorder)
    assert (await run(p)).published_reply == 'Test reply'
    recorder.record.assert_not_awaited()


@pytest.mark.asyncio
async def test_player_catalog_is_scoped_and_admin_catalog_can_list_all(playground):
    p = playground
    await p.service.list_characters(user_id='alice', admin=False)
    p.repo.list_for_user.assert_awaited_once_with('alice')
    p.repo.list.assert_not_awaited()
    await p.service.list_characters(user_id='root', admin=True)
    p.repo.list.assert_awaited_once()


@pytest.mark.asyncio
async def test_stored_core_template_never_applies_to_player_draft(playground):
    p = playground
    p.prompts.get_drafts = AsyncMock(return_value={'shared/role_boundary': 'CORE_DRAFT'})
    result = await run(p)
    assert result.draft_reply is None
    assert 'CORE_DRAFT' not in p.model.generate.call_args.args[0]


@pytest.mark.asyncio
async def test_preview_lists_saved_used_and_unused_drafts_without_generation(playground):
    p = playground
    await p.prompts.set_draft(name=STYLE, content='CHAT_DRAFT_MARKER', user_id='alice', admin=False)
    await p.prompts.set_draft(name='feed/composer_style', content='FEED_DRAFT_MARKER', user_id='alice', admin=False)
    preview = await p.service.preview(character_id=p.character.id, user_id='alice', admin=False)
    p.model.generate.assert_not_awaited()
    drafts = {item['name']: item for item in preview['draft_templates']}
    assert drafts[STYLE]['used']
    assert not drafts['feed/composer_style']['used']
    assert all('content' not in item for item in preview['template_usage']['published'])
    result = await run(p)
    assert result.template_usage == preview['template_usage']
    assert any(item['name'] == STYLE and item['source'] == 'draft' for item in result.template_usage['draft'])
    assert all(item['source'] == 'effective' for item in result.template_usage['published'])
    assert result.draft_templates == preview['draft_templates']


@pytest.mark.asyncio
async def test_preview_enforces_ownership_and_scope(playground):
    p = playground
    with pytest.raises(PromptPlaygroundAccessError):
        await p.service.preview(character_id=p.character.id, user_id='bob', admin=False)
    with pytest.raises(PromptPlaygroundAccessError):
        await p.service.preview(character_id=p.character.id, user_id='alice', admin=False, draft_scope='admin')
    p.model.generate.assert_not_awaited()


def test_render_trace_is_nested_and_excludes_raw_reads():
    from kokoro_link.infrastructure.prompts.loader import capture_template_renders, get_default_loader
    loader = get_default_loader()
    with capture_template_renders() as outer:
        loader.raw(STYLE)
        with capture_template_renders() as inner:
            loader.render(STYLE)
        assert outer == []
        loader.render('shared/role_boundary')
    assert [name for name, _ in inner] == [STYLE]
    assert [name for name, _ in outer] == ['shared/role_boundary']
    loader.render(STYLE)
    assert len(outer) == 1
