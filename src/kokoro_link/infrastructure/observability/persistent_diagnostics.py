"""Bounded fail-soft diagnostics. All database writes run off the request path."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import traceback
import time
from functools import lru_cache
from pathlib import PurePath
from collections import deque
from datetime import datetime, timedelta, timezone
from threading import Lock
from uuid import uuid4

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from kokoro_link.infrastructure.persistence.models import DiagnosticEventRow, DiagnosticQuotaRow
from .diagnostic_buffer import redact

SOFT_LIMIT_BYTES = 512 * 1024 * 1024
HARD_LIMIT_BYTES = 1024 * 1024 * 1024
ROW_CAP = 250_000
# Text fields are structural identifiers, never arbitrary request/response payloads.
SAFE_FIELDS = frozenset({
    'trace_id', 'operation_id', 'parent_operation_id', 'job_id', 'build_source_digest',
    'turn_id', 'account_id', 'platform_message_id', 'binding_id', 'attempt_id',
    'source_file', 'source_function', 'source_line', 'exception_chain',
    'parent_request_id', 'feature_key', 'model_id', 'profile_id', 'routing_source',
    'fallback_reason', 'error_type', 'elapsed_ms', 'protocol', 'has_text', 'has_tool_calls',
    'has_reasoning', 'text_chars', 'finish_reason', 'upstream_request_id', 'revision',
    'post_id', 'artifact_count', 'reason',
    'process_role', 'instance_id', 'build_commit_sha', 'build_tag', 'service_name',
    'provider', 'provider_id', 'provider_type', 'model', 'route', 'feature', 'channel',
    'operation', 'phase', 'status', 'outcome', 'reason_code', 'error_code', 'exception_type',
    'attempt', 'attempt_count', 'duration_ms', 'latency_ms', 'retry_count', 'http_status',
    'fallback', 'fallback_used', 'image_requested', 'image_delivered', 'video_requested',
    'config_version', 'changed_fields', 'enabled', 'count', 'success', 'logger',
    'exception_stack', 'template_hash', 'target', 'source', 'queue_depth',
})
_IDENTIFIER = re.compile(r'^[A-Za-z0-9_.:/@+ -]{1,160}$')


@lru_cache(maxsize=1)
def _process_metadata():
    from kokoro_link.infrastructure.build_info import get_build_info
    from kokoro_link.infrastructure.runtime_identity import instance_id
    build = get_build_info().build
    return {"instance_id": instance_id(), "build_commit_sha": build.commit_sha,
            "build_source_digest": build.source_digest}


def _identifier(value, max_length=128):
    if value is None:
        return None
    value = str(value)[:max_length]
    if not _IDENTIFIER.fullmatch(value) or '://' in value or redact(value) != value:
        return '[REDACTED]'
    return value


def _safe_metadata(metadata):
    result = {}
    truncated = {}
    for key, value in metadata.items():
        if key not in SAFE_FIELDS:
            continue
        if isinstance(value, (bool, int, float)) or value is None:
            result[key] = value
        elif key in {'exception_stack', 'exception_chain'} and isinstance(value, list):
            # Only internally generated frame locations; no source lines or locals.
            result[key] = [_identifier(v, 160) for v in value[:12]]
        elif key == 'changed_fields' and isinstance(value, (list, tuple)):
            result[key] = [_identifier(v, 64) for v in value[:30]]
        else:
            if isinstance(value, str) and len(value) > 160:
                truncated[key] = len(value)
            result[key] = _identifier(value, 160)
    if truncated:
        result['truncated_fields'] = sorted(truncated)
        result['original_lengths'] = truncated
    return redact(result)


def safe_log_metadata(record):
    """Never render logging arguments, exception messages, source text or locals."""
    import hashlib
    result = {'logger': _identifier(record.name),
              'source_file': _identifier(PurePath(record.pathname).name),
              'source_function': _identifier(record.funcName),
              'source_line': record.lineno,
              'template_hash': hashlib.sha256(str(record.msg).encode('utf-8')).hexdigest()[:20]}
    if record.exc_info and record.exc_info[0]:
        result['exception_type'] = _identifier(record.exc_info[0].__name__)
        result['exception_stack'] = [
            f'{frame.name}:{frame.lineno}' for frame in traceback.extract_tb(record.exc_info[2])[-12:]
        ]
        chain = []
        exc = record.exc_info[1]
        seen = set()
        while exc is not None and id(exc) not in seen and len(chain) < 8:
            seen.add(id(exc))
            chain.append(type(exc).__name__)
            exc = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
        result['exception_chain'] = chain
    return result


class _PersistentLogHandler(logging.Handler):
    def __init__(self, collector):
        super().__init__(logging.WARNING)
        self.collector = collector

    def emit(self, record):
        if not record.name.startswith('kokoro_link'):
            return
        try:
            from .runtime_diagnostics import current_context
            self.collector.emit('application.log', level=record.levelname,
                                **current_context(), **safe_log_metadata(record))
        except Exception:
            pass


class DiagnosticCollector:
    def __init__(self, *, queue_size=2000, batch_size=100, cleanup_batch=500,
                 soft_limit=SOFT_LIMIT_BYTES, hard_limit=HARD_LIMIT_BYTES, row_cap=ROW_CAP):
        self.queue = deque()
        self.recent = deque(maxlen=2000)
        self.lock = Lock()
        self._flush_lock = asyncio.Lock()
        self.queue_size, self.batch_size, self.cleanup_batch = queue_size, batch_size, cleanup_batch
        self.soft_limit, self.hard_limit, self.row_cap = soft_limit, hard_limit, row_cap
        self.dropped_count = self.persist_failed_count = 0
        self._pending_drops = self._pending_failures = 0
        self.factory = self.task = None
        self.running = False
        self.last_persisted_at = None
        self.last_error = None
        self._last_housekeeping = 0.0
        self.started_at = None
        self.handler = _PersistentLogHandler(self)

    def emit(self, name, *, character_id=None, conversation_id=None, request_id=None, level='INFO', **metadata):
        try:
            if level == 'DEBUG':
                return False
            now = datetime.now(timezone.utc)
            metadata = {**_process_metadata(), **metadata}
            name = _identifier(name)
            level = level if level in {'INFO', 'WARNING', 'WARN', 'ERROR', 'CRITICAL'} else 'INFO'
            failed = (metadata.get('status') in {'failed', 'error'} or name.endswith('failed')
                      or bool(metadata.get('error_type'))
                      or isinstance(metadata.get('http_status'), int) and metadata['http_status'] >= 400)
            if failed and level == 'INFO':
                level = 'WARNING'
            days = 30 if level != 'INFO' or any(s in name for s in ('config', 'lifecycle')) else 14
            safe_metadata = _safe_metadata(metadata)
            id_lengths = {key: len(str(value)) for key, value, cap in (
                ('character_id', character_id, 64), ('conversation_id', conversation_id, 64),
                ('request_id', request_id, 128)) if value is not None and len(str(value)) > cap}
            if id_lengths:
                safe_metadata.setdefault('original_lengths', {}).update(id_lengths)
                safe_metadata['truncated_fields'] = sorted(safe_metadata['original_lengths'])
            item = dict(id=str(uuid4()), created_at=now, expires_at=now + timedelta(days=days),
                        name=name, level=level, character_id=_identifier(character_id, 64),
                        conversation_id=_identifier(conversation_id, 64), request_id=_identifier(request_id),
                        details_json=json.dumps(safe_metadata, ensure_ascii=False, allow_nan=False))
            item['logical_bytes'] = len(json.dumps(item, default=str, ensure_ascii=False).encode('utf-8')) + 128
            with self.lock:
                self.recent.append(dict(item))
                if len(self.queue) >= self.queue_size:
                    self.dropped_count += 1
                    self._pending_drops += 1
                    if days == 30:
                        victim = next((old for old in self.queue if old['level'] == 'INFO'
                            and 'config' not in old['name'] and 'lifecycle' not in old['name']), None)
                        if victim is not None:
                            self.queue.remove(victim)
                        else:
                            return False
                    else:
                        return False
                self.queue.append(item)
            return True
        except Exception:
            with self.lock:
                self.dropped_count += 1
                self._pending_drops += 1
            return False

    async def start(self, factory):
        if self.running:
            return
        self.factory = factory
        self.running = True
        self.started_at = datetime.now(timezone.utc).isoformat()
        logging.getLogger().addHandler(self.handler)
        self.task = asyncio.create_task(self._run(), name='diagnostic-persistence')

    async def stop(self, timeout=3):
        logging.getLogger().removeHandler(self.handler)
        self.running = False
        if self.task:
            try:
                await asyncio.wait_for(self.task, timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        with self.lock:
            self.dropped_count += len(self.queue)
            self._pending_drops += len(self.queue)
            self.queue.clear()

    async def _run(self):
        while self.running or self.queue:
            if self.factory is None and not self.running:
                break
            await self.flush(housekeeping=time.monotonic() - self._last_housekeeping >= 60)
            if self.running:
                await asyncio.sleep(0.5)

    async def flush(self, *, housekeeping=True):
        async with self._flush_lock:
            await self._flush(housekeeping=housekeeping)

    async def _flush(self, *, housekeeping):
        if self.factory is None:
            return
        with self.lock:
            batch = [self.queue.popleft() for _ in range(min(self.batch_size, len(self.queue)))]
            drops, failures = self._pending_drops, self._pending_failures
        if not batch and not drops and not failures and not housekeeping:
            return
        try:
            async with self.factory() as session, session.begin():
                dialect = session.bind.dialect.name
                insert = pg_insert if dialect == 'postgresql' else sqlite_insert
                # The upsert takes the singleton write lock also on SQLite. PostgreSQL
                # row locking serializes admission and cleanup across every process.
                await session.execute(insert(DiagnosticQuotaRow).values(
                    id=1, logical_bytes=0, row_count=0, dropped_count=0,
                    persist_failed_count=0, housekeeping_json='{}',
                ).on_conflict_do_nothing(index_elements=['id']))
                quota = (await session.execute(select(DiagnosticQuotaRow).where(
                    DiagnosticQuotaRow.id == 1).with_for_update())).scalar_one()
                if dialect == 'sqlite':
                    # UPDATE precedes event reads to serialize deferred SQLite transactions.
                    from sqlalchemy import update
                    await session.execute(update(DiagnosticQuotaRow).where(
                        DiagnosticQuotaRow.id == 1).values(row_count=DiagnosticQuotaRow.row_count))
                now = datetime.now(timezone.utc)
                needs_cleanup = housekeeping or quota.logical_bytes > self.soft_limit or quota.row_count >= self.row_cap
                victims = []
                if needs_cleanup:
                    victims = list((await session.execute(select(DiagnosticEventRow).where(
                        DiagnosticEventRow.expires_at <= now).order_by(
                        DiagnosticEventRow.expires_at, DiagnosticEventRow.id).limit(self.cleanup_batch))).scalars())
                if not victims and (quota.logical_bytes > self.soft_limit or quota.row_count >= self.row_cap):
                    victims = list((await session.execute(select(DiagnosticEventRow).where(
                        DiagnosticEventRow.level == 'INFO',
                        ~DiagnosticEventRow.name.contains('config'),
                        ~DiagnosticEventRow.name.contains('lifecycle'),
                    ).order_by(
                        DiagnosticEventRow.created_at, DiagnosticEventRow.id).limit(self.cleanup_batch))).scalars())
                    if not victims:
                        victims = list((await session.execute(select(DiagnosticEventRow).order_by(
                            DiagnosticEventRow.created_at, DiagnosticEventRow.id).limit(self.cleanup_batch))).scalars())
                if victims:
                    await session.execute(delete(DiagnosticEventRow).where(
                        DiagnosticEventRow.id.in_([row.id for row in victims])))
                    quota.row_count -= len(victims)
                    quota.logical_bytes -= sum(row.logical_bytes for row in victims)
                rejected = 0
                for item in batch:
                    if quota.row_count >= self.row_cap or quota.logical_bytes + item['logical_bytes'] > self.hard_limit:
                        rejected += 1
                    else:
                        session.add(DiagnosticEventRow(**item))
                        quota.row_count += 1
                        quota.logical_bytes += item['logical_bytes']
                quota.dropped_count += drops + rejected
                quota.persist_failed_count += failures
                if len(batch) > rejected:
                    quota.last_persisted_at = now
                previous_cleanup = json.loads(quota.housekeeping_json)
                quota.housekeeping_json = json.dumps({
                    'last_started_at': now.isoformat() if needs_cleanup else previous_cleanup.get('last_started_at'),
                    'last_succeeded_at': now.isoformat() if needs_cleanup else previous_cleanup.get('last_succeeded_at'),
                    'deleted_rows': len(victims) if needs_cleanup else previous_cleanup.get('deleted_rows', 0),
                    'total_deleted_rows': previous_cleanup.get('total_deleted_rows', 0) + len(victims),
                    'first_persisted_at': previous_cleanup.get('first_persisted_at') or (
                        now.isoformat() if len(batch) > rejected else None),
                    'last_error': None})
            with self.lock:
                self._pending_drops -= drops
                self._pending_failures -= failures
                self.dropped_count += rejected
            if len(batch) > rejected:
                self.last_persisted_at = now.isoformat()
            self.last_error = None
            if needs_cleanup:
                self._last_housekeeping = time.monotonic()
        except asyncio.CancelledError:
            with self.lock:
                self.dropped_count += len(batch)
                self._pending_drops += len(batch)
            raise
        except Exception as exc:
            # Do not retain the exception message: driver errors can contain credentials/SQL values.
            with self.lock:
                self.persist_failed_count += 1
                self._pending_failures += 1
                self.dropped_count += len(batch)
                self._pending_drops += len(batch)
            self.last_error = type(exc).__name__
            if housekeeping:
                self._last_housekeeping = time.monotonic()

    def status(self):
        with self.lock:
            return {'enabled': True, 'running': self.running, 'queue_depth': len(self.queue),
                    'status': 'degraded' if self.last_error or not self.running else 'ok',
                    'started_at': self.started_at,
                    'dropped_count': self.dropped_count, 'persist_failed_count': self.persist_failed_count,
                    'last_persisted_at': self.last_persisted_at,
                    'logical_bytes': None, 'soft_limit_bytes': self.soft_limit,
                    'hard_limit_bytes': self.hard_limit, 'row_cap': self.row_cap,
                    'retention_days': {'info': 14, 'error': 30, 'config_lifecycle': 30},
                    'housekeeping': {'last_started_at': None, 'last_succeeded_at': None,
                                     'deleted_rows': 0, 'total_deleted_rows': 0,
                                     'first_persisted_at': None, 'last_error': self.last_error},
                    'host_disk': {'status': 'unknown'}}


_COLLECTOR = DiagnosticCollector()


def get_diagnostic_collector():
    return _COLLECTOR


def emit_event(name, *, character_id=None, conversation_id=None, request_id=None, **metadata):
    return _COLLECTOR.emit(name, character_id=character_id, conversation_id=conversation_id,
                           request_id=request_id, **metadata)


async def _diagnostic_storage_status(factory):
    status = _COLLECTOR.status()
    if factory is None:
        status.update(status='unavailable', storage_status='unavailable', reason='database_not_configured')
        return status
    try:
        async with factory() as session:
            quota = await session.get(DiagnosticQuotaRow, 1)
            status['storage_status'] = 'available'
            status['logical_bytes'] = quota.logical_bytes if quota else 0
            status['row_count'] = quota.row_count if quota else 0
            if status['logical_bytes'] >= SOFT_LIMIT_BYTES or status['row_count'] >= ROW_CAP:
                status['status'] = 'degraded'
            if quota:
                status['dropped_count'] = quota.dropped_count + _COLLECTOR._pending_drops
                status['persist_failed_count'] = quota.persist_failed_count + _COLLECTOR._pending_failures
                status['last_persisted_at'] = quota.last_persisted_at.isoformat() if quota.last_persisted_at else None
                status['housekeeping'].update(json.loads(quota.housekeeping_json))
                if _COLLECTOR.last_error:
                    status['housekeeping']['last_error'] = _COLLECTOR.last_error
    except Exception as exc:
        status['storage_status'] = 'unavailable'
        status['status'] = 'unavailable'
        status['housekeeping']['last_error'] = type(exc).__name__
    return status


async def _read_persistent_diagnostics(factory, start, end, *, character_id=None, limit=2000,
                                      include_global=False, include_logs=True):
    limit = max(1, min(limit, 10000))
    coverage = {'source': 'persistent_diagnostics', 'status': 'partial', 'row_count': 0,
                'max_rows': limit, 'historical_coverage': 'unknown_before_instrumentation'}
    try:
        async with factory() as session:
            query = select(DiagnosticEventRow).where(DiagnosticEventRow.created_at >= start,
                                                      DiagnosticEventRow.created_at <= end)
            if character_id is not None:
                scope_filter = DiagnosticEventRow.character_id == character_id
                if include_global:
                    scope_filter = or_(scope_filter, DiagnosticEventRow.character_id.is_(None))
                query = query.where(scope_filter)
            if not include_logs:
                query = query.where(DiagnosticEventRow.name != 'application.log')
            records = list((await session.execute(query.order_by(DiagnosticEventRow.created_at,
                                        DiagnosticEventRow.id).limit(limit + 1))).scalars())
        rows = [dict(id=row.id, created_at=row.created_at.isoformat(), name=row.name, level=row.level,
                     character_id=row.character_id, conversation_id=row.conversation_id,
                     request_id=row.request_id, scope='global' if row.character_id is None else 'character',
                     metadata=json.loads(row.details_json)) for row in records[:limit]]
        coverage.update(row_count=len(rows), truncated=len(records) > limit,
                        storage=await diagnostic_storage_status(factory))
        return rows, coverage

    except Exception as exc:
        with _COLLECTOR.lock:
            fallback = [dict(item) for item in _COLLECTOR.recent
                        if start <= item['created_at'] <= end and (
                            character_id is None or item['character_id'] == character_id or (
                                include_global and item['character_id'] is None)) and (
                            include_logs or item['name'] != 'application.log')]
        rows = [dict(id=row['id'], created_at=row['created_at'].isoformat(), name=row['name'],
                     level=row['level'], character_id=row['character_id'],
                     conversation_id=row['conversation_id'], request_id=row['request_id'],
                     scope='global' if row['character_id'] is None else 'character',
                     metadata=json.loads(row['details_json'])) for row in fallback[:limit]]
        coverage.update(reason='store_unavailable', error_type=type(exc).__name__,
                        truncated=len(fallback) > limit, row_count=len(rows),
                        fallback_source='in_process_structured_ring',
                        storage=await diagnostic_storage_status(factory))
        return rows, coverage


async def diagnostic_storage_status(factory):
    try:
        async with asyncio.timeout(5):
            return await _diagnostic_storage_status(factory)
    except TimeoutError:
        status = _COLLECTOR.status()
        status.update(status='unavailable', storage_status='unavailable', reason='read_timeout')
        status['housekeeping']['last_error'] = 'TimeoutError'
        return status


async def read_persistent_diagnostics(factory, start, end, *, character_id=None, limit=2000,
                                      include_global=False, include_logs=True):
    try:
        async with asyncio.timeout(5):
            return await _read_persistent_diagnostics(factory, start, end, character_id=character_id,
                limit=limit, include_global=include_global, include_logs=include_logs)
    except TimeoutError:
        return [], {'source': 'persistent_diagnostics', 'status': 'partial', 'row_count': 0,
                    'reason': 'read_timeout', 'error_type': 'TimeoutError', 'max_rows': limit,
                    'historical_coverage': 'unknown_before_instrumentation', 'truncated': False}
