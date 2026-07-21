"""Minimal runtime state shared across the engine/API/UI boundary."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from rangebot.domain.environment import EnvironmentRuntimeState


class RuntimeState(BaseModel):
    """A persisted snapshot of the engine lifecycle, not trading state."""

    model_config = ConfigDict(frozen=True)

    lifecycle: str
    started_at: datetime
    last_heartbeat_at: datetime
    state_revision: int
    environment: EnvironmentRuntimeState | None = None
