"""Authoritative public Gate REST providers for Paper, Testnet, and Live."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from threading import RLock
from typing import Literal

from rangebot.domain.discovery import DiscoveryMarketContract
from rangebot.domain.environment import ApplicationEnvironment
from rangebot.domain.market import PublicContract, PublicMarketSnapshot
from rangebot.domain.orders import FuturesContractRules
from rangebot.domain.strategy_runtime import NormalizedCandle
from rangebot.engine.contract_rules import GateContractRulesProvider
from rangebot.engine.historical_market_data import GateHistoricalMarketDataProvider
from rangebot.engine.market import GatePublicMarketProvider


PublicRestEnvironment = Literal["live", "testnet"]
PAPER_PUBLIC_MARKET_POLICY: PublicRestEnvironment = "live"
PublicMarketFactory = Callable[[PublicRestEnvironment], GatePublicMarketProvider]
ContractRulesFactory = Callable[[PublicRestEnvironment], GateContractRulesProvider]
HistoricalFactory = Callable[[PublicRestEnvironment], GateHistoricalMarketDataProvider]


def public_rest_environment(
    environment: ApplicationEnvironment,
) -> PublicRestEnvironment:
    """Paper uses public Live market data but never Live credentials or account state."""
    return "testnet" if environment == "testnet" else PAPER_PUBLIC_MARKET_POLICY


class PublicRestEnvironmentManager:
    """Rebuild all public REST providers atomically when the app environment changes."""

    def __init__(
        self,
        initial_environment: ApplicationEnvironment,
        *,
        public_market_factory: PublicMarketFactory | None = None,
        contract_rules_factory: ContractRulesFactory | None = None,
        historical_factory: HistoricalFactory | None = None,
    ) -> None:
        self._lock = RLock()
        self._public_market_factory = public_market_factory or (
            lambda environment: GatePublicMarketProvider(environment=environment)
        )
        self._contract_rules_factory = contract_rules_factory or (
            lambda environment: GateContractRulesProvider(environment=environment)
        )
        self._historical_factory = historical_factory or (
            lambda environment: GateHistoricalMarketDataProvider(environment)
        )
        self._application_environment = initial_environment
        self._effective_environment = public_rest_environment(initial_environment)
        (
            self._public_market,
            self._contract_rules,
            self._historical,
        ) = self._build(self._effective_environment)
        self._revision = 1
        self.public_market = EnvironmentBoundPublicMarketProvider(self)
        self.contract_rules = EnvironmentBoundContractRulesProvider(self)
        self.historical = EnvironmentBoundHistoricalMarketDataProvider(self)

    @property
    def application_environment(self) -> ApplicationEnvironment:
        with self._lock:
            return self._application_environment

    @property
    def effective_environment(self) -> PublicRestEnvironment:
        with self._lock:
            return self._effective_environment

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    def activate(self, environment: ApplicationEnvironment) -> None:
        """Build replacements first, then swap them together without mixed endpoints."""
        effective_environment = public_rest_environment(environment)
        replacements = self._build(effective_environment)
        previous_historical: GateHistoricalMarketDataProvider | None = None
        with self._lock:
            previous_historical = self._historical
            self._public_market, self._contract_rules, self._historical = replacements
            self._application_environment = environment
            self._effective_environment = effective_environment
            self._revision += 1
        if previous_historical is not replacements[2]:
            close = getattr(previous_historical, "close", None)
            if callable(close):
                close()

    def _build(
        self,
        environment: PublicRestEnvironment,
    ) -> tuple[
        GatePublicMarketProvider,
        GateContractRulesProvider,
        GateHistoricalMarketDataProvider,
    ]:
        return (
            self._public_market_factory(environment),
            self._contract_rules_factory(environment),
            self._historical_factory(environment),
        )

    def current_public_market(self) -> GatePublicMarketProvider:
        with self._lock:
            return self._public_market

    def current_contract_rules(self) -> GateContractRulesProvider:
        with self._lock:
            return self._contract_rules

    def current_historical(self) -> GateHistoricalMarketDataProvider:
        with self._lock:
            return self._historical


class EnvironmentBoundPublicMarketProvider:
    def __init__(self, manager: PublicRestEnvironmentManager) -> None:
        self._manager = manager

    def eligible_contracts(self) -> list[PublicContract]:
        return self._manager.current_public_market().eligible_contracts()

    def snapshot(self, symbol: str) -> PublicMarketSnapshot:
        return self._manager.current_public_market().snapshot(symbol)


class EnvironmentBoundContractRulesProvider:
    def __init__(self, manager: PublicRestEnvironmentManager) -> None:
        self._manager = manager

    def __call__(self, symbol: str) -> FuturesContractRules:
        return self._manager.current_contract_rules()(symbol)


class EnvironmentBoundHistoricalMarketDataProvider:
    def __init__(self, manager: PublicRestEnvironmentManager) -> None:
        self._manager = manager

    @property
    def warning_ar(self) -> str:
        return self._manager.current_historical().warning_ar

    def contracts(
        self,
        *,
        minimum_quote_volume: Decimal = Decimal("0"),
        maximum_contracts: int | None = None,
    ) -> tuple[DiscoveryMarketContract, ...]:
        return self._manager.current_historical().contracts(
            minimum_quote_volume=minimum_quote_volume,
            maximum_contracts=maximum_contracts,
        )

    def latest_candles(
        self,
        symbol: str,
        timeframe_minutes: int,
        *,
        limit: int,
    ) -> tuple[NormalizedCandle, ...]:
        return self._manager.current_historical().latest_candles(
            symbol,
            timeframe_minutes,
            limit=limit,
        )

    def candles(
        self,
        symbol: str,
        timeframe_minutes: int,
        *,
        start: datetime,
        end: datetime,
    ) -> tuple[NormalizedCandle, ...]:
        return self._manager.current_historical().candles(
            symbol,
            timeframe_minutes,
            start=start,
            end=end,
        )

    def funding_rates(
        self,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
    ) -> tuple[tuple[datetime, Decimal], ...]:
        return self._manager.current_historical().funding_rates(
            symbol,
            start=start,
            end=end,
        )

    def funding_cost(
        self,
        *,
        symbol: str,
        direction: str,
        notional: Decimal,
        entered_at: datetime,
        exited_at: datetime,
    ) -> Decimal:
        return self._manager.current_historical().funding_cost(
            symbol=symbol,
            direction=direction,
            notional=notional,
            entered_at=entered_at,
            exited_at=exited_at,
        )

    def cost(
        self,
        *,
        symbol: str,
        direction: str,
        notional: Decimal,
        entered_at: datetime,
        exited_at: datetime,
    ) -> Decimal:
        return self.funding_cost(
            symbol=symbol,
            direction=direction,
            notional=notional,
            entered_at=entered_at,
            exited_at=exited_at,
        )
