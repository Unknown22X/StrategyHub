"""Paper Trading account models with no exchange-account authority."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


PAPER_MODE = "paper"
DEFAULT_PAPER_STARTING_BALANCE = Decimal("1000")


class PaperAccountSnapshot(BaseModel):
    """The complete local state of the Paper Account."""

    model_config = ConfigDict(frozen=True)

    mode: str = PAPER_MODE
    starting_balance: Decimal
    available_futures_balance: Decimal
    position_quantity: Decimal
    pending_entry: bool
    protection_state: str
    cooldown_until: datetime | None
    risk_state: str
    last_change_reason: str
    revision: int


class PaperAccountChange(BaseModel):
    """Validated operator request to initialize or reset Paper Trading."""

    starting_balance: Decimal = Field(default=DEFAULT_PAPER_STARTING_BALANCE, gt=0)
    reason: str = Field(min_length=1, max_length=500)
    confirmation: str | None = None


class PaperAuditEntry(BaseModel):
    """A non-secret audit record for a Paper Account state change."""

    model_config = ConfigDict(frozen=True)

    occurred_at: datetime
    action: str
    reason: str
