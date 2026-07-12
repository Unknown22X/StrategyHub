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
)
from rangebot.domain.runtime import RuntimeState
from rangebot.engine.database import apply_migrations, create_database_engine
from rangebot.engine.market import EmptyPublicMarketProvider, PublicMarketProvider
from rangebot.engine.repository import (
    PaperAccountRepository,
    PaperWatchlistRepository,
    RuntimeStateRepository,
)


def create_app(
    database_url: str, public_market_provider: PublicMarketProvider | None = None
) -> FastAPI:
    """Create an engine API that exposes lifecycle state to the local UI."""
    database_engine = create_database_engine(database_url)
    repository = RuntimeStateRepository(database_engine)
    paper_repository = PaperAccountRepository(database_engine)
    watchlist_repository = PaperWatchlistRepository(database_engine)
    market_provider = public_market_provider or EmptyPublicMarketProvider()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        apply_migrations(database_url)
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
            watchlist_repository.start_automation()
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
