"""Localhost-only FastAPI contract for the desktop control UI."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException

from rangebot.domain.analysis import (
    RangeAnalysisRequest,
    RangeAnalysisResult,
    evaluate_range,
)
from rangebot.domain.entry_preview import (
    EntryPreview,
    EntryPreviewRequest,
    PreviewValidationRequest,
    create_entry_preview,
    preview_is_current,
)
from rangebot.domain.market import PaperWatchlist, PublicContract, WatchlistItem
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
    PaperMarketEntryRequest,
    PaperMarketEntryResult,
    PaperLimitCheck,
    PaperLimitCheckResult,
    PaperLimitEntryRequest,
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
from rangebot.domain.exchange import (
    LiveActivationRequest,
    LiveEntryRequest,
    ModeState,
    ProtectionChangeRequest,
    TradingMode,
)
from rangebot.engine.database import apply_migrations, create_database_engine
from rangebot.engine.exchange import (
    GateIoAdapter,
    UnavailableGateIoAdapter,
    entry_blocks,
    mode_state,
)
from rangebot.engine.market import EmptyPublicMarketProvider, PublicMarketProvider
from rangebot.engine.repository import (
    PaperAccountRepository,
    PaperWatchlistRepository,
    ExchangeModeRepository,
    RuntimeStateRepository,
)


def create_app(
    database_url: str,
    public_market_provider: PublicMarketProvider | None = None,
    exchange_adapter: GateIoAdapter | None = None,
) -> FastAPI:
    """Create an engine API that exposes lifecycle state to the local UI."""
    database_engine = create_database_engine(database_url)
    repository = RuntimeStateRepository(database_engine)
    paper_repository = PaperAccountRepository(database_engine)
    watchlist_repository = PaperWatchlistRepository(database_engine)
    exchange_repository = ExchangeModeRepository(database_engine)
    gate_adapter = exchange_adapter or UnavailableGateIoAdapter()
    market_provider = public_market_provider or EmptyPublicMarketProvider()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        apply_migrations(database_url)
        # A process/service/VPS restart always returns Live to its locked state.
        exchange_repository.set_live_locked(True)
        repository.record_started()
        stop_heartbeat = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            _persist_heartbeats(repository, stop_heartbeat)
        )
        try:
            yield
        finally:
            stop_heartbeat.set()
            await heartbeat_task

    app = FastAPI(title="RangeBot Engine", lifespan=lifespan)
    app.state.paper_repository = paper_repository

    def _exchange_state(mode: TradingMode) -> ModeState:
        snapshot = exchange_repository.get_snapshot(mode)
        return mode_state(
            mode,
            snapshot,
            exchange_repository.live_locked() if mode == "live" else False,
            exchange_repository.emergency_stop(mode),
        )

    @app.get("/v1/exchange/{mode}/state", response_model=ModeState)
    def exchange_state(mode: TradingMode) -> ModeState:
        return _exchange_state(mode)

    @app.post("/v1/exchange/{mode}/reconcile", response_model=ModeState)
    def reconcile_exchange(mode: TradingMode) -> ModeState:
        """Only a configured adapter may supply authoritative exchange state."""
        snapshot = gate_adapter.reconcile(mode)
        exchange_repository.save_snapshot(snapshot)
        return _exchange_state(mode)

    @app.post("/v1/live/activate", response_model=ModeState)
    def activate_live(request: LiveActivationRequest) -> ModeState:
        state = _exchange_state("live")
        non_lock_reasons = entry_blocks(state.snapshot, "testnet", False, state.emergency_stop)
        if request.confirmation != "LIVE":
            raise HTTPException(status_code=422, detail="يلزم إدخال LIVE حرفياً.")
        if non_lock_reasons:
            raise HTTPException(status_code=409, detail=" ".join(non_lock_reasons))
        exchange_repository.set_live_locked(False)
        return _exchange_state("live")

    @app.post("/v1/exchange/{mode}/emergency-stop", response_model=ModeState)
    def exchange_emergency_stop(mode: TradingMode) -> ModeState:
        exchange_repository.set_emergency_stop(mode, True)
        return _exchange_state(mode)

    @app.post("/v1/exchange/{mode}/resume", response_model=ModeState)
    def exchange_resume(mode: TradingMode, confirmation: str) -> ModeState:
        if confirmation != "RESUME":
            raise HTTPException(status_code=422, detail="يلزم إدخال RESUME حرفياً.")
        exchange_repository.set_emergency_stop(mode, False)
        return _exchange_state(mode)

    @app.post("/v1/live/protection", response_model=ModeState)
    def change_live_protection(request: ProtectionChangeRequest) -> ModeState:
        if not request.enabled:
            expected = "DISABLE TP" if request.protection == "tp" else "DISABLE SL"
            if request.confirmation != expected:
                raise HTTPException(status_code=422, detail=f"يلزم إدخال {expected} حرفياً.")
        return _exchange_state("live")

    @app.post("/v1/live/entries", response_model=ModeState)
    def submit_live_entry(request: LiveEntryRequest) -> ModeState:
        state = _exchange_state("live")
        if state.blocked_reasons_ar:
            raise HTTPException(status_code=409, detail=" ".join(state.blocked_reasons_ar))
        if not request.protections_enabled and request.confirmation != "UNPROTECTED POSITION":
            raise HTTPException(status_code=422, detail="يلزم إدخال UNPROTECTED POSITION حرفياً.")
        # Actual Gateway submission is intentionally unavailable until a configured adapter is injected.
        raise HTTPException(status_code=503, detail="لم يُضبط Gate.io adapter للتنفيذ؛ لم يُرسل أي أمر.")

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
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.delete("/v1/paper/watchlist/{symbol:path}", status_code=204)
    def remove_paper_watchlist_contract(symbol: str) -> None:
        normalized_symbol = _normalize_contract_symbol(symbol)
        try:
            watchlist_repository.remove(normalized_symbol)
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

    @app.post("/v1/paper/market-entry", response_model=PaperMarketEntryResult)
    def paper_market_entry(request: PaperMarketEntryRequest) -> PaperMarketEntryResult:
        try:
            return paper_repository.enter_market(request)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/v1/paper/position", response_model=PaperPosition)
    def paper_position() -> PaperPosition:
        try:
            return paper_repository.position()
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
        "/v1/paper/position/protection/check", response_model=PaperProtectionTriggerResult
    )
    def check_paper_protection(
        request: PaperProtectionCheck,
    ) -> PaperProtectionTriggerResult:
        try:
            return paper_repository.check_protection(request)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/v1/paper/position/close", response_model=PaperCloseResult)
    def close_paper_position(request: PaperCloseRequest) -> PaperCloseResult:
        try:
            return paper_repository.close_position(request)
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

    @app.get("/v1/paper/pending-entry", response_model=PaperPendingEntry)
    def paper_pending_entry() -> PaperPendingEntry:
        try:
            return paper_repository.pending_entry()
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/v1/paper/limit-entry", response_model=PaperLimitCheckResult)
    def create_paper_limit_entry(request: PaperLimitEntryRequest) -> PaperLimitCheckResult:
        try:
            return paper_repository.create_limit_entry(request)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/v1/paper/limit-entry/check", response_model=PaperLimitCheckResult)
    def check_paper_limit_entry(request: PaperLimitCheck) -> PaperLimitCheckResult:
        try:
            return paper_repository.check_limit_entry(request)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

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
        try:
            return paper_repository.automatic_market_entry(
                request.model_copy(update={"symbol": normalized_symbol})
            )
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
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
        try:
            return paper_repository.automatic_limit_entry(
                request.model_copy(update={"symbol": normalized_symbol})
            )
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/v1/paper/used-signals", response_model=list[PaperUsedSignal])
    def paper_used_signals() -> list[PaperUsedSignal]:
        return paper_repository.used_signals()

    @app.post("/v1/paper/used-signals/{symbol}/{direction}/reset", response_model=list[PaperUsedSignal])
    def reset_paper_signal(
        symbol: str, direction: str, request: PaperDirectionalResetRequest
    ) -> list[PaperUsedSignal]:
        if direction not in {"long", "short"}:
            raise HTTPException(status_code=422, detail="Direction must be long or short.")
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
            return paper_repository.emergency_close_position(request)
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
    def duplicate_paper_profile(profile_id: int, change: PaperProfileChange) -> PaperProfile:
        try:
            return paper_repository.duplicate_profile(profile_id, change)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.put("/v1/paper/profiles/{profile_id}", response_model=PaperProfile)
    def update_paper_profile(profile_id: int, change: PaperProfileChange) -> PaperProfile:
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

    @app.post("/v1/paper/profiles/{profile_id}/apply", response_model=PaperProfileApplyResult)
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

    return app


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
    repository: RuntimeStateRepository, stop_heartbeat: asyncio.Event
) -> None:
    while not await _wait_for_stop(stop_heartbeat):
        repository.record_heartbeat()


async def _wait_for_stop(stop_heartbeat: asyncio.Event) -> bool:
    try:
        await asyncio.wait_for(stop_heartbeat.wait(), timeout=1.0)
    except TimeoutError:
        return False
    return True
