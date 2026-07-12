"""Localhost-only FastAPI contract for the desktop control UI."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from rangebot.domain.analysis import RangeAnalysisRequest, RangeAnalysisResult, evaluate_range
from rangebot.domain.market import PaperWatchlist, PublicContract
from rangebot.domain.paper import PaperAccountChange, PaperAccountSnapshot, PaperAuditEntry
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
            raise HTTPException(status_code=422, detail="Explicit reset confirmation required.")
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

    @app.post("/v1/paper/watchlist/{symbol}", status_code=204)
    def add_paper_watchlist_contract(symbol: str) -> None:
        if symbol not in {contract.symbol for contract in market_provider.eligible_contracts()}:
            raise HTTPException(status_code=404, detail="Eligible Paper contract not found.")
        try:
            watchlist_repository.add(symbol)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.delete("/v1/paper/watchlist/{symbol}", status_code=204)
    def remove_paper_watchlist_contract(symbol: str) -> None:
        try:
            watchlist_repository.remove(symbol)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/v1/paper/watchlist/{symbol}/active", status_code=200)
    def set_active_paper_contract(symbol: str) -> PaperWatchlist:
        try:
            watchlist_repository.set_active(symbol)
            return watchlist_repository.get()
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
        return watchlist_repository.get()

    @app.post(
        "/v1/paper/range-analysis/evaluate", response_model=RangeAnalysisResult
    )
    def evaluate_paper_range(request: RangeAnalysisRequest) -> RangeAnalysisResult:
        return evaluate_range(request.config, request.candles, request.last_price)

    return app


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
