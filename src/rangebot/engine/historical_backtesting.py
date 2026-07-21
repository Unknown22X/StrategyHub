"""Production backtest orchestration over the existing strategy and data layers."""

from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import json
import logging
from threading import Lock
from typing import Callable

from rangebot.domain.backtesting import (
    BacktestPortfolioRequest,
    BacktestReadiness,
    StoredPortfolioBacktestRun,
)
from rangebot.domain.discovery import DiscoveryMarketDataProvider
from rangebot.domain.orders import FuturesContractRules
from rangebot.engine.backtest_repository import PortfolioBacktestRepository
from rangebot.engine.backtesting import BacktestEngine, FundingCostProvider
from rangebot.engine.strategy_registry import StrategyRegistry


logger = logging.getLogger(__name__)


class HistoricalBacktestService:
    """Persist progress and run both opportunity sources through BacktestEngine."""

    def __init__(
        self,
        registry: StrategyRegistry,
        market_data: DiscoveryMarketDataProvider,
        repository: PortfolioBacktestRepository,
        *,
        contract_rules: Callable[[str], FuturesContractRules] | None = None,
        funding_costs: FundingCostProvider | None = None,
        setup_validation: Callable[[BacktestPortfolioRequest], tuple[str, ...]] | None = None,
    ) -> None:
        self._registry = registry
        self._market_data = market_data
        self._repository = repository
        self._contract_rules = contract_rules
        self._setup_validation = setup_validation
        self._engine = BacktestEngine(registry, funding_costs)
        self._execution_lock = Lock()
        try:
            self._code_version = version("rangebot")
        except PackageNotFoundError:
            self._code_version = "development"

    def readiness(self, request: BacktestPortfolioRequest) -> BacktestReadiness:
        missing: list[str] = []
        warnings: list[str] = []
        try:
            metadata = self._registry.get(request.strategy_type_id)
            self._registry.validate_configuration(
                request.strategy_type_id,
                request.configuration | request.parameter_overrides,
            )
        except (LookupError, TypeError, ValueError) as error:
            missing.append(str(error))
            return BacktestReadiness(ready=False, missing_rules=tuple(missing))
        if not metadata.supports_backtesting:
            missing.append("الاستراتيجية لا تعلن قواعد اختبار تاريخي حتمية.")
        if request.strategy_version != metadata.version:
            missing.append("إصدار الاستراتيجية المطلوب لا يطابق الإصدار المسجل حالياً.")
        if request.timeframe_minutes not in metadata.supported_timeframes:
            missing.append("الإطار الزمني غير مدعوم من الاستراتيجية.")
        if request.settings.position_sizing_mode == "risk_based" and request.execution.stop_loss_percentage is None:
            # An evaluator may supply a stop, but readiness cannot assume every signal will.
            missing.append("حجم المخاطرة يحتاج قاعدة وقف خسارة صريحة لكل صفقة.")
        if request.mode == "historical_scanner" and not metadata.supports_scanning:
            missing.append("الوضع التاريخي للماسح يحتاج ماسحاً مسجلاً للاستراتيجية.")
        if request.mode == "historical_scanner":
            try:
                self._registry.scanner(request.strategy_type_id)
            except LookupError:
                missing.append("لا يوجد ماسح مسجل قابل لإعادة التشغيل لهذه الاستراتيجية.")
        if request.mode == "historical_scanner" and request.scanner_version is None:
            missing.append("إعادة تشغيل الماسح تحتاج إصدار ماسح ثابتاً داخل الإعداد.")
        if (
            request.mode == "historical_scanner"
            and request.scanner_version is not None
            and request.scanner_version != metadata.version
        ):
            missing.append("إصدار الماسح المطلوب لا يطابق الإصدار المسجل حالياً.")
        if request.exchange != "gateio":
            missing.append("الإصدار الحالي يدعم بيانات Gate.io التاريخية فقط.")
        if request.quote_currency != "USDT":
            missing.append("الإصدار الحالي يدعم عقود USDT فقط.")
        if request.universe_quality != "exact_historical":
            warnings.append("بيانات الإدراج التاريخية ليست كاملة؛ سيظهر تحذير تحيز الكون.")
        if request.setup_id is not None and self._setup_validation is not None:
            try:
                missing.extend(self._setup_validation(request))
            except LookupError as error:
                missing.append(str(error))
        return BacktestReadiness(
            ready=not missing,
            missing_rules=tuple(missing),
            warnings=tuple(warnings),
        )

    def run(self, request: BacktestPortfolioRequest) -> StoredPortfolioBacktestRun:
        stored = self.enqueue(request)
        return self.execute(stored.backtest_id, stored.request)

    def enqueue(self, request: BacktestPortfolioRequest) -> StoredPortfolioBacktestRun:
        if request.code_version is None:
            request = request.model_copy(update={"code_version": self._code_version})
        readiness = self.readiness(request)
        if not readiness.ready:
            raise ValueError("Not ready for backtesting: " + " ".join(readiness.missing_rules))
        return self._repository.create(request)

    def execute(
        self, backtest_id: str, request: BacktestPortfolioRequest
    ) -> StoredPortfolioBacktestRun:
        with self._execution_lock:
            return self._execute(backtest_id, request)

    def _execute(
        self, backtest_id: str, request: BacktestPortfolioRequest
    ) -> StoredPortfolioBacktestRun:
        try:
            self._repository.progress(
                backtest_id, "loading_data", 10,
                "جارٍ تحميل الشموع التاريخية المكتملة وقواعد العقود.",
            )
            warmup_start = request.start - timedelta(
                minutes=request.timeframe_minutes * request.warmup_candles
            )
            candles = {
                symbol: self._market_data.candles(
                    symbol, request.timeframe_minutes,
                    start=warmup_start, end=request.end,
                )
                for symbol in request.symbols
            }
            for symbol, values in candles.items():
                warmup_count = sum(item.closed_at < request.start for item in values)
                if warmup_count < request.warmup_candles:
                    raise ValueError(
                        f"Insufficient warm-up candles for {symbol}: "
                        f"required {request.warmup_candles}, received {warmup_count}."
                    )
            higher_timeframes = {
                symbol: {
                    timeframe: self._market_data.candles(
                        symbol, timeframe,
                        start=request.start - timedelta(
                            minutes=timeframe * request.warmup_candles
                        ),
                        end=request.end,
                    )
                    for timeframe in request.additional_timeframes
                }
                for symbol in request.symbols
            }
            rules: dict[str, FuturesContractRules] = {}
            if self._contract_rules is not None:
                for symbol in request.symbols:
                    rules[symbol] = self._contract_rules(symbol)
            fingerprint_payload = {
                "candles": {
                    symbol: [item.model_dump(mode="json") for item in values]
                    for symbol, values in sorted(candles.items())
                },
                "additional_timeframes": {
                    symbol: {
                        str(timeframe): [item.model_dump(mode="json") for item in values]
                        for timeframe, values in sorted(by_timeframe.items())
                    }
                    for symbol, by_timeframe in sorted(higher_timeframes.items())
                },
                "contract_rules": {
                    symbol: item.model_dump(mode="json")
                    for symbol, item in sorted(rules.items())
                },
            }
            input_fingerprint = sha256(
                json.dumps(
                    fingerprint_payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest()
            self._repository.record_input_fingerprint(backtest_id, input_fingerprint)
            self._repository.progress(
                backtest_id, "running", 40,
                "جارٍ إعادة تشغيل الإشارات والمحفظة زمنياً دون بيانات مستقبلية.",
            )
            result = self._engine.run_portfolio(
                request, candles, rules, higher_timeframes
            )
            self._repository.progress(
                backtest_id, "calculating_results", 90,
                "جارٍ حساب المقاييس ومنحنى الحقوق وسجل القرارات.",
            )
            return self._repository.complete(backtest_id, result)
        except Exception as error:
            logger.exception("Portfolio backtest failed", extra={"backtest_id": backtest_id})
            public_reason = (
                str(error)
                if isinstance(error, ValueError)
                else "Internal historical simulation failure. Review sanitized service logs."
            )
            self._repository.fail(backtest_id, public_reason)
            raise

    def get(self, backtest_id: str) -> StoredPortfolioBacktestRun:
        return self._repository.get(backtest_id)

    def list(self, limit: int = 50) -> list[StoredPortfolioBacktestRun]:
        return self._repository.list(limit)

    def fail_interrupted_runs(self) -> int:
        return self._repository.fail_interrupted_runs()

    def update_notes(self, backtest_id: str, observations: str) -> StoredPortfolioBacktestRun:
        return self._repository.update_notes(backtest_id, observations)
