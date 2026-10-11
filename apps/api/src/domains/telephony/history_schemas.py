"""Bounded reviewed call history, with the scope of the recorded cost stated."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from src.domains.telephony.schemas import TelephonyCallSummary


class PhoneHistoryRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cursor: UUID | None = None
    limit: StrictInt = Field(default=25, ge=1, le=50)


class PhoneHistoryProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    calls: list[TelephonyCallSummary]
    total: int = Field(ge=0)
    next_cursor: UUID | None = None
    usage_scope: Literal["recorded_platform_runs"] = "recorded_platform_runs"
