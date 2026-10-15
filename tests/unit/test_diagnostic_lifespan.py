"""Failure evidence must be emitted before the diagnostic writer is stopped."""
import importlib

import pytest

from tests.unit.test_app_role_gating import _app_for_role, _install_fakes


@pytest.mark.asyncio
@pytest.mark.parametrize("startup_failure", [True, False])
async def test_lifecycle_failure_precedes_collector_flush(monkeypatch, startup_failure):
    module = importlib.import_module("kokoro_link.api.app")
    observations = []

    class Collector:
        async def start(self, factory):
            observations.append("collector.started")

        async def stop(self):
            observations.append("collector.flushed")

    collector = Collector()
    monkeypatch.setattr(module, "get_diagnostic_collector", lambda: collector)
    monkeypatch.setattr(module, "event", lambda name, **metadata: observations.append(name))
    app = _app_for_role("api")
    _install_fakes(app.state.container)
    if startup_failure:
        async def fail(*args, **kwargs):
            raise RuntimeError("synthetic startup failure")
        monkeypatch.setattr(module, "run_startup_seeds", fail)
    with pytest.raises(RuntimeError, match="synthetic"):
        async with app.router.lifespan_context(app):
            raise RuntimeError("synthetic runtime failure")
    assert observations.index("lifecycle.failed") < observations.index("collector.flushed")
    assert observations.count("collector.flushed") == 1
