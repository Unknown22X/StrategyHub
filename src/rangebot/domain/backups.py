"""Sanitized backup contracts exposed by the localhost control API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


BackupKind = Literal["manual", "pre_migration", "pre_restore", "lifecycle"]


class BackupRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    kind: BackupKind
    created_at: datetime
    size_bytes: int = Field(ge=0)


class BackupDeleteResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    deleted: bool
    message_ar: str


class BackupRestoreRequest(BaseModel):
    confirmation: str


class BackupRestoreResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    restored: BackupRecord
    safety_backup: BackupRecord
    reconciled_mode: Literal["testnet", "live"] | None = None
    reconciliation_succeeded: bool
    emergency_stop_active: bool = True
    message_ar: str
