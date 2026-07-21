"""Runtime-refreshing Gate adapter for protected credential replacement/removal."""

from __future__ import annotations

from dataclasses import astuple
import hashlib
from threading import RLock
from typing import Callable

from rangebot.domain.exchange import (
    ExchangeEntryRequest,
    ExchangeOperationResult,
    ExchangeSnapshot,
    ExchangeTrailingStopRequest,
    MarketEntryGuardRequest,
    MarketGuardQuoteRequest,
    TradingMode,
)
from rangebot.domain.trades import TradeFillCreate
from rangebot.engine.credentials import StoredGateCredentials, load_gate_credentials
from rangebot.engine.exchange import (
    GateIoAdapter,
    GateIoConfiguration,
    UnavailableGateIoAdapter,
    configured_gate_adapter,
)


CredentialsProvider = Callable[[TradingMode], StoredGateCredentials | None]
AdapterFactory = Callable[[TradingMode], GateIoAdapter]


def effective_gate_credentials(mode: TradingMode) -> StoredGateCredentials | None:
    """Load environment or DPAPI credentials without exposing them to API/UI models."""
    try:
        configuration = GateIoConfiguration.from_environment(mode)
    except ValueError:
        return load_gate_credentials(mode)
    return StoredGateCredentials(configuration.key, configuration.secret)


class CredentialReloadingGateIoAdapter:
    """Keep one adapter while credentials are unchanged and replace it atomically."""

    def __init__(
        self,
        mode: TradingMode,
        *,
        enable_network: bool,
        enable_order_submission: bool,
        credentials_provider: CredentialsProvider = effective_gate_credentials,
        adapter_factory: AdapterFactory | None = None,
    ) -> None:
        self._mode = mode
        self._credentials_provider = credentials_provider
        self._adapter_factory = adapter_factory or (
            lambda active_mode: configured_gate_adapter(
                active_mode,
                enable_network=enable_network,
                enable_order_submission=enable_order_submission,
            )
        )
        self._lock = RLock()
        self._fingerprint: bytes | None | object = object()
        self._adapter: GateIoAdapter = UnavailableGateIoAdapter()

    def reconcile(self, mode: TradingMode) -> ExchangeSnapshot:
        return self._delegate(mode).reconcile(mode)

    def submit_entry(
        self, mode: TradingMode, request: ExchangeEntryRequest
    ) -> ExchangeOperationResult:
        return self._delegate(mode).submit_entry(mode, request)

    def cancel_managed_entry(self, mode: TradingMode) -> ExchangeOperationResult:
        return self._delegate(mode).cancel_managed_entry(mode)

    def close_managed_position(self, mode: TradingMode) -> ExchangeOperationResult:
        return self._delegate(mode).close_managed_position(mode)

    def ensure_protection(self, mode: TradingMode) -> ExchangeOperationResult:
        return self._delegate(mode).ensure_protection(mode)

    def ensure_trailing_protection(
        self, mode: TradingMode, request: ExchangeTrailingStopRequest
    ) -> ExchangeOperationResult:
        return self._delegate(mode).ensure_trailing_protection(mode, request)

    def cancel_trailing_protection(
        self, mode: TradingMode, order_id: str
    ) -> ExchangeOperationResult:
        return self._delegate(mode).cancel_trailing_protection(mode, order_id)

    def market_guard_quote(
        self, mode: TradingMode, request: MarketGuardQuoteRequest
    ) -> MarketEntryGuardRequest:
        return self._delegate(mode).market_guard_quote(mode, request)

    def set_protection_enabled(
        self, mode: TradingMode, protection: str, enabled: bool
    ) -> ExchangeOperationResult:
        return self._delegate(mode).set_protection_enabled(mode, protection, enabled)

    def recent_trade_fills(self, mode: TradingMode) -> tuple[TradeFillCreate, ...]:
        delegate = self._delegate(mode)
        loader = getattr(delegate, "recent_trade_fills", None)
        return tuple(loader(mode)) if callable(loader) else ()

    def _delegate(self, mode: TradingMode) -> GateIoAdapter:
        if mode != self._mode:
            raise ValueError(
                f"Credential adapter is configured for {self._mode}, not {mode}."
            )
        current = self._credentials_provider(mode)
        fingerprint = _fingerprint(current)
        with self._lock:
            if fingerprint != self._fingerprint:
                self._adapter = (
                    UnavailableGateIoAdapter()
                    if current is None
                    else self._adapter_factory(mode)
                )
                self._fingerprint = fingerprint
            return self._adapter


def _fingerprint(credentials: StoredGateCredentials | None) -> bytes | None:
    if credentials is None:
        return None
    digest = hashlib.sha256()
    for value in astuple(credentials):
        digest.update(value.encode("utf-8"))
        digest.update(b"\0")
    return digest.digest()
