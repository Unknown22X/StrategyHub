from __future__ import annotations

import threading

from fastapi.testclient import TestClient

import rangebot.engine.api as api_module


class _ObservedStrategyRuntimeRunner:
    created: "_ObservedStrategyRuntimeRunner | None" = None

    def __init__(self, **_: object) -> None:
        self.started = threading.Event()
        self.stopped = threading.Event()
        type(self).created = self

    async def run(self, stop_event) -> None:
        self.started.set()
        await stop_event.wait()
        self.stopped.set()


def test_strategy_runtime_runner_starts_and_stops_with_engine_lifespan(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        api_module,
        "StrategyRuntimeRunner",
        _ObservedStrategyRuntimeRunner,
    )
    app = api_module.create_app(f"sqlite:///{tmp_path / 'rangebot.db'}")
    runner = _ObservedStrategyRuntimeRunner.created

    assert runner is not None
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert runner.started.wait(timeout=2)
        assert not runner.stopped.is_set()

    assert runner.stopped.wait(timeout=2)
