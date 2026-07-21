"""Authoritative runtime environment contracts for Paper, Testnet, and Live."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from rangebot.domain.exchange import TradingMode


ApplicationEnvironment = Literal["paper", "testnet", "live"]
EnvironmentTransitionState = Literal[
    "ready",
    "switching",
    "restart_required",
    "failed",
    "mismatch",
]


class EnvironmentActivation(BaseModel):
    """Durable proof that one environment completed the authoritative switch flow."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    environment: ApplicationEnvironment
    confirmed_at: datetime
    revision: int


class EnvironmentSwitchRequest(BaseModel):
    """Request a complete runtime transition, not only a saved UI preference."""

    model_config = ConfigDict(extra="forbid")

    environment: ApplicationEnvironment
    confirmation: str = ""


class EnvironmentRuntimeState(BaseModel):
    """Sanitized authoritative environment state exposed to every frontend."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    configured_environment: ApplicationEnvironment
    requested_environment: ApplicationEnvironment
    active_engine_environment: ApplicationEnvironment
    exchange_adapter_environment: TradingMode | None = None
    public_rest_environment: TradingMode | None = None
    public_websocket_environment: TradingMode | None = None
    private_websocket_environment: TradingMode | None = None
    credential_profile: TradingMode | None = None
    transition_state: EnvironmentTransitionState = "ready"
    restart_required: bool = False
    activated: bool = True
    transition_started_at: datetime | None = None
    transition_completed_at: datetime | None = None
    failure_code: str | None = None
    message_ar: str | None = None
    revision: int = 0
