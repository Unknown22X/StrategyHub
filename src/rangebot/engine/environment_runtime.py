"""Atomic runtime ownership for Paper, Testnet, and Live components."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol, cast

from rangebot.domain.environment import (
    ApplicationEnvironment,
    EnvironmentRuntimeState,
    EnvironmentTransitionState,
)
from rangebot.domain.exchange import (
    ExchangeEntryRequest,
    ExchangeOperationResult,
    ExchangeSnapshot,
    ExchangeTrailingStopRequest,
    MarketEntryGuardRequest,
    MarketGuardQuoteRequest,
    TradingMode,
)
from rangebot.domain.private_stream import PrivateStreamState
from rangebot.domain.trades import TradeFillCreate
from rangebot.engine.exchange import GateIoAdapter, UnavailableGateIoAdapter
from rangebot.engine.gate_private_websocket import PrivateStreamStateStore


class AsyncEnvironmentService(Protocol):
    async def run(self, stop_event: asyncio.Event) -> None: ...


AdapterFactory = Callable[[TradingMode], GateIoAdapter]
PublicServiceFactory = Callable[[TradingMode], AsyncEnvironmentService | None]
PrivateServiceFactory = Callable[
    [TradingMode, GateIoAdapter, PrivateStreamStateStore],
    AsyncEnvironmentService | None,
]
SnapshotCallback = Callable[[ExchangeSnapshot], None]
InvalidateCallback = Callable[[TradingMode], None]
MarketResetCallback = Callable[[], None]
PublicRestActivationCallback = Callable[[ApplicationEnvironment], None]


class EnvironmentTransitionError(RuntimeError):
    """A sanitized transition failure that is safe to return through the API."""

    def __init__(
        self,
        code: str,
        message_ar: str,
        *,
        restart_required: bool = False,
    ) -> None:
        super().__init__(message_ar)
        self.code = code
        self.message_ar = message_ar
        self.restart_required = restart_required


class EnvironmentRuntimeManager:
    """Own the active adapter and WebSocket services as one atomic environment."""

    def __init__(
        self,
        *,
        initial_environment: ApplicationEnvironment,
        initial_adapter: GateIoAdapter | None = None,
        strict_adapter_mode: TradingMode | None = None,
        adapter_factory: AdapterFactory | None = None,
        initial_public_service: AsyncEnvironmentService | None = None,
        public_service_factory: PublicServiceFactory | None = None,
        initial_private_service: AsyncEnvironmentService | None = None,
        private_service_factory: PrivateServiceFactory | None = None,
        initial_private_state_store: PrivateStreamStateStore | None = None,
        persist_snapshot: SnapshotCallback | None = None,
        invalidate_snapshot: InvalidateCallback | None = None,
        reset_market_data: MarketResetCallback | None = None,
        activate_public_rest: PublicRestActivationCallback | None = None,
    ) -> None:
        self._state_lock = RLock()
        self._transition_lock = asyncio.Lock()
        self._active_environment = initial_environment
        self._requested_environment = initial_environment
        self._adapter_factory = adapter_factory
        self._strict_mode = (
            strict_adapter_mode is not None or adapter_factory is not None
        )
        self._adapter_mode = strict_adapter_mode
        if (
            self._adapter_mode is None
            and adapter_factory is not None
            and initial_environment != "paper"
        ):
            self._adapter_mode = cast(TradingMode, initial_environment)
        self._adapter = initial_adapter or UnavailableGateIoAdapter()
        self._public_service_factory = public_service_factory
        self._private_service_factory = private_service_factory
        self._public_service = initial_public_service
        self._private_service = initial_private_service
        self._private_state_store = (
            initial_private_state_store or PrivateStreamStateStore(self._adapter_mode)
        )
        self._public_environment = (
            self._public_market_environment(initial_environment)
            if initial_public_service is not None
            else None
        )
        self._private_environment = (
            self._adapter_mode if initial_private_service is not None else None
        )
        self._persist_snapshot = persist_snapshot or (lambda snapshot: None)
        self._invalidate_snapshot = invalidate_snapshot or (lambda mode: None)
        self._reset_market_data = reset_market_data or (lambda: None)
        self._activate_public_rest = activate_public_rest or (lambda environment: None)
        self._public_rest_environment = self._public_market_environment(
            initial_environment
        )
        self._public_stop: asyncio.Event | None = None
        self._private_stop: asyncio.Event | None = None
        self._public_task: asyncio.Task[None] | None = None
        self._private_task: asyncio.Task[None] | None = None
        self._started = False
        self._transition_state = "ready"
        self._transition_started_at: datetime | None = None
        self._transition_completed_at: datetime | None = datetime.now(UTC)
        self._failure_code: str | None = None
        self._message_ar: str | None = None
        self._restart_required = False
        self._revision = 1

    @property
    def active_environment(self) -> ApplicationEnvironment:
        with self._state_lock:
            return self._active_environment

    @property
    def active_adapter_mode(self) -> TradingMode | None:
        with self._state_lock:
            return self._adapter_mode

    @property
    def current_adapter(self) -> GateIoAdapter:
        with self._state_lock:
            return self._adapter

    @property
    def strict_mode(self) -> bool:
        return self._strict_mode

    @property
    def transition_state(self) -> EnvironmentTransitionState:
        with self._state_lock:
            return self._transition_state

    def adapter_for(self, mode: TradingMode) -> GateIoAdapter:
        with self._state_lock:
            if self._transition_state == "switching":
                raise EnvironmentTransitionError(
                    "environment_switching",
                    "جارٍ تبديل بيئة RangeBot. انتظر حتى تكتمل العملية.",
                )
            if self._strict_mode and self._adapter_mode != mode:
                raise EnvironmentTransitionError(
                    "adapter_mode_mismatch",
                    "بيئة الواجهة لا تطابق وضع محرك Gate.io الفعلي.",
                )
            return self._adapter

    def private_stream_state(self) -> PrivateStreamState:
        with self._state_lock:
            return self._private_state_store.snapshot()

    def request_private_reconnect(self) -> None:
        with self._state_lock:
            service = self._private_service
        reconnect = getattr(service, "request_reconnect", None)
        if callable(reconnect):
            reconnect()

    def snapshot(
        self, configured_environment: ApplicationEnvironment
    ) -> EnvironmentRuntimeState:
        with self._state_lock:
            transition_state = self._transition_state
            adapter_matches = (
                self._active_environment == "paper" and self._adapter_mode is None
            ) or self._adapter_mode == self._active_environment
            public_rest_matches = (
                self._public_rest_environment
                == self._public_market_environment(self._active_environment)
            )
            activated = (
                transition_state == "ready"
                and self._requested_environment == self._active_environment
                and configured_environment == self._active_environment
                and adapter_matches
                and public_rest_matches
            )
            if transition_state == "ready" and not activated:
                transition_state = "mismatch"
            return EnvironmentRuntimeState(
                configured_environment=configured_environment,
                requested_environment=self._requested_environment,
                active_engine_environment=self._active_environment,
                exchange_adapter_environment=self._adapter_mode,
                public_rest_environment=self._public_rest_environment,
                public_websocket_environment=self._public_environment,
                private_websocket_environment=self._private_environment,
                credential_profile=self._adapter_mode,
                transition_state=transition_state,
                restart_required=self._restart_required,
                activated=activated,
                transition_started_at=self._transition_started_at,
                transition_completed_at=self._transition_completed_at,
                failure_code=self._failure_code,
                message_ar=self._message_ar,
                revision=self._revision,
            )

    async def start(self) -> None:
        async with self._transition_lock:
            if self._started:
                return
            self._started = True
            await self._start_services()

    async def stop(self) -> None:
        async with self._transition_lock:
            await self._stop_services()
            self._started = False

    async def switch(
        self,
        target: ApplicationEnvironment,
        *,
        confirmation: str = "",
    ) -> None:
        async with self._transition_lock:
            previous_environment = self._active_environment
            previous_adapter = self._adapter
            previous_adapter_mode = self._adapter_mode
            if target == "live" and confirmation != "SWITCH TO LIVE":
                raise EnvironmentTransitionError(
                    "live_confirmation_required",
                    "تفعيل Live يستخدم أموالاً حقيقية. أدخل SWITCH TO LIVE للتأكيد.",
                )
            target_components_match = (
                (target == "paper" and self._adapter_mode is None)
                or self._adapter_mode == target
            ) and self._public_rest_environment == self._public_market_environment(
                target
            )
            if (
                target == previous_environment
                and self._transition_state == "ready"
                and target_components_match
            ):
                with self._state_lock:
                    self._requested_environment = target
                    self._failure_code = None
                    self._message_ar = None
                    self._restart_required = False
                    self._revision += 1
                return
            if target != "paper" and self._adapter_factory is None:
                target_mode = cast(TradingMode, target)
                if self._adapter_mode != target_mode:
                    with self._state_lock:
                        self._requested_environment = target
                        self._transition_state = "restart_required"
                        self._restart_required = True
                        self._failure_code = "restart_required"
                        self._message_ar = (
                            "يلزم إعادة تشغيل محرك RangeBot بالبيئة المطلوبة."
                        )
                        self._transition_started_at = datetime.now(UTC)
                        self._transition_completed_at = None
                        self._revision += 1
                    raise EnvironmentTransitionError(
                        "restart_required",
                        "يلزم إعادة تشغيل محرك RangeBot بالبيئة المطلوبة.",
                        restart_required=True,
                    )

            with self._state_lock:
                self._requested_environment = target
                self._transition_state = "switching"
                self._restart_required = False
                self._failure_code = None
                self._message_ar = f"جارٍ تبديل RangeBot إلى {target.upper()}..."
                self._transition_started_at = datetime.now(UTC)
                self._transition_completed_at = None
                self._revision += 1

            try:
                await self._stop_services()
                await asyncio.to_thread(
                    self._invalidate_for_transition, previous_environment, target
                )
                await asyncio.to_thread(self._reset_market_data)
                await asyncio.to_thread(self._activate_public_rest, target)
                target_adapter, target_mode = self._build_adapter(target)
                if target_mode is not None:
                    snapshot = await asyncio.to_thread(
                        target_adapter.reconcile, target_mode
                    )
                    if snapshot.mode != target_mode:
                        raise EnvironmentTransitionError(
                            "adapter_mode_mismatch",
                            "محرك Gate.io أعاد لقطة من بيئة مختلفة عن البيئة المطلوبة.",
                        )
                    if snapshot.reconciliation_error:
                        raise EnvironmentTransitionError(
                            "reconciliation_failed",
                            "تعذر تفعيل البيئة لأن المصالحة مع Gate.io لم تنجح.",
                        )
                    await asyncio.to_thread(self._persist_snapshot, snapshot)
                with self._state_lock:
                    self._adapter = target_adapter
                    self._adapter_mode = target_mode
                    self._active_environment = target
                    self._public_rest_environment = self._public_market_environment(
                        target
                    )
                    self._private_state_store = PrivateStreamStateStore(target_mode)
                    self._public_service = None
                    self._private_service = None
                if self._started:
                    await self._start_services()
                with self._state_lock:
                    self._transition_state = "ready"
                    self._failure_code = None
                    self._message_ar = None
                    self._transition_completed_at = datetime.now(UTC)
                    self._revision += 1
            except Exception as error:
                await self._stop_services()
                rollback_ok = await self._rollback(
                    previous_environment,
                    previous_adapter,
                    previous_adapter_mode,
                )
                transition_error = self._public_error(error)
                with self._state_lock:
                    self._transition_state = "failed" if rollback_ok else "mismatch"
                    self._failure_code = transition_error.code
                    self._message_ar = transition_error.message_ar
                    self._restart_required = transition_error.restart_required
                    self._transition_completed_at = datetime.now(UTC)
                    self._revision += 1
                raise transition_error from error

    def _build_adapter(
        self, environment: ApplicationEnvironment
    ) -> tuple[GateIoAdapter, TradingMode | None]:
        if environment == "paper":
            return UnavailableGateIoAdapter(), None
        mode = cast(TradingMode, environment)
        if self._adapter_factory is None:
            return self._adapter, mode
        return self._adapter_factory(mode), mode

    async def _rollback(
        self,
        environment: ApplicationEnvironment,
        adapter: GateIoAdapter,
        adapter_mode: TradingMode | None,
    ) -> bool:
        try:
            await asyncio.to_thread(self._activate_public_rest, environment)
            with self._state_lock:
                self._active_environment = environment
                self._adapter = adapter
                self._adapter_mode = adapter_mode
                self._public_rest_environment = self._public_market_environment(
                    environment
                )
                self._private_state_store = PrivateStreamStateStore(adapter_mode)
                self._public_service = None
                self._private_service = None
            if adapter_mode is not None:
                snapshot = await asyncio.to_thread(adapter.reconcile, adapter_mode)
                if snapshot.mode != adapter_mode or snapshot.reconciliation_error:
                    return False
                await asyncio.to_thread(self._persist_snapshot, snapshot)
            if self._started:
                await self._start_services()
            return True
        except Exception:
            with self._state_lock:
                self._adapter = UnavailableGateIoAdapter()
                self._adapter_mode = None
                self._public_environment = None
                self._private_environment = None
            return False

    async def _start_services(self) -> None:
        with self._state_lock:
            environment = self._active_environment
            adapter = self._adapter
            adapter_mode = self._adapter_mode
            public_service = self._public_service
            private_service = self._private_service
            if public_service is None and self._public_service_factory is not None:
                public_mode = self._public_market_environment(environment)
                public_service = self._public_service_factory(public_mode)
                self._public_service = public_service
            if (
                private_service is None
                and adapter_mode is not None
                and self._private_service_factory is not None
            ):
                private_service = self._private_service_factory(
                    adapter_mode, adapter, self._private_state_store
                )
                self._private_service = private_service
            self._public_environment = (
                self._public_market_environment(environment)
                if public_service is not None
                else None
            )
            self._private_environment = (
                adapter_mode if private_service is not None else None
            )
            if public_service is not None:
                self._public_stop = asyncio.Event()
                self._public_task = asyncio.create_task(
                    public_service.run(self._public_stop)
                )
            if private_service is not None:
                self._private_stop = asyncio.Event()
                self._private_task = asyncio.create_task(
                    private_service.run(self._private_stop)
                )

    async def _stop_services(self) -> None:
        with self._state_lock:
            public_stop = self._public_stop
            private_stop = self._private_stop
            public_task = self._public_task
            private_task = self._private_task
            self._public_stop = None
            self._private_stop = None
            self._public_task = None
            self._private_task = None
            self._public_environment = None
            self._private_environment = None
        if public_stop is not None:
            public_stop.set()
        if private_stop is not None:
            private_stop.set()
        for task in (public_task, private_task):
            if task is None:
                continue
            try:
                await task
            except asyncio.CancelledError:
                raise
            except Exception:
                # Transport failures are reflected by the service status stores.
                continue

    def _invalidate_for_transition(
        self,
        previous: ApplicationEnvironment,
        target: ApplicationEnvironment,
    ) -> None:
        modes: list[TradingMode] = []
        for environment in (previous, target):
            if environment == "paper":
                continue
            mode = cast(TradingMode, environment)
            if mode not in modes:
                modes.append(mode)
        for mode in modes:
            self._invalidate_snapshot(mode)

    @staticmethod
    def _public_market_environment(
        environment: ApplicationEnvironment,
    ) -> TradingMode:
        # Paper intentionally uses public Live prices but never Live credentials or account state.
        return "testnet" if environment == "testnet" else "live"

    @staticmethod
    def _public_error(error: Exception) -> EnvironmentTransitionError:
        if isinstance(error, EnvironmentTransitionError):
            return error
        return EnvironmentTransitionError(
            "environment_transition_failed",
            "تعذر تبديل بيئة RangeBot. بقي التداول محظوراً حتى مراجعة الحالة.",
        )


class EnvironmentBoundGateIoAdapter:
    """Delegate every exchange operation only to the authoritative active adapter."""

    def __init__(self, runtime: EnvironmentRuntimeManager) -> None:
        self._runtime = runtime

    def reconcile(self, mode: TradingMode) -> ExchangeSnapshot:
        return self._runtime.adapter_for(mode).reconcile(mode)

    def submit_entry(
        self, mode: TradingMode, request: ExchangeEntryRequest
    ) -> ExchangeOperationResult:
        return self._runtime.adapter_for(mode).submit_entry(mode, request)

    def cancel_managed_entry(self, mode: TradingMode) -> ExchangeOperationResult:
        return self._runtime.adapter_for(mode).cancel_managed_entry(mode)

    def close_managed_position(self, mode: TradingMode) -> ExchangeOperationResult:
        return self._runtime.adapter_for(mode).close_managed_position(mode)

    def ensure_protection(self, mode: TradingMode) -> ExchangeOperationResult:
        return self._runtime.adapter_for(mode).ensure_protection(mode)

    def ensure_trailing_protection(
        self, mode: TradingMode, request: ExchangeTrailingStopRequest
    ) -> ExchangeOperationResult:
        return self._runtime.adapter_for(mode).ensure_trailing_protection(mode, request)

    def cancel_trailing_protection(
        self, mode: TradingMode, order_id: str
    ) -> ExchangeOperationResult:
        return self._runtime.adapter_for(mode).cancel_trailing_protection(
            mode, order_id
        )

    def market_guard_quote(
        self, mode: TradingMode, request: MarketGuardQuoteRequest
    ) -> MarketEntryGuardRequest:
        return self._runtime.adapter_for(mode).market_guard_quote(mode, request)

    def set_protection_enabled(
        self, mode: TradingMode, protection: str, enabled: bool
    ) -> ExchangeOperationResult:
        return self._runtime.adapter_for(mode).set_protection_enabled(
            mode, protection, enabled
        )

    def recent_trade_fills(self, mode: TradingMode) -> tuple[TradeFillCreate, ...]:
        delegate = self._runtime.adapter_for(mode)
        loader = getattr(delegate, "recent_trade_fills", None)
        return tuple(loader(mode)) if callable(loader) else ()
