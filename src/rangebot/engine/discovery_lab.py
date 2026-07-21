"""Central Discovery Lab orchestration for scans, backtests, and safe application."""

from __future__ import annotations

from typing import cast

from rangebot.domain.backtesting import (
    BacktestRunRequest,
    BacktestStrategyCreateRequest,
    StoredBacktestRun,
)
from rangebot.domain.discovery import (
    DiscoveryMarketDataProvider,
    StoredStrategyScan,
    StrategyScanRequest,
)
from rangebot.domain.strategy import StrategyInstance, StrategyInstanceCreate
from rangebot.engine.backtesting import BacktestEngine, FundingCostProvider
from rangebot.engine.discovery import GateStrategyDiscoveryCoordinator
from rangebot.engine.discovery_repository import DiscoveryResearchRepository
from rangebot.engine.strategy_instances import StrategyInstanceRepository
from rangebot.engine.strategy_registry import StrategyRegistry


class DiscoveryLabService:
    """Own the complete research flow without any order-submission capability."""

    def __init__(
        self,
        registry: StrategyRegistry,
        market_data: DiscoveryMarketDataProvider,
        repository: DiscoveryResearchRepository,
        strategy_instances: StrategyInstanceRepository,
        *,
        maximum_scan_workers: int = 4,
    ) -> None:
        self._registry = registry
        self._market_data = market_data
        self._repository = repository
        self._strategy_instances = strategy_instances
        self._scanner = GateStrategyDiscoveryCoordinator(
            registry,
            market_data,
            maximum_workers=maximum_scan_workers,
        )
        funding_costs = (
            cast(FundingCostProvider, market_data)
            if callable(getattr(market_data, "cost", None))
            and hasattr(market_data, "warning_ar")
            else None
        )
        self._backtests = BacktestEngine(registry, funding_costs)

    def run_scan(self, request: StrategyScanRequest) -> StoredStrategyScan:
        metadata = self._registry.get(request.strategy_type_id)
        result = self._scanner.scan(request)
        return self._repository.save_scan(
            request,
            result,
            strategy_version=metadata.version,
        )

    def run_backtest(self, request: BacktestRunRequest) -> StoredBacktestRun:
        metadata = self._registry.get(request.strategy_type_id)
        if not metadata.supports_backtesting:
            raise ValueError(
                f"Strategy does not support backtesting: {request.strategy_type_id}"
            )
        if request.timeframe_minutes not in metadata.supported_timeframes:
            raise ValueError(
                "Requested timeframe is not supported by the selected strategy."
            )
        self._registry.validate_configuration(
            request.strategy_type_id,
            request.configuration,
        )
        configured_timeframe = request.configuration.get("timeframe_minutes")
        if (
            configured_timeframe is not None
            and int(configured_timeframe) != request.timeframe_minutes
        ):
            raise ValueError(
                "Backtest timeframe must match the strategy configuration timeframe."
            )
        if request.scan_id is not None:
            scan = self._repository.get_scan(request.scan_id)
            if scan.request.strategy_type_id != request.strategy_type_id:
                raise ValueError("Backtest strategy does not match the selected scan.")
            if scan.request.timeframe_minutes != request.timeframe_minutes:
                raise ValueError("Backtest timeframe does not match the selected scan.")
            if scan.request.configuration != request.configuration:
                raise ValueError("Backtest configuration must match the selected scan.")
            candidate = next(
                (
                    candidate
                    for candidate in scan.result.candidates
                    if candidate.symbol == request.symbol
                ),
                None,
            )
            if candidate is None:
                raise LookupError("Selected symbol is not part of the discovery scan.")
            if not candidate.backtest_ready:
                raise RuntimeError(
                    "Selected candidate does not have enough completed history for backtesting."
                )

        candles = self._market_data.candles(
            request.symbol,
            request.timeframe_minutes,
            start=request.start,
            end=request.end,
        )
        if len(candles) < 2:
            raise RuntimeError("Backtest requires at least two completed candles.")
        result = self._backtests.run(request.spec(), candles)
        warnings = list(result.warnings)
        if len(candles) < metadata.minimum_backtest_candles:
            warnings.append(
                "عدد الشموع أقل من الحد التاريخي الموصى به لهذه الاستراتيجية."
            )
        result = result.model_copy(update={"warnings": tuple(dict.fromkeys(warnings))})
        return self._repository.save_backtest(
            request,
            result,
            strategy_version=metadata.version,
        )

    def create_stopped_strategy(
        self,
        backtest_id: str,
        request: BacktestStrategyCreateRequest,
    ) -> StrategyInstance:
        stored = self._repository.get_backtest(backtest_id)
        if stored.applied_instance_id is not None:
            raise RuntimeError("This backtest has already created a strategy instance.")
        configuration = dict(stored.request.configuration)
        tested_direction = configuration.get("direction")
        if tested_direction in {"long_only", "short_only", "both"}:
            if request.direction != tested_direction:
                raise ValueError(
                    "Strategy direction must match the direction used by the backtest."
                )
        else:
            tested_direction = request.direction
        metadata = self._registry.get(stored.request.strategy_type_id)
        instance = self._strategy_instances.create(
            StrategyInstanceCreate(
                type_id=stored.request.strategy_type_id,
                template_id=self._registry.template_id(stored.request.strategy_type_id),
                name=request.name,
                environment=request.environment,
                symbol=stored.request.symbol,
                timeframe_minutes=stored.request.timeframe_minutes,
                direction=tested_direction,
                requested_margin=stored.request.settings.margin_per_trade,
                requested_leverage=stored.request.settings.leverage,
                configuration=configuration,
            ),
            template_version=metadata.version,
        )
        try:
            self._repository.record_strategy_application(
                backtest_id,
                instance.instance_id,
            )
        except Exception:
            self._strategy_instances.delete(instance.instance_id)
            raise
        return instance

    def get_scan(self, scan_id: str) -> StoredStrategyScan:
        return self._repository.get_scan(scan_id)

    def list_scans(self, limit: int = 50) -> list[StoredStrategyScan]:
        return self._repository.list_scans(limit)

    def get_backtest(self, backtest_id: str) -> StoredBacktestRun:
        return self._repository.get_backtest(backtest_id)

    def list_backtests(self, limit: int = 50) -> list[StoredBacktestRun]:
        return self._repository.list_backtests(limit)
