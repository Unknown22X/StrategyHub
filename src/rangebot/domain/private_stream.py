"""Sanitized state for Gate.io authenticated futures notifications."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from rangebot.domain.exchange import TradingMode


PrivateStreamConnectionState = Literal[
    "disabled",
    "credentials_missing",
    "connecting",
    "connected",
    "reconciling",
    "reconnecting",
    "error",
]


class PrivateStreamState(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: TradingMode | None = None
    status: PrivateStreamConnectionState = "disabled"
    connected: bool = False
    subscribed_channels: tuple[str, ...] = ()
    last_event_at: datetime | None = None
    last_reconciled_at: datetime | None = None
    last_error: str | None = None
    revision: int = 1
