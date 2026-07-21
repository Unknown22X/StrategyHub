"""Central strategy-discovery orchestration over normalized market contexts."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

from rangebot.domain.discovery import (
    DiscoveryMarketContract,
    DiscoveryMarketDataProvider,
    StrategyScanFailure,
    StrategyScanRequest,
    StrategyScanResult,
)
from rangebot.domain.strategy_runtime import StrategyEvaluationContext
from rangebot.engine.strategy_registry import StrategyRegistry


class StrategyDiscoveryService:
    """Rank strategy-owned candidate evaluations without exchange execution."""

    def __init__(self, registry: StrategyRegistry) -> None:
        self._registry = registry

    def scan(
        self,
        request: StrategyScanRequest,
        contexts: tuple[StrategyEvaluationContext, ...]
        | list[StrategyEvaluationContext],
    ) -> StrategyScanResult:
        metadata = self._registry.get(request.strategy_type_id)
        if not metadata.supports_scanning:
            raise ValueError(
                f"Strategy does not support market scanning: {request.strategy_type_id}"
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
                "Scanner timeframe must match the strategy configuration timeframe."
            )
        scanner = self._registry.scanner(request.strategy_type_id)

        latest_by_symbol: dict[str, StrategyEvaluationContext] = {}
        for context in contexts:
            if context.timeframe_minutes != request.timeframe_minutes:
                continue
            current = latest_by_symbol.get(context.symbol)
            if current is None or context.evaluated_at > current.evaluated_at:
                latest_by_symbol[context.symbol] = context

        candidates = [
            scanner.scan_candidate(
                context,
                request.configuration,
                minimum_backtest_candles=metadata.minimum_backtest_candles,
            )
            for context in latest_by_symbol.values()
        ]
        candidates = [
            candidate
            for candidate in candidates
            if candidate.score >= request.minimum_score
        ]
        candidates.sort(
            key=lambda candidate: (
                -candidate.score,
                not candidate.eligible_now,
                candidate.symbol,
            )
        )
        scanned_at = max(
            (context.evaluated_at for context in latest_by_symbol.values()),
            default=datetime.now(UTC),
        )
        return StrategyScanResult(
            strategy_type_id=request.strategy_type_id,
            timeframe_minutes=request.timeframe_minutes,
            scanned_at=scanned_at,
            universe_symbols=len(latest_by_symbol),
            scanned_symbols=len(latest_by_symbol),
            candidates=tuple(candidates[: request.maximum_candidates]),
        )


class GateStrategyDiscoveryCoordinator:
    """Build scan contexts from Gate public contracts and historical candles."""

    def __init__(
        self,
        registry: StrategyRegistry,
        market_data: DiscoveryMarketDataProvider,
        *,
        maximum_workers: int = 4,
    ) -> None:
        if maximum_workers < 1 or maximum_workers > 16:
            raise ValueError("Discovery worker count must be between 1 and 16.")
        self._registry = registry
        self._market_data = market_data
        self._maximum_workers = maximum_workers
        self._scanner = StrategyDiscoveryService(registry)

    def scan(self, request: StrategyScanRequest) -> StrategyScanResult:
        metadata = self._registry.get(request.strategy_type_id)
        if not metadata.supports_scanning:
            raise ValueError(
                f"Strategy does not support market scanning: {request.strategy_type_id}"
            )
        contracts = self._market_data.contracts(
            minimum_quote_volume=request.minimum_quote_volume,
            maximum_contracts=request.maximum_symbols,
        )
        contexts: list[StrategyEvaluationContext] = []
        failures: list[StrategyScanFailure] = []
        history_limit = min(metadata.minimum_backtest_candles, 1999)

        with ThreadPoolExecutor(
            max_workers=min(self._maximum_workers, max(1, len(contracts)))
        ) as executor:
            futures = {
                executor.submit(
                    self._context,
                    contract,
                    request.timeframe_minutes,
                    history_limit,
                ): contract.symbol
                for contract in contracts
            }
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    contexts.append(future.result())
                except (ConnectionError, LookupError, ValueError):
                    failures.append(
                        StrategyScanFailure(
                            symbol=symbol,
                            reason_code="market_history_unavailable",
                            explanation_ar=(
                                "تعذر تحميل سجل Gate.io المكتمل لهذا العقد؛ "
                                "تم تخطيه دون إيقاف الفحص بالكامل."
                            ),
                        )
                    )

        result = self._scanner.scan(request, contexts)
        return result.model_copy(
            update={
                "universe_symbols": len(contracts),
                "failures": tuple(sorted(failures, key=lambda item: item.symbol)),
            }
        )

    def _context(
        self,
        contract: DiscoveryMarketContract,
        timeframe_minutes: int,
        history_limit: int,
    ) -> StrategyEvaluationContext:
        candles = self._market_data.latest_candles(
            contract.symbol,
            timeframe_minutes,
            limit=history_limit,
        )
        if not candles:
            raise LookupError(f"Gate has no completed candles for {contract.symbol}.")
        return StrategyEvaluationContext(
            symbol=contract.symbol,
            evaluated_at=candles[-1].closed_at,
            timeframe_minutes=timeframe_minutes,
            candles=candles,
            last_price=contract.last_price,
            mark_price=contract.mark_price,
            best_bid=contract.best_bid,
            best_ask=contract.best_ask,
            market_data_state="fresh",
            reconciliation_ready=True,
            emergency_stop=False,
        )
