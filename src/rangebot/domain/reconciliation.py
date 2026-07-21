"""Structured reconciliation readiness exposed to order validation and the UI."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rangebot.domain.exchange import ExchangeSnapshot, TradingMode


ReconciliationState = Literal["ready", "refreshing", "stale", "missing", "failed"]


class ReconciliationReadiness(BaseModel):
    """Sanitized snapshot freshness and reconciliation state for one environment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: TradingMode
    state: ReconciliationState
    ready: bool
    refresh_in_progress: bool = False
    snapshot_age_seconds: float | None = Field(default=None, ge=0)
    maximum_snapshot_age_seconds: float = Field(gt=0)
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    attempt_count: int = Field(default=0, ge=0)
    failure_code: str | None = None
    message_ar: str | None = None
    reason_codes: tuple[str, ...] = ()
    snapshot: ExchangeSnapshot | None = None
