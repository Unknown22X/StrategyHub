"""Application-wide persisted settings shared by every control frontend."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rangebot.domain.account_risk import AccountRiskPolicy
from rangebot.domain.paper import PaperEmergencyState, PaperRiskSnapshot


type JsonScalar = str | int | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]

_SECRET_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "api_secret",
    "secret",
    "password",
    "passphrase",
    "private_key",
    "credential",
    "authorization",
    "signature",
    "token",
    "database_url",
)
_SECRET_VALUE_MARKERS = (
    "api_key=",
    "apikey=",
    "api_secret=",
    "secret=",
    "password=",
    "passphrase=",
    "private_key=",
    "authorization:",
    "bearer ",
)


def _contains_secret_material(value: JsonValue, path: tuple[str, ...] = ()) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = key.casefold().replace("-", "_")
            if any(fragment in normalized_key for fragment in _SECRET_KEY_FRAGMENTS):
                return True
            if _contains_secret_material(nested, (*path, key)):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_secret_material(item, path) for item in value)
    if isinstance(value, str):
        normalized_value = value.casefold()
        return any(marker in normalized_value for marker in _SECRET_VALUE_MARKERS)
    return False


class ApplicationSettingsUpdate(BaseModel):
    """Backend-owned preferences that are safe to persist as JSON."""

    model_config = ConfigDict(extra="forbid")

    environment: Literal["paper", "testnet", "live"] = "paper"
    ui_language: Literal["ar", "en"] = "ar"
    dashboard_layout: dict[str, JsonValue] = Field(default_factory=dict)
    dashboard_filters: dict[str, JsonValue] = Field(default_factory=dict)
    sidebar_preferences: dict[str, JsonValue] = Field(default_factory=dict)
    application_preferences: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_secret_material(self) -> "ApplicationSettingsUpdate":
        persisted_values: tuple[JsonValue, ...] = (
            self.dashboard_layout,
            self.dashboard_filters,
            self.sidebar_preferences,
            self.application_preferences,
        )
        if any(_contains_secret_material(value) for value in persisted_values):
            raise ValueError(
                "Application settings must not contain credentials or secrets."
            )
        return self


class ApplicationSettings(ApplicationSettingsUpdate):
    """Committed application settings returned by the central engine."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int = Field(ge=0)
    updated_at: datetime | None = None


class ApplicationSettingsOverview(BaseModel):
    """Typed aggregate view while safety-critical settings keep dedicated storage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    application: ApplicationSettings
    account_risk_policy: AccountRiskPolicy
    paper_risk: PaperRiskSnapshot | None
    paper_emergency_stop: PaperEmergencyState | None
    testnet_emergency_stop: bool
    live_emergency_stop: bool
