"""Sanitized operational activity exposed to the localhost control panel."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ActivityCategory = Literal[
    "decision",
    "strategy",
    "order",
    "paper",
    "risk",
    "system",
    "connection",
    "research",
]
ActivitySeverity = Literal["neutral", "positive", "warning", "negative"]


class ActivityEvent(BaseModel):
    event_id: str
    occurred_at: datetime
    category: ActivityCategory
    severity: ActivitySeverity = "neutral"
    title_ar: str = Field(min_length=1, max_length=200)
    detail_ar: str = Field(min_length=1, max_length=1000)
    environment: Literal["paper", "testnet", "live"] | None = None
    symbol: str | None = None
    strategy_instance_id: str | None = None
    strategy_name: str | None = None
    status: str | None = None
    source_identity: str | None = None


class ActivityQuery(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    category: ActivityCategory | None = None
    environment: Literal["paper", "testnet", "live"] | None = None
    strategy_instance_id: str | None = None
    symbol: str | None = None
    since: datetime | None = None
