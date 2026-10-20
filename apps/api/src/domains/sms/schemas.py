"""Strict SMS wire values and content-free per-item acknowledgements."""

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from src.core.config import settings


class SmsIngestItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    sender: StrictStr = Field(min_length=1, max_length=settings.sms_max_sender_chars)
    date: AwareDatetime
    body: StrictStr = Field(min_length=1, max_length=settings.sms_max_body_chars)
    o: StrictStr = Field(
        min_length=1,
        max_length=settings.sms_max_origin_chars,
        pattern=r"^[a-zA-Z0-9_-]+$",
    )
    event_id: UUID | None = None
    schema_version: StrictInt = 1
    date_kind: Literal["received", "captured", "unknown"] = "unknown"

    @field_validator("date", mode="before")
    @classmethod
    def date_requires_text(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("date_requires_iso8601_text")
        return value

    @field_validator("date")
    @classmethod
    def canonical_date(cls, value: datetime) -> datetime:
        if value > datetime.now(UTC) + timedelta(seconds=settings.sms_max_future_skew_seconds):
            raise ValueError("future_date")
        try:
            return value.astimezone(UTC)
        except OverflowError:
            raise ValueError("invalid_date_range") from None

    @field_validator("sender", "body", "o")
    @classmethod
    def meaningful_text(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("invalid_text")
        return value

    @field_validator("schema_version")
    @classmethod
    def supported_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported_schema_version")
        return value


Verdict = Literal[
    "stored",
    "duplicate",
    "ignored_sensitive",
    "ignored_sender",
    "invalid",
    "conflict",
    "storage_full",
]


class IngestItemReceipt(BaseModel):
    index: int
    verdict: Verdict
    message_id: UUID | None = None


class SmsIngestResponse(BaseModel):
    received: int
    inserted: int = 0
    duplicate: int = 0
    ignored: int = 0
    rejected: int = 0
    conflict: int = 0
    items: list[IngestItemReceipt]

    @model_validator(mode="after")
    def balanced_counts(self) -> SmsIngestResponse:
        if (
            self.received
            != self.inserted + self.duplicate + self.ignored + self.rejected + self.conflict
        ):
            raise ValueError("unbalanced_ingestion_ack")
        if len(self.items) != self.received:
            raise ValueError("missing_ingestion_ack")
        return self
