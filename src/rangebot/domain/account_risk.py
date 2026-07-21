"""Account-wide risk policy and daily status for Gate Testnet and Live."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RiskLimitKey = Literal[
    "daily_equity_loss",
    "daily_losing_trades",
    "daily_automatic_entries",
]
RiskLimitState = Literal[
    "disabled",
    "not_reached",
    "reached",
    "data_unavailable",
    "synchronizing",
]
RiskDataState = Literal[
    "ready",
    "baseline_missing",
    "account_data_unavailable",
    "synchronizing",
]


class AccountRiskPolicyValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daily_loss_enabled: bool = True
    daily_loss_limit: Decimal = Field(gt=0)
    losing_trade_enabled: bool = True
    losing_trade_limit: int = Field(ge=1, le=1000)
    automatic_trade_enabled: bool = True
    automatic_trade_limit: int = Field(ge=1, le=100000)


class AccountRiskPolicyUpdate(AccountRiskPolicyValues):
    """Policy values plus an explicit confirmation used only for LIVE weakening."""

    confirmation: str = Field(default="", max_length=100)


class AccountRiskPolicy(AccountRiskPolicyValues):
    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int = Field(ge=1)
    updated_at: datetime


class AccountRiskLimitStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: RiskLimitKey
    enabled: bool
    state: RiskLimitState
    unit: Literal["USDT", "trades", "entries"]
    limit_value: Decimal
    used_value: Decimal | None
    remaining_value: Decimal | None
    blocks_manual_entries: bool
    blocks_automatic_entries: bool


class AccountRiskStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    environment: Literal["testnet", "live"]
    day: date
    timezone: Literal["Asia/Riyadh"] = "Asia/Riyadh"
    synchronization_complete: bool
    risk_data_state: RiskDataState
    baseline_ready: bool
    baseline_equity: Decimal | None
    baseline_captured_at: datetime | None
    current_equity: Decimal | None
    equity_loss_used: Decimal
    remaining_loss_allowance: Decimal
    losing_trades: int
    automatic_trades: int
    policy: AccountRiskPolicy
    limits: tuple[AccountRiskLimitStatus, ...]
    manual_entries_blocked: bool
    automatic_entries_blocked: bool
    blocked_reason_codes: tuple[str, ...] = ()
