"""Bounded personal metadata; credentials, blind indexes and bodies are excluded."""

from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, model_validator

from src.domains.ingestion.schemas import IngestionTokenRow
from src.domains.sms.preferences import SmsPreferences


class SmsManagementPageQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    limit: StrictInt = Field(default=20, ge=1, le=100)
    after_id: UUID | None = None
    as_of: AwareDatetime | None = None

    @model_validator(mode="after")
    def paired_cursor(self) -> SmsManagementPageQuery:
        if self.after_id is not None and self.as_of is None:
            raise ValueError("Continue with the previous observation time")
        return self


class SmsArchiveUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    message_count: int = Field(ge=0)
    receipt_count: int = Field(ge=0)
    logical_bytes: int = Field(ge=0)
    max_logical_bytes: int = Field(ge=1)
    max_receipts: int = Field(ge=1)
    last_received_at: datetime | None


class SmsDeviceDeliveryCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    pending: int = Field(default=0, ge=0)
    sending: int = Field(default=0, ge=0)
    sent: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    unknown: int = Field(default=0, ge=0)
    cancelled: int = Field(default=0, ge=0)


class SmsSettingsView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    preferences: SmsPreferences
    usage: SmsArchiveUsage
    device_deliveries: SmsDeviceDeliveryCounts


class SmsTokenPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tokens: list[IngestionTokenRow]
    total: int = Field(ge=0)
    as_of: datetime
    next_cursor: UUID | None = None


class SmsSenderBlockView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    sender: str
    created_at: datetime


class SmsSenderBlockPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    blocks: list[SmsSenderBlockView]
    total: int = Field(ge=0)
    as_of: datetime
    next_cursor: UUID | None = None
