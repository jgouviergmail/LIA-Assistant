"""Private exact scope is stored in approved commands, never in approval copy."""

from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    model_validator,
)

from src.domains.sms.read_schemas import SmsQuery


class SmsEraseRequest(SmsQuery):
    all_messages: StrictBool = False
    message_ids: tuple[UUID, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def explicit_scope(self) -> SmsEraseRequest:
        if self.query is not None or self.cursor is not None:
            raise ValueError("erasure_requires_explicit_source_scope")
        if not (
            self.all_messages or self.sender_id or self.from_ts or self.to_ts or self.message_ids
        ):
            raise ValueError("erasure_scope_required")
        if self.all_messages and (self.sender_id or self.from_ts or self.to_ts or self.message_ids):
            raise ValueError("conflicting_erasure_scope")
        return self


class SmsEraseSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: SmsEraseRequest
    as_of: AwareDatetime
    count: StrictInt = Field(ge=0)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    def public_scope(self) -> dict[str, object]:
        return {
            "count": self.count,
            "as_of": self.as_of.isoformat(),
            "all_messages": self.request.all_messages,
            "sender_id": str(self.request.sender_id) if self.request.sender_id else None,
            "from_ts": self.request.from_ts.isoformat() if self.request.from_ts else None,
            "to_ts": self.request.to_ts.isoformat() if self.request.to_ts else None,
            "message_ids": [str(identifier) for identifier in self.request.message_ids],
        }
