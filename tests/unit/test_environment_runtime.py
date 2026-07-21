from __future__ import annotations

import asyncio
from threading import Event

import pytest

from rangebot.domain.exchange import ExchangeSnapshot, TradingMode
from rangebot.engine.environment_runtime import (
    EnvironmentRuntimeManager,
    EnvironmentTransitionError,
)
from rangebot.engine.exchange import MockGateIoAdapter
from rangebot.engine.gate_private_websocket import PrivateStreamStateStore


class _BlockingAdapter(MockGateIoAdapter):
    def __init__(self, entered: Event, release: Event) -> None:
        super().__init__()
        self._entered = entered
        self._release = release

    def reconcile(self, mode: TradingMode) -> ExchangeSnapshot:
        self._entered.set()
        if not self._release.wait(timeout=2):
            raise TimeoutError("Test adapter was not released.")
        return super().reconcile(mode)


class _Service:
    def __init__(self, kind: str, mode: TradingMode, events: list[str]) -> None:
        self.kind = kind
        self.mode = mode
        self.events = events

    async def run(self, stop_event: asyncio.Event) -> None:
        self.events.append(f"start:{self.kind}:{self.mode}")
        await stop_event.wait()
        self.events.append(f"stop:{self.kind}:{self.mode}")


def test_environment_runtime_replaces_all_environment_bound_components_together() -> (
    None
):
    events: list[str] = []
    invalidated: list[TradingMode] = []
    persisted: list[TradingMode] = []
    reset_count = 0

    def reset_market_data() -> None:
        nonlocal reset_count
        reset_count += 1

    def public_factory(mode: TradingMode) -> _Service:
        return _Service("public", mode, events)

    def private_factory(
        mode: TradingMode,
        adapter: MockGateIoAdapter,
        status_store: PrivateStreamStateStore,
    ) -> _Service:
        assert isinstance(adapter, MockGateIoAdapter)
        assert status_store.snapshot().mode == mode
        return _Service("private", mode, events)

    runtime = EnvironmentRuntimeManager(
        initial_environment="paper",
        adapter_factory=lambda mode: MockGateIoAdapter(),
        public_service_factory=public_factory,
        private_service_factory=private_factory,
        persist_snapshot=lambda snapshot: persisted.append(snapshot.mode),
        invalidate_snapshot=invalidated.append,
        reset_market_data=reset_market_data,
    )

    async def scenario() -> None:
        await runtime.start()
        await asyncio.sleep(0)
        assert runtime.snapshot("paper").public_websocket_environment == "live"
        assert runtime.snapshot("paper").private_websocket_environment is None

        await runtime.switch("testnet")
        await asyncio.sleep(0)
        testnet = runtime.snapshot("testnet")
        assert testnet.active_engine_environment == "testnet"
        assert testnet.exchange_adapter_environment == "testnet"
        assert testnet.public_websocket_environment == "testnet"
        assert testnet.private_websocket_environment == "testnet"
        assert testnet.activated is True

        await runtime.switch("live", confirmation="SWITCH TO LIVE")
        await asyncio.sleep(0)
        live = runtime.snapshot("live")
        assert live.active_engine_environment == "live"
        assert live.exchange_adapter_environment == "live"
        assert live.public_websocket_environment == "live"
        assert live.private_websocket_environment == "live"
        assert live.activated is True

        await runtime.stop()

    asyncio.run(scenario())

    assert events == [
        "start:public:live",
        "stop:public:live",
        "start:public:testnet",
        "start:private:testnet",
        "stop:public:testnet",
        "stop:private:testnet",
        "start:public:live",
        "start:private:live",
        "stop:public:live",
        "stop:private:live",
    ]
    assert invalidated == ["testnet", "testnet", "live"]
    assert persisted == ["testnet", "live"]
    assert reset_count == 2


def test_exchange_calls_are_blocked_while_environment_switch_is_running() -> None:
    entered = Event()
    release = Event()
    runtime = EnvironmentRuntimeManager(
        initial_environment="paper",
        adapter_factory=lambda mode: _BlockingAdapter(entered, release),
    )

    async def scenario() -> None:
        switch_task = asyncio.create_task(runtime.switch("testnet"))
        assert await asyncio.to_thread(entered.wait, 1)
        assert runtime.transition_state == "switching"
        with pytest.raises(EnvironmentTransitionError) as captured:
            runtime.adapter_for("testnet")
        assert captured.value.code == "environment_switching"
        release.set()
        await switch_task
        assert runtime.transition_state == "ready"
        assert runtime.active_adapter_mode == "testnet"

    asyncio.run(scenario())
