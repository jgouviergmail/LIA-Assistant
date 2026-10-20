"""Owner-scoped projections shared by pages, tools and aggregation surfaces."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from src.core.config import settings


class SmsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    query: str | None = Field(default=None, max_length=256)
    sender_id: UUID | None = Field(
        default=None,
        description="UUID of an already retrieved SMS from that sender; never a contact UUID.",
        json_schema_extra={"x-semantic-type": "sms_message_id"},
    )
    sender: str | None = Field(
        default=None,
        min_length=1,
        max_length=settings.sms_max_sender_chars,
        description="Exact literal raw sender: phone number, email or sender name. Resolve an unambiguous contact first when needed; do not search for a person in body text.",
    )
    from_ts: AwareDatetime | None = None
    to_ts: AwareDatetime | None = None
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(default=None, max_length=4096)

    @model_validator(mode="after")
    def ordered_range(self) -> SmsQuery:
        if self.sender_id is not None and self.sender is not None:
            raise ValueError("choose_one_sender_filter")
        if self.from_ts and self.to_ts and self.from_ts >= self.to_ts:
            raise ValueError("invalid_date_range")
        return self


class SmsView(BaseModel):
    id: UUID
    sender: str
    display_name: str
    identity_source: Literal["contact", "relation", "raw"] = "raw"
    identity_state: str = "unresolved"
    relation_key: str | None = None
    body: str
    received_at: datetime
    date_kind: str
    origin: str


class SmsPage(BaseModel):
    items: list[SmsView]
    total: int
    as_of: datetime
    revision: int
    next_cursor: str | None = None


class SmsSenderView(BaseModel):
    id: UUID
    sender: str
    display_name: str
    identity_source: Literal["contact", "relation", "raw"] = "raw"
    identity_state: str = "unresolved"
    relation_key: str | None = None
    total: int
    latest_at: datetime


class SmsSenderPage(BaseModel):
    items: list[SmsSenderView]
    total: int
    as_of: datetime
    revision: int
    next_cursor: str | None = None
