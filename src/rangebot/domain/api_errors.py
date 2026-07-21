"""Backward-compatible public API error envelope."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PublicApiError(BaseModel):
    """Machine-readable error metadata while retaining FastAPI's `detail` field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    detail: Any
    code: str = Field(min_length=1, max_length=100)
    context: dict[str, Any] = Field(default_factory=dict)
