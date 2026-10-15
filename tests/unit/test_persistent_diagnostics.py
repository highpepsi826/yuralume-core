from __future__ import annotations

import importlib.util
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from kokoro_link.infrastructure.observability.persistent_diagnostics import (
    DiagnosticCollector, read_persistent_diagnostics, safe_log_metadata,
)
from kokoro_link.infrastructure.persistence.models import DiagnosticEventRow, DiagnosticQuotaRow


def test_log_event_carries_correlation_and_safe_build_identity(monkeypatch):
    from kokoro_link.infrastructure.observability import persistent_diagnostics as module
    from kokoro_link.infrastructure.observability.runtime_diagnostics import diagnostic_scope
    collector = DiagnosticCollector()
    monkeypatch.setattr(module, '_process_metadata', lambda: {
        'instance_id': 'instance-a', 'build_commit_sha': 'abcdef123456',
        'build_source_digest': 'sha256:' + 'a' * 64})
    with diagnostic_scope(character_id='character-a', job_id='job-a') as context:
        record = logging.LogRecord('kokoro_link.test', logging.WARNING, __file__, 1,
                                   'private log %s', ('private body',), None)
        collector.handler.emit(record)
    row = collector.queue[0]
    metadata = json.loads(row['details_json'])
    assert row['character_id'] == 'character-a'
    assert row['request_id'] == context['request_id']
    assert metadata['trace_id'] == context['trace_id']
    assert metadata['job_id'] == 'job-a'
    assert metadata['instance_id'] == 'instance-a'
    assert metadata['build_source_digest'] == 'sha256:' + 'a' * 64
    assert 'private' not in json.dumps(row, default=str)


@pytest_asyncio.fixture
async def diagnostics_db(tmp_path):
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "diagnostics.db"}')
    async with engine.begin() as conn:
        for table in (DiagnosticEventRow.__table__, DiagnosticQuotaRow.__table__):
            await conn.run_sync(table.create)
        await conn.execute(text('CREATE TABLE business_history (body TEXT)'))
        await conn.execute(text("INSERT INTO business_history VALUES ('untouched')"))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_persist_restart_redaction_and_safe_exceptions(diagnostics_db):
    first = DiagnosticCollector()
    first.factory = diagnostics_db
    first.emit('provider.attempt', character_id='character-1', request_id='request-1',
               status='failed', provider_id='provider-1', api_key='hidden', prompt='private body',
               model='https://user:password@example.test/model?token=hidden')
    await first.flush()
    second = DiagnosticCollector()
    second.factory = diagnostics_db
    second.emit('config.changed', changed_fields=['model_id'], revision='revision-2')
    await second.flush()
    rows, coverage = await read_persistent_diagnostics(
        diagnostics_db, datetime.now(timezone.utc) - timedelta(hours=1),
        datetime.now(timezone.utc) + timedelta(hours=1))
    assert len(rows) == 2
    encoded = json.dumps(rows)
    assert 'private body' not in encoded and 'password' not in encoded and 'hidden' not in encoded
    assert rows[0]['metadata']['model'] == '[REDACTED]'
    assert coverage['storage']['logical_bytes'] > 0
    assert coverage['status'] == 'partial'
    try:
        raise ValueError('secret exception body')
    except ValueError:
        import sys
        record = logging.LogRecord('kokoro_link.test', logging.ERROR, __file__, 1,
                                   'private %s', ('request body',), sys.exc_info())
    safe = safe_log_metadata(record)
    assert safe['exception_type'] == 'ValueError'
    assert safe['exception_stack']
    assert 'secret' not in json.dumps(safe)
    assert 'request body' not in json.dumps(safe)


@pytest.mark.asyncio
async def test_bounded_queue_hard_admission_cleanup_business_isolation(diagnostics_db):
    collector = DiagnosticCollector(queue_size=2, batch_size=2, cleanup_batch=1,
                                    soft_limit=1, hard_limit=2000, row_cap=2)
    collector.factory = diagnostics_db
    assert collector.emit('lifecycle.started')
    assert collector.emit('provider.attempt')
    assert not collector.emit('queue.overflow')
    await collector.flush()
    async with diagnostics_db() as session:
        records = list((await session.execute(select(DiagnosticEventRow))).scalars())
        assert len(records) == 2
        assert (records[0].expires_at - records[0].created_at).days == 30
        assert (records[1].expires_at - records[1].created_at).days == 14
        records[0].expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        await session.commit()
    await collector.flush()
    async with diagnostics_db() as session:
        quota = await session.get(DiagnosticQuotaRow, 1)
        assert quota.row_count == 1
        assert quota.dropped_count == 1
        assert json.loads(quota.housekeeping_json)['deleted_rows'] == 1
        assert (await session.execute(text('SELECT body FROM business_history'))).scalar_one() == 'untouched'
    # Second pass is bounded and trims old diagnostics under the soft limit.
    await collector.flush()
    await collector.flush()
    async with diagnostics_db() as session:
        quota = await session.get(DiagnosticQuotaRow, 1)
        assert quota.row_count == quota.logical_bytes == 0
    collector.hard_limit = 1
    collector.emit('too.large')
    await collector.flush()
    async with diagnostics_db() as session:
        quota = await session.get(DiagnosticQuotaRow, 1)
        assert quota.row_count == 0
        assert quota.dropped_count == 2


@pytest.mark.asyncio
async def test_two_collectors_serialize_row_quota(diagnostics_db):
    import asyncio
    collectors = [DiagnosticCollector(row_cap=1, cleanup_batch=1) for _ in range(2)]
    for collector in collectors:
        collector.factory = diagnostics_db
        collector.emit('provider.attempt')
    await asyncio.gather(*(collector.flush() for collector in collectors))
    async with diagnostics_db() as session:
        quota = await session.get(DiagnosticQuotaRow, 1)
        rows = list((await session.execute(select(DiagnosticEventRow))).scalars())
        assert len(rows) == quota.row_count == 1
        assert quota.logical_bytes == sum(row.logical_bytes for row in rows)
    assert all(collector.persist_failed_count == 0 for collector in collectors)


@pytest.mark.asyncio
async def test_missing_tables_fail_soft_and_shutdown_flush(tmp_path, diagnostics_db, monkeypatch):
    from kokoro_link.infrastructure.observability import persistent_diagnostics
    monkeypatch.setattr(persistent_diagnostics, '_COLLECTOR', DiagnosticCollector())
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "empty.db"}')
    factory = async_sessionmaker(engine)
    collector = DiagnosticCollector()
    collector.factory = factory
    collector.emit('provider.failed')
    await collector.flush()
    assert collector.persist_failed_count == 1 and collector.dropped_count == 1
    rows, coverage = await read_persistent_diagnostics(
        factory, datetime.now(timezone.utc) - timedelta(hours=1), datetime.now(timezone.utc))
    assert rows == [] and coverage['reason'] == 'store_unavailable'
    collector.factory = diagnostics_db
    await collector.flush()
    async with diagnostics_db() as session:
        quota = await session.get(DiagnosticQuotaRow, 1)
        assert quota.persist_failed_count == quota.dropped_count == 1
    await collector.start(diagnostics_db)
    collector.emit('lifecycle.stopping')
    await collector.stop()
    assert not collector.running and not collector.queue
    async with diagnostics_db() as session:
        quota = await session.get(DiagnosticQuotaRow, 1)
        assert quota.row_count == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_additive_migration_upgrade_downgrade_local_sqlite(tmp_path):
    path = Path(__file__).parents[2] / 'alembic/versions/x3l8n0p10061_persistent_diagnostics.py'
    spec = importlib.util.spec_from_file_location('diagnostic_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "migration.db"}')
    async with engine.begin() as conn:
        def rehearse(sync_conn):
            module.op = Operations(MigrationContext.configure(sync_conn))
            sync_conn.execute(text('CREATE TABLE business_history (id INTEGER PRIMARY KEY)'))
            module.upgrade()
            sync_conn.execute(text('SELECT * FROM diagnostic_events'))
            module.downgrade()
            sync_conn.execute(text('SELECT * FROM business_history'))
        await conn.run_sync(rehearse)
    await engine.dispose()

@pytest.mark.asyncio
async def test_global_scope_logs_and_priority_cleanup(diagnostics_db):
    collector = DiagnosticCollector(soft_limit=1, cleanup_batch=1)
    collector.factory = diagnostics_db
    collector.emit('lifecycle.started')
    collector.emit('application.log', level='ERROR', exception_type='TimeoutError')
    collector.emit('provider.attempt', character_id='a')
    collector.emit('provider.attempt', character_id='b')
    await collector.flush()
    await collector.flush()
    async with diagnostics_db() as session:
        rows = list((await session.execute(select(DiagnosticEventRow))).scalars())
        assert 'lifecycle.started' in [row.name for row in rows]
        assert 'application.log' in [row.name for row in rows]
        assert len(rows) == 3
    rows, _ = await read_persistent_diagnostics(
        diagnostics_db, datetime.now(timezone.utc) - timedelta(hours=1),
        datetime.now(timezone.utc) + timedelta(hours=1), character_id='a',
        include_global=True, include_logs=False)
    assert len(rows) == 1
    assert rows[0]['scope'] == 'global' and rows[0]['name'] == 'lifecycle.started'


@pytest.mark.asyncio
async def test_idle_flush_skips_transactions(diagnostics_db):
    collector = DiagnosticCollector()
    calls = []
    def factory():
        calls.append(True)
        return diagnostics_db()
    collector.factory = factory
    await collector.flush(housekeeping=False)
    assert calls == []
    await collector.flush(housekeeping=True)
    assert len(calls) == 1


def test_redaction_sensitive_strings():
    from kokoro_link.infrastructure.observability.diagnostic_buffer import redact
    result = redact({'header': 'Bearer abcdef-raw-token',
                     'url': 'https://user:pass@example.test/path?key=secret',
                     'x': 'api_key=hidden password:secret',
                     'headers': {'x-custom': 'sensitive'}})
    value = json.dumps(result)
    for secret in ('abcdef-raw-token', 'example.test', 'hidden', 'sensitive', 'password:secret'):
        assert secret not in value

@pytest.mark.asyncio
async def test_no_factory_stop_is_bounded_and_repeatable():
    import asyncio
    collector = DiagnosticCollector()
    collector.emit('provider.attempt')
    await collector.start(None)
    await asyncio.wait_for(collector.stop(timeout=0.2), 0.5)
    await asyncio.wait_for(collector.stop(timeout=0.2), 0.5)
    assert not collector.queue and not collector.running
    assert collector.dropped_count == 1


@pytest.mark.asyncio
async def test_failure_priority_retention_metadata_truncation_and_log_locations(diagnostics_db):
    collector = DiagnosticCollector(queue_size=1)
    collector.factory = diagnostics_db
    collector.emit('provider.attempt', status='ok')
    assert collector.emit('provider.attempt.response', http_status=500,
                          turn_id='turn-1', attempt_id='attempt-1', model_id='a' * 200)
    assert collector.dropped_count == 1
    await collector.flush()
    async with diagnostics_db() as session:
        record = (await session.execute(select(DiagnosticEventRow))).scalar_one()
        assert record.level == 'WARNING'
        assert (record.expires_at - record.created_at).days == 30
        details = json.loads(record.details_json)
        assert details['turn_id'] == 'turn-1' and details['attempt_id'] == 'attempt-1'
        assert details['truncated_fields'] == ['model_id']
        assert details['original_lengths'] == {'model_id': 200}
    try:
        try:
            raise ValueError('private inner')
        except ValueError as cause:
            raise RuntimeError('private outer') from cause
    except RuntimeError:
        import sys
        log = logging.LogRecord('kokoro_link.test', logging.ERROR, __file__, 42,
                                'secret log', (), sys.exc_info(), func='safe_function')
    details = safe_log_metadata(log)
    assert details['source_line'] == 42 and details['source_function'] == 'safe_function'
    assert details['source_file'] == 'test_persistent_diagnostics.py'
    assert details['exception_chain'] == ['RuntimeError', 'ValueError']
    assert 'private' not in json.dumps(details) and 'secret log' not in json.dumps(details)


@pytest.mark.asyncio
async def test_read_status_timeout_and_unconfigured(monkeypatch):
    import asyncio
    from kokoro_link.infrastructure.observability import persistent_diagnostics as module
    status = await module.diagnostic_storage_status(None)
    assert status['status'] == 'unavailable' and status['reason'] == 'database_not_configured'
    async def hang(*args, **kwargs):
        await asyncio.sleep(60)
    monkeypatch.setattr(module, '_diagnostic_storage_status', hang)
    monkeypatch.setattr(module, '_read_persistent_diagnostics', hang)
    real_timeout = asyncio.timeout
    monkeypatch.setattr(module.asyncio, 'timeout', lambda delay: real_timeout(0.01))
    status = await module.diagnostic_storage_status(object())
    assert status['reason'] == 'read_timeout'
    rows, coverage = await module.read_persistent_diagnostics(
        object(), datetime.now(timezone.utc), datetime.now(timezone.utc))
    assert rows == [] and coverage['reason'] == 'read_timeout'
