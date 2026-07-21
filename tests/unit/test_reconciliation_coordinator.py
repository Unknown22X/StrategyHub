from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Event, Lock
import time

from rangebot.domain.exchange import ExchangeSnapshot, TradingMode
from rangebot.engine.reconciliation import ReconciliationCoordinator


NOW = datetime(2026, 7, 21, 8, 0, tzinfo=UTC)


def _snapshot(
    mode: TradingMode = "testnet",
    *,
    reconciled_at: datetime = NOW,
    **changes,
) -> ExchangeSnapshot:
    values = {
        "mode": mode,
        "reconciled_at": reconciled_at,
        "one_way_confirmed": True,
        "cross_margin_confirmed": True,
        "risk_ready": True,
        "daily_baseline_ready": True,
        "protection_ready": True,
        "subscription_confirmed": True,
        "rest_snapshot_confirmed": True,
    }
    values.update(changes)
    return ExchangeSnapshot.model_validate(values)


class _BlockingAdapter:
    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()
        self.calls = 0
        self._lock = Lock()

    def reconcile(self, mode: TradingMode) -> ExchangeSnapshot:
        with self._lock:
            self.calls += 1
        self.entered.set()
        if not self.release.wait(timeout=2):
            raise TimeoutError("test adapter release timed out")
        return _snapshot(mode)


def test_stale_snapshot_refresh_is_nonblocking_and_single_flight() -> None:
    snapshots = {"testnet": _snapshot(reconciled_at=NOW - timedelta(minutes=5))}
    adapter = _BlockingAdapter()
    coordinator = ReconciliationCoordinator(
        adapter=adapter,
        load_snapshot=lambda mode: snapshots.get(mode),
        save_snapshot=lambda snapshot: snapshots.__setitem__(snapshot.mode, snapshot),
        maximum_snapshot_age_seconds=30,
        clock=lambda: NOW,
        maximum_attempts=1,
    )

    started = time.perf_counter()
    first = coordinator.status("testnet", request_refresh=True)
    second = coordinator.status("testnet", request_refresh=True)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.2
    assert adapter.entered.wait(timeout=1)
    assert adapter.calls == 1
    assert first.ready is False
    assert first.state == "refreshing"
    assert "reconciliation_snapshot_stale" in first.reason_codes
    assert "reconciliation_refreshing" in first.reason_codes
    assert second.refresh_in_progress is True

    adapter.release.set()
    deadline = time.monotonic() + 1
    while (
        coordinator.status("testnet").refresh_in_progress
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    ready = coordinator.status("testnet")
    coordinator.close()

    assert ready.ready is True
    assert ready.reason_codes == ()
    assert ready.snapshot_age_seconds == 0


def test_retry_backoff_recovers_temporary_failure() -> None:
    snapshots: dict[TradingMode, ExchangeSnapshot] = {}
    attempts = 0
    delays: list[float] = []

    class Adapter:
        def reconcile(self, mode: TradingMode) -> ExchangeSnapshot:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ConnectionError("temporary network failure")
            return _snapshot(mode)

    coordinator = ReconciliationCoordinator(
        adapter=Adapter(),
        load_snapshot=lambda mode: snapshots.get(mode),
        save_snapshot=lambda snapshot: snapshots.__setitem__(snapshot.mode, snapshot),
        clock=lambda: NOW,
        sleep=delays.append,
        maximum_attempts=3,
        initial_backoff_seconds=0.25,
    )

    readiness = coordinator.request("live", wait=True, force=True)
    coordinator.close()

    assert readiness.ready is True
    assert readiness.attempt_count == 3
    assert attempts == 3
    assert delays == [0.25, 0.5]


def test_timeout_is_structured_while_refresh_continues() -> None:
    snapshots: dict[TradingMode, ExchangeSnapshot] = {}
    adapter = _BlockingAdapter()
    coordinator = ReconciliationCoordinator(
        adapter=adapter,
        load_snapshot=lambda mode: snapshots.get(mode),
        save_snapshot=lambda snapshot: snapshots.__setitem__(snapshot.mode, snapshot),
        clock=lambda: NOW,
        request_timeout_seconds=0.01,
        maximum_attempts=1,
    )

    readiness = coordinator.request("testnet", wait=True, force=True)

    assert readiness.ready is False
    assert readiness.refresh_in_progress is True
    assert readiness.failure_code == "reconciliation_timeout"
    assert "reconciliation_timeout" in readiness.reason_codes
    assert "reconciliation_snapshot_missing" in readiness.reason_codes

    adapter.release.set()
    coordinator.close()


def test_readiness_preserves_specific_snapshot_reason_codes() -> None:
    snapshot = _snapshot(
        unmanaged_state=True,
        one_way_confirmed=False,
        cross_margin_confirmed=False,
        risk_ready=False,
        daily_baseline_ready=False,
        protection_ready=False,
        subscription_confirmed=False,
        rest_snapshot_confirmed=False,
    )
    coordinator = ReconciliationCoordinator(
        adapter=_BlockingAdapter(),
        load_snapshot=lambda mode: snapshot,
        save_snapshot=lambda value: None,
        clock=lambda: NOW,
    )

    readiness = coordinator.status("testnet")
    coordinator.close()

    assert readiness.ready is False
    assert set(readiness.reason_codes) == {
        "unmanaged_exchange_state",
        "one_way_not_confirmed",
        "cross_margin_not_confirmed",
        "risk_data_unavailable",
        "daily_baseline_missing",
        "protection_not_ready",
        "private_stream_not_ready",
        "rest_snapshot_not_ready",
        "reconciliation_not_ready",
    }
