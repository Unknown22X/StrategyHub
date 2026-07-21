"""Account-wide risk policy and daily status for Gate Testnet and Live."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AccountRiskPolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daily_loss_limit: Decimal = Field(gt=0)
    losing_trade_limit: int = Field(ge=1, le=1000)
    automatic_trade_limit: int = Field(ge=1, le=100000)


class AccountRiskPolicy(AccountRiskPolicyUpdate):
    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int = Field(ge=1)
    updated_at: datetime


class AccountRiskStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    environment: Literal["testnet", "live"]
    day: date
    baseline_ready: bool
    baseline_equity: Decimal | None
    current_equity: Decimal | None
    equity_loss_used: Decimal
    remaining_loss_allowance: Decimal
    losing_trades: int
    automatic_trades: int
    policy: AccountRiskPolicy
    manual_entries_blocked: bool
    automatic_entries_blocked: bool
    blocked_reason_codes: tuple[str, ...] = ()
