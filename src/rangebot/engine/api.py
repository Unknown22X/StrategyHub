"""Localhost-only FastAPI contract for the desktop control UI."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from rangebot.domain.paper import PaperAccountChange, PaperAccountSnapshot, PaperAuditEntry
from rangebot.domain.runtime import RuntimeState
from rangebot.engine.database import apply_migrations, create_database_engine
from rangebot.engine.repository import PaperAccountRepository, RuntimeStateRepository


def create_app(database_url: str) -> FastAPI:
    """Create an engine API that exposes lifecycle state to the local UI."""
    database_engine = create_database_engine(database_url)
    repository = RuntimeStateRepository(database_engine)
    paper_repository = PaperAccountRepository(database_engine)

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
