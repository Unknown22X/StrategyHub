"""Sanitized engine events safe to publish to local control frontends."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


EngineEventCategory = Literal[
    "engine",
    "account",
    "order",
    "strategy",
    "market",
    "settings",
    "credentials",
    "backup",
    "activity",
]


class EngineEvent(BaseModel):
    """One bounded, frontend-safe notification that a REST snapshot may have changed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(min_length=1, max_length=100)
    sequence: int = Field(ge=1)
    category: EngineEventCategory
    action: str = Field(min_length=1, max_length=100)
    resource: str = Field(min_length=1, max_length=300)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Engine event timestamps must include a timezone.")
        return value


class EngineEventStreamStatus(BaseModel):
    """Current local event-stream metadata used during reconnect recovery."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: int = Field(ge=0)
    subscriber_count: int = Field(ge=0)
