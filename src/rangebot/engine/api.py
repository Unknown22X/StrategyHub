"""Localhost-only FastAPI contract for the desktop control UI."""

import asyncio
from collections.abc import AsyncIterator, Callable
import hashlib
import json
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import sys
from threading import RLock
from typing import Literal, cast
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from rangebot.domain.account_risk import (
    AccountRiskPolicy,
    AccountRiskPolicyUpdate,
    AccountRiskStatus,
)
from rangebot.domain.api_errors import PublicApiError
from rangebot.domain.activity import ActivityCategory, ActivityEvent, ActivityQuery
from rangebot.domain.analysis import (
    RangeAnalysisRequest,
    RangeAnalysisResult,
    evaluate_range,
)
from rangebot.domain.application import (
    ApplicationSettings,
    ApplicationSettingsOverview,
    ApplicationSettingsUpdate,
)
from rangebot.domain.backtesting import (
    BacktestPostTestNotesUpdate,
    BacktestPortfolioRequest,
    BacktestReadiness,
    BacktestEquityPoint,
    BacktestRunRequest,
    BacktestStrategyCreateRequest,
    BacktestTrade,
    StoredBacktestRun,
    StoredPortfolioBacktestRun,
)
from rangebot.domain.backups import (
    BackupDeleteResult,
    BackupRecord,
    BackupRestoreRequest,
    BackupRestoreResult,
)
from rangebot.domain.discovery import (
    DiscoveryMarketDataProvider,
    StoredStrategyScan,
    StrategyScanRequest,
)
from rangebot.domain.entry_preview import (
    EntryPreview,
    EntryPreviewRequest,
    PreviewValidationRequest,
    create_entry_preview,
    preview_is_current,
)
from rangebot.domain.events import EngineEventCategory, EngineEventStreamStatus
from rangebot.domain.market import (
    PaperWatchlist,
    PublicContract,
    WatchlistItem,
)
from rangebot.domain.market_data import (
    MarketCandleSeries,
    MarketDataSnapshot,
    MarketDataStatus,
    MarketPriceUpdate,
)
from rangebot.domain.performance import (
    AccountPerformanceSeries,
    PerformanceMode,
    PerformancePeriod,
)
from rangebot.domain.orders import (
    FuturesContractRules,
    ManualOrderPreview,
    ManualOrderPreviewRequest,
    ManualOrderSubmissionRequest,
    ManualOrderSubmissionResult,
    OrderAccountContext,
    OrderOrigin,
    OrderSubmissionContext,
)
from pydantic import BaseModel, Field
from rangebot.domain.paper import (
    PaperAccountChange,
    PaperAccountSnapshot,
    PaperAuditEntry,
    PaperAutomaticLimitRequest,
    PaperAutomaticSignalRequest,
    PaperCloseRequest,
    PaperCloseResult,
    PaperDirectionalResetRequest,
    PaperEmergencyState,
    PaperEmergencyStopRequest,
    PaperMarketEntryResult,
    PaperLimitCheck,
    PaperLimitCheckResult,
    PaperPendingEntry,
    PaperPosition,
    PaperProfile,
    PaperProfileApplyResult,
    PaperProfileChange,
    PaperProtection,
    PaperProtectionCheck,
    PaperProtectionTriggerResult,
    PaperFeeSchedule,
    PaperResumeRequest,
    PaperRiskAdjustment,
    PaperRiskSettings,
    PaperRiskSnapshot,
    PaperUsedSignal,
    PaperVerificationRecord,
    PaperVerificationRequest,
    PaperHelpTopic,
)
from rangebot.domain.runtime import RuntimeState
from rangebot.domain.trades import TradeFill, TradeFillCreate, TradeHistorySummary
from rangebot.domain.strategy import (
    StrategyConfigurationVersion,
    StrategyDecision,
    StrategyInstance,
    StrategyInstanceCreate,
    StrategyInstanceDuplicate,
    StrategyInstanceUpdate,
    StrategyLifecycle,
    StrategyOverviewItem,
    StrategyRun,
    StrategyTypeMetadata,
    TradeOwnership,
    TradeOwnershipCreate,
)
from rangebot.domain.private_stream import PrivateStreamState
from rangebot.domain.strategy_runtime import StrategyEvaluationContext
from rangebot.domain.strategy_workflow import (
    BotDeployment,
    BotDeploymentCreate,
    OpportunityConversionRequest,
    OpportunityStatusUpdate,
    SetupApprovalRequest,
    SetupBacktestRequest,
    StrategyCoinSetup,
    StrategyCoinSetupCreate,
    StrategyCoinSetupUpdate,
    StrategyCoinSetupVersion,
    StrategyOpportunity,
    StrategySetupApproval,
    StrategyTemplate,
    StrategyTemplateCreate,
    StrategyTemplateUpdate,
    StrategyTemplateVersion,
    WorkflowSummary,
    price_state_from_market_state,
)
from rangebot.strategies.fixed_price_ladder import (
    FixedPriceLadderConfig,
    FixedPriceLadderPreview,
    build_ladder_preview,
)
from rangebot.domain.exchange import (
    AutomaticSignalRequest,
    AutomaticStartRequest,
    ExchangeCloseRequest,
    ExchangeCredentialRequest,
    ExchangeCredentialStatus,
    ExchangeCredentialTestResult,
    ExchangeEntryRequest,
    ExchangeOperationResult,
    ExchangeRequestAudit,
    ExchangeSnapshot,
    ExchangeTrailingStopRequest,
    ExchangeVerificationRecord,
    ExchangeVerificationRequest,
    MarketEntryGuardRequest,
    MarketEntryGuardResult,
    MarketGuardQuoteRequest,
    LiveEntryRequest,
    ModeState,
    ProtectionChangeRequest,
    TradingMode,
)
from rangebot.engine.account_risk import (
    AccountRiskPolicyRepository,
    AccountRiskService,
)
from rangebot.engine.activity_feed import ActivityFeedService
from rangebot.engine.application_settings import ApplicationSettingsRepository
from rangebot.engine.backups import SQLiteBackupError, SQLiteBackupManager
from rangebot.engine.backtest_repository import PortfolioBacktestRepository
from rangebot.engine.backtesting import FundingCostProvider
from rangebot.engine.contract_rules import GateContractRulesProvider
from rangebot.engine.credential_adapter import effective_gate_credentials
from rangebot.engine.database import apply_migrations, create_database_engine
from rangebot.engine.discovery_lab import DiscoveryLabService
from rangebot.engine.discovery_repository import DiscoveryResearchRepository
from rangebot.engine.credentials import (
    load_gate_credentials,
    remove_gate_credentials,
    save_gate_credentials,
)
from rangebot.engine.events import EngineEventPublisher
from rangebot.engine.exchange import (
    GateIoAdapter,
    MockGateIoAdapter,
    UnavailableGateIoAdapter,
    configured_gate_adapter,
    guard_market_entry,
    mode_state,
)
from rangebot.engine.gate_private_websocket import (
    GateFuturesPrivateWebSocketService,
    PrivateStreamStateStore,
)
from rangebot.engine.gate_websocket import (
    GateFuturesWebSocketService,
    GateMarketTarget,
    MarketSubscriptionRegistry,
)
from rangebot.engine.historical_market_data import GateHistoricalMarketDataProvider
from rangebot.engine.historical_backtesting import HistoricalBacktestService
from rangebot.engine.market import EmptyPublicMarketProvider, PublicMarketProvider
from rangebot.engine.market_data_manager import MarketDataManager
from rangebot.engine.performance import AccountPerformanceRepository
from rangebot.engine.order_manager import (
    OrderManager,
    OrderValidationError,
    StaleOrderPreviewError,
)
from rangebot.engine.paths import application_paths
from rangebot.engine.support_logs import SupportLogExporter
from rangebot.engine.trade_history import TradeHistoryRepository
from rangebot.engine.strategy_instances import StrategyInstanceRepository
from rangebot.engine.strategy_manager import StrategyManager
from rangebot.engine.strategy_workflow import StrategyWorkflowRepository
from rangebot.engine.strategy_overview import StrategyOverviewService
from rangebot.engine.strategy_runtime_runner import StrategyRuntimeRunner
from rangebot.engine.strategy_registry import StrategyRegistry, discover_strategy_registry
from rangebot.engine.repository import (
    ENGINE_BUILD_ID,
    PaperAccountRepository,
    PaperWatchlistRepository,
    ExchangeModeRepository,
    RuntimeStateRepository,
)


_LOGGER = logging.getLogger(__name__)
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _event_category_for_path(path: str) -> EngineEventCategory:
    if (
        path.startswith("/v1/strateg")
        or path.startswith("/v1/discovery")
        or path.startswith("/v1/opportunities")
        or path.startswith("/v1/backtests")
        or path.startswith("/v1/bot-deployments")
    ):
        return "strategy"
    if path.startswith("/v1/manual-orders") or "entry" in path or "position" in path:
        return "order"
    if path.startswith("/v1/market-data") or path.startswith("/v1/paper/watchlist"):
        return "market"
    if "credentials" in path:
        return "credentials"
    if path.startswith("/v1/backups") or path.startswith("/v1/support"):
        return "backup"
    if path.startswith("/v1/settings") or path.startswith("/v1/account-risk"):
        return "settings"
    if path.startswith("/v1/paper") or path.startswith("/v1/exchange"):
        return "account"
    return "activity"


def _default_error_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        410: "deprecated_endpoint",
        422: "request_validation_error",
        429: "rate_limited",
        500: "internal_error",
        503: "service_unavailable",
    }.get(status_code, f"http_{status_code}")


def _mock_contract_rules(symbol: str) -> FuturesContractRules:
    """Deterministic contract metadata for the explicit local simulation adapter."""
    return FuturesContractRules(
        symbol=symbol,
        contract_multiplier=Decimal("0.001"),
        quantity_step=Decimal("1"),
        minimum_quantity=Decimal("1"),
        maximum_quantity=Decimal("1000"),
        maximum_market_quantity=Decimal("500"),
        price_step=Decimal("0.1"),
        maximum_leverage=20,
        maintenance_rate=Decimal("0.005"),
        maker_fee_rate=Decimal("0.0002"),
        taker_fee_rate=Decimal("0.0005"),
    )


def create_app(
    database_url: str,
    public_market_provider: PublicMarketProvider | None = None,
    exchange_adapter: GateIoAdapter | None = None,
    restored_state: bool = False,
    credential_test_adapter_factory: Callable[[TradingMode], GateIoAdapter]
    | None = None,
    strategy_registry: StrategyRegistry | None = None,
    market_data_manager: MarketDataManager | None = None,
    contract_rules_provider: Callable[[str], FuturesContractRules] | None = None,
    order_manager: OrderManager | None = None,
    exchange_adapter_mode: TradingMode | None = None,
    frontend_dist: str | Path | None = None,
    log_directory: str | Path | None = None,
    market_subscription_registry: MarketSubscriptionRegistry | None = None,
    market_websocket_service: GateFuturesWebSocketService | None = None,
    enable_private_websocket: bool = False,
    private_stream_state_store: PrivateStreamStateStore | None = None,
    private_websocket_service: GateFuturesPrivateWebSocketService | None = None,
    historical_market_data_provider: DiscoveryMarketDataProvider | None = None,
    discovery_lab_service: DiscoveryLabService | None = None,
) -> FastAPI:
    """Create an engine API that exposes lifecycle state to the local UI."""
    database_engine = create_database_engine(database_url)
    database_maintenance_lock = RLock()
    event_publisher = EngineEventPublisher()
    repository = RuntimeStateRepository(database_engine)
    paper_repository = PaperAccountRepository(database_engine)
    watchlist_repository = PaperWatchlistRepository(database_engine)
    exchange_repository = ExchangeModeRepository(database_engine)
    performance_repository = AccountPerformanceRepository(database_engine)
    settings_repository = ApplicationSettingsRepository(database_engine)
    account_risk_policy_repository = AccountRiskPolicyRepository(database_engine)
    strategy_instance_repository = StrategyInstanceRepository(database_engine)
    research_repository = DiscoveryResearchRepository(database_engine)
    portfolio_backtest_repository = PortfolioBacktestRepository(database_engine)
    trade_history_repository = TradeHistoryRepository(database_engine)
    account_risk_service = AccountRiskService(
        account_risk_policy_repository,
        performance_repository,
        trade_history_repository,
    )
    strategy_overview_service = StrategyOverviewService(
        strategy_instance_repository,
        trade_history_repository,
    )
    activity_feed_service = ActivityFeedService(database_engine)
    try:
        backup_manager: SQLiteBackupManager | None = SQLiteBackupManager(
            database_url, database_engine
        )
    except ValueError:
        backup_manager = None
    support_log_exporter = SupportLogExporter(
        Path(log_directory).expanduser().resolve()
        if log_directory is not None
        else application_paths().logs
    )
    registered_strategies = strategy_registry or discover_strategy_registry()
    strategy_workflow_repository = StrategyWorkflowRepository(
        database_engine,
        registered_strategies,
        strategy_instance_repository,
    )
    strategy_manager = StrategyManager(
        registered_strategies, strategy_instance_repository
    )
    historical_environment: Literal["live", "testnet"] = (
        "testnet" if exchange_adapter_mode == "testnet" else "live"
    )
    historical_market_data = (
        historical_market_data_provider
        or GateHistoricalMarketDataProvider(historical_environment)
    )
    discovery_lab = discovery_lab_service or DiscoveryLabService(
        registered_strategies,
        historical_market_data,
        research_repository,
        strategy_instance_repository,
    )

    def _validate_backtest_setup(
        request: BacktestPortfolioRequest,
    ) -> tuple[str, ...]:
        if request.setup_id is None:
            return ()
        setup = strategy_workflow_repository.get_setup(request.setup_id)
        template = strategy_workflow_repository.get_template(setup.template_id)
        missing: list[str] = []
        if request.setup_revision != setup.revision:
            missing.append("نسخة إعداد العملة تغيرت؛ أعد فتح الإعداد وشغّل نسخة جديدة.")
        if request.strategy_type_id != template.type_id:
            missing.append("نوع الاستراتيجية لا يطابق إعداد العملة المحفوظ.")
        if request.timeframe_minutes != setup.timeframe_minutes:
            missing.append("الإطار الزمني لا يطابق إعداد العملة المحفوظ.")
        if request.exchange != setup.exchange or request.market_type != setup.market_type:
            missing.append("السوق لا يطابق إعداد العملة المحفوظ.")
        if request.configuration != setup.effective_configuration:
            missing.append("إعدادات الاستراتيجية لا تطابق لقطة إعداد العملة الحالية.")
        return tuple(missing)

    historical_backtests = HistoricalBacktestService(
        registered_strategies,
        historical_market_data,
        portfolio_backtest_repository,
        contract_rules=contract_rules_provider,
        funding_costs=(
            cast(FundingCostProvider, historical_market_data)
            if callable(getattr(historical_market_data, "cost", None))
            and hasattr(historical_market_data, "warning_ar")
            else None
        ),
        setup_validation=_validate_backtest_setup,
    )
    gate_adapter = exchange_adapter or UnavailableGateIoAdapter()
    _persist_raw_snapshot = exchange_repository.save_snapshot

    def _position_identity(
        environment: str, symbol: str, direction: str
    ) -> str:
        return f"{environment}:{symbol}:{direction}"

    def _strategy_name_snapshot(ownership: TradeOwnership | None) -> str | None:
        if ownership is None or ownership.instance_id is None:
            return None
        try:
            return strategy_instance_repository.get(ownership.instance_id).name
        except LookupError:
            return None

    def _ownership_for_fill(fill: TradeFillCreate) -> TradeOwnership | None:
        if fill.order_id is not None:
            ownership = strategy_instance_repository.trade_ownership(
                "order", fill.order_id
            )
            if ownership is not None:
                return ownership
        if fill.position_effect in {"close", "mixed"}:
            direction = "long" if fill.side == "sell" else "short"
            return strategy_instance_repository.trade_ownership(
                "position",
                _position_identity(fill.environment, fill.contract, direction),
            )
        return None

    def _sync_gate_trade_history(mode: TradingMode) -> None:
        loader = getattr(gate_adapter, "recent_trade_fills", None)
        if not callable(loader):
            return
        for raw_fill in loader(mode):
            ownership = _ownership_for_fill(raw_fill)
            attributed = raw_fill.model_copy(
                update={
                    "origin": ownership.origin if ownership is not None else "external",
                    "instance_id": ownership.instance_id if ownership is not None else None,
                    "run_id": ownership.run_id if ownership is not None else None,
                    "strategy_name_snapshot": _strategy_name_snapshot(ownership),
                }
            )
            trade_history_repository.record(attributed)

    def _attach_paper_fill_ownership(
        trade_id: str | None, ownership: TradeOwnership | None
    ) -> None:
        if trade_id is None or ownership is None:
            return
        trade_history_repository.attach_fill_ownership(
            environment="paper",
            external_trade_id=trade_id,
            origin=ownership.origin,
            instance_id=ownership.instance_id,
            run_id=ownership.run_id,
            strategy_name_snapshot=_strategy_name_snapshot(ownership),
        )

    def _ensure_position_ownership(
        environment: Literal["paper", "testnet", "live"],
        symbol: str,
        direction: Literal["long", "short"],
        source: TradeOwnership,
    ) -> None:
        identity = _position_identity(environment, symbol, direction)
        if strategy_instance_repository.trade_ownership("position", identity) is not None:
            return
        strategy_instance_repository.record_trade_ownership(
            TradeOwnershipCreate(
                identity_kind="position",
                external_identity=identity,
                origin=source.origin,
                environment=environment,
                symbol=symbol,
                direction=direction,
                trailing_stop_price=source.trailing_stop_price,
                trailing_stop_distance=source.trailing_stop_distance,
                trailing_state=source.trailing_state,
                trailing_order_id=source.trailing_order_id,
                trailing_last_error=source.trailing_last_error,
                trailing_updated_at=source.trailing_updated_at,
                instance_id=source.instance_id,
                run_id=source.run_id,
            )
        )

    def _sync_position_ownership(
        previous: ExchangeSnapshot | None,
        current: ExchangeSnapshot,
    ) -> None:
        current_positions = {
            _position_identity(current.mode, position.contract, position.side): position
            for position in current.positions
            if position.quantity != 0
        }
        for ownership in strategy_instance_repository.trade_ownerships(
            identity_kind="position", environment=current.mode
        ):
            if ownership.external_identity in current_positions:
                continue
            if (
                ownership.trailing_stop_distance is not None
                and not current.trailing_reconciliation_ready
            ):
                continue
            if (
                ownership.trailing_order_id is not None
                and ownership.trailing_order_id in current.trailing_order_ids
            ):
                continue
            strategy_instance_repository.delete_trade_ownership(
                "position", ownership.external_identity
            )
        if previous is None:
            return
        current_order_ids = {order.order_id for order in current.open_orders}
        previous_positions = {
            (position.contract, position.side): abs(position.quantity)
            for position in previous.positions
        }
        for order in previous.open_orders:
            if order.order_id in current_order_ids:
                continue
            ownership = strategy_instance_repository.trade_ownership(
                "order", order.order_id
            )
            if ownership is None:
                continue
            position = current_positions.get(
                _position_identity(current.mode, order.contract, order.side)
            )
            if position is None:
                continue
            prior_quantity = previous_positions.get(
                (order.contract, order.side), Decimal("0")
            )
            if abs(position.quantity) <= prior_quantity:
                continue
            _ensure_position_ownership(
                current.mode,
                order.contract,
                order.side,
                ownership,
            )

    def _cleanup_closed_position_trails(
        snapshot: ExchangeSnapshot,
    ) -> ExchangeSnapshot:
        if not snapshot.trailing_reconciliation_ready or not snapshot.trailing_order_ids:
            return snapshot
        current_positions = {
            _position_identity(snapshot.mode, position.contract, position.side)
            for position in snapshot.positions
            if position.quantity != 0
        }
        remaining_order_ids = list(snapshot.trailing_order_ids)
        cleanup_ready = True
        cancel_trailing = getattr(gate_adapter, "cancel_trailing_protection", None)
        now = datetime.now(UTC)
        ownerships = strategy_instance_repository.trade_ownerships(
            identity_kind="position", environment=snapshot.mode
        )
        closed_trailing_ownerships = [
            ownership
            for ownership in ownerships
            if ownership.external_identity not in current_positions
            and ownership.trailing_stop_distance is not None
        ]
        may_infer_single_order = (
            len(closed_trailing_ownerships) == 1
            and len(remaining_order_ids) == 1
            and not any(
                ownership.external_identity in current_positions
                and ownership.trailing_stop_distance is not None
                for ownership in ownerships
            )
        )
        for ownership in closed_trailing_ownerships:
            order_id = ownership.trailing_order_id
            if order_id not in remaining_order_ids:
                if not may_infer_single_order:
                    continue
                order_id = remaining_order_ids[0]
            if (
                ownership.trailing_state == "error"
                and ownership.trailing_updated_at is not None
                and now - ownership.trailing_updated_at < timedelta(seconds=30)
            ):
                cleanup_ready = False
                continue
            if not callable(cancel_trailing):
                result_message = "Adapter Gate.io لا يدعم إلغاء وقف التتبع."
                strategy_instance_repository.update_trailing_protection(
                    "position",
                    ownership.external_identity,
                    state="error",
                    trailing_order_id=order_id,
                    error=result_message,
                )
                cleanup_ready = False
                continue
            result = cancel_trailing(snapshot.mode, order_id)
            if result.accepted:
                remaining_order_ids.remove(order_id)
                continue
            strategy_instance_repository.update_trailing_protection(
                "position",
                ownership.external_identity,
                state="error",
                trailing_order_id=order_id,
                error=result.message_ar,
            )
            cleanup_ready = False
        if (
            tuple(remaining_order_ids) == snapshot.trailing_order_ids
            and cleanup_ready
        ):
            return snapshot
        return snapshot.model_copy(
            update={
                "trailing_order_ids": tuple(remaining_order_ids),
                "trailing_reconciliation_ready": cleanup_ready,
                "trailing_protection_ready": (
                    snapshot.trailing_protection_ready
                    if remaining_order_ids and cleanup_ready
                    else False
                    if remaining_order_ids
                    else None
                ),
            }
        )

    def _recover_trailing_protection(snapshot: ExchangeSnapshot) -> None:
        if not snapshot.trailing_reconciliation_ready:
            return
        current_positions = {
            _position_identity(snapshot.mode, position.contract, position.side): position
            for position in snapshot.positions
            if position.quantity != 0
        }
        active_trail_id = snapshot.trailing_order_ids[0] if snapshot.trailing_order_ids else None
        for ownership in strategy_instance_repository.trade_ownerships(
            identity_kind="position", environment=snapshot.mode
        ):
            if ownership.trailing_stop_distance is None:
                continue
            position = current_positions.get(ownership.external_identity)
            if position is None:
                continue
            if active_trail_id is not None and snapshot.trailing_protection_ready is True:
                strategy_instance_repository.update_trailing_protection(
                    "position",
                    ownership.external_identity,
                    state="active",
                    trailing_order_id=active_trail_id,
                    error=None,
                )
                continue
            if (
                ownership.trailing_updated_at is not None
                and datetime.now(UTC) - ownership.trailing_updated_at
                < timedelta(seconds=30)
            ):
                continue
            result = gate_adapter.ensure_trailing_protection(
                snapshot.mode,
                ExchangeTrailingStopRequest(
                    symbol=position.contract,
                    direction=position.side,
                    quantity=abs(position.quantity),
                    trailing_stop_distance=ownership.trailing_stop_distance,
                    client_request_id=f"recover-trail-{ownership.ownership_id}",
                ),
            )
            strategy_instance_repository.update_trailing_protection(
                "position",
                ownership.external_identity,
                state="active" if result.accepted else "error",
                trailing_order_id=result.order_id if result.accepted else None,
                error=None if result.accepted else result.message_ar,
            )

    def _save_exchange_snapshot(snapshot: ExchangeSnapshot) -> None:
        snapshot = _cleanup_closed_position_trails(snapshot)
        previous = exchange_repository.get_snapshot(snapshot.mode)
        _persist_raw_snapshot(snapshot)
        try:
            _sync_gate_trade_history(snapshot.mode)
        except Exception:
            _LOGGER.exception(
                "Failed to ingest sanitized Gate trade history for %s.", snapshot.mode
            )
        try:
            performance_repository.record(snapshot)
        except Exception:
            _LOGGER.exception(
                "Failed to append sanitized account performance point for %s.",
                snapshot.mode,
            )
        try:
            _sync_position_ownership(previous, snapshot)
        except Exception:
            _LOGGER.exception(
                "Failed to reconcile position ownership for %s.", snapshot.mode
            )
        try:
            _recover_trailing_protection(snapshot)
        except Exception:
            _LOGGER.exception(
                "Failed to reconcile trailing protection for %s.", snapshot.mode
            )
        event_publisher.publish(
            category="account",
            action="snapshot_updated",
            resource=f"/v1/exchange/{snapshot.mode}/snapshot",
        )

    private_stream_status = private_stream_state_store or PrivateStreamStateStore(
        exchange_adapter_mode
    )
    if (
        private_websocket_service is None
        and enable_private_websocket
        and exchange_adapter_mode is not None
    ):
        private_websocket_service = GateFuturesPrivateWebSocketService(
            mode=exchange_adapter_mode,
            credentials=effective_gate_credentials,
            reconcile=gate_adapter.reconcile,
            persist_snapshot=_save_exchange_snapshot,
            status_store=private_stream_status,
        )
    market_provider = public_market_provider or EmptyPublicMarketProvider()
    normalized_market_data = market_data_manager or MarketDataManager()
    pinned_market_targets = set(
        market_subscription_registry.snapshot()[1]
        if market_subscription_registry is not None
        else ()
    )

    def _sync_market_subscriptions() -> None:
        if market_subscription_registry is None:
            return
        targets = set(pinned_market_targets)
        for instance in strategy_instance_repository.list():
            try:
                targets.add(
                    GateMarketTarget(instance.symbol, instance.timeframe_minutes)
                )
            except ValueError:
                targets.add(GateMarketTarget(instance.symbol))
        for item in watchlist_repository.get().items:
            targets.add(GateMarketTarget(item.symbol))
        market_subscription_registry.replace(tuple(targets))

    contract_rule_lookup = (
        contract_rules_provider
        or (_mock_contract_rules if isinstance(gate_adapter, MockGateIoAdapter) else GateContractRulesProvider())
    )
    test_adapter_factory = credential_test_adapter_factory or (
        lambda mode: configured_gate_adapter(
            mode,
            enable_network=True,
            enable_order_submission=False,
        )
    )

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        apply_migrations(database_url)
        historical_backtests.fail_interrupted_runs()
        if restored_state:
            exchange_repository.invalidate_snapshot("testnet")
            exchange_repository.invalidate_snapshot("live")
        if isinstance(gate_adapter, MockGateIoAdapter):
            for mode in ("testnet", "live"):
                persisted = exchange_repository.adapter_state(mode)
                if persisted is not None:
                    restored = MockGateIoAdapter.from_state(persisted)
                    gate_adapter.__dict__.update(restored.__dict__)
        repository.record_started()
        event_publisher.publish(
            category="engine", action="started", resource="/health"
        )
        _sync_market_subscriptions()
        stop_heartbeat = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            _persist_heartbeats(
                repository,
                stop_heartbeat,
                database_maintenance_lock,
            )
        )
        stop_market_websocket = asyncio.Event()
        market_websocket_task = (
            asyncio.create_task(
                market_websocket_service.run(stop_market_websocket)
            )
            if market_websocket_service is not None
            else None
        )
        stop_private_websocket = asyncio.Event()
        private_websocket_task = (
            asyncio.create_task(
                private_websocket_service.run(stop_private_websocket)
            )
            if private_websocket_service is not None
            else None
        )
        strategy_runtime_runner = getattr(
            app_instance.state, "strategy_runtime_runner", None
        )
        stop_strategy_runtime = asyncio.Event()
        strategy_runtime_task = (
            asyncio.create_task(strategy_runtime_runner.run(stop_strategy_runtime))
            if strategy_runtime_runner is not None
            else None
        )
        try:
            yield
        finally:
            event_publisher.publish(
                category="engine", action="stopping", resource="/health"
            )
            stop_heartbeat.set()
            stop_market_websocket.set()
            stop_private_websocket.set()
            stop_strategy_runtime.set()
            await heartbeat_task
            if market_websocket_task is not None:
                await market_websocket_task
            if private_websocket_task is not None:
                await private_websocket_task
            if strategy_runtime_task is not None:
                await strategy_runtime_task

    app = FastAPI(title="RangeBot Engine", lifespan=lifespan)
    app.state.exchange_repository = exchange_repository
    app.state.paper_repository = paper_repository
    app.state.strategy_instance_repository = strategy_instance_repository
    app.state.strategy_workflow_repository = strategy_workflow_repository
    app.state.strategy_manager = strategy_manager
    app.state.account_risk_policy_repository = account_risk_policy_repository
    app.state.account_risk_service = account_risk_service
    app.state.performance_repository = performance_repository
    app.state.strategy_overview_service = strategy_overview_service
    app.state.discovery_research_repository = research_repository
    app.state.trade_history_repository = trade_history_repository
    app.state.discovery_lab_service = discovery_lab
    app.state.historical_backtest_service = historical_backtests
    app.state.historical_market_data_provider = historical_market_data
    app.state.market_data_manager = normalized_market_data
    app.state.market_subscription_registry = market_subscription_registry
    app.state.market_websocket_service = market_websocket_service
    app.state.private_stream_state_store = private_stream_status
    app.state.private_websocket_service = private_websocket_service
    app.state.backup_manager = backup_manager
    app.state.support_log_exporter = support_log_exporter
    app.state.event_publisher = event_publisher

    @app.exception_handler(HTTPException)
    async def structured_http_error(
        request: Request, error: HTTPException
    ) -> JSONResponse:
        payload = PublicApiError(
            detail=error.detail,
            code=_default_error_code(error.status_code),
            context={"path": request.url.path, "method": request.method},
        )
        return JSONResponse(
            status_code=error.status_code,
            content=payload.model_dump(mode="json"),
            headers=error.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def structured_validation_error(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        payload = PublicApiError(
            detail=jsonable_encoder(error.errors()),
            code="request_validation_error",
            context={"path": request.url.path, "method": request.method},
        )
        return JSONResponse(status_code=422, content=payload.model_dump(mode="json"))

    @app.middleware("http")
    async def publish_successful_mutation(request: Request, call_next):
        response = await call_next(request)
        if (
            request.method in _MUTATING_METHODS
            and request.url.path.startswith("/v1/")
            and response.status_code < 400
        ):
            event_publisher.publish(
                category=_event_category_for_path(request.url.path),
                action=request.method.lower(),
                resource=request.url.path,
            )
        return response

    @app.get("/v1/events/status", response_model=EngineEventStreamStatus)
    def event_stream_status() -> EngineEventStreamStatus:
        return event_publisher.status()

    @app.websocket("/v1/events")
    async def frontend_event_stream(websocket: WebSocket) -> None:
        await websocket.accept()
        connected = event_publisher.publish(
            category="engine", action="frontend_connected", resource="/v1/events"
        )
        await websocket.send_json(connected.model_dump(mode="json"))
        try:
            async for event in event_publisher.subscribe():
                await websocket.send_json(event.model_dump(mode="json"))
        except WebSocketDisconnect:
            return

    def _require_backup_manager() -> SQLiteBackupManager:
        if backup_manager is None:
            raise HTTPException(
                status_code=409,
                detail="عمليات النسخ الاحتياطي متاحة فقط مع قاعدة SQLite محلية.",
            )
        return backup_manager

    def _stop_strategy_execution_for_restore() -> None:
        for instance in strategy_instance_repository.list():
            if instance.status in {"running", "monitoring"}:
                strategy_instance_repository.transition(instance.instance_id, "stopped")

    def _enforce_post_restore_safety() -> None:
        for mode in ("testnet", "live"):
            exchange_repository.set_emergency_stop(mode, True)
            exchange_repository.invalidate_snapshot(mode)
        _stop_strategy_execution_for_restore()
        _sync_market_subscriptions()

    def _enrich_paper_position(position: PaperPosition) -> PaperPosition:
        if position.symbol is None:
            return position
        identity = _position_identity("paper", position.symbol, position.direction)
        ownership = strategy_instance_repository.trade_ownership("position", identity)
        if ownership is None:
            return position
        strategy_name = None
        if ownership.instance_id is not None:
            try:
                strategy_name = strategy_instance_repository.get(
                    ownership.instance_id
                ).name
            except LookupError:
                strategy_name = None
        try:
            protection = paper_repository.protection()
        except LookupError:
            protection = None
        return position.model_copy(
            update={
                "managed_by_rangebot": True,
                "origin": ownership.origin,
                "instance_id": ownership.instance_id,
                "run_id": ownership.run_id,
                "strategy_name": strategy_name,
                "ownership_created_at": ownership.created_at,
                "trailing_stop_price": (
                    protection.trailing_stop_price
                    if protection is not None
                    else ownership.trailing_stop_price
                ),
                "trailing_stop_distance": ownership.trailing_stop_distance,
                "trailing_state": ownership.trailing_state,
                "trailing_order_id": ownership.trailing_order_id,
                "trailing_last_error": ownership.trailing_last_error,
            }
        )

    def _sync_paper_limit_ownership(
        result: PaperLimitCheckResult,
    ) -> PaperLimitCheckResult:
        if result.order_id is None:
            return result
        ownership = strategy_instance_repository.trade_ownership(
            "order", result.order_id
        )
        if result.expired:
            strategy_instance_repository.delete_trade_ownership(
                "order", result.order_id
            )
            return result
        if not result.filled or result.position is None or ownership is None:
            return result
        _attach_paper_fill_ownership(result.trade_id, ownership)
        if result.position.symbol is None:
            return result
        _ensure_position_ownership(
            "paper",
            result.position.symbol,
            result.position.direction,
            ownership,
        )
        return result.model_copy(
            update={"position": _enrich_paper_position(result.position)}
        )

    def _paper_position_ownership(position: PaperPosition) -> TradeOwnership | None:
        if position.symbol is None:
            return None
        identity = _position_identity("paper", position.symbol, position.direction)
        return strategy_instance_repository.trade_ownership("position", identity)

    def _clear_paper_position_ownership(position: PaperPosition) -> None:
        if position.symbol is None:
            return
        identity = _position_identity("paper", position.symbol, position.direction)
        strategy_instance_repository.delete_trade_ownership("position", identity)

    def _enrich_exchange_snapshot(snapshot: ExchangeSnapshot) -> ExchangeSnapshot:
        def _strategy_name(ownership: TradeOwnership | None) -> str | None:
            if ownership is None or ownership.instance_id is None:
                return None
            try:
                return strategy_instance_repository.get(ownership.instance_id).name
            except LookupError:
                return None

        enriched_positions = []
        for position in snapshot.positions:
            identity = _position_identity(snapshot.mode, position.contract, position.side)
            ownership = strategy_instance_repository.trade_ownership(
                "position", identity
            )
            enriched_positions.append(
                position.model_copy(
                    update={
                        "managed_by_rangebot": ownership is not None,
                        "origin": ownership.origin if ownership else None,
                        "instance_id": ownership.instance_id if ownership else None,
                        "run_id": ownership.run_id if ownership else None,
                        "strategy_name": _strategy_name(ownership),
                        "ownership_created_at": (
                            ownership.created_at if ownership else None
                        ),
                        "trailing_stop_price": (
                            ownership.trailing_stop_price if ownership else None
                        ),
                        "trailing_stop_distance": (
                            ownership.trailing_stop_distance if ownership else None
                        ),
                        "trailing_state": (
                            ownership.trailing_state if ownership else None
                        ),
                        "trailing_order_id": (
                            ownership.trailing_order_id if ownership else None
                        ),
                        "trailing_last_error": (
                            ownership.trailing_last_error if ownership else None
                        ),
                    }
                )
            )

        enriched_orders = []
        for order in snapshot.open_orders:
            ownership = strategy_instance_repository.trade_ownership(
                "order", order.order_id
            )
            enriched_orders.append(
                order.model_copy(
                    update={
                        "managed_by_rangebot": (
                            order.managed_by_rangebot or ownership is not None
                        ),
                        "origin": ownership.origin if ownership else None,
                        "instance_id": ownership.instance_id if ownership else None,
                        "run_id": ownership.run_id if ownership else None,
                        "strategy_name": _strategy_name(ownership),
                    }
                )
            )
        return snapshot.model_copy(
            update={
                "positions": tuple(enriched_positions),
                "open_orders": tuple(enriched_orders),
            }
        )

    def _exchange_state(mode: TradingMode) -> ModeState:
        snapshot = exchange_repository.get_snapshot(mode)
        if snapshot is not None:
            snapshot = _enrich_exchange_snapshot(snapshot)
        return mode_state(
            mode,
            snapshot,
            exchange_repository.emergency_stop(mode),
        )

    def _persist_mock_state(mode: TradingMode) -> None:
        if isinstance(gate_adapter, MockGateIoAdapter):
            exchange_repository.save_adapter_state(mode, gate_adapter.export_state())

    def _credentials_changed(mode: TradingMode) -> None:
        exchange_repository.invalidate_snapshot(mode)
        if (
            private_websocket_service is not None
            and private_stream_status.snapshot().mode == mode
        ):
            private_websocket_service.request_reconnect()

    def _managed_operation(
        mode: TradingMode, kind: str, operation: Callable[[], ExchangeOperationResult]
    ) -> ExchangeOperationResult:
        client_request_id = str(uuid4())
        exchange_repository.persist_intent(mode, client_request_id, kind, "{}")
        try:
            result = operation()
        except Exception as error:
            exchange_repository.mark_intent(client_request_id, "pending_unknown")
            raise HTTPException(
                status_code=503,
                detail="نتيجة العملية غير معروفة؛ يلزم إجراء المصالحة.",
            ) from error
        exchange_repository.mark_intent(
            client_request_id,
            "accepted" if result.accepted else "rejected",
        )
        return result.model_copy(update={"client_request_id": client_request_id})

    def _mock_adapter() -> MockGateIoAdapter:
        if not isinstance(gate_adapter, MockGateIoAdapter):
            raise HTTPException(
                status_code=503,
                detail="مسار التشغيل التلقائي المحلي متاح في Mock فقط.",
            )
        return gate_adapter

    def _snapshot_revision_payload(snapshot: object) -> str:
        payload = cast(
            ExchangeSnapshot,
            snapshot,
        ).model_dump(
            mode="json",
            exclude={"reconciled_at", "market_observed_at"},
        )
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _order_account_context(
        environment: Literal["paper", "testnet", "live"],
        origin: OrderOrigin,
    ) -> OrderAccountContext:
        if environment == "paper":
            try:
                account = paper_repository.get()
                risk = paper_repository.risk_snapshot()
                emergency = paper_repository.emergency_state()
            except LookupError:
                return OrderAccountContext(
                    environment="paper",
                    account_ready=False,
                    credentials_configured=True,
                    available_balance=Decimal("0"),
                    existing_position_quantity=Decimal("0"),
                    one_way_confirmed=True,
                    daily_risk_allowed=False,
                    emergency_stop=False,
                    reconciliation_ready=True,
                    protection_ready=True,
                    account_revision="paper-uninitialized",
                )
            protection_ready = (
                account.position_quantity == 0
                or account.protection_state == "protected"
            )
            return OrderAccountContext(
                environment="paper",
                account_ready=True,
                credentials_configured=True,
                available_balance=account.available_futures_balance,
                existing_position_quantity=account.position_quantity,
                one_way_confirmed=True,
                daily_risk_allowed=(
                    not risk.manual_entries_blocked
                    if origin == "manual"
                    else not risk.automatic_entries_blocked
                ),
                emergency_stop=emergency.active,
                reconciliation_ready=True,
                protection_ready=protection_ready,
                account_revision=(
                    f"paper-{account.revision}-{risk.day}-"
                    f"{risk.realized_net_loss}-{risk.losing_trades}"
                ),
            )

        mode = cast(TradingMode, environment)
        adapter_mode_matches = (
            exchange_adapter_mode is None or exchange_adapter_mode == mode
        )
        credentials_configured = (
            load_gate_credentials(mode) is not None
            or (
                isinstance(gate_adapter, MockGateIoAdapter)
                and origin != "manual"
            )
        )
        if not adapter_mode_matches:
            return OrderAccountContext(
                environment=environment,
                account_ready=False,
                adapter_mode_matches=False,
                credentials_configured=credentials_configured,
                available_balance=Decimal("0"),
                existing_position_quantity=Decimal("0"),
                one_way_confirmed=False,
                daily_risk_allowed=False,
                emergency_stop=exchange_repository.emergency_stop(mode),
                reconciliation_ready=False,
                protection_ready=False,
                account_revision=(
                    f"{environment}-adapter-mode-{exchange_adapter_mode}"
                ),
            )
        reconciliation_succeeded = False
        snapshot = None
        try:
            snapshot = gate_adapter.reconcile(mode)
            _save_exchange_snapshot(snapshot)
            reconciliation_succeeded = True
        except Exception:
            snapshot = exchange_repository.get_snapshot(mode)
        if snapshot is None:
            return OrderAccountContext(
                environment=environment,
                account_ready=False,
                credentials_configured=credentials_configured,
                available_balance=Decimal("0"),
                existing_position_quantity=Decimal("0"),
                one_way_confirmed=False,
                daily_risk_allowed=False,
                emergency_stop=exchange_repository.emergency_stop(mode),
                reconciliation_ready=False,
                protection_ready=False,
                account_revision=f"{environment}-missing-snapshot",
            )
        account_risk = account_risk_service.status(environment)
        risk_allowed = (
            not account_risk.manual_entries_blocked
            if origin == "manual"
            else not account_risk.automatic_entries_blocked
        )
        reconciliation_ready = (
            reconciliation_succeeded
            and snapshot.reconciliation_error is None
            and not snapshot.unmanaged_state
            and snapshot.one_way_confirmed
            and snapshot.cross_margin_confirmed
            and snapshot.risk_ready
            and snapshot.daily_baseline_ready
            and account_risk.baseline_ready
            and snapshot.protection_ready
            and snapshot.subscription_confirmed
            and snapshot.rest_snapshot_confirmed
        )
        risk_revision = (
            f"risk-{account_risk.policy.revision}-{account_risk.day}-"
            f"{account_risk.equity_loss_used}-{account_risk.losing_trades}-"
            f"{account_risk.automatic_trades}"
        )
        return OrderAccountContext(
            environment=environment,
            account_ready=True,
            credentials_configured=credentials_configured,
            available_balance=snapshot.available_futures_balance,
            existing_position_quantity=snapshot.position_quantity,
            one_way_confirmed=snapshot.one_way_confirmed,
            daily_risk_allowed=(
                snapshot.risk_ready
                and snapshot.daily_baseline_ready
                and risk_allowed
            ),
            emergency_stop=exchange_repository.emergency_stop(mode),
            reconciliation_ready=reconciliation_ready,
            protection_ready=snapshot.protection_ready,
            account_revision=f"{_snapshot_revision_payload(snapshot)}-{risk_revision}",
        )

    def _execute_order(
        environment: Literal["paper", "testnet", "live"],
        request: ExchangeEntryRequest,
    ) -> ExchangeOperationResult:
        if environment == "paper":
            market = normalized_market_data.snapshot(request.symbol)
            rules = _order_contract_rules(request.symbol, "paper")
            if request.order_type == "limit":
                paper_repository.enter_central_limit(
                    request,
                    placement_price=market.last_price,
                    contract_multiplier=rules.contract_multiplier,
                )
                return ExchangeOperationResult(
                    accepted=True,
                    client_request_id=request.client_request_id,
                    order_id=f"paper-{request.client_request_id}",
                    message_ar="تم إنشاء أمر Paper Limit بعد التحقق المركزي.",
                )
            fill_price = (
                market.best_ask
                if request.direction == "long" and market.best_ask is not None
                else market.best_bid
                if request.direction == "short" and market.best_bid is not None
                else market.last_price
            )
            paper_repository.enter_central_market(
                request,
                fill_price=fill_price,
                contract_multiplier=rules.contract_multiplier,
            )
            return ExchangeOperationResult(
                accepted=True,
                client_request_id=request.client_request_id,
                order_id=f"paper-{request.client_request_id}",
                message_ar="تم تنفيذ أمر Paper Market بعد التحقق المركزي.",
            )
        mode = cast(TradingMode, environment)
        if exchange_adapter_mode is not None and exchange_adapter_mode != mode:
            return ExchangeOperationResult(
                accepted=False,
                client_request_id=request.client_request_id,
                message_ar="وضع محرك Gate.io لا يطابق بيئة الأمر المطلوبة.",
            )
        exchange_repository.persist_intent(
            mode,
            request.client_request_id,
            f"{request.origin}_entry",
            request.model_dump_json(),
        )
        try:
            result = gate_adapter.submit_entry(mode, request)
        except Exception as error:
            exchange_repository.mark_intent(
                request.client_request_id, "pending_unknown"
            )
            raise RuntimeError(
                "Order result is unknown; reconciliation is required."
            ) from error
        exchange_repository.mark_intent(
            request.client_request_id,
            "accepted" if result.accepted else "rejected",
        )
        _persist_mock_state(mode)
        try:
            _save_exchange_snapshot(gate_adapter.reconcile(mode))
        except Exception:
            exchange_repository.invalidate_snapshot(mode)
        return result

    def _record_order_ownership(
        order_id: str,
        client_request_id: str,
        environment: Literal["paper", "testnet", "live"],
        request: ExchangeEntryRequest,
        context: OrderSubmissionContext,
    ) -> None:
        del client_request_id
        ownership = strategy_instance_repository.record_trade_ownership(
            TradeOwnershipCreate(
                identity_kind="order",
                external_identity=order_id,
                origin=context.origin,
                environment=environment,
                symbol=request.symbol,
                direction=request.direction,
                trailing_stop_price=request.trailing_stop_price,
                trailing_stop_distance=request.trailing_stop_distance,
                trailing_state=(
                    "active"
                    if environment == "paper" and request.trailing_stop_distance is not None
                    else "desired"
                    if request.trailing_stop_distance is not None
                    else None
                ),
                instance_id=context.instance_id,
                run_id=context.run_id,
            )
        )
        trade_history_repository.attach_order_ownership(
            environment=environment,
            order_id=order_id,
            origin=ownership.origin,
            instance_id=ownership.instance_id,
            run_id=ownership.run_id,
            strategy_name_snapshot=_strategy_name_snapshot(ownership),
        )
        if environment == "paper":
            if request.order_type == "market":
                _ensure_position_ownership(
                    environment,
                    request.symbol,
                    request.direction,
                    ownership,
                )
            return
        snapshot = exchange_repository.get_snapshot(environment)
        if snapshot is None:
            return
        if any(
            position.contract == request.symbol
            and position.side == request.direction
            and position.quantity != 0
            for position in snapshot.positions
        ):
            _ensure_position_ownership(
                environment,
                request.symbol,
                request.direction,
                ownership,
            )

    def _order_contract_rules(
        symbol: str,
        environment: Literal["paper", "testnet", "live"],
    ) -> FuturesContractRules:
        if environment == "paper" and contract_rules_provider is None:
            public_contract = next(
                (
                    contract
                    for contract in market_provider.eligible_contracts()
                    if contract.symbol == symbol
                ),
                None,
            )
            if public_contract is None:
                raise LookupError(f"No eligible Paper contract rules for {symbol}.")
            fees = paper_repository.fee_schedule()
            return FuturesContractRules(
                symbol=symbol,
                contract_multiplier=Decimal("1"),
                quantity_step=public_contract.quantity_step,
                minimum_quantity=public_contract.minimum_quantity,
                price_step=Decimal("0.00000001"),
                maximum_leverage=10,
                maker_fee_rate=fees.maker_fee_rate,
                taker_fee_rate=fees.taker_fee_rate,
            )

        rules = contract_rule_lookup(symbol)
        if environment != "paper":
            return rules
        fees = paper_repository.fee_schedule()
        return rules.model_copy(
            update={
                "maker_fee_rate": fees.maker_fee_rate,
                "taker_fee_rate": fees.taker_fee_rate,
            }
        )

    central_order_manager = order_manager or OrderManager(
        market_data=normalized_market_data,
        contract_rules=_order_contract_rules,
        account_context=_order_account_context,
        executor=_execute_order,
        record_ownership=_record_order_ownership,
    )
    app.state.order_manager = central_order_manager

    def _strategy_runtime_context(
        instance: StrategyInstance,
    ) -> StrategyEvaluationContext:
        latest_entry = trade_history_repository.latest_entry_time(
            environment=instance.environment,
            contract=instance.symbol,
            instance_id=instance.instance_id,
        )
        candles_since_last_entry: int | None = None
        if latest_entry is not None:
            series = normalized_market_data.candle_series(
                instance.symbol,
                instance.timeframe_minutes,
            )
            candles_since_last_entry = sum(
                1
                for candle in series.candles
                if candle.closed and candle.closed_at > latest_entry
            )
        market_snapshot = normalized_market_data.snapshot(instance.symbol)
        if instance.environment == "paper":
            reconciliation_ready = True
            emergency_stop = paper_repository.emergency_state().active
        else:
            snapshot = exchange_repository.get_snapshot(instance.environment)
            reconciliation_ready = bool(
                snapshot is not None
                and snapshot.reconciliation_error is None
                and snapshot.rest_snapshot_confirmed
            )
            emergency_stop = exchange_repository.emergency_stop(instance.environment)
        return normalized_market_data.strategy_context(
            instance.symbol,
            instance.timeframe_minutes,
            evaluated_at=market_snapshot.received_at,
            reconciliation_ready=reconciliation_ready,
            emergency_stop=emergency_stop,
            candles_since_last_entry=candles_since_last_entry,
        )

    app.state.strategy_runtime_runner = StrategyRuntimeRunner(
        instance_repository=strategy_instance_repository,
        strategy_registry=registered_strategies,
        strategy_manager=strategy_manager,
        market_data_manager=normalized_market_data,
        order_manager=central_order_manager,
        context_builder=_strategy_runtime_context,
        execution_plan_resolver=lambda instance: (
            strategy_workflow_repository.execution_plan_for_instance(
                instance.instance_id
            )
        ),
    )

    @app.post("/v1/exchange/{mode}/automatic/start", response_model=ModeState)
    def start_exchange_automatic(
        mode: TradingMode, request: AutomaticStartRequest
    ) -> ModeState:
        current = _exchange_state(mode)
        if current.blocked_reasons_ar:
            raise HTTPException(
                status_code=409, detail=" ".join(current.blocked_reasons_ar)
            )
        adapter = _mock_adapter()
        try:
            adapter.start_automatic(request.active_contract)
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        _persist_mock_state(mode)
        _save_exchange_snapshot(adapter.reconcile(mode))
        return _exchange_state(mode)

    @app.post("/v1/exchange/{mode}/automatic/signal", response_model=ModeState)
    def consume_exchange_signal(
        mode: TradingMode, request: AutomaticSignalRequest
    ) -> ModeState:
        adapter = _mock_adapter()
        try:
            adapter.consume_automatic_signal(request.symbol, request.direction)
            mock_quote = adapter.market_guard_quote(
                mode,
                MarketGuardQuoteRequest(
                    symbol=request.symbol,
                    direction=request.direction,
                    quantity=request.quantity,
                ),
            )
            normalized_market_data.apply_rest_snapshot(
                MarketPriceUpdate(
                    symbol=request.symbol,
                    last_price=mock_quote.last_price,
                    mark_price=mock_quote.last_price,
                    best_bid=(
                        mock_quote.bids[0].price if mock_quote.bids else None
                    ),
                    best_ask=(
                        mock_quote.asks[0].price if mock_quote.asks else None
                    ),
                    observed_at=mock_quote.last_price_observed_at,
                    source="gate_rest",
                )
            )
            preview_request = ManualOrderPreviewRequest(
                environment=mode,
                symbol=request.symbol,
                direction=request.direction,
                order_type=request.order_type,
                size_mode="quantity",
                quantity=request.quantity,
                leverage=request.leverage,
                limit_price=request.limit_price,
                time_in_force=request.time_in_force,
            )
            if (request.instance_id is None) != (request.run_id is None):
                raise ValueError(
                    "Automatic strategy ownership requires both instance_id and run_id."
                )
            origin: Literal["automatic_strategy", "legacy_automatic"] = (
                "automatic_strategy"
                if request.instance_id is not None
                else "legacy_automatic"
            )
            result = central_order_manager.submit_automatic(
                preview_request,
                origin=origin,
                instance_id=request.instance_id,
                run_id=request.run_id,
            )
            if not result.accepted:
                raise HTTPException(status_code=503, detail=result.message_ar)
            return _exchange_state(mode)
        except OrderValidationError as error:
            adapter.used_signals.discard((request.symbol, request.direction))
            raise HTTPException(
                status_code=409,
                detail={
                    "message_ar": "فشل الأمر التلقائي في التحقق المركزي.",
                    "validation_issues": [
                        issue.model_dump(mode="json")
                        for issue in error.preview.validation_issues
                    ],
                },
            ) from error
        except (LookupError, ValueError, RuntimeError, HTTPException) as error:
            adapter.used_signals.discard((request.symbol, request.direction))
            if isinstance(error, HTTPException):
                raise
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post(
        "/v1/exchange/{mode}/verification",
        response_model=ExchangeVerificationRecord,
    )
    def record_exchange_verification(
        mode: TradingMode, request: ExchangeVerificationRequest
    ) -> ExchangeVerificationRecord:
        record = ExchangeVerificationRecord(
            mode=mode,
            recorded_at=datetime.now(UTC),
            engine_build=ENGINE_BUILD_ID,
            safety_fingerprint="rangebot-default-safety-profile",
            evidence=request.evidence,
        )
        exchange_repository.save_verification(mode, record.model_dump(mode="json"))
        return record

    @app.get(
        "/v1/exchange/{mode}/verification",
        response_model=ExchangeVerificationRecord | None,
    )
    def exchange_verification(mode: TradingMode) -> ExchangeVerificationRecord | None:
        value = exchange_repository.verification(mode)
        if value is None:
            return None
        record = ExchangeVerificationRecord.model_validate(value)
        return record.model_copy(
            update={"stale": record.engine_build != ENGINE_BUILD_ID}
        )

    @app.get("/v1/exchange/{mode}/state", response_model=ModeState)
    def exchange_state(mode: TradingMode) -> ModeState:
        return _exchange_state(mode)

    @app.get("/v1/exchange/private-stream", response_model=PrivateStreamState)
    def private_stream_state() -> PrivateStreamState:
        return private_stream_status.snapshot()

    @app.get(
        "/v1/exchange/{mode}/operations",
        response_model=list[ExchangeRequestAudit],
    )
    def exchange_operations(mode: TradingMode) -> list[ExchangeRequestAudit]:
        return exchange_repository.request_audit(mode)

    @app.get(
        "/v1/performance/account/{mode}",
        response_model=AccountPerformanceSeries,
    )
    def account_performance(
        mode: PerformanceMode,
        period: PerformancePeriod = "today",
        maximum_points: int = 1000,
    ) -> AccountPerformanceSeries:
        try:
            return performance_repository.series(
                mode,
                period,
                maximum_points=maximum_points,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/v1/trades", response_model=list[TradeFill])
    def trade_history(
        environment: Literal["paper", "testnet", "live"] | None = None,
        contract: str | None = None,
        instance_id: str | None = None,
        run_id: str | None = None,
        since: datetime | None = None,
        limit: int = 200,
    ) -> list[TradeFill]:
        try:
            return trade_history_repository.list(
                environment=environment,
                contract=contract,
                instance_id=instance_id,
                run_id=run_id,
                since=since,
                limit=limit,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/v1/trades/summary", response_model=TradeHistorySummary)
    def trade_history_summary(
        environment: Literal["paper", "testnet", "live"] | None = None,
        contract: str | None = None,
        instance_id: str | None = None,
        run_id: str | None = None,
        since: datetime | None = None,
    ) -> TradeHistorySummary:
        return trade_history_repository.summary(
            environment=environment,
            contract=contract,
            instance_id=instance_id,
            run_id=run_id,
            since=since,
        )

    @app.get("/v1/activity", response_model=list[ActivityEvent])
    def activity_feed(
        limit: int = 100,
        category: ActivityCategory | None = None,
        environment: TradingMode | None = None,
        strategy_instance_id: str | None = None,
        symbol: str | None = None,
        since: datetime | None = None,
    ) -> list[ActivityEvent]:
        return activity_feed_service.list(
            ActivityQuery(
                limit=limit,
                category=category,
                environment=environment,
                strategy_instance_id=strategy_instance_id,
                symbol=symbol,
                since=since,
            )
        )

    @app.post("/v1/exchange/{mode}/reconcile", response_model=ModeState)
    def reconcile_exchange(mode: TradingMode) -> ModeState:
        """Only a configured adapter may supply authoritative exchange state."""
        snapshot = gate_adapter.reconcile(mode)
        _save_exchange_snapshot(snapshot)
        _persist_mock_state(mode)
        return _exchange_state(mode)

    @app.post("/v1/exchange/credentials", response_model=ExchangeCredentialStatus)
    def store_exchange_credentials(
        request: ExchangeCredentialRequest,
    ) -> ExchangeCredentialStatus:
        try:
            save_gate_credentials(request.mode, request.api_key, request.api_secret)
        except (OSError, RuntimeError, ValueError) as error:
            raise HTTPException(
                status_code=503,
                detail="تعذر حفظ بيانات الحساب في مخزن Windows الآمن.",
            ) from error
        _credentials_changed(request.mode)
        return ExchangeCredentialStatus(mode=request.mode, configured=True)

    @app.get("/v1/exchange/{mode}/credentials", response_model=ExchangeCredentialStatus)
    def exchange_credential_status(mode: TradingMode) -> ExchangeCredentialStatus:
        return ExchangeCredentialStatus(
            mode=mode, configured=load_gate_credentials(mode) is not None
        )

    @app.delete(
        "/v1/exchange/{mode}/credentials", response_model=ExchangeCredentialStatus
    )
    def delete_exchange_credentials(mode: TradingMode) -> ExchangeCredentialStatus:
        remove_gate_credentials(mode)
        _credentials_changed(mode)
        return ExchangeCredentialStatus(mode=mode, configured=False)

    @app.post(
        "/v1/exchange/{mode}/credentials/test",
        response_model=ExchangeCredentialTestResult,
    )
    def test_exchange_credentials(mode: TradingMode) -> ExchangeCredentialTestResult:
        if load_gate_credentials(mode) is None:
            raise HTTPException(status_code=409, detail="بيانات Gate.io غير محفوظة.")
        try:
            snapshot = test_adapter_factory(mode).reconcile(mode)
        except Exception as error:
            raise HTTPException(
                status_code=503,
                detail="تعذر اختبار بيانات Gate.io حالياً.",
            ) from error
        if snapshot.reconciliation_error:
            return ExchangeCredentialTestResult(
                mode=mode,
                valid=False,
                message_ar="فشل اختبار بيانات Gate.io دون إجراء أي تداول.",
            )
        return ExchangeCredentialTestResult(
            mode=mode,
            valid=True,
            message_ar="تم التحقق من بيانات Gate.io بعملية قراءة فقط.",
        )

    @app.post("/v1/exchange/{mode}/emergency-stop", response_model=ModeState)
    def exchange_emergency_stop(mode: TradingMode) -> ModeState:
        # Only adapter-owned pending entries may be cancelled; unmanaged state is never touched.
        exchange_repository.set_emergency_stop(mode, True)
        _managed_operation(
            mode,
            "emergency_cancel_entry",
            lambda: gate_adapter.cancel_managed_entry(mode),
        )
        _persist_mock_state(mode)
        _save_exchange_snapshot(gate_adapter.reconcile(mode))
        return _exchange_state(mode)

    @app.post("/v1/exchange/{mode}/resume", response_model=ModeState)
    def exchange_resume(mode: TradingMode, confirmation: str) -> ModeState:
        if confirmation != "RESUME":
            raise HTTPException(status_code=422, detail="يلزم إدخال RESUME حرفياً.")
        snapshot = gate_adapter.reconcile(mode)
        _save_exchange_snapshot(snapshot)
        if (
            snapshot.reconciliation_error
            or snapshot.unmanaged_state
            or not snapshot.protection_ready
        ):
            raise HTTPException(
                status_code=409,
                detail="لا يمكن الاستئناف قبل اكتمال المصالحة والحماية.",
            )
        exchange_repository.set_emergency_stop(mode, False)
        _persist_mock_state(mode)
        return _exchange_state(mode)

    @app.post("/v1/live/protection", response_model=ModeState)
    def change_live_protection(request: ProtectionChangeRequest) -> ModeState:
        if not request.enabled:
            expected = "DISABLE TP" if request.protection == "tp" else "DISABLE SL"
            if request.confirmation != expected:
                raise HTTPException(
                    status_code=422, detail=f"يلزم إدخال {expected} حرفياً."
                )
        result = _managed_operation(
            "live",
            f"set_{request.protection}_protection",
            lambda: gate_adapter.set_protection_enabled(
                "live", request.protection, request.enabled
            ),
        )
        if not result.accepted:
            raise HTTPException(status_code=503, detail=result.message_ar)
        snapshot = gate_adapter.reconcile("live")
        _save_exchange_snapshot(snapshot)
        _persist_mock_state("live")
        return _exchange_state("live")

    @app.post(
        "/v1/exchange/{mode}/protection/check", response_model=ExchangeOperationResult
    )
    def check_exchange_protection(mode: TradingMode) -> ExchangeOperationResult:
        result = _managed_operation(
            mode, "ensure_protection", lambda: gate_adapter.ensure_protection(mode)
        )
        _save_exchange_snapshot(gate_adapter.reconcile(mode))
        _persist_mock_state(mode)
        return result

    @app.post("/v1/live/entries", response_model=ModeState)
    def submit_live_entry(request: LiveEntryRequest) -> ModeState:
        return _submit_exchange_entry("live", request)

    @app.post("/v1/exchange/{mode}/entries", response_model=ModeState)
    def submit_exchange_entry(
        mode: TradingMode, request: LiveEntryRequest
    ) -> ModeState:
        return _submit_exchange_entry(mode, request)

    @app.post("/v1/exchange/market-entry-guard", response_model=MarketEntryGuardResult)
    def preview_market_entry_guard(
        request: MarketEntryGuardRequest,
    ) -> MarketEntryGuardResult:
        return guard_market_entry(request)

    @app.post(
        "/v1/exchange/{mode}/market-guard-quote",
        response_model=MarketEntryGuardRequest,
    )
    def exchange_market_guard_quote(
        mode: TradingMode, request: MarketGuardQuoteRequest
    ) -> MarketEntryGuardRequest:
        try:
            return gate_adapter.market_guard_quote(mode, request)
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    def _submit_exchange_entry(
        mode: TradingMode, request: LiveEntryRequest
    ) -> ModeState:
        state = _exchange_state(mode)
        if state.blocked_reasons_ar:
            raise HTTPException(
                status_code=409, detail=" ".join(state.blocked_reasons_ar)
            )
        if (
            state.snapshot is not None
            and state.snapshot.leverage_confirmed != request.leverage
        ):
            raise HTTPException(
                status_code=409,
                detail="الرافعة المختارة لا تطابق رافعة الحساب المصالَحة.",
            )
        globally_unprotected = bool(
            state.snapshot
            and not state.snapshot.tp_enabled
            and not state.snapshot.sl_enabled
        )
        if (
            mode == "live"
            and (not request.protections_enabled or globally_unprotected)
            and request.confirmation != "UNPROTECTED POSITION"
        ):
            raise HTTPException(
                status_code=422, detail="يلزم إدخال UNPROTECTED POSITION حرفياً."
            )
        if request.order_type == "market":
            try:
                authoritative_quote = gate_adapter.market_guard_quote(
                    mode,
                    MarketGuardQuoteRequest(
                        symbol=request.symbol,
                        direction=request.direction,
                        quantity=request.quantity,
                    ),
                )
            except RuntimeError as error:
                raise HTTPException(status_code=503, detail=str(error)) from error
            guard = guard_market_entry(authoritative_quote)
            if not guard.allowed:
                raise HTTPException(status_code=409, detail=guard.reason_ar)
        client_request_id = request.client_request_id or str(uuid4())
        prior_status = exchange_repository.intent_status(client_request_id)
        if prior_status == "pending_unknown":
            raise HTTPException(
                status_code=409,
                detail="نتيجة الطلب السابق غير معروفة؛ يلزم إجراء المصالحة قبل المحاولة.",
            )
        exchange_request = ExchangeEntryRequest(
            symbol=request.symbol,
            direction=request.direction,
            order_type=request.order_type,
            quantity=request.quantity,
            limit_price=request.limit_price,
            client_request_id=client_request_id,
            protections_enabled=request.protections_enabled,
            leverage=request.leverage,
            take_profit_percentage=request.take_profit_percentage,
            stop_loss_percentage=request.stop_loss_percentage,
        )
        exchange_repository.persist_intent(
            mode,
            exchange_request.client_request_id,
            "entry",
            exchange_request.model_dump_json(),
        )
        try:
            result = gate_adapter.submit_entry(mode, exchange_request)
        except Exception as error:
            exchange_repository.mark_intent(
                exchange_request.client_request_id, "pending_unknown"
            )
            raise HTTPException(
                status_code=503,
                detail="نتيجة إرسال أمر الدخول غير معروفة؛ يلزم إجراء المصالحة.",
            ) from error
        exchange_repository.mark_intent(
            exchange_request.client_request_id,
            (
                "accepted"
                if result.accepted
                else "pending_unknown"
                if result.pending_unknown
                else "rejected"
            ),
        )
        _persist_mock_state(mode)
        if not result.accepted:
            raise HTTPException(status_code=503, detail=result.message_ar)
        _save_exchange_snapshot(gate_adapter.reconcile(mode))
        return _exchange_state(mode)

    @app.post(
        "/v1/exchange/{mode}/cancel-entry", response_model=ExchangeOperationResult
    )
    def cancel_exchange_entry(mode: TradingMode) -> ExchangeOperationResult:
        result = _managed_operation(
            mode, "cancel_entry", lambda: gate_adapter.cancel_managed_entry(mode)
        )
        _persist_mock_state(mode)
        _save_exchange_snapshot(gate_adapter.reconcile(mode))
        return result

    @app.post("/v1/exchange/{mode}/close", response_model=ExchangeOperationResult)
    def close_exchange_position(
        mode: TradingMode, request: ExchangeCloseRequest
    ) -> ExchangeOperationResult:
        if request.confirmation != "CLOSE POSITION":
            raise HTTPException(
                status_code=422, detail="يلزم إدخال CLOSE POSITION حرفياً."
            )
        result = _managed_operation(
            mode,
            "manual_close",
            lambda: gate_adapter.close_managed_position(mode),
        )
        _persist_mock_state(mode)
        _save_exchange_snapshot(gate_adapter.reconcile(mode))
        return result

    @app.post(
        "/v1/exchange/{mode}/emergency-close", response_model=ExchangeOperationResult
    )
    def emergency_close_exchange(mode: TradingMode) -> ExchangeOperationResult:
        """Persist the stop first; close only after a current safe reconciliation state."""
        exchange_repository.set_emergency_stop(mode, True)
        _managed_operation(
            mode,
            "emergency_cancel_entry",
            lambda: gate_adapter.cancel_managed_entry(mode),
        )
        snapshot = gate_adapter.reconcile(mode)
        _save_exchange_snapshot(snapshot)
        if snapshot.reconciliation_error or snapshot.unmanaged_state:
            raise HTTPException(
                status_code=409, detail="تعذر الإغلاق الطارئ حتى تكتمل المصالحة الآمنة."
            )
        result = ExchangeOperationResult(
            accepted=True,
            client_request_id="emergency-close-empty",
            message_ar="لا يوجد مركز مُدار مفتوح.",
        )
        final_snapshot = snapshot
        for _ in range(8):
            if final_snapshot.position_quantity == 0:
                break
            result = _managed_operation(
                mode,
                "emergency_close",
                lambda: gate_adapter.close_managed_position(mode),
            )
            if not result.accepted:
                break
            final_snapshot = gate_adapter.reconcile(mode)
            _save_exchange_snapshot(final_snapshot)
        _persist_mock_state(mode)
        if result.accepted and (
            final_snapshot.position_quantity != 0
            or bool(final_snapshot.managed_order_ids)
        ):
            raise HTTPException(
                status_code=503,
                detail="لم يكتمل الإغلاق الطارئ إلى مركز صفري وأوامر مُدارة صفرية.",
            )
        return result

    @app.get(
        "/v1/market-data/{symbol}/status", response_model=MarketDataStatus
    )
    def market_data_status(symbol: str) -> MarketDataStatus:
        return normalized_market_data.status(symbol)

    @app.get(
        "/v1/market-data/{symbol}/candles/{timeframe_minutes}",
        response_model=MarketCandleSeries,
    )
    def market_candles(
        symbol: str, timeframe_minutes: int
    ) -> MarketCandleSeries:
        try:
            return normalized_market_data.candle_series(symbol, timeframe_minutes)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/v1/market-data/{symbol}", response_model=MarketDataSnapshot)
    def market_data_snapshot(symbol: str) -> MarketDataSnapshot:
        try:
            return normalized_market_data.snapshot(symbol)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get(
        "/v1/futures/contracts/{symbol}/rules",
        response_model=FuturesContractRules,
    )
    def futures_contract_rules(symbol: str) -> FuturesContractRules:
        try:
            return contract_rule_lookup(symbol)
        except LookupError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid Gate contract rules: {error}",
            ) from error

    @app.post(
        "/v1/strategies/fixed-price-ladder/preview",
        response_model=FixedPriceLadderPreview,
    )
    def fixed_price_ladder_preview(
        config: FixedPriceLadderConfig,
    ) -> FixedPriceLadderPreview:
        """Return an authoritative, read-only ladder activation preview."""
        try:
            market = normalized_market_data.snapshot(config.contract_symbol)
            rules = _order_contract_rules(config.contract_symbol, config.environment)
            account = _order_account_context(config.environment, "automatic_strategy")
            return build_ladder_preview(
                config,
                rules,
                available_balance=account.available_balance,
                market_price=market.last_price,
                market_state=market.state,
                best_ask=market.best_ask,
                unmanaged_position=account.existing_position_quantity != 0,
            )
        except LookupError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post(
        "/v1/manual-orders/preview", response_model=ManualOrderPreview
    )
    def preview_manual_order(
        request: ManualOrderPreviewRequest,
    ) -> ManualOrderPreview:
        try:
            return central_order_manager.preview(request)
        except LookupError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post(
        "/v1/manual-orders", response_model=ManualOrderSubmissionResult
    )
    def submit_manual_order(
        submission: ManualOrderSubmissionRequest,
    ) -> ManualOrderSubmissionResult:
        try:
            return central_order_manager.submit(submission)
        except StaleOrderPreviewError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except OrderValidationError as error:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": str(error),
                    "preview": error.preview.model_dump(mode="json"),
                },
            ) from error
        except LookupError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    def _strategy_instance_or_404(instance_id: str) -> StrategyInstance:
        try:
            return strategy_instance_repository.get(instance_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    def _validate_strategy_configuration(
        type_id: str,
        configuration: dict[str, object],
        timeframe_minutes: int,
        direction: str,
    ) -> None:
        try:
            metadata = registered_strategies.get(type_id)
            effective = dict(configuration)
            properties = metadata.configuration_schema.get("properties", {})
            if "timeframe_minutes" in properties:
                effective["timeframe_minutes"] = timeframe_minutes
            if "direction" in properties:
                effective["direction"] = {
                    "long": "long_only",
                    "short": "short_only",
                    "both": "both",
                }[direction]
            registered_strategies.validate_configuration(type_id, effective)
        except LookupError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid strategy configuration: {error}",
            ) from error

    def _transition_strategy(
        instance_id: str, target: StrategyLifecycle
    ) -> StrategyInstance:
        _strategy_instance_or_404(instance_id)
        try:
            deployment = strategy_workflow_repository.deployment_for_instance(instance_id)
            deployment_action = {
                "running": "start",
                "paused": "pause",
                "stopped": "stop",
            }.get(target)
            if deployment is not None and deployment_action is not None:
                strategy_workflow_repository.transition_deployment(
                    deployment.deployment_id, deployment_action
                )
                return strategy_instance_repository.get(instance_id)
            if target == "running":
                strategy_workflow_repository.ensure_instance_can_start(instance_id)
            return strategy_instance_repository.transition(instance_id, target)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    def _workflow_http_exception(error: Exception) -> HTTPException:
        if isinstance(error, LookupError):
            return HTTPException(status_code=404, detail=str(error))
        if isinstance(error, ValueError):
            return HTTPException(status_code=422, detail=str(error))
        if isinstance(error, RuntimeError):
            return HTTPException(status_code=409, detail=str(error))
        return HTTPException(status_code=500, detail=str(error))

    def _setup_price(symbol: str) -> tuple[Decimal | None, datetime | None, str]:
        try:
            snapshot = normalized_market_data.snapshot(symbol)
        except LookupError:
            return None, None, "unavailable"
        return (
            snapshot.last_price,
            snapshot.observed_at,
            price_state_from_market_state(snapshot.state),
        )

    @app.get("/v1/workflow/summary", response_model=WorkflowSummary)
    def workflow_summary() -> WorkflowSummary:
        return strategy_workflow_repository.summary()

    @app.get("/v1/strategy-templates", response_model=list[StrategyTemplate])
    def strategy_templates(include_archived: bool = False) -> list[StrategyTemplate]:
        return strategy_workflow_repository.list_templates(include_archived)

    @app.post(
        "/v1/strategy-templates",
        response_model=StrategyTemplate,
        status_code=201,
    )
    def create_strategy_template(change: StrategyTemplateCreate) -> StrategyTemplate:
        try:
            return strategy_workflow_repository.create_template(change)
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.get(
        "/v1/strategy-templates/{template_id}", response_model=StrategyTemplate
    )
    def strategy_template(template_id: str) -> StrategyTemplate:
        try:
            return strategy_workflow_repository.get_template(template_id)
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.put(
        "/v1/strategy-templates/{template_id}", response_model=StrategyTemplate
    )
    def update_strategy_template(
        template_id: str, change: StrategyTemplateUpdate
    ) -> StrategyTemplate:
        try:
            return strategy_workflow_repository.update_template(template_id, change)
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.get(
        "/v1/strategy-templates/{template_id}/versions",
        response_model=list[StrategyTemplateVersion],
    )
    def strategy_template_versions(
        template_id: str,
    ) -> list[StrategyTemplateVersion]:
        try:
            return strategy_workflow_repository.template_versions(template_id)
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.post(
        "/v1/strategy-templates/{template_id}/archive",
        response_model=StrategyTemplate,
    )
    def archive_strategy_template(template_id: str) -> StrategyTemplate:
        try:
            return strategy_workflow_repository.archive_template(template_id)
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.delete("/v1/strategy-templates/{template_id}", status_code=204)
    def delete_strategy_template(template_id: str) -> None:
        try:
            strategy_workflow_repository.delete_template(template_id)
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.get("/v1/strategy-setups", response_model=list[StrategyCoinSetup])
    def strategy_setups(
        template_id: str | None = None,
        include_archived: bool = False,
    ) -> list[StrategyCoinSetup]:
        try:
            return strategy_workflow_repository.list_setups(
                template_id=template_id,
                include_archived=include_archived,
            )
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.post(
        "/v1/strategy-setups",
        response_model=StrategyCoinSetup,
        status_code=201,
    )
    def create_strategy_setup(change: StrategyCoinSetupCreate) -> StrategyCoinSetup:
        price, observed_at, state = _setup_price(change.symbol)
        try:
            created = strategy_workflow_repository.create_setup(
                change,
                current_price=price,
                price_observed_at=observed_at,
                price_state=state,
            )
            _sync_market_subscriptions()
            return created
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.get("/v1/strategy-setups/{setup_id}", response_model=StrategyCoinSetup)
    def strategy_setup(setup_id: str) -> StrategyCoinSetup:
        try:
            return strategy_workflow_repository.get_setup(setup_id)
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.put("/v1/strategy-setups/{setup_id}", response_model=StrategyCoinSetup)
    def update_strategy_setup(
        setup_id: str, change: StrategyCoinSetupUpdate
    ) -> StrategyCoinSetup:
        try:
            updated = strategy_workflow_repository.update_setup(setup_id, change)
            if change.symbol is not None:
                price, observed_at, state = _setup_price(updated.symbol)
                updated = strategy_workflow_repository.update_setup_price(
                    setup_id,
                    current_price=price,
                    observed_at=observed_at,
                    price_state=state,
                )
            _sync_market_subscriptions()
            return updated
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.post(
        "/v1/strategy-setups/{setup_id}/reset-defaults",
        response_model=StrategyCoinSetup,
    )
    def reset_strategy_setup_defaults(setup_id: str) -> StrategyCoinSetup:
        try:
            return strategy_workflow_repository.reset_setup_defaults(setup_id)
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.post(
        "/v1/strategy-setups/{setup_id}/rebase",
        response_model=StrategyCoinSetup,
    )
    def rebase_strategy_setup(setup_id: str) -> StrategyCoinSetup:
        try:
            return strategy_workflow_repository.rebase_setup(setup_id)
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.post(
        "/v1/strategy-setups/{setup_id}/refresh-price",
        response_model=StrategyCoinSetup,
    )
    def refresh_strategy_setup_price(setup_id: str) -> StrategyCoinSetup:
        try:
            current = strategy_workflow_repository.get_setup(setup_id)
            price, observed_at, state = _setup_price(current.symbol)
            return strategy_workflow_repository.update_setup_price(
                setup_id,
                current_price=price,
                observed_at=observed_at,
                price_state=state,
            )
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.get(
        "/v1/strategy-setups/{setup_id}/versions",
        response_model=list[StrategyCoinSetupVersion],
    )
    def strategy_setup_versions(setup_id: str) -> list[StrategyCoinSetupVersion]:
        try:
            return strategy_workflow_repository.setup_versions(setup_id)
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.post(
        "/v1/strategy-setups/{setup_id}/archive",
        response_model=StrategyCoinSetup,
    )
    def archive_strategy_setup(setup_id: str) -> StrategyCoinSetup:
        try:
            return strategy_workflow_repository.archive_setup(setup_id)
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.delete("/v1/strategy-setups/{setup_id}", status_code=204)
    def delete_strategy_setup(setup_id: str) -> None:
        try:
            strategy_workflow_repository.delete_setup(setup_id)
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.post(
        "/v1/strategy-setups/{setup_id}/backtests",
        response_model=StoredBacktestRun,
    )
    def run_strategy_setup_backtest(
        setup_id: str, request: SetupBacktestRequest
    ) -> StoredBacktestRun:
        try:
            backtest_request = strategy_workflow_repository.build_backtest_request(
                setup_id, request
            )
            stored = discovery_lab.run_backtest(backtest_request)
            strategy_workflow_repository.record_backtest(setup_id, stored)
            return stored
        except ConnectionError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.post(
        "/v1/strategy-setups/{setup_id}/approve",
        response_model=StrategySetupApproval,
    )
    def approve_strategy_setup(
        setup_id: str, request: SetupApprovalRequest
    ) -> StrategySetupApproval:
        try:
            return strategy_workflow_repository.approve_setup(setup_id, request)
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.get(
        "/v1/strategy-setups/{setup_id}/approvals",
        response_model=list[StrategySetupApproval],
    )
    def strategy_setup_approvals(setup_id: str) -> list[StrategySetupApproval]:
        try:
            return strategy_workflow_repository.approvals(setup_id)
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.post(
        "/v1/strategy-setups/{setup_id}/deployments",
        response_model=BotDeployment,
        status_code=201,
    )
    def create_bot_deployment(
        setup_id: str, request: BotDeploymentCreate
    ) -> BotDeployment:
        try:
            deployment = strategy_workflow_repository.create_deployment(
                setup_id, request
            )
            _sync_market_subscriptions()
            return deployment
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.get("/v1/opportunities", response_model=list[StrategyOpportunity])
    def opportunities(
        status: str | None = None,
        strategy_type_id: str | None = None,
        scan_id: str | None = None,
    ) -> list[StrategyOpportunity]:
        try:
            return strategy_workflow_repository.list_opportunities(
                status=status,
                strategy_type_id=strategy_type_id,
                scan_id=scan_id,
            )
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.get(
        "/v1/opportunities/{opportunity_id}", response_model=StrategyOpportunity
    )
    def opportunity(opportunity_id: str) -> StrategyOpportunity:
        try:
            return strategy_workflow_repository.get_opportunity(opportunity_id)
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.put(
        "/v1/opportunities/{opportunity_id}", response_model=StrategyOpportunity
    )
    def update_opportunity(
        opportunity_id: str, change: OpportunityStatusUpdate
    ) -> StrategyOpportunity:
        try:
            return strategy_workflow_repository.update_opportunity(
                opportunity_id, change
            )
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.post(
        "/v1/opportunities/{opportunity_id}/convert",
        response_model=StrategyCoinSetup,
        status_code=201,
    )
    def convert_opportunity(
        opportunity_id: str, change: OpportunityConversionRequest
    ) -> StrategyCoinSetup:
        try:
            setup = strategy_workflow_repository.convert_opportunity(
                opportunity_id, change
            )
            _sync_market_subscriptions()
            return setup
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.get("/v1/bot-deployments", response_model=list[BotDeployment])
    def bot_deployments() -> list[BotDeployment]:
        return strategy_workflow_repository.list_deployments()

    @app.get(
        "/v1/bot-deployments/{deployment_id}", response_model=BotDeployment
    )
    def bot_deployment(deployment_id: str) -> BotDeployment:
        try:
            return strategy_workflow_repository.get_deployment(deployment_id)
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.post(
        "/v1/bot-deployments/{deployment_id}/{action}",
        response_model=BotDeployment,
    )
    def transition_bot_deployment(deployment_id: str, action: str) -> BotDeployment:
        try:
            deployment = strategy_workflow_repository.transition_deployment(
                deployment_id, action
            )
            _sync_market_subscriptions()
            return deployment
        except Exception as error:
            raise _workflow_http_exception(error) from error

    @app.get("/v1/strategies", response_model=list[StrategyInstance])
    def strategy_instances() -> list[StrategyInstance]:
        return strategy_instance_repository.list()

    @app.get("/v1/strategies/overview", response_model=list[StrategyOverviewItem])
    def strategy_overview() -> list[StrategyOverviewItem]:
        return strategy_overview_service.list()

    @app.post("/v1/strategies", response_model=StrategyInstance, status_code=201)
    def create_strategy_instance(change: StrategyInstanceCreate) -> StrategyInstance:
        _validate_strategy_configuration(
            change.type_id,
            change.configuration,
            change.timeframe_minutes,
            change.direction,
        )
        created = strategy_instance_repository.create(change)
        _sync_market_subscriptions()
        return created

    @app.post(
        "/v1/strategies/{instance_id}/duplicate",
        response_model=StrategyInstance,
        status_code=201,
    )
    def duplicate_strategy_instance(
        instance_id: str, change: StrategyInstanceDuplicate
    ) -> StrategyInstance:
        try:
            duplicated = strategy_instance_repository.duplicate(instance_id, change)
            _sync_market_subscriptions()
            return duplicated
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/v1/strategies/{instance_id}", response_model=StrategyInstance)
    def strategy_instance(instance_id: str) -> StrategyInstance:
        return _strategy_instance_or_404(instance_id)

    @app.get(
        "/v1/strategies/{instance_id}/configuration-versions",
        response_model=list[StrategyConfigurationVersion],
    )
    def strategy_configuration_versions(
        instance_id: str,
    ) -> list[StrategyConfigurationVersion]:
        try:
            return strategy_instance_repository.configuration_versions(instance_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get(
        "/v1/strategies/{instance_id}/runs", response_model=list[StrategyRun]
    )
    def strategy_runs(instance_id: str) -> list[StrategyRun]:
        try:
            return strategy_instance_repository.runs(instance_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get(
        "/v1/strategies/{instance_id}/decisions",
        response_model=list[StrategyDecision],
    )
    def strategy_decisions(
        instance_id: str, limit: int = 100
    ) -> list[StrategyDecision]:
        try:
            return strategy_instance_repository.decisions(instance_id, limit)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.put("/v1/strategies/{instance_id}", response_model=StrategyInstance)
    def update_strategy_instance(
        instance_id: str, change: StrategyInstanceUpdate
    ) -> StrategyInstance:
        current = _strategy_instance_or_404(instance_id)
        _validate_strategy_configuration(
            current.type_id,
            change.configuration
            if change.configuration is not None
            else current.configuration,
            change.timeframe_minutes
            if change.timeframe_minutes is not None
            else current.timeframe_minutes,
            change.direction if change.direction is not None else current.direction,
        )
        try:
            updated = strategy_instance_repository.update(instance_id, change)
            _sync_market_subscriptions()
            return updated
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.delete("/v1/strategies/{instance_id}", status_code=204)
    def delete_strategy_instance(instance_id: str) -> None:
        try:
            strategy_instance_repository.delete(instance_id)
            _sync_market_subscriptions()
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/v1/strategies/{instance_id}/start", response_model=StrategyInstance)
    def start_strategy_instance(instance_id: str) -> StrategyInstance:
        return _transition_strategy(instance_id, "running")

    @app.post("/v1/strategies/{instance_id}/monitor", response_model=StrategyInstance)
    def monitor_strategy_instance(instance_id: str) -> StrategyInstance:
        return _transition_strategy(instance_id, "monitoring")

    @app.post("/v1/strategies/{instance_id}/pause", response_model=StrategyInstance)
    def pause_strategy_instance(instance_id: str) -> StrategyInstance:
        return _transition_strategy(instance_id, "paused")

    @app.post("/v1/strategies/{instance_id}/stop", response_model=StrategyInstance)
    def stop_strategy_instance(instance_id: str) -> StrategyInstance:
        return _transition_strategy(instance_id, "stopped")

    @app.get(
        "/v1/trade-ownership/{identity_kind}/{external_identity}",
        response_model=TradeOwnership,
    )
    def trade_ownership(identity_kind: str, external_identity: str) -> TradeOwnership:
        ownership = strategy_instance_repository.trade_ownership(
            identity_kind, external_identity
        )
        if ownership is None:
            raise HTTPException(status_code=404, detail="Trade ownership is not recorded.")
        return ownership

    @app.get("/v1/strategy-types", response_model=list[StrategyTypeMetadata])
    def strategy_types() -> list[StrategyTypeMetadata]:
        return registered_strategies.list()

    @app.get("/v1/strategy-types/{type_id}", response_model=StrategyTypeMetadata)
    def strategy_type(type_id: str) -> StrategyTypeMetadata:
        try:
            return registered_strategies.get(type_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/v1/discovery/scans", response_model=StoredStrategyScan)
    def run_discovery_scan(request: StrategyScanRequest) -> StoredStrategyScan:
        try:
            stored = discovery_lab.run_scan(request)
            strategy_workflow_repository.ingest_scan(stored)
            return stored
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except ConnectionError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.get("/v1/discovery/scans", response_model=list[StoredStrategyScan])
    def list_discovery_scans(limit: int = 50) -> list[StoredStrategyScan]:
        try:
            return discovery_lab.list_scans(limit)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/v1/discovery/scans/{scan_id}", response_model=StoredStrategyScan)
    def discovery_scan(scan_id: str) -> StoredStrategyScan:
        try:
            return discovery_lab.get_scan(scan_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/v1/backtests", response_model=StoredBacktestRun)
    def run_backtest(request: BacktestRunRequest) -> StoredBacktestRun:
        try:
            return discovery_lab.run_backtest(request)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ConnectionError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.post(
        "/v1/backtests/portfolio/readiness", response_model=BacktestReadiness
    )
    def portfolio_backtest_readiness(
        request: BacktestPortfolioRequest,
    ) -> BacktestReadiness:
        return historical_backtests.readiness(request)

    @app.post(
        "/v1/backtests/portfolio", response_model=StoredPortfolioBacktestRun
    )
    def run_portfolio_backtest(
        request: BacktestPortfolioRequest,
        background_tasks: BackgroundTasks,
    ) -> StoredPortfolioBacktestRun:
        try:
            stored = historical_backtests.enqueue(request)

            def execute_persisted_backtest() -> None:
                try:
                    historical_backtests.execute(stored.backtest_id, stored.request)
                except Exception:
                    # The service already persisted a sanitized failed state.
                    return

            background_tasks.add_task(
                execute_persisted_backtest
            )
            return stored
        except (LookupError, RuntimeError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get(
        "/v1/backtests/portfolio", response_model=list[StoredPortfolioBacktestRun]
    )
    def list_portfolio_backtests(limit: int = 50) -> list[StoredPortfolioBacktestRun]:
        try:
            return historical_backtests.list(limit)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get(
        "/v1/backtests/portfolio/{backtest_id}",
        response_model=StoredPortfolioBacktestRun,
    )
    def portfolio_backtest(backtest_id: str) -> StoredPortfolioBacktestRun:
        try:
            return historical_backtests.get(backtest_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.put(
        "/v1/backtests/portfolio/{backtest_id}/notes",
        response_model=StoredPortfolioBacktestRun,
    )
    def update_portfolio_backtest_notes(
        backtest_id: str,
        change: BacktestPostTestNotesUpdate,
    ) -> StoredPortfolioBacktestRun:
        try:
            return historical_backtests.update_notes(
                backtest_id, change.observations
            )
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/v1/backtests", response_model=list[StoredBacktestRun])
    def list_backtests(limit: int = 50) -> list[StoredBacktestRun]:
        try:
            return discovery_lab.list_backtests(limit)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/v1/backtests/{backtest_id}", response_model=StoredBacktestRun)
    def backtest(backtest_id: str) -> StoredBacktestRun:
        try:
            return discovery_lab.get_backtest(backtest_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get(
        "/v1/backtests/{backtest_id}/trades",
        response_model=list[BacktestTrade],
    )
    def backtest_trades(backtest_id: str) -> list[BacktestTrade]:
        try:
            return research_repository.backtest_trades(backtest_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get(
        "/v1/backtests/{backtest_id}/equity",
        response_model=list[BacktestEquityPoint],
    )
    def backtest_equity(backtest_id: str) -> list[BacktestEquityPoint]:
        try:
            return research_repository.backtest_equity(backtest_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post(
        "/v1/backtests/{backtest_id}/create-strategy",
        response_model=StrategyInstance,
    )
    def create_strategy_from_backtest(
        backtest_id: str,
        request: BacktestStrategyCreateRequest,
    ) -> StrategyInstance:
        try:
            instance = discovery_lab.create_stopped_strategy(backtest_id, request)
            _sync_market_subscriptions()
            return instance
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/v1/settings", response_model=ApplicationSettings)
    def application_settings() -> ApplicationSettings:
        return settings_repository.get()

    @app.get("/v1/settings/overview", response_model=ApplicationSettingsOverview)
    def application_settings_overview() -> ApplicationSettingsOverview:
        try:
            paper_risk = paper_repository.risk_snapshot()
            paper_emergency = paper_repository.emergency_state()
        except LookupError:
            paper_risk = None
            paper_emergency = None
        return ApplicationSettingsOverview(
            application=settings_repository.get(),
            account_risk_policy=account_risk_policy_repository.get(),
            paper_risk=paper_risk,
            paper_emergency_stop=paper_emergency,
            testnet_emergency_stop=exchange_repository.emergency_stop("testnet"),
            live_emergency_stop=exchange_repository.emergency_stop("live"),
        )

    @app.put("/v1/settings", response_model=ApplicationSettings)
    def update_application_settings(
        settings: ApplicationSettingsUpdate,
    ) -> ApplicationSettings:
        return settings_repository.save(settings)

    @app.get("/v1/backups", response_model=list[BackupRecord])
    def list_backups() -> list[BackupRecord]:
        return _require_backup_manager().list()

    @app.post("/v1/backups", response_model=BackupRecord)
    def create_backup() -> BackupRecord:
        try:
            return _require_backup_manager().create("manual")
        except SQLiteBackupError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.delete("/v1/backups/{name}", response_model=BackupDeleteResult)
    def delete_backup(name: str) -> BackupDeleteResult:
        try:
            deleted = _require_backup_manager().delete(name)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return BackupDeleteResult(
            name=name,
            deleted=deleted,
            message_ar=(
                "تم حذف النسخة الاحتياطية."
                if deleted
                else "النسخة الاحتياطية غير موجودة."
            ),
        )

    @app.post("/v1/backups/{name}/restore", response_model=BackupRestoreResult)
    def restore_backup(
        name: str, request: BackupRestoreRequest
    ) -> BackupRestoreResult:
        if request.confirmation != "RESTORE RANGEBOT":
            raise HTTPException(
                status_code=422,
                detail="يلزم إدخال RESTORE RANGEBOT حرفياً.",
            )
        manager = _require_backup_manager()
        try:
            manager.validate(name)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except SQLiteBackupError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        with database_maintenance_lock:
            _stop_strategy_execution_for_restore()
            for mode in ("testnet", "live"):
                exchange_repository.set_emergency_stop(mode, True)
            try:
                restored, safety_backup = manager.restore(name)
            except SQLiteBackupError as error:
                raise HTTPException(status_code=409, detail=str(error)) from error

            _enforce_post_restore_safety()
            reconciled_mode = exchange_adapter_mode
            reconciliation_succeeded = reconciled_mode is None
            if reconciled_mode is not None:
                try:
                    snapshot = gate_adapter.reconcile(reconciled_mode)
                    _save_exchange_snapshot(snapshot)
                    reconciliation_succeeded = not (
                        snapshot.reconciliation_error
                        or snapshot.unmanaged_state
                        or not snapshot.protection_ready
                    )
                except Exception:
                    reconciliation_succeeded = False
        return BackupRestoreResult(
            restored=restored,
            safety_backup=safety_backup,
            reconciled_mode=reconciled_mode,
            reconciliation_succeeded=reconciliation_succeeded,
            message_ar=(
                "تمت الاستعادة والمصالحة. الإيقاف الطارئ ما زال نشطاً حتى يراجعه المستخدم."
                if reconciliation_succeeded
                else "تمت الاستعادة، لكن المصالحة لم تكتمل. بقيت الأوامر محظورة."
            ),
        )

    @app.post("/v1/logs/export", response_class=FileResponse)
    def export_support_logs() -> FileResponse:
        archive = support_log_exporter.export()
        return FileResponse(
            archive,
            media_type="application/zip",
            filename=archive.name,
        )

    @app.get("/health", response_model=RuntimeState)
    def health() -> RuntimeState:
        return repository.get_state()

    @app.get("/v1/runtime-state", response_model=RuntimeState)
    def runtime_state() -> RuntimeState:
        return repository.get_state()

    @app.get("/v1/paper-account", response_model=PaperAccountSnapshot)
    def paper_account() -> PaperAccountSnapshot:
        try:
            return paper_repository.get()
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/v1/paper-account/initialize", response_model=PaperAccountSnapshot)
    def initialize_paper_account(change: PaperAccountChange) -> PaperAccountSnapshot:
        try:
            return paper_repository.initialize(change)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/v1/paper-account/reset", response_model=PaperAccountSnapshot)
    def reset_paper_account(change: PaperAccountChange) -> PaperAccountSnapshot:
        if change.confirmation != "RESET PAPER ACCOUNT":
            raise HTTPException(
                status_code=422, detail="Explicit reset confirmation required."
            )
        try:
            return paper_repository.reset(change)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/v1/paper-account/audit", response_model=list[PaperAuditEntry])
    def paper_account_audit() -> list[PaperAuditEntry]:
        return paper_repository.audit_entries()

    @app.get("/v1/paper/contracts", response_model=list[PublicContract])
    def paper_contracts(query: str = "") -> list[PublicContract]:
        normalized_query = query.upper()
        return [
            contract
            for contract in market_provider.eligible_contracts()
            if normalized_query in contract.symbol
        ]

    @app.post("/v1/paper/watchlist/{symbol:path}/active", status_code=200)
    def set_active_paper_contract(symbol: str) -> PaperWatchlist:
        normalized_symbol = _normalize_contract_symbol(symbol)
        try:
            watchlist_repository.set_active(normalized_symbol)
            return watchlist_repository.get()
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.patch(
        "/v1/paper/watchlist/{symbol:path}/priority", response_model=PaperWatchlist
    )
    def set_paper_watchlist_priority(
        symbol: str, request: "PriorityRequest"
    ) -> PaperWatchlist:
        normalized_symbol = _normalize_contract_symbol(symbol)
        try:
            watchlist_repository.set_priority(normalized_symbol, request.priority)
            return _watchlist_with_prices(watchlist_repository.get(), market_provider)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.patch(
        "/v1/paper/watchlist/{symbol:path}/direction", response_model=PaperWatchlist
    )
    def set_paper_watchlist_direction(
        symbol: str, request: "DirectionRequest"
    ) -> PaperWatchlist:
        normalized_symbol = _normalize_contract_symbol(symbol)
        try:
            watchlist_repository.set_direction(normalized_symbol, request.direction)
            return _watchlist_with_prices(watchlist_repository.get(), market_provider)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/v1/paper/watchlist/{symbol:path}", status_code=204)
    def add_paper_watchlist_contract(symbol: str) -> None:
        normalized_symbol = _normalize_contract_symbol(symbol)
        if normalized_symbol not in {
            contract.symbol for contract in market_provider.eligible_contracts()
        }:
            raise HTTPException(
                status_code=404, detail="Eligible Paper contract not found."
            )
        try:
            watchlist_repository.add(normalized_symbol)
            _sync_market_subscriptions()
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.delete("/v1/paper/watchlist/{symbol:path}", status_code=204)
    def remove_paper_watchlist_contract(symbol: str) -> None:
        normalized_symbol = _normalize_contract_symbol(symbol)
        try:
            watchlist_repository.remove(normalized_symbol)
            _sync_market_subscriptions()
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/v1/paper/automatic-trading/start", status_code=200)
    def start_paper_automatic_trading() -> PaperWatchlist:
        try:
            if paper_repository.emergency_state().active:
                raise ValueError("Paper Emergency Stop blocks automatic trading.")
            watchlist_repository.start_automation()
            paper_repository.confirm_automatic_restart()
            return watchlist_repository.get()
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/v1/paper/watchlist", response_model=PaperWatchlist)
    def paper_watchlist() -> PaperWatchlist:
        return _watchlist_with_prices(watchlist_repository.get(), market_provider)

    @app.post("/v1/paper/range-analysis/evaluate", response_model=RangeAnalysisResult)
    def evaluate_paper_range(request: RangeAnalysisRequest) -> RangeAnalysisResult:
        config = request.config
        if request.symbol is not None:
            try:
                config = config.model_copy(
                    update={
                        "direction": watchlist_repository.direction_for(
                            _normalize_contract_symbol(request.symbol)
                        )
                    }
                )
            except LookupError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
        return evaluate_range(
            config,
            request.candles,
            request.last_price,
            request.evaluated_at,
        )

    @app.post("/v1/paper/entry-preview", response_model=EntryPreview)
    def paper_entry_preview(request: EntryPreviewRequest) -> EntryPreview:
        return create_entry_preview(request)

    @app.post("/v1/paper/entry-preview/validate", response_model=EntryPreview)
    def validate_paper_entry_preview(request: PreviewValidationRequest) -> EntryPreview:
        if not preview_is_current(request.preview, request.current_request):
            raise HTTPException(status_code=409, detail="Paper Entry Preview is stale.")
        return request.preview

    @app.post("/v1/paper/market-entry", deprecated=True)
    def deprecated_paper_market_entry() -> None:
        raise HTTPException(
            status_code=410,
            detail=(
                "The legacy Paper Market endpoint was removed. "
                "Use /v1/manual-orders/preview and /v1/manual-orders."
            ),
        )

    @app.get("/v1/paper/position", response_model=PaperPosition)
    def paper_position() -> PaperPosition:
        try:
            return _enrich_paper_position(paper_repository.position())
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/v1/paper/position/protection", response_model=PaperProtection)
    def paper_protection() -> PaperProtection:
        try:
            return paper_repository.protection()
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/v1/paper/fee-schedule", response_model=PaperFeeSchedule)
    def paper_fee_schedule() -> PaperFeeSchedule:
        return paper_repository.fee_schedule()

    @app.put("/v1/paper/fee-schedule", response_model=PaperFeeSchedule)
    def update_paper_fee_schedule(schedule: PaperFeeSchedule) -> PaperFeeSchedule:
        return paper_repository.update_fee_schedule(schedule)

    @app.post(
        "/v1/paper/position/protection/check",
        response_model=PaperProtectionTriggerResult,
    )
    def check_paper_protection(
        request: PaperProtectionCheck,
    ) -> PaperProtectionTriggerResult:
        try:
            position = paper_repository.position()
            ownership = _paper_position_ownership(position)
            result = paper_repository.check_protection(request)
            if result.triggered:
                _attach_paper_fill_ownership(result.trade_id, ownership)
                _clear_paper_position_ownership(position)
            return result
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/v1/paper/position/close", response_model=PaperCloseResult)
    def close_paper_position(request: PaperCloseRequest) -> PaperCloseResult:
        try:
            position = paper_repository.position()
            ownership = _paper_position_ownership(position)
            result = paper_repository.close_position(request)
            _attach_paper_fill_ownership(result.trade_id, ownership)
            if result.account.position_quantity == 0:
                _clear_paper_position_ownership(position)
            return result
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (RuntimeError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.delete("/v1/paper/pending-entry", response_model=PaperAccountSnapshot)
    def cancel_paper_pending_entry() -> PaperAccountSnapshot:
        try:
            return paper_repository.cancel_pending_entry()
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get(
        "/v1/paper/pending-entry-state",
        response_model=PaperPendingEntry | None,
    )
    def paper_pending_entry_state() -> PaperPendingEntry | None:
        try:
            return paper_repository.pending_entry()
        except LookupError:
            return None

    @app.get("/v1/paper/pending-entry", response_model=PaperPendingEntry)
    def paper_pending_entry() -> PaperPendingEntry:
        try:
            return paper_repository.pending_entry()
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/v1/paper/limit-entry", deprecated=True)
    def deprecated_paper_limit_entry() -> None:
        raise HTTPException(
            status_code=410,
            detail=(
                "The legacy Paper Limit endpoint was removed. "
                "Use /v1/manual-orders/preview and /v1/manual-orders."
            ),
        )

    @app.post("/v1/paper/limit-entry/check", response_model=PaperLimitCheckResult)
    def check_paper_limit_entry(request: PaperLimitCheck) -> PaperLimitCheckResult:
        try:
            return _sync_paper_limit_ownership(
                paper_repository.check_limit_entry(request)
            )
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/v1/account-risk/policy", response_model=AccountRiskPolicy)
    def account_risk_policy() -> AccountRiskPolicy:
        return account_risk_policy_repository.get()

    @app.put("/v1/account-risk/policy", response_model=AccountRiskPolicy)
    def update_account_risk_policy(
        change: AccountRiskPolicyUpdate,
    ) -> AccountRiskPolicy:
        return account_risk_policy_repository.update(change)

    @app.get(
        "/v1/account-risk/{mode}",
        response_model=AccountRiskStatus,
    )
    def account_risk_status(
        mode: Literal["testnet", "live"],
    ) -> AccountRiskStatus:
        return account_risk_service.status(mode)

    @app.get("/v1/paper/risk", response_model=PaperRiskSnapshot)
    def paper_risk() -> PaperRiskSnapshot:
        try:
            return paper_repository.risk_snapshot()
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.put("/v1/paper/risk/settings", response_model=PaperRiskSnapshot)
    def update_paper_risk(settings: PaperRiskSettings) -> PaperRiskSnapshot:
        try:
            return paper_repository.update_risk_settings(settings)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/v1/paper/risk/adjust", response_model=PaperRiskSnapshot)
    def adjust_paper_risk(adjustment: PaperRiskAdjustment) -> PaperRiskSnapshot:
        try:
            return paper_repository.adjust_risk(adjustment)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/v1/paper/automatic-market-entry", response_model=PaperMarketEntryResult)
    def automatic_paper_market_entry(
        request: PaperAutomaticSignalRequest,
    ) -> PaperMarketEntryResult:
        watchlist = watchlist_repository.get()
        normalized_symbol = _normalize_contract_symbol(request.symbol)
        active = next((item for item in watchlist.items if item.is_active), None)
        if (
            not watchlist.automatic_trading_enabled
            or active is None
            or active.symbol != normalized_symbol
            or paper_repository.emergency_state().automatic_trading_requires_restart
        ):
            raise HTTPException(
                status_code=409,
                detail="Automatic Paper trading requires the active contract and explicit start.",
            )
        if not preview_is_current(request.preview, request.current_request):
            raise HTTPException(status_code=409, detail="Paper Entry Preview is stale.")
        recalculated = create_entry_preview(request.current_request)
        if not recalculated.can_submit:
            raise HTTPException(
                status_code=409,
                detail="Paper automatic entry is blocked by allocation safeguards.",
            )

        signal_reserved = False

        def _release_reserved_signal() -> None:
            if signal_reserved:
                paper_repository.release_automatic_signal(
                    normalized_symbol,
                    request.direction,
                    request.trigger_zone,
                )

        try:
            public_snapshot = market_provider.snapshot(normalized_symbol)
            normalized_market_data.apply_rest_snapshot(
                MarketPriceUpdate(
                    symbol=normalized_symbol,
                    last_price=public_snapshot.last_price,
                    mark_price=public_snapshot.last_price,
                    observed_at=public_snapshot.observed_at,
                    source="gate_rest",
                )
            )
            paper_repository.reserve_automatic_signal(
                normalized_symbol,
                request.direction,
                request.trigger_zone,
            )
            signal_reserved = True
            result = central_order_manager.submit_automatic(
                ManualOrderPreviewRequest(
                    environment="paper",
                    symbol=normalized_symbol,
                    direction=request.direction,
                    order_type="market",
                    size_mode="quantity",
                    quantity=recalculated.quantity,
                    leverage=request.current_request.leverage,
                    time_in_force="ioc",
                ),
                origin="legacy_automatic",
            )
            if not result.accepted:
                raise RuntimeError(result.message_ar)
            return PaperMarketEntryResult(
                position=paper_repository.position(),
                account=paper_repository.get(),
                activity=result.message_ar,
                order_id=result.order_id,
                origin=result.origin,
            )
        except OrderValidationError as error:
            _release_reserved_signal()
            raise HTTPException(
                status_code=409,
                detail={
                    "message_ar": "فشل أمر Paper التلقائي في التحقق المركزي.",
                    "validation_issues": [
                        issue.model_dump(mode="json")
                        for issue in error.preview.validation_issues
                    ],
                },
            ) from error
        except LookupError as error:
            _release_reserved_signal()
            raise HTTPException(status_code=404, detail=str(error)) from error
        except RuntimeError as error:
            _release_reserved_signal()
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            _release_reserved_signal()
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/v1/paper/automatic-limit-entry", response_model=PaperLimitCheckResult)
    def automatic_paper_limit_entry(
        request: PaperAutomaticLimitRequest,
    ) -> PaperLimitCheckResult:
        watchlist = watchlist_repository.get()
        normalized_symbol = _normalize_contract_symbol(request.symbol)
        active = next((item for item in watchlist.items if item.is_active), None)
        if (
            not watchlist.automatic_trading_enabled
            or active is None
            or active.symbol != normalized_symbol
            or paper_repository.emergency_state().automatic_trading_requires_restart
        ):
            raise HTTPException(
                status_code=409,
                detail="Automatic Paper trading requires the active contract and explicit start.",
            )
        if not request.market_ready or not request.history_ready:
            raise HTTPException(
                status_code=422,
                detail="Automatic Paper Limit requires fresh market and history data.",
            )
        if not preview_is_current(request.preview, request.current_request):
            raise HTTPException(status_code=409, detail="Paper Entry Preview is stale.")
        recalculated = create_entry_preview(request.current_request)
        if not recalculated.can_submit:
            raise HTTPException(
                status_code=409,
                detail="Paper automatic Limit is blocked by allocation safeguards.",
            )

        try:
            public_snapshot = market_provider.snapshot(normalized_symbol)
            normalized_market_data.apply_rest_snapshot(
                MarketPriceUpdate(
                    symbol=normalized_symbol,
                    last_price=public_snapshot.last_price,
                    mark_price=public_snapshot.last_price,
                    observed_at=public_snapshot.observed_at,
                    source="gate_rest",
                )
            )
            paper_repository.ensure_automatic_signal_available(
                normalized_symbol,
                request.current_request.direction,
                request.trigger_zone,
            )
            offset = request.offset_percentage / Decimal("100")
            limit_price = (
                public_snapshot.last_price * (Decimal("1") - offset)
                if request.current_request.direction == "long"
                else public_snapshot.last_price * (Decimal("1") + offset)
            )
            result = central_order_manager.submit_automatic(
                ManualOrderPreviewRequest(
                    environment="paper",
                    symbol=normalized_symbol,
                    direction=request.current_request.direction,
                    order_type="limit",
                    size_mode="quantity",
                    quantity=recalculated.quantity,
                    leverage=request.current_request.leverage,
                    limit_price=limit_price,
                    time_in_force="gtc",
                    expires_at=request.expires_at,
                ),
                origin="legacy_automatic",
                signal_zone=request.trigger_zone,
                signal_symbol=normalized_symbol,
            )
            if not result.accepted:
                raise RuntimeError(result.message_ar)
            return PaperLimitCheckResult(
                filled=False,
                expired=False,
                account=paper_repository.get(),
                pending_entry=paper_repository.pending_entry(),
                activity=result.message_ar,
                order_id=result.order_id,
                origin=result.origin,
            )
        except OrderValidationError as error:
            raise HTTPException(
                status_code=409,
                detail={
                    "message_ar": "فشل أمر Paper Limit التلقائي في التحقق المركزي.",
                    "validation_issues": [
                        issue.model_dump(mode="json")
                        for issue in error.preview.validation_issues
                    ],
                },
            ) from error
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/v1/paper/used-signals", response_model=list[PaperUsedSignal])
    def paper_used_signals() -> list[PaperUsedSignal]:
        return paper_repository.used_signals()

    @app.post(
        "/v1/paper/used-signals/{symbol}/{direction}/reset",
        response_model=list[PaperUsedSignal],
    )
    def reset_paper_signal(
        symbol: str, direction: str, request: PaperDirectionalResetRequest
    ) -> list[PaperUsedSignal]:
        if direction not in {"long", "short"}:
            raise HTTPException(
                status_code=422, detail="Direction must be long or short."
            )
        return paper_repository.directional_reset(
            _normalize_contract_symbol(symbol), direction, request
        )

    @app.get("/v1/paper/emergency-stop", response_model=PaperEmergencyState)
    def paper_emergency_state() -> PaperEmergencyState:
        return paper_repository.emergency_state()

    @app.post("/v1/paper/emergency-stop", response_model=PaperEmergencyState)
    def emergency_stop(request: PaperEmergencyStopRequest) -> PaperEmergencyState:
        try:
            state = paper_repository.activate_emergency_stop(request)
            watchlist_repository.stop_automation()
            return state
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/v1/paper/emergency-stop/resume", response_model=PaperEmergencyState)
    def resume_paper_trading(request: PaperResumeRequest) -> PaperEmergencyState:
        try:
            state = paper_repository.resume_after_emergency(request)
            watchlist_repository.stop_automation()
            return state
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/v1/paper/emergency-close", response_model=PaperCloseResult)
    def emergency_close_paper_position(request: PaperCloseRequest) -> PaperCloseResult:
        try:
            position = paper_repository.position()
            ownership = _paper_position_ownership(position)
            result = paper_repository.emergency_close_position(request)
            _attach_paper_fill_ownership(result.trade_id, ownership)
            if result.account.position_quantity == 0:
                _clear_paper_position_ownership(position)
            return result
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/v1/paper/profiles", response_model=list[PaperProfile])
    def paper_profiles() -> list[PaperProfile]:
        return paper_repository.profiles()

    @app.post("/v1/paper/profiles", response_model=PaperProfile)
    def save_paper_profile(change: PaperProfileChange) -> PaperProfile:
        return paper_repository.save_profile(change)

    @app.post("/v1/paper/profiles/{profile_id}/duplicate", response_model=PaperProfile)
    def duplicate_paper_profile(
        profile_id: int, change: PaperProfileChange
    ) -> PaperProfile:
        try:
            return paper_repository.duplicate_profile(profile_id, change)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.put("/v1/paper/profiles/{profile_id}", response_model=PaperProfile)
    def update_paper_profile(
        profile_id: int, change: PaperProfileChange
    ) -> PaperProfile:
        try:
            return paper_repository.update_profile(profile_id, change)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.delete("/v1/paper/profiles/{profile_id}", status_code=204)
    def delete_paper_profile(profile_id: int) -> None:
        try:
            paper_repository.delete_profile(profile_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post(
        "/v1/paper/profiles/{profile_id}/apply", response_model=PaperProfileApplyResult
    )
    def apply_paper_profile(
        profile_id: int, change: PaperProfileChange
    ) -> PaperProfileApplyResult:
        try:
            return paper_repository.apply_profile(profile_id, change)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/v1/paper/help", response_model=list[PaperHelpTopic])
    def paper_help() -> list[PaperHelpTopic]:
        return paper_repository.help_topics()

    @app.post("/v1/paper/verification", response_model=PaperVerificationRecord)
    def record_paper_verification(
        request: PaperVerificationRequest,
    ) -> PaperVerificationRecord:
        return paper_repository.record_verification(request)

    @app.get("/v1/paper/verification", response_model=PaperVerificationRecord)
    def paper_verification() -> PaperVerificationRecord:
        return paper_repository.verification()

    resolved_frontend_dist = _resolve_frontend_dist(frontend_dist)
    app.state.frontend_dist = resolved_frontend_dist
    if resolved_frontend_dist is not None:
        app.mount(
            "/app",
            StaticFiles(directory=resolved_frontend_dist, html=True),
            name="dashboard",
        )

    return app


def _resolve_frontend_dist(explicit: str | Path | None) -> Path | None:
    if explicit is not None:
        resolved = Path(explicit).resolve()
        return resolved if resolved.is_dir() and (resolved / "index.html").is_file() else None

    candidates: list[Path] = []
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root is not None:
        candidates.append(Path(bundled_root) / "frontend" / "dist")
    candidates.extend(
        (
            Path(sys.executable).resolve().parent / "frontend" / "dist",
            Path(__file__).resolve().parents[3] / "frontend" / "dist",
        )
    )

    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_dir() and (resolved / "index.html").is_file():
            return resolved
    return None


class PriorityRequest(BaseModel):
    priority: int = Field(ge=1)


class DirectionRequest(BaseModel):
    direction: Literal["long_only", "short_only", "both"]


def _normalize_contract_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace("/", "_")


def _watchlist_with_prices(
    watchlist: PaperWatchlist, market_provider: PublicMarketProvider
) -> PaperWatchlist:
    items: list[WatchlistItem] = []
    for item in watchlist.items:
        try:
            last_price = market_provider.snapshot(item.symbol).last_price
        except LookupError:
            last_price = None
        items.append(item.model_copy(update={"last_price": last_price}))
    return watchlist.model_copy(update={"items": items})


async def _persist_heartbeats(
    repository: RuntimeStateRepository,
    stop_heartbeat: asyncio.Event,
    database_maintenance_lock: RLock,
) -> None:
    while not await _wait_for_stop(stop_heartbeat):
        with database_maintenance_lock:
            repository.record_heartbeat()


async def _wait_for_stop(stop_heartbeat: asyncio.Event) -> bool:
    try:
        await asyncio.wait_for(stop_heartbeat.wait(), timeout=1.0)
    except TimeoutError:
        return False
    return True
