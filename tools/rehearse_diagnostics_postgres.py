"""Run only against a newly created disposable loopback PostgreSQL container.

Execute from the source checkout with .venv/Scripts/python.exe. No .env or
production configuration is read by this runner; Alembic receives explicit
local database URLs that override .env. No application runtime is started.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
BASELINE = "w2k7m9n10060"
HEAD = "x3l8n0p10061"


def main():
    token = uuid4().hex[:12]
    name = f"yuralume-diagnostic-rehearsal-{token}"
    env = dict(os.environ, POSTGRES_PASSWORD=secrets.token_hex(24))
    report = {"scope": "disposable_local_postgresql_synthetic_data", "checks": [], "status": "running"}
    output = ROOT / "temp" / f"diagnostic-postgres-rehearsal-{token}.json"
    output.parent.mkdir(exist_ok=True)
    created = False

    def run(args):
        result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True)
        if result.returncode:
            from kokoro_link.infrastructure.observability.diagnostic_buffer import redact
            safe_error = result.stderr[-8000:].replace(env["POSTGRES_PASSWORD"], "[REDACTED]")
            report["command_error_tail"] = redact(safe_error)
            raise RuntimeError(f"command_failed:{args[0]}:{result.returncode}")
        return result.stdout.strip()

    def migrate(target, direction="upgrade"):
        run([sys.executable, "-m", "alembic", direction, target])
        report["checks"].append(f"alembic_{direction}_{target}")
        print(report["checks"][-1], flush=True)

    try:
        run(["docker", "version", "--format", "{{.Server.Version}}"])
        report["phase"] = "create_isolated_container"
        run(["docker", "run", "--detach", "--name", name,
             "--label", f"yuralume.diagnostic-rehearsal={token}",
             "--publish", "127.0.0.1::5432", "--tmpfs", "/var/lib/postgresql/data:rw",
             "--env", "POSTGRES_PASSWORD", "--env", "POSTGRES_USER=diag_rehearsal",
             "--env", "POSTGRES_DB=diag_rehearsal", "pgvector/pgvector:pg17"])
        created = True
        port = run(["docker", "port", name, "5432/tcp"])
        if not port.startswith("127.0.0.1:") or not port.rsplit(":", 1)[1].isdigit():
            raise RuntimeError("unexpected_non_loopback_binding")
        hostport = port.rsplit(":", 1)[1]
        for _ in range(60):
            ready = subprocess.run(["docker", "exec", name, "pg_isready", "-U", "diag_rehearsal"],
                                   capture_output=True, env=env)
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("postgres_start_timeout")
        local_url = f"postgresql+psycopg2://diag_rehearsal:{env['POSTGRES_PASSWORD']}@127.0.0.1:{hostport}/diag_rehearsal"
        env["DATABASE_URL"] = env["KOKORO_DATABASE_URL"] = local_url
        report["phase"] = "migration_graph"
        migrate(BASELINE)
        from sqlalchemy import create_engine, inspect, text
        with create_engine(local_url).begin() as connection:
            tables_before = set(inspect(connection).get_table_names())
            connection.execute(text("CREATE TABLE diagnostic_rehearsal_sentinel (id INTEGER PRIMARY KEY, body TEXT)"))
            connection.execute(text("INSERT INTO diagnostic_rehearsal_sentinel VALUES (1, 'synthetic-preserve')"))
        migrate(HEAD)
        migrate(BASELINE, "downgrade")
        with create_engine(local_url).begin() as connection:
            assert set(inspect(connection).get_table_names()) == tables_before | {"diagnostic_rehearsal_sentinel"}
            assert connection.execute(text("SELECT body FROM diagnostic_rehearsal_sentinel")).scalar_one() == "synthetic-preserve"
        migrate(HEAD)
        report["checks"].append("rollback_preserves_previous_schema_and_sentinel")
        report["phase"] = "persistence_quota_cleanup"
        asyncio.run(exercise(local_url.replace("+psycopg2", "+asyncpg"), report))
        report["status"] = "passed"
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__)
        print("Rehearsal failed in phase:", report.get("phase", "docker_access"), type(exc).__name__, flush=True)
    finally:
        if created:
            try:
                label = run(["docker", "inspect", "--format", '{{index .Config.Labels "yuralume.diagnostic-rehearsal"}}', name])
                if label != token:
                    raise RuntimeError("container_ownership_mismatch")
                run(["docker", "rm", "--force", "--volumes", name])
                report["cleanup"] = "owned_disposable_container_removed"
            except Exception as exc:
                report.update(cleanup="failed", cleanup_error_type=type(exc).__name__, container_to_inspect=name)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("Report:", output, flush=True)
    return 0 if report["status"] == "passed" and report.get("cleanup") == "owned_disposable_container_removed" else 1


async def exercise(url, report):
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from kokoro_link.infrastructure.observability.persistent_diagnostics import DiagnosticCollector
    from kokoro_link.infrastructure.persistence.models import DiagnosticEventRow, DiagnosticQuotaRow
    spec = importlib.util.spec_from_file_location("diagnostic_pg_checks", ROOT / "tests/unit/test_persistent_diagnostics.py")
    checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checks)
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as c:
            await c.execute(text("CREATE TABLE business_history (body TEXT)"))
            await c.execute(text("INSERT INTO business_history VALUES ('untouched')"))
        for name in ("test_persist_restart_redaction_and_safe_exceptions",
                     "test_bounded_queue_hard_admission_cleanup_business_isolation",
                     "test_two_collectors_serialize_row_quota",
                     "test_global_scope_logs_and_priority_cleanup"):
            async with engine.begin() as c:
                await c.execute(text("TRUNCATE diagnostic_events, diagnostic_quota"))
            await getattr(checks, name)(factory)
            report["checks"].append(name)
            print(name, "passed", flush=True)
        async with engine.begin() as c:
            await c.execute(text("TRUNCATE diagnostic_events, diagnostic_quota"))
        writers = [DiagnosticCollector(row_cap=40, cleanup_batch=7) for _ in range(16)]
        for writer in writers:
            writer.factory = factory
            for _ in range(20):
                writer.emit("provider.attempt", status="succeeded")
        await asyncio.gather(*(writer.flush() for writer in writers))
        assert all(writer.persist_failed_count == 0 for writer in writers)
        async with factory() as session:
            quota = await session.get(DiagnosticQuotaRow, 1)
            rows = list((await session.execute(select(DiagnosticEventRow))).scalars())
            assert 0 < len(rows) == quota.row_count <= 40
            assert quota.logical_bytes == sum(row.logical_bytes for row in rows)
            assert quota.dropped_count > 0
            assert (await session.execute(text("SELECT body FROM business_history"))).scalar_one() == "untouched"
        report["checks"].append("16_concurrent_writers_quota_accounting_business_isolation")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
