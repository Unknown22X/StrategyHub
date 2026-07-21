"""Historical account performance derived from persisted reconciliation snapshots."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

PerformanceMode = Literal["paper", "testnet", "live"]
PerformancePeriod = Literal["today", "7d", "30d", "all"]


class AccountEquityPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    point_id: int
    mode: PerformanceMode
    occurred_at: datetime
    total_equity: Decimal
    available_balance: Decimal
    used_margin: Decimal
    margin_usage_percentage: Decimal
    realized_pnl_total: Decimal
    unrealized_pnl: Decimal
    fees_total: Decimal
    funding_total: Decimal
    net_pnl_total: Decimal
    open_exposure: Decimal


class AccountPerformanceSeries(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: PerformanceMode
    period: PerformancePeriod
    generated_at: datetime
    points: tuple[AccountEquityPoint, ...]
    baseline_equity: Decimal | None
    ending_equity: Decimal | None
    equity_change: Decimal | None
    equity_change_percentage: Decimal | None
    maximum_drawdown_percentage: Decimal | None
    realized_pnl_total: Decimal | None
    unrealized_pnl: Decimal | None
    fees_total: Decimal | None
    funding_total: Decimal | None
    net_pnl_total: Decimal | None
    open_exposure: Decimal | None
