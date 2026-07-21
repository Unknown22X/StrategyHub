"""Bounded, single-flight background reconciliation for Gate account snapshots."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from datetime import UTC, datetime
import time
from threading import RLock
from typing import Protocol

from rangebot.domain.exchange import ExchangeSnapshot, TradingMode
from rangebot.domain.reconciliation import ReconciliationReadiness


class ReconciliationAdapter(Protocol):
    def reconcile(self, mode: TradingMode) -> ExchangeSnapshot: ...


SnapshotLoader = Callable[[TradingMode], ExchangeSnapshot | None]
SnapshotSaver = Callable[[ExchangeSnapshot], None]
Clock = Callable[[], datetime]
Sleep = Callable[[float], None]
ActiveModeProvider = Callable[[], TradingMode | None]


@dataclass
class _ModeRunState:
    future: Future[ExchangeSnapshot] | None = None
    generation: int = 0
    current_forced: bool = False
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    attempt_count: int = 0
    failure_code: str | None = None
    message_ar: str | None = None


class ReconciliationCoordinator:
    """Refresh account state without putting network reconciliation on Preview latency."""

    def __init__(
        self,
        *,
        adapter: ReconciliationAdapter,
        load_snapshot: SnapshotLoader,
        save_snapshot: SnapshotSaver,
        maximum_snapshot_age_seconds: float = 30.0,
        request_timeout_seconds: float = 8.0,
        maximum_attempts: int = 3,
        initial_backoff_seconds: float = 0.25,
        clock: Clock | None = None,
        sleep: Sleep = time.sleep,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        if maximum_snapshot_age_seconds <= 0:
            raise ValueError("Snapshot freshness window must be positive.")
        if request_timeout_seconds <= 0:
            raise ValueError("Reconciliation timeout must be positive.")
        if maximum_attempts < 1:
            raise ValueError("Reconciliation attempts must be at least one.")
        self._adapter = adapter
        self._load_snapshot = load_snapshot
        self._save_snapshot = save_snapshot
        self._maximum_age = maximum_snapshot_age_seconds
        self._request_timeout = request_timeout_seconds
        self._maximum_attempts = maximum_attempts
        self._initial_backoff = initial_backoff_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleep = sleep
        self._executor = executor or ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="rangebot-reconcile",
        )
        self._owns_executor = executor is None
        self._lock = RLock()
        self._states: dict[TradingMode, _ModeRunState] = {
            "testnet": _ModeRunState(),
            "live": _ModeRunState(),
        }

    def status(
        self,
        mode: TradingMode,
        *,
        request_refresh: bool = False,
        wait_for_refresh: bool = False,
        force_refresh: bool = False,
    ) -> ReconciliationReadiness:
        if request_refresh:
            self.request(
                mode,
                wait=wait_for_refresh,
                force=force_refresh,
            )
        return self._readiness(mode)

    def request(
        self,
        mode: TradingMode,
        *,
        wait: bool = False,
        force: bool = False,
    ) -> ReconciliationReadiness:
        target_generation: int | None = None
        with self._lock:
            state = self._states[mode]
            current = state.future
            if current is None or current.done():
                snapshot = self._load_snapshot(mode)
                if not force and self._snapshot_is_fresh(snapshot):
                    return self._readiness(mode)
                self._start_locked(mode, state, forced=force)
                current = state.future
            elif force and wait and not state.current_forced:
                # A manual forced refresh must observe state that existed after the
                # caller requested it. Joining an older background flight is not
                # sufficient because ownership or protection may have changed while
                # that flight was already running. Concurrent forced callers share
                # the same one-generation follow-up.
                target_generation = state.generation + 1
        if wait and current is not None:
            if not self._wait_for_future(mode, current):
                return self._readiness(mode)
        if target_generation is not None:
            with self._lock:
                state = self._states[mode]
                current = state.future
                if state.generation < target_generation and (
                    current is None or current.done()
                ):
                    self._start_locked(mode, state, forced=True)
                    current = state.future
            if wait and current is not None:
                self._wait_for_future(mode, current)
        return self._readiness(mode)

    def _start_locked(
        self,
        mode: TradingMode,
        state: _ModeRunState,
        *,
        forced: bool,
    ) -> None:
        state.generation += 1
        state.current_forced = forced
        state.last_attempt_at = self._clock()
        state.failure_code = None
        state.message_ar = None
        state.future = self._executor.submit(self._run, mode)

    def _wait_for_future(
        self,
        mode: TradingMode,
        future: Future[ExchangeSnapshot],
    ) -> bool:
        try:
            future.result(timeout=self._request_timeout)
            return True
        except FutureTimeout:
            with self._lock:
                state = self._states[mode]
                state.failure_code = "reconciliation_timeout"
                state.message_ar = "انتهت مهلة المصالحة؛ تستمر المحاولة في الخلفية."
            return False
        except Exception:
            # _run records a sanitized failure state.
            return True

    async def run(
        self,
        stop_event: asyncio.Event,
        active_mode: ActiveModeProvider,
        *,
        interval_seconds: float = 10.0,
    ) -> None:
        while not stop_event.is_set():
            mode = active_mode()
            if mode is not None:
                self.request(mode)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            except TimeoutError:
                continue

    def close(self) -> None:
        if self._owns_executor:
            self._executor.shutdown(wait=False, cancel_futures=True)

    def _run(self, mode: TradingMode) -> ExchangeSnapshot:
        delay = self._initial_backoff
        last_error: Exception | None = None
        for attempt in range(1, self._maximum_attempts + 1):
            with self._lock:
                state = self._states[mode]
                state.attempt_count = attempt
                state.last_attempt_at = self._clock()
            try:
                snapshot = self._adapter.reconcile(mode)
                if snapshot.mode != mode:
                    raise RuntimeError("adapter_mode_mismatch")
                if snapshot.reconciliation_error:
                    raise RuntimeError("reconciliation_failed")
                self._save_snapshot(snapshot)
                with self._lock:
                    state = self._states[mode]
                    state.last_success_at = snapshot.reconciled_at
                    state.failure_code = None
                    state.message_ar = None
                return snapshot
            except Exception as error:
                last_error = error
                if attempt < self._maximum_attempts:
                    self._sleep(delay)
                    delay *= 2
        code = self._failure_code(last_error)
        with self._lock:
            state = self._states[mode]
            state.failure_code = code
            state.message_ar = self._failure_message(code)
        raise RuntimeError(code) from last_error

    def _readiness(self, mode: TradingMode) -> ReconciliationReadiness:
        snapshot = self._load_snapshot(mode)
        now = self._clock()
        age = self._snapshot_age(snapshot, now)
        with self._lock:
            state = self._states[mode]
            refreshing = state.future is not None and not state.future.done()
            failure_code = state.failure_code
            message_ar = state.message_ar
            last_attempt_at = state.last_attempt_at
            last_success_at = state.last_success_at
            attempt_count = state.attempt_count

        reason_codes: list[str] = []
        readiness_state = "ready"
        if snapshot is None:
            readiness_state = "refreshing" if refreshing else "missing"
            reason_codes.append("reconciliation_snapshot_missing")
        elif age is None or age > self._maximum_age:
            readiness_state = "refreshing" if refreshing else "stale"
            reason_codes.append("reconciliation_snapshot_stale")
        elif snapshot.reconciliation_error:
            readiness_state = "failed"
            reason_codes.append("reconciliation_failed")
        else:
            self._snapshot_reason_codes(snapshot, reason_codes)
            if reason_codes:
                readiness_state = "failed"

        if failure_code and readiness_state != "ready":
            reason_codes.append(failure_code)
            readiness_state = "failed" if not refreshing else readiness_state
        if refreshing and readiness_state != "ready":
            reason_codes.append("reconciliation_refreshing")
        if reason_codes:
            reason_codes.append("reconciliation_not_ready")
        deduplicated = tuple(dict.fromkeys(reason_codes))
        ready = not deduplicated
        return ReconciliationReadiness(
            mode=mode,
            state="ready" if ready else readiness_state,
            ready=ready,
            refresh_in_progress=refreshing,
            snapshot_age_seconds=age,
            maximum_snapshot_age_seconds=self._maximum_age,
            last_attempt_at=last_attempt_at,
            last_success_at=last_success_at,
            attempt_count=attempt_count,
            failure_code=failure_code,
            message_ar=message_ar,
            reason_codes=deduplicated,
            snapshot=snapshot,
        )

    def _snapshot_is_fresh(self, snapshot: ExchangeSnapshot | None) -> bool:
        age = self._snapshot_age(snapshot, self._clock())
        return age is not None and age <= self._maximum_age

    @staticmethod
    def _snapshot_age(
        snapshot: ExchangeSnapshot | None,
        now: datetime,
    ) -> float | None:
        if snapshot is None:
            return None
        reconciled_at = snapshot.reconciled_at
        if reconciled_at.tzinfo is None:
            reconciled_at = reconciled_at.replace(tzinfo=UTC)
        return max(
            0.0, (now.astimezone(UTC) - reconciled_at.astimezone(UTC)).total_seconds()
        )

    @staticmethod
    def _snapshot_reason_codes(
        snapshot: ExchangeSnapshot,
        reason_codes: list[str],
    ) -> None:
        if snapshot.unmanaged_state:
            reason_codes.append("unmanaged_exchange_state")
        if not snapshot.one_way_confirmed:
            reason_codes.append("one_way_not_confirmed")
        if not snapshot.cross_margin_confirmed:
            reason_codes.append("cross_margin_not_confirmed")
        if not snapshot.risk_ready:
            reason_codes.append("risk_data_unavailable")
        if not snapshot.protection_ready:
            reason_codes.append("protection_not_ready")
        if not snapshot.subscription_confirmed:
            reason_codes.append("private_stream_not_ready")
        if not snapshot.rest_snapshot_confirmed:
            reason_codes.append("rest_snapshot_not_ready")

    @staticmethod
    def _failure_code(error: Exception | None) -> str:
        text = str(error or "").casefold()
        if "adapter_mode_mismatch" in text:
            return "adapter_mode_mismatch"
        if "credential" in text or "auth" in text:
            return "credentials_invalid"
        if "timeout" in text:
            return "reconciliation_timeout"
        return "reconciliation_failed"

    @staticmethod
    def _failure_message(code: str) -> str:
        return {
            "adapter_mode_mismatch": "بيئة Gate.io لا تطابق بيئة المصالحة المطلوبة.",
            "credentials_invalid": "تعذر التحقق من بيانات Gate.io المحفوظة.",
            "reconciliation_timeout": "انتهت مهلة المصالحة مع Gate.io.",
            "reconciliation_failed": "تعذرت المصالحة مع Gate.io حالياً.",
        }[code]
