"""Bounded read-only sources for incident exports; no production writes."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from kokoro_link.infrastructure.persistence.models import (
    CharacterAlbumItemRow, CharacterRow, ConversationRow, MessageRow, TurnRecordRow,
)
from kokoro_link.infrastructure.persistence.sa_turn_record_repository import _row_to_domain

MAX_MESSAGES = 2000
MAX_MESSAGE_CHARS = 16000
MAX_OBJECTS = 100
STAT_TIMEOUT = 2.0


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def factory_for(container):
    for name in ('conversation_repository', 'turn_record_repository'):
        factory = getattr(getattr(container, name, None), '_session_factory', None)
        if factory is not None:
            return factory
    return None


async def read_turns(repo, character_id, start, end, limit=500):
    """Apply the upper time bound BEFORE LIMIT (older incidents otherwise vanish)."""
    factory = getattr(repo, '_session_factory', None)
    if factory:
        async with factory() as session:
            rows = (await session.execute(select(TurnRecordRow).where(
                TurnRecordRow.character_id == character_id,
                TurnRecordRow.created_at >= start, TurnRecordRow.created_at <= end,
            ).order_by(TurnRecordRow.created_at.desc(), TurnRecordRow.id.desc()).limit(limit + 1))).scalars().all()
            records = [_row_to_domain(r) for r in rows]
        return records[:limit], len(records) > limit
    # In-memory/test implementations: report possible loss instead of claiming completeness.
    records = await repo.list_recent(character_id=character_id, since=start, limit=limit + 1)
    return [r for r in records if utc(r.created_at) <= end][:limit], len(records) > limit


async def read_messages(factory, character_id, start, end):
    async with factory() as session:
        rows = (await session.execute(select(
            MessageRow.id, MessageRow.conversation_id, MessageRow.position,
            MessageRow.role, MessageRow.kind, MessageRow.created_at,
            func.substr(MessageRow.content, 1, MAX_MESSAGE_CHARS).label('content'),
            func.length(MessageRow.content).label('original_chars'),
            func.substr(MessageRow.attachments_json, 1, 64000).label('attachments'),
        ).join(ConversationRow, ConversationRow.id == MessageRow.conversation_id).where(
            ConversationRow.character_id == character_id,
            MessageRow.created_at >= start, MessageRow.created_at <= end,
        ).order_by(MessageRow.created_at, MessageRow.id).limit(MAX_MESSAGES + 1))).all()
    messages = [dict(id=r.id, conversation_id=r.conversation_id, position=r.position,
                     role=r.role, kind=r.kind, content=r.content,
                     original_chars=r.original_chars, content_truncated=r.original_chars > MAX_MESSAGE_CHARS,
                     created_at=utc(r.created_at).isoformat()) for r in rows[:MAX_MESSAGES]]
    return messages, [r.attachments for r in rows[:MAX_MESSAGES]], len(rows) > MAX_MESSAGES


def reference_urls(value: Any, depth=0):
    """Read only explicit URL references, not arbitrary object keys or message text."""
    if depth > 8:
        return
    if isinstance(value, list):
        for child in value[:200]:
            yield from reference_urls(child, depth + 1)
    elif isinstance(value, dict):
        for key, child in value.items():
            if key in ('url', 'image_url', 'thumbnail_url') and isinstance(child, str):
                yield child
            elif isinstance(child, (dict, list)):
                yield from reference_urls(child, depth + 1)


async def read_storage(container, factory, character_id, start, end, attachments):
    """Stat only this character's references using existing HTTP/memory/decorated port."""
    storage = getattr(container, 'object_storage', None)
    if storage is None:
        return [], {'status': 'unavailable', 'reason': 'storage_not_configured'}
    keys: set[str] = set()
    errors: dict[str, str] = {}
    truncated = False

    def add_url(url):
        nonlocal truncated
        if not isinstance(url, str):
            return
        key = storage.object_key_from_url(url)
        if key and key not in keys:
            if len(keys) == MAX_OBJECTS:
                truncated = True
            else:
                keys.add(key)

    for raw in attachments:
        try:
            for url in reference_urls(json.loads(raw or '[]')):
                add_url(url)
        except (ValueError, TypeError):
            errors['message_attachments'] = 'invalid_or_truncated_json'
    # Portraits are a current snapshot; album additions are restricted to the window.
    for name, query in (
        ('portraits', select(CharacterRow.image_urls).where(CharacterRow.id == character_id)),
        ('album', select(CharacterAlbumItemRow.url).where(
            CharacterAlbumItemRow.character_id == character_id,
            CharacterAlbumItemRow.created_at >= start, CharacterAlbumItemRow.created_at <= end,
        ).order_by(CharacterAlbumItemRow.created_at, CharacterAlbumItemRow.id).limit(MAX_OBJECTS + 1)),
    ):
        try:
            async with factory() as session:
                values = (await session.execute(query)).scalars().all()
            if name == 'portraits':
                values = json.loads(values[0]) if values else []
            elif len(values) > MAX_OBJECTS:
                truncated = True
            for value in values[:MAX_OBJECTS]:
                add_url(value)
        except Exception as exc:
            errors[name] = type(exc).__name__

    semaphore = asyncio.Semaphore(5)

    async def stat(key):
        async with semaphore:
            try:
                item = await asyncio.wait_for(storage.stat(object_key=key), timeout=STAT_TIMEOUT)
                if item is None:
                    return {'object_key': key, 'status': 'missing'}
                return {'object_key': key, 'status': 'available', 'content_type': item.content_type,
                        'size_bytes': item.size_bytes, 'sha256': item.sha256,
                        'metadata': {k: v for k, v in (item.metadata or {}).items()
                                     if k in ('width', 'height', 'format', 'duration_ms')}}
            except Exception as exc:
                return {'object_key': key, 'status': 'error', 'error_type': type(exc).__name__}

    objects = await asyncio.gather(*(stat(k) for k in sorted(keys)))
    return objects, {
        'status': 'partial' if errors or truncated or any(x['status'] != 'available' for x in objects) else 'complete',
        'scope': 'current_metadata_for_character_portraits_and_window_message_album_references',
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'row_count': len(objects), 'max_objects': MAX_OBJECTS, 'truncated': truncated,
        'reference_errors': errors, 'not_a_full_storage_inventory': True,
    }
